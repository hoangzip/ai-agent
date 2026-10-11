/**
 * Kiểm thử Tự động Toàn diện: Quản lý Chứng từ Kiểm kê (Round 04 - Fix 01 Data Integrity)
 * Module: apps/api/tests/inventory.test.js
 *
 * Kiểm tra đầy đủ các yêu cầu cốt lõi và các kịch bản hồi quy (Regression Suite):
 * 1. Phân tích trực tiếp 4 file Excel thật tại Data Source/Kiem ke/
 * 2. Bảo toàn số 0 ở đầu mã sản phẩm (e.g. '02AA15')
 * 3. Đối soát toán học với Dòng 2 (sum quantity == E2, sum amount == H2)
 * 4. P1-01: Không công bố snapshot trước khi import hoàn chỉnh (batch lỗi -> cleanup + FAILED)
 * 5. P1-02: Commit kiểm tra lại DB count/sums, từ chối duyệt snapshot thiếu dòng/lệch tổng
 * 6. P1-03: Hai snapshot khác mã nhưng cùng dữ liệu tồn kho -> Nhập hợp lệ, không chặn DUPLICATE_CONTENT
 * 7. P2-01: Metadata ca kiểm kê (Sáng/Chiều/Tối) và giờ kiểm kê
 * 8. P2-02: Validator nghiêm ngặt không ép chuỗi sai về 0/1; phát hiện trùng SKU trong file
 * 9. P2-03: API Preview không ghi DB
 * 10. P2-04: Giới hạn tài nguyên (vượt quá số file -> 400)
 * 11. Hỗ trợ đa snapshot trong ngày (339000 & 339513 ngày 09/10/2026)
 * 12. Soft delete và phân quyền ADMIN
 */

import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import * as XLSX from "xlsx";
import worker from "../dist/index.js";
import { parseInventoryExcel } from "../dist/services/excelParser.js";
import { importSnapshot, commitSnapshot } from "../dist/services/inventoryService.js";
import { hashPassword } from "../dist/security/password.js";
import { hashSessionToken } from "../dist/security/session.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATION_PATH = path.resolve(__dirname, "../../../database/migrations/0001_initial_schema.sql");
const REAL_DATA_DIR = path.resolve(__dirname, "../../../../../Data Source/Kiem ke");

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
let adminToken = "admin-session-token-round4";
let adminTokenHash;
let userToken = "user-session-token-round4";
let userTokenHash;

const REAL_FILES = [
  "KiemKe_KK.CH41551.26.339000_20261009.xlsx",
  "KiemKe_KK.CH41551.26.339513_20261009.xlsx",
  "KiemKe_KK.CH41551.26.339931_20261010.xlsx",
  "KiemKe_KK.CH41551.26.340231_20261011.xlsx"
];

test.before(async () => {
  mf = new Miniflare({
    modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "test_db" }
  });
  testDb = await setupTestDb(mf);

  baseEnv = {
    DB: testDb,
    ENVIRONMENT: "test",
    ROUND: "04",
    APP_TIMEZONE: "Asia/Ho_Chi_Minh",
    ALLOWED_ORIGINS: "http://localhost:3000",
    BOOTSTRAP_TOKEN: "bootstrap-secret-round-04"
  };

  // Tạo tài khoản Admin và User để test xác thực
  const pwdHash = await hashPassword("Vinamilk@Admin2026");
  await testDb
    .prepare(
      `INSERT INTO users (id, username, password_hash, role, full_name, must_change_password, is_active)
       VALUES (1, 'admin', ?, 'ADMIN', 'Quản trị viên', 0, 1),
              (2, 'user1', ?, 'USER', 'Nhân viên kiểm kho', 0, 1)`
    )
    .bind(pwdHash, pwdHash)
    .run();

  // Tạo phiên hợp lệ cho Admin và User
  adminTokenHash = await hashSessionToken(adminToken);
  userTokenHash = await hashSessionToken(userToken);
  const future = new Date(Date.now() + 86400000).toISOString();

  await testDb
    .prepare(
      `INSERT INTO sessions (id, user_id, expires_at)
       VALUES (?, 1, ?), (?, 2, ?)`
    )
    .bind(adminTokenHash, future, userTokenHash, future)
    .run();
});

