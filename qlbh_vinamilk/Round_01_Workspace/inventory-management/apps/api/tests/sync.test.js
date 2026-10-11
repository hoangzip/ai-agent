/**
 * Kiểm thử Tự động: Đồng bộ Tự động Google Drive (Round 07)
 * Module: apps/api/tests/sync.test.js
 *
 * Kiểm tra đầy đủ:
 * 1. Kiến trúc Dual-Driver: Simulation driver hoạt động ổn định khi chưa có Google Service Account credentials.
 * 2. Phân biệt rõ ràng SIMULATION vs LIVE qua Driver Mode và cờ is_live_connected.
 * 3. Quét thư mục Google Drive Folder ID '1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk' phát hiện 4 file mẫu thật.
 * 4. API Endpoints:
 *    - GET /api/v1/sync/status (Xác thực, cấu hình nguồn, trạng thái driver, thống kê đợt chạy)
 *    - POST /api/v1/sync/trigger (Kích hoạt đồng bộ, bóc tách Excel, lưu DB với source_type='GDRIVE_SYNC')
 *    - GET /api/v1/sync/runs (Lịch sử đợt đồng bộ phân trang)
 * 5. Tính lũy đẳng (Idempotency):
 *    - Lần chạy 1: Nạp 4 file thành công (files_imported = 4, files_skipped = 0).
 *    - Lần chạy 2: Bỏ qua 4 file đã nạp (files_imported = 0, files_skipped = 4).
 *    - Không tạo snapshot trùng lặp trong cơ sở dữ liệu.
 * 6. Bảo vệ an ninh RBAC & Xác thực đăng nhập trên các endpoint đồng bộ.
 */

import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import worker from "../dist/index.js";
import { getGoogleDriveDriver, LiveGoogleDriveDriver, SimulationGoogleDriveDriver } from "../dist/services/googleDriveService.js";
import { hashPassword } from "../dist/security/password.js";
import { hashSessionToken } from "../dist/security/session.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATION_PATH_1 = path.resolve(__dirname, "../../../database/migrations/0001_initial_schema.sql");
const MIGRATION_PATH_2 = path.resolve(__dirname, "../../../database/migrations/0002_sync_concurrency_lock.sql");
const GDRIVE_FOLDER_ID = "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk";

async function setupTestDb(mfInstance) {
  const db = await mfInstance.getD1Database("DB");
  for (const mPath of [MIGRATION_PATH_1, MIGRATION_PATH_2]) {
    if (fs.existsSync(mPath)) {
      const sql = fs.readFileSync(mPath, "utf8");
      const cleanSql = sql.replace(/--.*$/gm, "").trim();
      const statements = cleanSql.split(";").map((s) => s.trim()).filter((s) => s.length > 0);
      for (const stmt of statements) {
        await db.prepare(stmt).run();
      }
    }
  }
  return db;
}

let mf;
let testDb;
let baseEnv;
let adminToken = "admin-session-token-round7";
let adminTokenHash;
let userToken = "user-session-token-round7";
let userTokenHash;

test.before(async () => {
  mf = new Miniflare({
    modules: true,
    script: 'export default { fetch() { return new Response("ok"); } }',
    d1Databases: { DB: "test_db" }
  });

  testDb = await setupTestDb(mf);
  baseEnv = {
    DB: testDb,
    ENVIRONMENT: "test",
    ROUND: "07/10",
    APP_TIMEZONE: "Asia/Ho_Chi_Minh",
    ALLOWED_ORIGINS: "http://localhost:3000,http://localhost:5173",
    BOOTSTRAP_TOKEN: "bootstrap-secret-round7",
    SYNC_WEBHOOK_SECRET: "secure-webhook-secret-r07",
    GDRIVE_FOLDER_ID
  };

  // Tạo tài khoản Admin & User
  const passHash = await hashPassword("Vinamilk@2026");
  await testDb
    .prepare(
      `INSERT INTO users (id, username, password_hash, role, full_name, must_change_password, is_active)
       VALUES (1, 'admin', ?, 'ADMIN', 'Quản trị viên', 0, 1),
              (2, 'user1', ?, 'USER', 'Nhân viên kiểm kê', 0, 1)`
    )
    .bind(passHash, passHash)
    .run();

  adminTokenHash = await hashSessionToken(adminToken);
  userTokenHash = await hashSessionToken(userToken);
  const futureExp = "2099-01-01T00:00:00.000Z";

  await testDb
    .prepare(
      `INSERT INTO sessions (id, user_id, expires_at)
       VALUES (?, 1, ?), (?, 2, ?)`
    )
    .bind(adminTokenHash, futureExp, userTokenHash, futureExp)
    .run();
});

