/**
 * Kiểm thử Tự động: Động cơ Đối soát & So sánh Tồn kho (Round 05)
 * Module: apps/api/tests/comparison.test.js
 *
 * Kiểm tra đầy đủ:
 * 1. So sánh 2 file cùng ngày 09/10/2026 (339000 vs 339513)
 * 2. So sánh ngày 09/10 vs 10/10 (339513 vs 339931) -> 2 SKU mới xuất hiện
 * 3. So sánh ngày 10/10 vs 11/10 (339931 vs 340231) -> 28 SKU giảm, 5 mã mẫu
 * 4. So sánh với chính nó (delta = 0, 100% không đổi)
 * 5. So sánh đảo chiều (B vs A đảo dấu delta)
 * 6. Công thức bắt buộc: B.qty - A.qty, không dùng cột chênh lệch Excel
 * 7. Lịch sử biến động theo SKU (SKU Timeline) qua 4 snapshot
 * 8. Xuất báo cáo CSV đối soát có UTF-8 BOM
 * 9. API REST endpoints, bộ lọc, tìm kiếm và phân trang
 */

import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import worker from "../dist/index.js";
import { parseInventoryExcel } from "../dist/services/excelParser.js";
import { importSnapshot } from "../dist/services/inventoryService.js";
import { hashPassword } from "../dist/security/password.js";
import { hashSessionToken } from "../dist/security/session.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATION_PATH = path.resolve(__dirname, "../../../database/migrations/0001_initial_schema.sql");
const REAL_DATA_DIR = path.resolve(__dirname, "../../../../../Data Source/Kiem ke");

const REAL_FILES = [
  "KiemKe_KK.CH41551.26.339000_20261009.xlsx",
  "KiemKe_KK.CH41551.26.339513_20261009.xlsx",
  "KiemKe_KK.CH41551.26.339931_20261010.xlsx",
  "KiemKe_KK.CH41551.26.340231_20261011.xlsx"
];

async function setupTestDb(mfInstance) {
  const db = await mfInstance.getD1Database("DB");
  const sql = fs.readFileSync(MIGRATION_PATH, "utf8");
  const cleanSql = sql.replace(/--.*$/gm, "").trim();
  const statements = cleanSql.split(";").map((s) => s.trim()).filter((s) => s.length > 0);
  for (const stmt of statements) {
    await db.prepare(stmt).run();
  }
  return db;
}

let mf;
let testDb;
let baseEnv;
let adminToken = "admin-session-token-round5";
let adminTokenHash;
let userToken = "user-session-token-round5";
let userTokenHash;

let snap339000Id;
let snap339513Id;
let snap339931Id;
let snap340231Id;

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
    ROUND: "05/10",
    APP_TIMEZONE: "Asia/Ho_Chi_Minh",
    ALLOWED_ORIGINS: "http://localhost:3000,http://localhost:5173",
    BOOTSTRAP_TOKEN: "bootstrap-secret-round5"
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

  // Nạp 4 file kiểm kê thật vào DB
  const p0 = await parseInventoryExcel(fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[0])), REAL_FILES[0]);
  const s0 = await importSnapshot(testDb, p0, { autoCommit: true, userId: 1, shift: "Sáng" });
  snap339000Id = s0.id;

  const p1 = await parseInventoryExcel(fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[1])), REAL_FILES[1]);
  const s1 = await importSnapshot(testDb, p1, { autoCommit: true, userId: 1, shift: "Chiều" });
  snap339513Id = s1.id;

  const p2 = await parseInventoryExcel(fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[2])), REAL_FILES[2]);
  const s2 = await importSnapshot(testDb, p2, { autoCommit: true, userId: 1, shift: "Sáng" });
  snap339931Id = s2.id;

  const p3 = await parseInventoryExcel(fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[3])), REAL_FILES[3]);
  const s3 = await importSnapshot(testDb, p3, { autoCommit: true, userId: 1, shift: "Sáng" });
  snap340231Id = s3.id;
});

test.after(async () => {
  if (mf) await mf.dispose();
});

// ====================================================================
// NHÓM 1: BASELINE GROUND TRUTH (3 CẶP ĐỐI SOÁT CHUẨN)
// ====================================================================