test.after(async () => {
  if (mf) {
    await mf.dispose();
  }
});

// ====================================================================
// NHÓM 1: KIỂM THỬ ĐỌC VÀ PHÂN TÍCH 4 FILE EXCEL THẬT
// ====================================================================

for (const filename of REAL_FILES) {
  test(`PARSER: Đọc và xác thực cấu trúc file thật: ${filename}`, async () => {
    const filePath = path.join(REAL_DATA_DIR, filename);
    assert.ok(fs.existsSync(filePath), `File không tồn tại: ${filePath}`);

    const buffer = fs.readFileSync(filePath);
    const parsed = await parseInventoryExcel(buffer, filename);

    // 1. Phải 100% hợp lệ
    assert.strictEqual(parsed.isValid, true, `Lỗi: ${parsed.errors.join("; ")}`);
    assert.strictEqual(parsed.errors.length, 0);

    // 2. Kiểm tra số lượng mặt hàng (> 430 mặt hàng)
    assert.ok(parsed.total_sku_count >= 430, `Tổng số SKU thấp: ${parsed.total_sku_count}`);

    // 3. Bảo toàn số 0 ở đầu mã SKU (vd: '02AA15')
    const item02AA15 = parsed.items.find((it) => it.product_code === "02AA15");
    assert.ok(item02AA15, "Không tìm thấy mã sản phẩm '02AA15'");
    assert.strictEqual(typeof item02AA15.product_code, "string");
    assert.strictEqual(item02AA15.product_code, "02AA15");

    // 4. Kiểm tra đối soát toán học với Dòng 2
    assert.strictEqual(parsed.summary.is_math_matched, true);
    assert.strictEqual(parsed.summary.quantity_diff, 0);
    assert.strictEqual(parsed.summary.amount_diff, 0);
    assert.strictEqual(parsed.summary.calculated_quantity, parsed.summary.row2_quantity);
    assert.strictEqual(parsed.summary.calculated_total_amount, parsed.summary.row2_total_amount);

    // 5. Kiểm tra băm nhị phân và dữ liệu
    assert.strictEqual(parsed.file_sha256.length, 64);
    assert.strictEqual(parsed.content_hash.length, 64);
  });
}

// ====================================================================
// NHÓM 2: VALIDATOR & PREVIEW & METADATA (R04-P2)
// ====================================================================

test("VALIDATOR (R04-P2-02): Ô số chứa chuỗi sai định dạng -> Báo lỗi chi tiết dòng/cột, KHÔNG tự ép về 0", async () => {
  // Tạo file Excel giả lập có ô SL tồn kho sai định dạng
  const wb = XLSX.utils.book_new();
  const wsData = [
    ["STT", "NGÀNH HÀNG", "MÃ SẢN PHẨM", "TÊN SẢN PHẨM", "SL TỒN KHO", "LOẠI KHO", "GIÁ (SAU VAT)", "THÀNH TIỀN", "SL PACKAGE KIỂM KÊ", "SL LẺ KIỂM KÊ", "TỔNG SL KIỂM KÊ", "CHÊNH LỆCH", "ĐVT PACKAGE", "QUY ĐỔI", "ĐVT LẺ"],
    ["", "", "", "", 10, "", "", 100000, "", "", 0, 0, "", "", ""],
    [1, "A", "02AA15", "Sữa bột", "invalid_text_abc", "Kho hàng bán", 10000, 100000, 0, 0, 0, 0, "THU", 12, "Hộp"]
  ];
  const ws = XLSX.utils.aoa_to_sheet(wsData);
  XLSX.utils.book_append_sheet(wb, ws, "Kiem-ke");
  const badBuf = XLSX.write(wb, { type: "buffer", bookType: "xlsx" });

  const parsed = await parseInventoryExcel(badBuf, "KiemKe_KK.CH41551.26.123456_20261009.xlsx");
  assert.strictEqual(parsed.isValid, false);
  assert.ok(
    parsed.errors.some((e) => e.includes("SL TỒN KHO") && e.includes("không phải là định dạng số hợp lệ")),
    `Kỳ vọng bắt lỗi số sai định dạng, nhưng nhận: ${parsed.errors.join("; ")}`
  );
});