test("DRIVER: Dual-Driver chọn SimulationGoogleDriveDriver khi chưa có Service Account", () => {
  const driver = getGoogleDriveDriver(baseEnv);
  assert.strictEqual(driver.getMode(), "SIMULATION");
  assert.ok(driver instanceof SimulationGoogleDriveDriver);
});

test("DRIVER: Simulation driver quét danh sách 4 file trong thư mục Google Drive 1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk", async () => {
  const driver = getGoogleDriveDriver(baseEnv);
  const files = await driver.listFiles(GDRIVE_FOLDER_ID);

  assert.strictEqual(files.length, 4, "Phải quét đúng 4 file Excel trong thư mục fixture");
  for (const f of files) {
    assert.ok(f.id.startsWith("gdrive_"));
    assert.ok(f.name.endsWith(".xlsx"));
    assert.ok(f.sizeBytes > 0);
  }
});

test("DRIVER: Simulation driver tải nội dung file trả về ArrayBuffer hợp lệ", async () => {
  const driver = getGoogleDriveDriver(baseEnv);
  const files = await driver.listFiles(GDRIVE_FOLDER_ID);
  const buffer = await driver.downloadFile(files[0].id);

  assert.ok(buffer instanceof ArrayBuffer);
  assert.strictEqual(buffer.byteLength, files[0].sizeBytes);
});

test("DRIVER: LiveGoogleDriveDriver từ chối gọi API khi thiếu credentials và không làm giả kết nối", async () => {
  const liveDriver = new LiveGoogleDriveDriver(null);
  assert.strictEqual(liveDriver.getMode(), "LIVE");

  await assert.rejects(
    async () => {
      await liveDriver.listFiles(GDRIVE_FOLDER_ID);
    },
    /Chưa cấu hình Google Service Account credentials/
  );
});

test("SECURITY: GET /api/v1/sync/status yêu cầu xác thực (401 khi không đăng nhập)", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/status", {
    method: "GET"
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);
  const data = await res.json();
  assert.strictEqual(data.error.code, "UNAUTHORIZED");
});

test("GET /api/v1/sync/status: Trả về trạng thái nguồn, driver mode SIMULATION và thống kê", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/status", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const body = await res.json();
  assert.strictEqual(body.success, true);
  assert.strictEqual(body.data.driver_mode, "SIMULATION");
  assert.strictEqual(body.data.is_live_connected, false);
  assert.strictEqual(body.data.source.folder_id, GDRIVE_FOLDER_ID);
  assert.strictEqual(body.data.source.provider, "GOOGLE_DRIVE");
  assert.strictEqual(body.data.metrics.total_runs, 0);
});

test("SECURITY: POST /api/v1/sync/trigger yêu cầu xác thực (401 khi không đăng nhập)", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/trigger", {
    method: "POST",
    headers: {
      Origin: "http://localhost:5173"
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);
});

test("POST /api/v1/sync/trigger: Chạy đợt 1 nạp thành công 4 file Excel vào database", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/trigger", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const body = await res.json();
  assert.strictEqual(body.success, true);
  assert.strictEqual(body.data.status, "COMPLETED");
  assert.strictEqual(body.data.summary.files_detected, 4);
  assert.strictEqual(body.data.summary.files_imported, 4);
  assert.strictEqual(body.data.summary.files_skipped, 0);
  assert.strictEqual(body.data.summary.files_failed, 0);

  // Xác minh dữ liệu trong bảng inventory_files
  const snapshots = (await testDb
    .prepare("SELECT full_code, source_type, source_file_id, status FROM inventory_files WHERE is_deleted = 0")
    .all())?.results;

  assert.strictEqual(snapshots.length, 4);
  for (const snap of snapshots) {
    assert.strictEqual(snap.source_type, "GDRIVE_SYNC", "Snapshot từ Google Drive phải có source_type = GDRIVE_SYNC");
    assert.ok(snap.source_file_id.startsWith("gdrive_"));
    assert.strictEqual(snap.status, "COMPLETED");
  }

  // Xác minh bản ghi sync_runs
  const syncRun = await testDb
    .prepare("SELECT * FROM sync_runs WHERE id = ?")
    .bind(body.data.run_id)
    .first();

  assert.strictEqual(syncRun.status, "COMPLETED");
  assert.strictEqual(syncRun.files_detected, 4);
  assert.strictEqual(syncRun.files_imported, 4);
  assert.strictEqual(syncRun.files_skipped, 0);
});