test("BASELINE CẶP 1: So sánh 2 file cùng ngày 09/10/2026 (339000 -> 339513) khớp 100% Ground Truth", async () => {
  const req = new Request(
    `http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${snap339513Id}&limit=1000`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  const sm = json.data.summary;

  // Ground Truth:
  // Matched: 432, Tăng: 19, Giảm: 58, Không đổi: 355, Mới: 0, Mất: 0
  // Delta SL = +129, Delta VND = +1,736,526
  assert.strictEqual(sm.matched_count, 432);
  assert.strictEqual(sm.increased_count, 19, "Số SKU tăng phải là 19");
  assert.strictEqual(sm.decreased_count, 58, "Số SKU giảm phải là 58");
  assert.strictEqual(sm.unchanged_count, 355, "Số SKU không đổi phải là 355");
  assert.strictEqual(sm.new_count, 0, "Không có SKU mới");
  assert.strictEqual(sm.not_present_count, 0, "Không có SKU vắng mặt");
  assert.strictEqual(sm.delta_quantity, 129, "Biến động số lượng phải là +129");
  assert.strictEqual(sm.delta_amount, 1736526, "Biến động giá trị phải là +1,736,526 VND");

  // Kiểm tra top biến động
  assert.ok(sm.top_increased.length <= 5);
  assert.ok(sm.top_decreased.length <= 5);
});

test("BASELINE CẶP 2: So sánh 09/10 -> 10/10 (339513 -> 339931) phát hiện đúng 2 SKU mới xuất hiện", async () => {
  const req = new Request("http://localhost/api/v1/comparison/compare", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${userToken}`
    },
    body: JSON.stringify({
      base_id: snap339513Id,
      target_id: snap339931Id,
      limit: 1000
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  const sm = json.data.summary;

  // Ground Truth:
  // Matched: 432, Tăng: 18, Giảm: 42, Không đổi: 372
  // Mới: 2 (02AO18 tại Kho hàng bán, 9NH277 tại Kho hàng vật phẩm KM)
  // Delta SL = +57, Delta VND = +3,235,734
  assert.strictEqual(sm.matched_count, 432);
  assert.strictEqual(sm.increased_count, 18, "Số SKU tăng phải là 18");
  assert.strictEqual(sm.decreased_count, 42, "Số SKU giảm phải là 42");
  assert.strictEqual(sm.unchanged_count, 372, "Số SKU không đổi phải là 372");
  assert.strictEqual(sm.new_count, 2, "Phải phát hiện chính xác 2 SKU mới xuất hiện");
  assert.strictEqual(sm.not_present_count, 0, "Không có SKU vắng mặt");
  assert.strictEqual(sm.out_of_stock_count, 2, "Có 2 SKU giảm về 0 tồn");
  assert.strictEqual(sm.delta_quantity, 57, "Biến động số lượng phải là +57");
  assert.strictEqual(sm.delta_amount, 3235734, "Biến động giá trị phải là +3,235,734 VND");

  // Tìm 2 SKU mới trong danh sách items
  const newItems = json.data.items.filter((it) => it.status === "NEW_ADDED");
  assert.strictEqual(newItems.length, 2);

  const item1 = newItems.find((it) => it.product_code === "02AO18");
  assert.ok(item1, "Phải tìm thấy 02AO18");
  assert.strictEqual(item1.warehouse, "Kho hàng bán");
  assert.strictEqual(item1.base_quantity, null);
  assert.strictEqual(item1.percentage_change, null, "Base qty = null thì percentage_change phải là null");

  const item2 = newItems.find((it) => it.product_code === "9NH277");
  assert.ok(item2, "Phải tìm thấy 9NH277");
  assert.strictEqual(item2.warehouse, "Kho hàng vật phẩm KM");
  assert.strictEqual(item2.base_quantity, null);
});

test("BASELINE CẶP 3: So sánh 10/10 -> 11/10 (339931 -> 340231) kiểm chứng 28 SKU giảm và 5 mã mẫu", async () => {
  const req = new Request(
    `http://localhost/api/v1/compare?snapshot_a=${snap339931Id}&snapshot_b=${snap340231Id}&limit=1000`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  const sm = json.data.summary;

  // Ground Truth:
  // Matched: 434, Tăng: 0, Giảm: 28, Không đổi: 406, Mới: 0, Mất: 0
  // Delta SL = -175, Delta VND = -1,935,846
  assert.strictEqual(sm.matched_count, 434);
  assert.strictEqual(sm.increased_count, 0, "Không có SKU nào tăng");
  assert.strictEqual(sm.decreased_count, 28, "Chính xác 28 SKU giảm tồn");
  assert.strictEqual(sm.unchanged_count, 406, "Chính xác 406 SKU không đổi");
  assert.strictEqual(sm.new_count, 0);
  assert.strictEqual(sm.not_present_count, 0, "Không có SKU vắng mặt");
  assert.strictEqual(sm.out_of_stock_count, 2, "Có 2 SKU giảm về 0 tồn");
  assert.strictEqual(sm.delta_quantity, -175, "Biến động số lượng phải là -175");
  assert.strictEqual(sm.delta_amount, -1935846, "Biến động giá trị phải là -1,935,846 VND");

  // Kiểm chứng 5 mã SKU mẫu:
  // 1. 07KD12: 113 -> 89 (delta -24)
  // 2. 04FT32: 88 -> 67 (delta -21)
  // 3. 07NH12: 56 -> 37 (delta -19)
  // 4. 04EC33: 124 -> 108 (delta -16)
  // 5. 07TR33: 94 -> 82 (delta -12)
  const items = json.data.items;
  const sample1 = items.find((it) => it.product_code === "07KD12" && it.warehouse === "Kho hàng bán");
  assert.ok(sample1);
  assert.strictEqual(sample1.base_quantity, 113);
  assert.strictEqual(sample1.target_quantity, 89);
  assert.strictEqual(sample1.delta_quantity, -24);

  const sample2 = items.find((it) => it.product_code === "04FT32" && it.warehouse === "Kho hàng bán");
  assert.ok(sample2);
  assert.strictEqual(sample2.base_quantity, 88);
  assert.strictEqual(sample2.target_quantity, 67);
  assert.strictEqual(sample2.delta_quantity, -21);

  const sample3 = items.find((it) => it.product_code === "07NH12" && it.warehouse === "Kho hàng bán");
  assert.ok(sample3);
  assert.strictEqual(sample3.base_quantity, 56);
  assert.strictEqual(sample3.target_quantity, 37);
  assert.strictEqual(sample3.delta_quantity, -19);

  const sample4 = items.find((it) => it.product_code === "04EC33" && it.warehouse === "Kho hàng bán");
  assert.ok(sample4);
  assert.strictEqual(sample4.base_quantity, 124);
  assert.strictEqual(sample4.target_quantity, 108);
  assert.strictEqual(sample4.delta_quantity, -16);

  const sample5 = items.find((it) => it.product_code === "07TR33" && it.warehouse === "Kho hàng bán");
  assert.ok(sample5);
  assert.strictEqual(sample5.base_quantity, 94);
  assert.strictEqual(sample5.target_quantity, 82);
  assert.strictEqual(sample5.delta_quantity, -12);
});

// ====================================================================
// NHÓM 2: TÍNH CHẤT TOÁN HỌC & ĐỐI XỨNG
// ====================================================================

test("TÍNH CHẤT: So sánh 1 snapshot với chính nó -> 100% Khớp, delta = 0", async () => {
  const req = new Request(
    `http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${snap339000Id}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  const sm = json.data.summary;

  assert.strictEqual(sm.matched_count, 432);
  assert.strictEqual(sm.increased_count, 0);
  assert.strictEqual(sm.decreased_count, 0);
  assert.strictEqual(sm.unchanged_count, 432);
  assert.strictEqual(sm.delta_quantity, 0);
  assert.strictEqual(sm.delta_amount, 0);
});

test("TÍNH CHẤT: So sánh đảo chiều (B -> A) đối xứng hoàn hảo với (A -> B)", async () => {
  // So sánh ngược 339513 -> 339000 (thay vì 339000 -> 339513)
  const req = new Request(
    `http://localhost/api/v1/comparison?base_id=${snap339513Id}&target_id=${snap339000Id}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  const sm = json.data.summary;

  // Thuận: tăng 19, giảm 58, delta SL +129, delta VND +1,736,526
  // Nghịch: tăng 58, giảm 19, delta SL -129, delta VND -1,736,526
  assert.strictEqual(sm.increased_count, 58);
  assert.strictEqual(sm.decreased_count, 19);
  assert.strictEqual(sm.unchanged_count, 355);
  assert.strictEqual(sm.delta_quantity, -129);
  assert.strictEqual(sm.delta_amount, -1736526);
});

// ====================================================================
// NHÓM 3: BỘ LỌC, TÌM KIẾM & PHÂN TRANG
// ====================================================================

test("FILTER: Lọc theo trạng thái status=INCREASED chỉ trả về mặt hàng tăng tồn", async () => {
  const req = new Request(
    `http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${snap339513Id}&status=INCREASED`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.data.pagination.total, 19);
  assert.ok(json.data.items.every((it) => it.status === "INCREASED" && it.delta_quantity > 0));
});

test("SEARCH: Tìm kiếm theo mã SKU '02AA15' trả về kết quả chính xác", async () => {
  const req = new Request(
    `http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${snap339513Id}&search=02AA15`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.data.items.length, 1);
  assert.strictEqual(json.data.items[0].product_code, "02AA15");
});

// ====================================================================
// NHÓM 4: LỊCH SỬ BIẾN ĐỘNG THEO SKU (SKU TIMELINE)
// ====================================================================

test("SKU HISTORY: Tra cứu lịch sử mặt hàng '02AA15' qua toàn bộ 4 snapshot", async () => {
  const req = new Request("http://localhost/api/v1/comparison/history/02AA15", {
    method: "GET",
    headers: { Authorization: `Bearer ${userToken}` }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.strictEqual(json.data.product_code, "02AA15");
  assert.ok(json.data.history.length >= 4, "Phải có ít nhất 4 điểm lịch sử");

  // Kiểm tra điểm đầu tiên
  const p0 = json.data.history[0];
  assert.strictEqual(p0.ticket_number, "339000");
  assert.strictEqual(p0.delta_quantity, null, "Điểm đầu tiên không có delta");
});

test("SKU HISTORY: Mã SKU không tồn tại trả về 404 PRODUCT_NOT_FOUND", async () => {
  const req = new Request("http://localhost/api/v1/comparison/history/NONEXISTENT_SKU_999", {
    method: "GET",
    headers: { Authorization: `Bearer ${userToken}` }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 404);
  const json = await res.json();
  assert.strictEqual(json.error.code, "PRODUCT_NOT_FOUND");
});

// ====================================================================
// NHÓM 5: XUẤT BÁO CÁO CSV ĐỐI SOÁT
// ====================================================================

test("EXPORT CSV: Xuất báo cáo đối soát ra file CSV có UTF-8 BOM và đầy đủ tiêu đề", async () => {
  const req = new Request(
    `http://localhost/api/v1/comparison/export?base_id=${snap339000Id}&target_id=${snap339513Id}`,
    {
      method: "GET",
      headers: { Authorization: `Bearer ${userToken}` }
    }
  );

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.headers.get("Content-Type"), "text/csv; charset=utf-8");
  assert.ok(res.headers.get("Content-Disposition")?.includes("attachment"));

  const arrayBuffer = await res.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  // Ký tự UTF-8 BOM: 0xEF, 0xBB, 0xBF
  assert.strictEqual(bytes[0], 0xef, "Byte 0 phải là 0xEF");
  assert.strictEqual(bytes[1], 0xbb, "Byte 1 phải là 0xBB");
  assert.strictEqual(bytes[2], 0xbf, "Byte 2 phải là 0xBF");

  const text = new TextDecoder().decode(bytes);
  assert.ok(text.includes("Mã sản phẩm"), "Phải chứa cột Mã sản phẩm");
  assert.ok(text.includes("Biến động SL (B - A)"), "Phải chứa cột Biến động SL");
  assert.ok(text.includes("02AA15"), "Phải chứa SKU mẫu");
});

// ====================================================================
// NHÓM 6: BẢO MẬT & XỬ LÝ LỖI ĐẦU VÀO
// ====================================================================

test("VALIDATION: Thiếu base_id hoặc target_id trả về 400 MISSING_SNAPSHOT_IDS", async () => {
  const req = new Request("http://localhost/api/v1/comparison?base_id=1", {
    method: "GET",
    headers: { Authorization: `Bearer ${userToken}` }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 400);
  const json = await res.json();
  assert.strictEqual(json.error.code, "MISSING_SNAPSHOT_IDS");
});

test("VALIDATION: Snapshot ID không tồn tại trả về 404 BASE_SNAPSHOT_NOT_FOUND", async () => {
  const req = new Request("http://localhost/api/v1/comparison?base_id=999999&target_id=1", {
    method: "GET",
    headers: { Authorization: `Bearer ${userToken}` }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 404);
  const json = await res.json();
  assert.strictEqual(json.error.code, "BASE_SNAPSHOT_NOT_FOUND");
});

test("SECURITY: Gọi API so sánh mà không đăng nhập bị từ chối 401 UNAUTHORIZED", async () => {
  const req = new Request(`http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${snap339513Id}`, {
    method: "GET"
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);
});

// ====================================================================
// NHÓM 7: REGRESSION TESTS ROUND 05 FIX 01 (P1-01, P1-02, P1-03, P2-01, P2-02)
// ====================================================================

test("P1-01 REGRESSION: Chặn so sánh nếu Snapshot cơ sở (A) hoặc đối soát (B) chưa COMPLETED (422)", async () => {
  // 1. Tạo snapshot ở trạng thái STAGING
  const resStaging = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH41551.26.STAGING1', 'STAGING1', 'CH41551', '2026-10-12', 'Sáng',
         10, 100, 1000000, 'sha_staging_1', 'hash_staging_1', 'staging.xlsx', 'STAGING', 1
       )`
    )
    .run();
  const stagingId = Number(resStaging.meta.last_row_id);

  // 2. Tạo snapshot ở trạng thái FAILED
  const resFailed = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH41551.26.FAILED1', 'FAILED1', 'CH41551', '2026-10-12', 'Chiều',
         0, 0, 0, 'sha_failed_1', 'hash_failed_1', 'failed.xlsx', 'FAILED', 1
       )`
    )
    .run();
  const failedId = Number(resFailed.meta.last_row_id);

  // Thử so sánh base là STAGING -> 422 SNAPSHOT_NOT_COMPLETED
  const req1 = new Request(`http://localhost/api/v1/comparison?base_id=${stagingId}&target_id=${snap339000Id}`, {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const res1 = await worker.fetch(req1, baseEnv);
  assert.strictEqual(res1.status, 422);
  const json1 = await res1.json();
  assert.strictEqual(json1.error.code, "SNAPSHOT_NOT_COMPLETED");
  assert.ok(json1.error.message.includes("STAGING"));

  // Thử so sánh target là FAILED -> 422 SNAPSHOT_NOT_COMPLETED
  const req2 = new Request(`http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${failedId}`, {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const res2 = await worker.fetch(req2, baseEnv);
  assert.strictEqual(res2.status, 422);
  const json2 = await res2.json();
  assert.strictEqual(json2.error.code, "SNAPSHOT_NOT_COMPLETED");
  assert.ok(json2.error.message.includes("FAILED"));
});

test("P1-02 REGRESSION: Phân biệt chính xác NOT_PRESENT (Không xuất hiện) vs OUT_OF_STOCK (Hết tồn SL=0)", async () => {
  // Tạo Snapshot Snap_A_Custom
  const snapA = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH41551.26.DIFF_A', 'DIFF_A', 'CH41551', '2026-10-12', 'Sáng',
         2, 25, 250000, 'sha_diff_a', 'hash_diff_a', 'diff_a.xlsx', 'COMPLETED', 1
       )`
    )
    .run();
  const idA = Number(snapA.meta.last_row_id);

  // Snap A có 2 sản phẩm:
  // SKU_MISSING (SL: 15) -> Sẽ vắng mặt hoàn toàn ở B
  // SKU_ZERO (SL: 10) -> Sẽ có dòng ở B với SL = 0
  await testDb
    .prepare(
      `INSERT INTO inventory_items (
         file_id, row_index, stt, category, product_code, product_name,
         quantity, warehouse, unit_price, total_amount, conversion_rate
       ) VALUES 
       (?, 1, 1, 'Sữa tươi', 'SKU_MISSING', 'Sản phẩm vắng mặt', 15, 'Kho hàng bán', 10000, 150000, 1),
       (?, 2, 2, 'Sữa chua', 'SKU_ZERO', 'Sản phẩm hết tồn', 10, 'Kho hàng bán', 10000, 100000, 1)`
    )
    .bind(idA, idA)
    .run();

  // Tạo Snapshot Snap_B_Custom
  const snapB = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH41551.26.DIFF_B', 'DIFF_B', 'CH41551', '2026-10-12', 'Chiều',
         1, 0, 0, 'sha_diff_b', 'hash_diff_b', 'diff_b.xlsx', 'COMPLETED', 1
       )`
    )
    .run();
  const idB = Number(snapB.meta.last_row_id);

  // Snap B CHỈ có SKU_ZERO với SL = 0. Hoàn toàn không có dòng SKU_MISSING!
  await testDb
    .prepare(
      `INSERT INTO inventory_items (
         file_id, row_index, stt, category, product_code, product_name,
         quantity, warehouse, unit_price, total_amount, conversion_rate
       ) VALUES 
       (?, 1, 1, 'Sữa chua', 'SKU_ZERO', 'Sản phẩm hết tồn', 0, 'Kho hàng bán', 10000, 0, 1)`
    )
    .bind(idB)
    .run();

  const req = new Request(`http://localhost/api/v1/comparison?base_id=${idA}&target_id=${idB}`, {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.strictEqual(json.success, true);

  // Kiểm tra summary
  assert.strictEqual(json.data.summary.not_present_count, 1, "Phải có 1 SKU không xuất hiện");
  assert.strictEqual(json.data.summary.out_of_stock_count, 1, "Phải có 1 SKU hết tồn");

  // Kiểm tra chi tiết từng mặt hàng
  const itemMissing = json.data.items.find((it) => it.product_code === "SKU_MISSING");
  assert.ok(itemMissing, "Phải tìm thấy SKU_MISSING");
  assert.strictEqual(itemMissing.status, "NOT_PRESENT");
  assert.strictEqual(itemMissing.status_label_vi, "Không xuất hiện ở kỳ B");
  assert.strictEqual(itemMissing.base_quantity, 15);
  assert.strictEqual(itemMissing.target_quantity, null, "target_quantity phải là null");
  assert.strictEqual(itemMissing.delta_quantity, null, "delta_quantity phải là null");
  assert.strictEqual(itemMissing.delta_amount, null, "delta_amount phải là null");

  const itemZero = json.data.items.find((it) => it.product_code === "SKU_ZERO");
  assert.ok(itemZero, "Phải tìm thấy SKU_ZERO");
  assert.strictEqual(itemZero.status, "OUT_OF_STOCK");
  assert.strictEqual(itemZero.status_label_vi, "Hết tồn (SL = 0)");
  assert.strictEqual(itemZero.base_quantity, 10);
  assert.strictEqual(itemZero.target_quantity, 0, "target_quantity phải là 0");
  assert.strictEqual(itemZero.delta_quantity, -10, "delta_quantity = 0 - 10 = -10");
});

test("P1-03 REGRESSION: Cảnh báo khác cửa hàng (scope_warning) và Lịch sử SKU không trừ chéo cửa hàng", async () => {
  // Tạo snapshot của cửa hàng KHÁC (CH99999)
  const snapOther = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH99999.26.111222', '111222', 'CH99999', '2026-10-09', 'Sáng',
         1, 50, 500000, 'sha_store_other', 'hash_store_other', 'other.xlsx', 'COMPLETED', 1
       )`
    )
    .run();
  const otherId = Number(snapOther.meta.last_row_id);

  await testDb
    .prepare(
      `INSERT INTO inventory_items (
         file_id, row_index, stt, category, product_code, product_name,
         quantity, warehouse, unit_price, total_amount, conversion_rate
       ) VALUES 
       (?, 1, 1, 'Sữa', '02AA15', 'Sữa tươi test', 50, 'Kho hàng bán', 10000, 500000, 1)`
    )
    .bind(otherId)
    .run();

  // 1. So sánh giữa CH41551 (snap339000Id) và CH99999 (otherId) -> Phải có scope_warning
  const req = new Request(`http://localhost/api/v1/comparison?base_id=${snap339000Id}&target_id=${otherId}`, {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.ok(json.data.summary.scope_warning, "Phải có cảnh báo scope_warning");
  assert.ok(json.data.summary.scope_warning.includes("CH41551") && json.data.summary.scope_warning.includes("CH99999"));

  // 2. Tra cứu lịch sử của SKU '02AA15'
  // Điểm của cửa hàng CH99999 KHÔNG được trừ delta với điểm của CH41551
  const reqHist = new Request("http://localhost/api/v1/comparison/history/02AA15", {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const resHist = await worker.fetch(reqHist, baseEnv);
  const jsonHist = await resHist.json();
  const otherPoint = jsonHist.data.history.find((p) => p.store_code === "CH99999");
  assert.ok(otherPoint, "Phải có điểm lịch sử từ CH99999");
  assert.strictEqual(otherPoint.delta_quantity, null, "Điểm đầu tiên của cửa hàng CH99999 phải có delta_quantity = null");
});

test("P2-01 REGRESSION: Xuất CSV không bị cắt dòng ở 1.000 dòng (>1.000 SKU xuất đầy đủ)", async () => {
  // Tạo snapshot với 1.050 SKU
  const snapLarge = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH41551.26.LARGE_A', 'LARGE_A', 'CH41551', '2026-10-12', 'Sáng',
         1050, 1050, 10500000, 'sha_large_a', 'hash_large_a', 'large.xlsx', 'COMPLETED', 1
       )`
    )
    .run();
  const largeId = Number(snapLarge.meta.last_row_id);

  // Batch insert 1050 items
  for (let batch = 0; batch < 7; batch++) {
    const stmts = [];
    for (let i = 1; i <= 150; i++) {
      const idx = batch * 150 + i;
      stmts.push(`INSERT INTO inventory_items (
        file_id, row_index, stt, category, product_code, product_name,
        quantity, warehouse, unit_price, total_amount, conversion_rate
      ) VALUES (${largeId}, ${idx}, ${idx}, 'Sữa', 'SKU_L_${String(idx).padStart(4, "0")}', 'Sản phẩm ${idx}', 1, 'Kho hàng bán', 10000, 10000, 1)`);
    }
    await testDb.prepare(stmts.join(";")).run();
  }

  // Gọi xuất CSV so sánh LARGE_A với chính nó
  const req = new Request(`http://localhost/api/v1/comparison/export?base_id=${largeId}&target_id=${largeId}`, {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const arrayBuffer = await res.arrayBuffer();
  const text = new TextDecoder().decode(new Uint8Array(arrayBuffer));
  const lines = text.trim().split("\r\n");

  // Dòng 0 là header, từ dòng 1 trở đi là data: phải có 1.050 dòng data (tổng 1.051 dòng)
  assert.strictEqual(lines.length, 1051, "CSV phải xuất đầy đủ 1.050 dòng dữ liệu, không bị cắt ở 1.000 dòng");
});

test("P2-02 REGRESSION: Chống tấn công Spreadsheet Formula Injection trong CSV", async () => {
  // Tạo snapshot chứa các trường text độc hại: =cmd, @SUM, +123, -DANGER
  const snapMalicious = await testDb
    .prepare(
      `INSERT INTO inventory_files (
         full_code, ticket_number, store_code, inventory_date, shift,
         total_sku_count, total_quantity, total_amount_vnd, file_sha256,
         content_hash, source_filename, status, created_by
       ) VALUES (
         'KK.CH41551.26.FORMULA', 'FORMULA', 'CH41551', '2026-10-12', 'Sáng',
         1, 5, 50000, 'sha_formula', 'hash_formula', 'formula.xlsx', 'COMPLETED', 1
       )`
    )
    .run();
  const maliciousId = Number(snapMalicious.meta.last_row_id);

  await testDb
    .prepare(
      `INSERT INTO inventory_items (
         file_id, row_index, stt, category, product_code, product_name,
         quantity, warehouse, unit_price, total_amount, conversion_rate
       ) VALUES (
         ?, 1, 1, '=SUM(A1:A10)', '@MALICIOUS_SKU', '+calc|cmd!test', 5, '-KHO_DOC', 10000, 50000, 1
       )`
    )
    .bind(maliciousId)
    .run();

  const req = new Request(`http://localhost/api/v1/comparison/export?base_id=${maliciousId}&target_id=${maliciousId}`, {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const arrayBuffer = await res.arrayBuffer();
  const text = new TextDecoder().decode(new Uint8Array(arrayBuffer));

  // Kiểm tra text fields được vô hiệu hóa công thức bằng cách chèn dấu ' phía trước
  assert.ok(text.includes("\"'=SUM(A1:A10)\""), "Category bắt đầu bằng = phải được chèn '");
  assert.ok(text.includes("\"'@MALICIOUS_SKU\""), "Product_code bắt đầu bằng @ phải được chèn '");
  assert.ok(text.includes("\"'+calc|cmd!test\""), "Product_name bắt đầu bằng + phải được chèn '");
  assert.ok(text.includes("\"'-KHO_DOC\""), "Warehouse bắt đầu bằng - phải được chèn '");
});