test("VALIDATOR (R04-P2-02): Phát hiện trùng lặp SKU (product_code, warehouse) trong cùng file trước khi ghi DB", async () => {
  const wb = XLSX.utils.book_new();
  const wsData = [
    ["STT", "NGÀNH HÀNG", "MÃ SẢN PHẨM", "TÊN SẢN PHẨM", "SL TỒN KHO", "LOẠI KHO", "GIÁ (SAU VAT)", "THÀNH TIỀN", "SL PACKAGE KIỂM KÊ", "SL LẺ KIỂM KÊ", "TỔNG SL KIỂM KÊ", "CHÊNH LỆCH", "ĐVT PACKAGE", "QUY ĐỔI", "ĐVT LẺ"],
    ["", "", "", "", 20, "", "", 200000, "", "", 0, 0, "", "", ""],
    [1, "A", "02AA15", "Sữa bột 1", 10, "Kho hàng bán", 10000, 100000, 0, 0, 0, 0, "THU", 12, "Hộp"],
    [2, "A", "02AA15", "Sữa bột 1 trùng lặp", 10, "Kho hàng bán", 10000, 100000, 0, 0, 0, 0, "THU", 12, "Hộp"]
  ];
  const ws = XLSX.utils.aoa_to_sheet(wsData);
  XLSX.utils.book_append_sheet(wb, ws, "Kiem-ke");
  const badBuf = XLSX.write(wb, { type: "buffer", bookType: "xlsx" });

  const parsed = await parseInventoryExcel(badBuf, "KiemKe_KK.CH41551.26.123457_20261009.xlsx");
  assert.strictEqual(parsed.isValid, false);
  assert.ok(
    parsed.errors.some((e) => e.includes("Trùng lặp mặt hàng") && e.includes("02AA15")),
    `Kỳ vọng phát hiện trùng SKU, nhưng nhận: ${parsed.errors.join("; ")}`
  );
});

test("PREVIEW (R04-P2-03): API POST /api/v1/inventory/preview phân tích và xác thực mà KHÔNG ghi vào DB", async () => {
  const filePath = path.join(REAL_DATA_DIR, REAL_FILES[0]);
  const buf = fs.readFileSync(filePath);
  const base64 = buf.toString("base64");

  const countBefore = await testDb
    .prepare("SELECT COUNT(*) as cnt FROM inventory_files")
    .first();

  const req = new Request("http://localhost/api/v1/inventory/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: REAL_FILES[0],
      content_base64: base64
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.strictEqual(json.data.isValid, true);
  assert.strictEqual(json.data.total_sku_count, 432);
  assert.ok(json.data.preview_items.length <= 50);

  // Cơ sở dữ liệu KHÔNG ĐƯỢC TĂNG bản ghi
  const countAfter = await testDb
    .prepare("SELECT COUNT(*) as cnt FROM inventory_files")
    .first();
  assert.strictEqual(countAfter.cnt, countBefore.cnt);
});

test("RESOURCE LIMITS (R04-P2-04): Từ chối khi tải lên vượt quá 10 file trong một lượt (400 TOO_MANY_FILES)", async () => {
  const dummyFiles = Array.from({ length: 11 }, (_, i) => ({
    filename: `file_${i}.xlsx`,
    content_base64: "dummy"
  }));

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({ files: dummyFiles })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 400);

  const json = await res.json();
  assert.strictEqual(json.error.code, "TOO_MANY_FILES");
});