test("IDEMPOTENCY: Chạy đợt 2 bỏ qua toàn bộ 4 file đã nạp (files_skipped = 4, files_imported = 0)", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/trigger", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const body = await res.json();
  assert.strictEqual(body.success, true);
  assert.strictEqual(body.data.status, "COMPLETED");
  assert.strictEqual(body.data.summary.files_detected, 4);
  assert.strictEqual(body.data.summary.files_imported, 0, "Không được import lại file đã có");
  assert.strictEqual(body.data.summary.files_skipped, 4, "Toàn bộ 4 file phải được skip an toàn");

  // Kiểm tra không bị tăng thêm bản ghi nào trong inventory_files
  const countRow = await testDb
    .prepare("SELECT COUNT(*) as total FROM inventory_files WHERE is_deleted = 0")
    .first();
  assert.strictEqual(Number(countRow.total), 4, "Số lượng snapshot trong DB vẫn giữ nguyên là 4");
});

test("GET /api/v1/sync/runs: Lấy lịch sử các đợt đồng bộ có phân trang và thông tin chi tiết", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/runs?page=1&limit=10", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const body = await res.json();
  assert.strictEqual(body.success, true);
  assert.strictEqual(body.data.pagination.total, 2);
  assert.strictEqual(body.data.items.length, 2);

  // Đợt gần nhất là đợt 2 (files_skipped = 4)
  const latestRun = body.data.items[0];
  assert.strictEqual(latestRun.status, "COMPLETED");
  assert.strictEqual(latestRun.files_skipped, 4);
  assert.strictEqual(latestRun.files_imported, 0);

  // Đợt đầu tiên là đợt 1 (files_imported = 4)
  const firstRun = body.data.items[1];
  assert.strictEqual(firstRun.status, "COMPLETED");
  assert.strictEqual(firstRun.files_imported, 4);
});

test("GET /api/v1/sync/status: Cập nhật chỉ số sau khi chạy đồng bộ (total_runs=2, total_files_imported=4)", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/status", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const body = await res.json();
  assert.strictEqual(body.data.metrics.total_runs, 2);
  assert.strictEqual(body.data.metrics.successful_runs, 2);
  assert.strictEqual(body.data.metrics.failed_runs, 0);
  assert.strictEqual(body.data.metrics.total_files_imported, 4);
  assert.strictEqual(body.data.metrics.total_files_skipped, 4);
  assert.ok(body.data.last_run !== null);
  assert.strictEqual(body.data.last_run.status, "COMPLETED");
});