// ====================================================================
// NHÓM 3: TOÀN VẸN IMPORT & COMMIT (R04-P1-01 & R04-P1-02)
// ====================================================================

let snapshot1Id;
let snapshot2Id;

test("DATA INTEGRITY (R04-P1-01): Nhập khẩu thành công, xác thực DB count và sums thật từ DB", async () => {
  const filePath = path.join(REAL_DATA_DIR, REAL_FILES[0]);
  const buf = fs.readFileSync(filePath);
  const base64 = buf.toString("base64");

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: REAL_FILES[0],
      content_base64: base64,
      auto_commit: false, // Lưu STAGING trước
      shift: "Sáng",
      inventory_time: "08:30"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 201);

  const json = await res.json();
  const snap = json.data.results[0].snapshot;
  assert.strictEqual(snap.status, "STAGING");
  assert.strictEqual(snap.shift, "Sáng");
  assert.strictEqual(snap.inventory_time, "08:30");
  assert.strictEqual(snap.total_sku_count, 432);
  snapshot1Id = snap.id;

  // Kiểm tra bảng inventory_items trong DB thực sự có 432 dòng
  const dbItems = await testDb
    .prepare("SELECT COUNT(*) as cnt, SUM(quantity) as qty, SUM(total_amount) as amt FROM inventory_items WHERE file_id = ?")
    .bind(snap.id)
    .first();
  assert.strictEqual(dbItems.cnt, 432);
  assert.strictEqual(dbItems.qty, 16961);
  assert.strictEqual(dbItems.amt, 270739477);
});

test("DATA INTEGRITY (R04-P1-01): Lỗi batch chi tiết -> Snapshot bị đánh dấu FAILED, xóa rác, KHÔNG công bố COMPLETED", async () => {
  const rawBuf = fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[1]));
  const wb = XLSX.read(rawBuf, { type: "buffer" });
  wb.Props = { Title: "Simulated Batch Failure Test 999888", CreatedDate: new Date() };
  const failBuf = XLSX.write(wb, { type: "buffer", bookType: "xlsx" });

  const parsed = await parseInventoryExcel(
    failBuf,
    "KiemKe_KK.CH41551.26.999888_20261009.xlsx"
  );

  // Mock DB lỗi ở batch thứ 2
  let batchCount = 0;
  const failingDb = {
    prepare: (q) => {
      const origStmt = testDb.prepare(q);
      return {
        bind: (...args) => {
          const bound = origStmt.bind(...args);
          return {
            run: async () => bound.run(),
            first: async () => bound.first(),
            all: async () => bound.all()
          };
        }
      };
    },
    batch: async (stmts) => {
      batchCount++;
      if (batchCount === 2) {
        throw new Error("D1 simulated batch failure: disk full");
      }
      return testDb.batch(stmts);
    }
  };

  await assert.rejects(
    async () => {
      await importSnapshot(failingDb, parsed, { autoCommit: true, userId: 1 });
    },
    (err) => {
      assert.strictEqual(err.code, "ITEM_INSERT_FAILED");
      return true;
    }
  );

  // Kiểm tra trong DB: snapshot header bị chuyển FAILED, inventory_items đã bị cleanup (không còn dòng rác)
  const failedFile = await testDb
    .prepare("SELECT id, status FROM inventory_files WHERE full_code = 'KK.CH41551.26.999888'")
    .first();
  assert.ok(failedFile);
  assert.strictEqual(failedFile.status, "FAILED");

  const orphanedItems = await testDb
    .prepare("SELECT COUNT(*) as cnt FROM inventory_items WHERE file_id = ?")
    .bind(failedFile.id)
    .first();
  assert.strictEqual(orphanedItems.cnt, 0); // Không bị rác
});

test("DATA INTEGRITY (R04-P1-02): commitSnapshot() từ chối nếu DB không có mặt hàng (EMPTY_SNAPSHOT_ITEMS 422)", async () => {
  // Tạo một snapshot rỗng không có item
  const res = await testDb
    .prepare(
      `INSERT INTO inventory_files (full_code, ticket_number, store_code, inventory_date, shift,
        file_sha256, content_hash, source_filename, status, total_sku_count, total_quantity, total_amount_vnd)
       VALUES ('KK.CH41551.26.EMPTY01', 'EMPTY01', 'CH41551', '2026-10-09', 'Sáng',
        'dummy_sha', 'dummy_cnt', 'empty.xlsx', 'STAGING', 432, 16961, 270739477)`
    )
    .run();
  const emptyId = res.meta.last_row_id;

  await assert.rejects(
    async () => {
      await commitSnapshot(testDb, emptyId, { userId: 1 });
    },
    (err) => {
      assert.strictEqual(err.code, "EMPTY_SNAPSHOT_ITEMS");
      assert.strictEqual(err.status, 422);
      return true;
    }
  );

  // Trạng thái vẫn là STAGING, KHÔNG ĐỔI sang COMPLETED
  const row = await testDb.prepare("SELECT status FROM inventory_files WHERE id = ?").bind(emptyId).first();
  assert.strictEqual(row.status, "STAGING");
});

test("DATA INTEGRITY (R04-P1-02): commitSnapshot() từ chối nếu DB lệch tổng hoặc thiếu dòng (TOTALS_MISMATCH 422)", async () => {
  // Tạo snapshot có 1 item nhưng tổng DB khác tóm tắt
  const res = await testDb
    .prepare(
      `INSERT INTO inventory_files (full_code, ticket_number, store_code, inventory_date, shift,
        file_sha256, content_hash, source_filename, status, total_sku_count, total_quantity, total_amount_vnd)
       VALUES ('KK.CH41551.26.MISMATCH', 'MISMATCH', 'CH41551', '2026-10-09', 'Sáng',
        'dummy_sha_2', 'dummy_cnt_2', 'mismatch.xlsx', 'STAGING', 1, 100, 100000)`
    )
    .run();
  const mismatchId = res.meta.last_row_id;

  // Insert item có tổng lệch (chỉ có 50 thay vì 100)
  await testDb
    .prepare(
      `INSERT INTO inventory_items (file_id, row_index, stt, category, product_code, product_name,
        quantity, warehouse, unit_price, total_amount)
       VALUES (?, 3, 1, 'A', '02AA15', 'Sữa', 50, 'Kho hàng bán', 1000, 50000)`
    )
    .bind(mismatchId)
    .run();

  await assert.rejects(
    async () => {
      await commitSnapshot(testDb, mismatchId, { userId: 1 });
    },
    (err) => {
      assert.strictEqual(err.code, "TOTALS_MISMATCH");
      assert.strictEqual(err.status, 422);
      return true;
    }
  );

  const row = await testDb.prepare("SELECT status FROM inventory_files WHERE id = ?").bind(mismatchId).first();
  assert.strictEqual(row.status, "STAGING");
});

test("DATA INTEGRITY (R04-P1-02): commitSnapshot() hợp lệ duyệt thành công khi số liệu DB khớp 100%", async () => {
  const result = await commitSnapshot(testDb, snapshot1Id, { userId: 1 });
  assert.strictEqual(result.snapshot.status, "COMPLETED");

  const row = await testDb.prepare("SELECT status FROM inventory_files WHERE id = ?").bind(snapshot1Id).first();
  assert.strictEqual(row.status, "COMPLETED");
});

// ====================================================================
// NHÓM 4: CHỐNG TRÙNG LẶP & ĐA SNAPSHOT TRONG NGÀY (R04-P1-03)
// ====================================================================