test("P1-03 & P2-08: verifyConnection() từ chối khi thiếu credentials và đánh dấu BLOCKED_FOR_LIVE", async () => {
  const liveDriver = new LiveGoogleDriveDriver(null);
  const check = await liveDriver.verifyConnection(GDRIVE_FOLDER_ID);
  assert.strictEqual(check.success, false);
  assert.ok(check.error.includes("Chưa cấu hình Google Service Account credentials"));

  // Kiểm tra getSyncStatus khi env cấu hình live driver nhưng không có token
  const liveEnv = { ...baseEnv, GDRIVE_ACCESS_TOKEN: null, GDRIVE_API_KEY: null, ENVIRONMENT: "production" };
  const req = new Request("http://localhost:8787/api/v1/sync/status", {
    method: "GET",
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const res = await worker.fetch(req, liveEnv);
  assert.strictEqual(res.status, 200);
  const body = await res.json();
  assert.strictEqual(body.data.connection_status, "BLOCKED_FOR_LIVE");
  assert.strictEqual(body.data.is_live_connected, false);
  assert.ok(body.data.connection_error !== null);
});

test("P2-01: LiveGoogleDriveDriver.listFiles() hỗ trợ phân trang nextPageToken cho danh sách > 100 file", async () => {
  // Mock fetch toàn cục cho Google Drive API trả về 2 trang
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async (url, opts) => {
    const urlStr = String(url);
    if (urlStr.includes("googleapis.com/drive/v3/files")) {
      callCount++;
      if (callCount === 1) {
        return new Response(
          JSON.stringify({
            nextPageToken: "TOKEN_PAGE_2",
            files: Array.from({ length: 100 }, (_, i) => ({
              id: `gdrive_page1_${i}`,
              name: `file_page1_${i}.xlsx`,
              mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              size: "1024"
            }))
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      } else {
        return new Response(
          JSON.stringify({
            files: Array.from({ length: 5 }, (_, i) => ({
              id: `gdrive_page2_${i}`,
              name: `file_page2_${i}.xlsx`,
              mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              size: "2048"
            }))
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
    }
    return originalFetch(url, opts);
  };

  try {
    const driver = new LiveGoogleDriveDriver({ apiKey: "test_dummy_key" });
    const files = await driver.listFiles(GDRIVE_FOLDER_ID);
    assert.strictEqual(callCount, 2, "Phải gọi 2 lần request để duyệt qua nextPageToken");
    assert.strictEqual(files.length, 105, "Tổng số file phải là 100 trang đầu + 5 trang sau = 105 files");
    assert.strictEqual(files[0].id, "gdrive_page1_0");
    assert.strictEqual(files[104].id, "gdrive_page2_4");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("P1-01 FAIL-CLOSED: Endpoint scheduled từ chối khi thiếu SYNC_WEBHOOK_SECRET trong môi trường", async () => {
  const envWithoutSecret = { ...baseEnv, SYNC_WEBHOOK_SECRET: undefined };
  const req = new Request("http://localhost:8787/api/v1/sync/scheduled", {
    method: "POST",
    headers: { "X-Webhook-Secret": "any-token" }
  });
  const res = await worker.fetch(req, envWithoutSecret);
  assert.strictEqual(res.status, 401);
  const data = await res.json();
  assert.strictEqual(data.error.code, "UNCONFIGURED_WEBHOOK_SECRET");
});

test("P1-01 NEGATIVE: Scheduled webhook từ chối khi thiếu auth, sai secret, hoặc dùng BOOTSTRAP_TOKEN", async () => {
  // 1. Thiếu thông tin xác thực
  const reqNoAuth = new Request("http://localhost:8787/api/v1/sync/scheduled", { method: "POST" });
  const resNoAuth = await worker.fetch(reqNoAuth, baseEnv);
  assert.strictEqual(resNoAuth.status, 401);
  const dataNoAuth = await resNoAuth.json();
  assert.strictEqual(dataNoAuth.error.code, "UNAUTHORIZED_CRON");

  // 2. Sai secret
  const reqWrong = new Request("http://localhost:8787/api/v1/sync/scheduled", {
    method: "POST",
    headers: { "X-Webhook-Secret": "wrong-secret-123" }
  });
  const resWrong = await worker.fetch(reqWrong, baseEnv);
  assert.strictEqual(resWrong.status, 401);
  const dataWrong = await resWrong.json();
  assert.strictEqual(dataWrong.error.code, "INVALID_WEBHOOK_SECRET");

  // 3. Fallback sang BOOTSTRAP_TOKEN bị CHẶN HOÀN TOÀN
  const reqBootstrapFallback = new Request("http://localhost:8787/api/v1/sync/scheduled", {
    method: "POST",
    headers: { Authorization: `Bearer ${baseEnv.BOOTSTRAP_TOKEN}` }
  });
  const resBootstrapFallback = await worker.fetch(reqBootstrapFallback, baseEnv);
  assert.strictEqual(resBootstrapFallback.status, 401, "Tuyệt đối không cho phép fallback sang BOOTSTRAP_TOKEN");
  const dataFallback = await resBootstrapFallback.json();
  assert.strictEqual(dataFallback.error.code, "INVALID_WEBHOOK_SECRET");
});

test("P1-01 NEGATIVE: Chặn request có Origin từ bên ngoài không tin cậy (403 FORBIDDEN_ORIGIN)", async () => {
  const reqOrigin = new Request("http://localhost:8787/api/v1/sync/scheduled", {
    method: "POST",
    headers: {
      Origin: "https://malicious-attacker.com",
      "X-Webhook-Secret": baseEnv.SYNC_WEBHOOK_SECRET
    }
  });
  const resOrigin = await worker.fetch(reqOrigin, baseEnv);
  assert.strictEqual(resOrigin.status, 403);
  const dataOrigin = await resOrigin.json();
  assert.strictEqual(dataOrigin.error.code, "FORBIDDEN_ORIGIN");
});

test("P1-01 POSITIVE: Scheduled webhook xác thực thành công với SYNC_WEBHOOK_SECRET chuẩn", async () => {
  const req = new Request("http://localhost:8787/api/v1/sync/scheduled", {
    method: "POST",
    headers: {
      "X-Webhook-Secret": baseEnv.SYNC_WEBHOOK_SECRET
    }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);
  assert.strictEqual(data.data.triggered_by, "SCHEDULED");
});

test("P1-02 ATOMIC CONCURRENCY: Hai request chạy đồng thời thật sự bị khóa nguyên tử (1 PASS, 1 từ chối 409)", async () => {
  const { triggerSync } = await import("../dist/services/syncService.js");

  // Chạy đồng thời 2 lệnh triggerSync song song qua Promise.all
  const [res1, res2] = await Promise.allSettled([
    triggerSync(testDb, baseEnv, { triggeredBy: "MANUAL" }),
    triggerSync(testDb, baseEnv, { triggeredBy: "MANUAL" })
  ]);

  // Phải có đúng 1 lệnh thành công (fulfilled) và 1 lệnh bị từ chối 409 (rejected)
  const fulfilled = [res1, res2].filter((r) => r.status === "fulfilled");
  const rejected = [res1, res2].filter((r) => r.status === "rejected");

  assert.strictEqual(fulfilled.length, 1, "Chính xác 1 request đồng thời được cấp khóa thành công");
  assert.strictEqual(rejected.length, 1, "Chính xác 1 request đồng thời bị từ chối nguyên tử");
  assert.strictEqual(rejected[0].reason.code, "SYNC_ALREADY_RUNNING");
});

test("P1-02 STALE LEASE RECOVERY: Tự động thu hồi khóa đồng bộ khi lease bị quá hạn (Stale Lease)", async () => {
  const { acquireSyncLock, releaseSyncLock } = await import("../dist/services/syncService.js");

  // Giả lập một khóa đồng bộ bị bỏ rơi quá hạn 15 phút trước
  const pastIso = new Date(Date.now() - 15 * 60 * 1000).toISOString();
  await testDb
    .prepare(
      `INSERT INTO sync_locks (source_id, lock_token, locked_at, lease_expires_at)
       VALUES (1, 'stale-token-123', ?, ?)`
    )
    .bind(pastIso, pastIso)
    .run();

  // Yêu cầu cấp khóa mới -> phải thu hồi thành công lease quá hạn
  const newLock = await acquireSyncLock(testDb, 1, 10 * 60 * 1000);
  assert.strictEqual(newLock.acquired, true, "Phải thu hồi thành công khóa quá hạn");
  assert.ok(newLock.lockToken !== "stale-token-123");

  // Giải phóng khóa
  await releaseSyncLock(testDb, 1, newLock.lockToken);
});

test("P1-02 WORKER CRASH MIDWAY: Khóa được giải phóng trong finally khi xảy ra lỗi bất ngờ", async () => {
  const { triggerSync } = await import("../dist/services/syncService.js");

  const faultDriver = {
    getMode() { return "SIMULATION"; },
    async listFiles() {
      throw new Error("Mô phỏng lỗi Worker OOM hoặc sự cố mạng giữa chừng");
    },
    async downloadFile() { return new ArrayBuffer(0); },
    async verifyConnection() { return { success: true }; }
  };

  // Đợt 1 gặp lỗi giữa chừng
  const result1 = await triggerSync(testDb, baseEnv, { driver: faultDriver });
  assert.strictEqual(result1.status, "FAILED");

  // Đợt 2 chạy ngay sau đó phải thu nhận được khóa bình thường vì đợt 1 đã giải phóng trong finally
  const result2 = await triggerSync(testDb, baseEnv);
  assert.strictEqual(result2.status, "COMPLETED");
});

test("P1-02 & P2-03 REVISION CONFLICT: Driver injection phát hiện CONFLICT khi file nguồn bị sửa revision", async () => {
  const { triggerSync } = await import("../dist/services/syncService.js");

  // Lấy 1 snapshot đã nhập thành công trong DB
  const snap = await testDb
    .prepare("SELECT * FROM inventory_files WHERE status = 'COMPLETED' AND is_deleted = 0 LIMIT 1")
    .first();
  assert.ok(snap);

  // Tạo mock driver mô phỏng file trên Google Drive đã bị thay đổi version/revision
  const mockDriver = {
    getMode() { return "SIMULATION"; },
    async listFiles() {
      return [
        {
          id: snap.source_file_id || "gdrive_01",
          name: snap.source_filename || "test.xlsx",
          mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          sizeBytes: 1000,
          modifiedTime: new Date().toISOString(),
          version: "REVISION_v2_MODIFIED_CONTENT" // Revision đã đổi!
        }
      ];
    },
    async downloadFile() {
      const fixturePath = path.resolve(__dirname, "../../../fixtures/Kiem ke/KiemKe_KK.CH41551.26.339000_20261009.xlsx");
      const buf = fs.readFileSync(fixturePath);
      return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
    },
    async verifyConnection() {
      return { success: true };
    }
  };

  // Gọi triggerSync với driver injection thực tế
  const result = await triggerSync(testDb, baseEnv, { driver: mockDriver });

  // Kiểm tra kết quả phản ánh đúng xung đột phiên bản
  assert.strictEqual(result.summary.files_conflict, 1, "Phải phát hiện chính xác 1 file xung đột revision");
  assert.strictEqual(result.summary.files_imported, 0, "Không được ghi đè snapshot lịch sử");
  assert.strictEqual(result.outcome, "CONFLICT");
  assert.strictEqual(result.details[0].action, "CONFLICT");
  assert.ok(result.details[0].reason.includes("xung đột phiên bản"));
});

test("P2-01 PARTIAL OUTCOME: Ghi nhận outcome = 'PARTIAL' nhất quán khi có file lỗi kèm file thành công", async () => {
  const { triggerSync } = await import("../dist/services/syncService.js");

  // Driver mô phỏng trả về 1 file hợp lệ và 1 file rác/hỏng
  const partialDriver = {
    getMode() { return "SIMULATION"; },
    async listFiles() {
      return [
        {
          id: "valid_file_01",
          name: "KiemKe_KK.CH41551.26.339000_20261009.xlsx",
          mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          sizeBytes: 1024,
          modifiedTime: new Date().toISOString()
        },
        {
          id: "corrupted_file_02",
          name: "corrupted_file.xlsx",
          mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          sizeBytes: 100,
          modifiedTime: new Date().toISOString()
        }
      ];
    },
    async downloadFile(fileId) {
      if (fileId === "valid_file_01") {
        const fixturePath = path.resolve(__dirname, "../../../fixtures/Kiem ke/KiemKe_KK.CH41551.26.339000_20261009.xlsx");
        const buf = fs.readFileSync(fixturePath);
        return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
      } else {
        // Trả về file rác không phải định dạng Excel hợp lệ
        return new TextEncoder().encode("CORRUPTED_FILE_DATA_NOT_EXCEL").buffer;
      }
    },
    async verifyConnection() {
      return { success: true };
    }
  };

  const result = await triggerSync(testDb, baseEnv, { driver: partialDriver });
  assert.strictEqual(result.outcome, "PARTIAL");
  assert.strictEqual(result.status, "FAILED");
  assert.strictEqual(result.summary.files_failed, 1);
  assert.ok(result.summary.files_skipped > 0 || result.summary.files_imported > 0);

  // Kiểm tra giá trị lưu trong cơ sở dữ liệu
  const runRow = await testDb
    .prepare("SELECT status, outcome, error_message FROM sync_runs WHERE id = ?")
    .bind(result.run_id)
    .first();
  assert.strictEqual(runRow.outcome, "PARTIAL");
  assert.ok(runRow.error_message.includes("PARTIAL"));
});

test("P2-02 PAGINATION LIMIT: Báo lỗi an toàn khi vượt quá 20 trang / 2.000 file thay vì âm thầm cắt kết quả", async () => {
  const originalFetch = globalThis.fetch;
  let pageReqCount = 0;
  globalThis.fetch = async (url) => {
    const urlStr = String(url);
    if (urlStr.includes("googleapis.com/drive/v3/files")) {
      pageReqCount++;
      return new Response(
        JSON.stringify({
          nextPageToken: `TOKEN_PAGE_${pageReqCount + 1}`,
          files: [{ id: `f_${pageReqCount}`, name: `f_${pageReqCount}.xlsx`, size: "100" }]
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    return originalFetch(url);
  };

  try {
    const driver = new LiveGoogleDriveDriver({ apiKey: "test_dummy_key" });
    await assert.rejects(
      async () => {
        await driver.listFiles(GDRIVE_FOLDER_ID);
      },
      /Vượt quá giới hạn phân trang an toàn/
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("P2-09: Production guard: getGoogleDriveDriver từ chối Simulation trên production nếu thiếu flag", () => {
  const prodEnv = {
    ENVIRONMENT: "production",
    DB: testDb
  };
  const driver = getGoogleDriveDriver(prodEnv);
  assert.strictEqual(driver.getMode(), "LIVE");
});

test.after(async () => {
  if (mf) {
    await mf.dispose();
  }
});