test("BUSINESS LOGIC (FIX 02): Cùng nguyên buffer nhị phân nhưng khác mã kiểm kê -> Lưu thành 2 record độc lập", async () => {
  const filePath = path.join(REAL_DATA_DIR, REAL_FILES[0]);
  const originalBuf = fs.readFileSync(filePath); // CÙNG NGUYÊN BUFFER NHỊ PHÂN (KHÔNG RE-SAVE)

  // Nhập với mã chứng từ KHÁC: KK.CH41551.26.777888
  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: "KiemKe_KK.CH41551.26.777888_20261009.xlsx",
      content_base64: originalBuf.toString("base64"),
      auto_commit: false
    })
  });

  const res = await worker.fetch(req, baseEnv);
  // Phải THÀNH CÔNG (201), KHÔNG BỊ CHẶN BỞI FILE_SHA256!
  assert.strictEqual(res.status, 201);
  const json = await res.json();
  assert.strictEqual(json.data.results[0].success, true);
  assert.strictEqual(json.data.results[0].snapshot.full_code, "KK.CH41551.26.777888");

  // Xác minh trong DB có CẢ 2 RECORD ĐỘC LẬP cùng tồn tại
  const rec1 = await testDb.prepare("SELECT id, full_code, file_sha256 FROM inventory_files WHERE full_code = 'KK.CH41551.26.339000'").first();
  const rec2 = await testDb.prepare("SELECT id, full_code, file_sha256 FROM inventory_files WHERE full_code = 'KK.CH41551.26.777888'").first();
  assert.ok(rec1, "Snapshot 339000 phải tồn tại");
  assert.ok(rec2, "Snapshot 777888 phải tồn tại");
  assert.notStrictEqual(rec1.id, rec2.id, "Phải là 2 record với ID khác nhau");
  assert.strictEqual(rec1.file_sha256, rec2.file_sha256, "Checksum nhị phân của 2 snapshot giống hệt nhau");
});

test("DEDUPLICATION (FIX 02): Cùng mã full_code và cùng nội dung nhị phân -> Bị từ chối 409 ALREADY_IMPORTED", async () => {
  const filePath = path.join(REAL_DATA_DIR, REAL_FILES[0]);
  const originalBuf = fs.readFileSync(filePath);

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: REAL_FILES[0], // Cùng mã 339000
      content_base64: originalBuf.toString("base64")
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 409);
  const json = await res.json();
  assert.strictEqual(json.error.code, "ALREADY_IMPORTED");
});

test("CONFLICT: Cùng full_code nhưng dữ liệu mặt hàng khác nhau -> Bị từ chối 409 CONFLICT", async () => {
  // Dùng file 340231 (nội dung khác) nhưng gán tên file trùng mã KK.CH41551.26.339000
  const filePath = path.join(REAL_DATA_DIR, REAL_FILES[3]);
  const buf = fs.readFileSync(filePath);

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: "KiemKe_KK.CH41551.26.339000_20261009.xlsx",
      content_base64: buf.toString("base64")
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 409);
  const json = await res.json();
  assert.strictEqual(json.error.code, "CONFLICT");
});

test("SOFT DELETE (FIX 02): Nạp lại snapshot đã bị xóa mềm -> Báo lỗi SNAPSHOT_SOFT_DELETED rõ ràng (409)", async () => {
  await testDb.prepare(
    `INSERT INTO inventory_files (full_code, ticket_number, store_code, inventory_date, shift,
      file_sha256, content_hash, source_filename, status, total_sku_count, total_quantity, total_amount_vnd, is_deleted, deleted_at)
     VALUES ('KK.CH41551.26.888111', '888111', 'CH41551', '2026-10-09', 'Sáng',
      'sha_del_1', 'hash_del_1', 'deleted01.xlsx', 'STAGING', 1, 10, 10000, 1, datetime('now', 'utc'))`
  ).run();

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: "KiemKe_KK.CH41551.26.888111_20261009.xlsx",
      content_base64: fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[0])).toString("base64")
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 409);
  const json = await res.json();
  assert.strictEqual(json.error.code, "SNAPSHOT_SOFT_DELETED");
  assert.ok(json.error.message.includes("thùng rác") || json.error.message.includes("khôi phục"));
});

test("MULTI-SNAPSHOT: Nạp Snapshot 2 (339513) trong CÙNG NGÀY 2026-10-09 -> Thành công song song", async () => {
  const filePath = path.join(REAL_DATA_DIR, REAL_FILES[1]);
  const buf = fs.readFileSync(filePath);

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      filename: REAL_FILES[1],
      content_base64: buf.toString("base64"),
      auto_commit: false
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 201);
  const json = await res.json();
  snapshot2Id = json.data.results[0].snapshot.id;
  assert.strictEqual(json.data.results[0].snapshot.ticket_number, "339513");
});

test("IMPORT BATCH: Nạp đồng thời 2 file còn lại (ngày 10/10 và 11/10) với auto_commit=true", async () => {
  const f3 = fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[2])).toString("base64");
  const f4 = fs.readFileSync(path.join(REAL_DATA_DIR, REAL_FILES[3])).toString("base64");

  const req = new Request("http://localhost/api/v1/inventory/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      auto_commit: true,
      files: [
        { filename: REAL_FILES[2], content_base64: f3 },
        { filename: REAL_FILES[3], content_base64: f4 }
      ]
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 201);

  const json = await res.json();
  assert.strictEqual(json.data.total_files, 2);
  assert.strictEqual(json.data.successful_count, 2);
  assert.strictEqual(json.data.results[0].snapshot.status, "COMPLETED");
  assert.strictEqual(json.data.results[1].snapshot.status, "COMPLETED");
});

// ====================================================================
// NHÓM 5: DANH SÁCH & CHI TIẾT & SOFT DELETE (RBAC)
// ====================================================================

test("LIST SNAPSHOTS: Lấy danh sách snapshot kèm bộ lọc", async () => {
  const req = new Request("http://localhost/api/v1/inventory/snapshots?store_code=CH41551", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${userToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.ok(json.data.pagination.total >= 4);
});

test("GET SNAPSHOT DETAILS: Lấy chi tiết 15 cột bảo toàn số 0 đầu mã SKU", async () => {
  const req = new Request(`http://localhost/api/v1/inventory/snapshots/${snapshot1Id}?include_items=true`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${userToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.strictEqual(json.data.snapshot.full_code, "KK.CH41551.26.339000");
  assert.strictEqual(json.data.items.length, 432);

  const item0 = json.data.items[0];
  assert.strictEqual(item0.product_code, "02AA15");
  assert.strictEqual(item0.quantity, 2);
  assert.strictEqual(item0.warehouse, "Kho hàng bán");
  assert.strictEqual(item0.unit_price, 164268);
  assert.strictEqual(item0.total_amount, 328536);
  assert.strictEqual(item0.package_unit, "THU");
  assert.strictEqual(item0.conversion_rate, 24);
  assert.strictEqual(item0.loose_unit, "Hộp");
});

test("RBAC: Nhân viên thường (USER) không thể xóa snapshot (403)", async () => {
  const req = new Request(`http://localhost/api/v1/inventory/snapshots/${snapshot2Id}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${userToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
});

test("SOFT DELETE: Admin xóa mềm snapshot 2 thành công", async () => {
  const req = new Request(`http://localhost/api/v1/inventory/snapshots/${snapshot2Id}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  // Sau khi xóa mềm, không xuất hiện trong danh sách thông thường
  const listReq = new Request("http://localhost/api/v1/inventory/snapshots", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });
  const listRes = await worker.fetch(listReq, baseEnv);
  const listJson = await listRes.json();
  assert.ok(!listJson.data.items.some((it) => it.id === snapshot2Id));
});
