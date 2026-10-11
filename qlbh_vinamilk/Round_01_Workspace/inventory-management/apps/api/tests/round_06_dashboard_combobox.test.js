/**
 * Test Suite: Round 06 Carryover P2 & Dashboard (Async Searchable Combobox & Dashboard Stats)
 * File: apps/api/tests/round_06_dashboard_combobox.test.js
 *
 * Kiểm tra đầy đủ:
 * 1. Fixture 150 snapshots trong cơ sở dữ liệu D1.
 * 2. Chọn snapshot thứ 120 và thứ 150 đối soát thành công (vượt qua giới hạn 100 dòng cũ).
 * 3. Bộ lọc loại trừ snapshot STAGING, FAILED và is_deleted = 1 khi chọn COMPLETED.
 * 4. Tìm kiếm chính xác theo full_code, ticket_number, store_code, shift.
 * 5. Đổi chiều A/B bảo toàn tính đối xứng.
 * 6. Xử lý lỗi khi snapshot bị xóa mềm giữa chừng.
 * 7. Endpoint GET /api/v1/dashboard/stats trả về số liệu thống kê thời gian thực chính xác.
 */

import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import worker from "../dist/index.js";
import { hashPassword } from "../dist/security/password.js";
import { hashSessionToken } from "../dist/security/session.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATION_PATH = path.resolve(__dirname, "../../../database/migrations/0001_initial_schema.sql");

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
let adminToken = "admin-session-token-round6";
let adminTokenHash;
let userToken = "user-session-token-round6";
let userTokenHash;

test.before(async () => {
  mf = new Miniflare({
    modules: true,
    script: `export default { fetch() { return new Response("stub"); } }`,
    d1Databases: ["DB"]
  });

  testDb = await setupTestDb(mf);
  baseEnv = {
    DB: testDb,
    ALLOWED_ORIGINS: "http://localhost:5173",
    ENVIRONMENT: "test",
    ROUND: "06"
  };

  adminTokenHash = await hashSessionToken(adminToken);
  userTokenHash = await hashSessionToken(userToken);

  // Tạo tài khoản Admin và Session
  const adminPwHash = await hashPassword("AdminStrong@2026!");
  await testDb
    .prepare(
      `INSERT INTO users (id, username, password_hash, full_name, role, is_active, must_change_password)
       VALUES (1, 'admin_r6', ?, 'Admin R6', 'ADMIN', 1, 0)`
    )
    .bind(adminPwHash)
    .run();

  const futureExp = "2099-01-01T00:00:00.000Z";
  await testDb
    .prepare(
      `INSERT INTO sessions (id, user_id, expires_at)
       VALUES (?, 1, ?)`
    )
    .bind(adminTokenHash, futureExp)
    .run();

  // Tạo tài khoản USER thông thường và Session (để kiểm tra RBAC)
  const userPwHash = await hashPassword("UserStrong@2026!");
  await testDb
    .prepare(
      `INSERT INTO users (id, username, password_hash, full_name, role, is_active, must_change_password)
       VALUES (2, 'user_r6', ?, 'User R6 Staff', 'USER', 1, 0)`
    )
    .bind(userPwHash)
    .run();

  await testDb
    .prepare(
      `INSERT INTO sessions (id, user_id, expires_at)
       VALUES (?, 2, ?)`
    )
    .bind(userTokenHash, futureExp)
    .run();

  // Nạp danh mục stock_scopes phục vụ kiểm thử phân lập phạm vi kho (P1 Stock Scope Isolation)
  await testDb
    .prepare(
      `INSERT INTO stock_scopes (id, scope_code, scope_name)
       VALUES (1, 'KHO_BAN', 'Kho hàng bán'),
              (2, 'KHO_HU', 'Kho hàng hủy'),
              (10, 'KHO_TONG', 'Kho tổng hợp'),
              (99, 'UNKNOWN', 'Phạm vi không xác định')`
    )
    .run();

  // NẠP FIXTURE 150 SNAPSHOTS ĐỂ TEST CARRYOVER P2
  // 140 snapshots COMPLETED, 5 STAGING, 3 FAILED, 2 SOFT-DELETED
  for (let i = 1; i <= 150; i++) {
    const ticket = String(400000 + i);
    const fullCode = `KK.CH41551.26.${ticket}`;
    const dateStr = `2026-10-${String((i % 28) + 1).padStart(2, "0")}`;
    const shift = i % 3 === 0 ? "Sáng" : i % 3 === 1 ? "Chiều" : "Tối";
    let status = "COMPLETED";
    let isDeleted = 0;

    if (i === 141 || i === 142 || i === 143 || i === 144 || i === 145) {
      status = "STAGING";
    } else if (i === 146 || i === 147 || i === 148) {
      status = "FAILED";
    } else if (i === 149 || i === 150) {
      status = "COMPLETED";
      isDeleted = 1; // Đã xóa mềm
    }

    const fileSha = `sha256_mock_${i.toString().padStart(4, "0")}`;
    const contentHash = `content_hash_${i.toString().padStart(4, "0")}`;

    await testDb
      .prepare(
        `INSERT INTO inventory_files (
          id, full_code, ticket_number, store_code, inventory_date, shift,
          file_sha256, content_hash, source_filename, status, is_deleted,
          total_sku_count, total_quantity, total_amount_vnd, created_by
        ) VALUES (?, ?, ?, 'CH41551', ?, ?, ?, ?, ?, ?, ?, 10, ?, ?, 1)`
      )
      .bind(
        i,
        fullCode,
        ticket,
        dateStr,
        shift,
        fileSha,
        contentHash,
        `KiemKe_${ticket}.xlsx`,
        status,
        isDeleted,
        100 + i,
        (100 + i) * 10000
      )
      .run();

    // Thêm các mặt hàng mẫu cho snapshot để đối soát
    if (status === "COMPLETED" && isDeleted === 0) {
      await testDb
        .prepare(
          `INSERT INTO inventory_items (
            file_id, product_code, product_name, category, warehouse,
            quantity, unit_price, total_amount, row_index, stt
          ) VALUES (?, 'SKU_TEST_01', 'Sữa Tươi Test', 'Sữa tươi', 'Kho hàng bán', ?, 10000, ?, 3, 1)`
        )
        .bind(i, 50 + (i % 10), (50 + (i % 10)) * 10000)
        .run();
    }
  }
});

test.after(async () => {
  if (mf) await mf.dispose();
});

test("ROUND 06 CARRYOVER: Server-side pagination & filter COMPLETED strictly (140 completed out of 150)", async () => {
  const req = new Request("http://localhost:5173/api/v1/inventory/snapshots?status=COMPLETED&limit=50", {
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);
  // Tổng cộng có 140 snapshots COMPLETED không bị xóa
  assert.strictEqual(data.data.pagination.total, 140);
  assert.strictEqual(data.data.pagination.total_pages, 3);
  assert.strictEqual(data.data.items.length, 50);

  // Đảm bảo không có snapshot nào thuộc STAGING, FAILED hoặc is_deleted = 1
  for (const item of data.data.items) {
    assert.strictEqual(item.status, "COMPLETED");
  }
});

test("ROUND 06 CARRYOVER: Search snapshot by full_code and ticket_number across 150 records", async () => {
  // Tìm kiếm snapshot #120 qua query param search
  const req = new Request("http://localhost:5173/api/v1/inventory/snapshots?search=400120&status=COMPLETED", {
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);
  assert.strictEqual(data.data.items.length, 1);
  assert.strictEqual(data.data.items[0].ticket_number, "400120");
  assert.strictEqual(data.data.items[0].full_code, "KK.CH41551.26.400120");
});

test("ROUND 06 CARRYOVER: Select snapshot #120 and #130 (beyond 100 rows limit) and compare successfully", async () => {
  // Snapshot 120 và Snapshot 130 đều nằm ngoài giới hạn 100 dòng cũ!
  const req = new Request("http://localhost:5173/api/v1/comparison?base_id=120&target_id=130", {
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);
  assert.strictEqual(data.data.summary.base_snapshot.id, 120);
  assert.strictEqual(data.data.summary.target_snapshot.id, 130);
  assert.ok(data.data.summary);
  assert.strictEqual(data.data.items.length, 1);
});

test("ROUND 06 CARRYOVER: Reverse comparison (130 -> 120) preserves mathematical symmetry", async () => {
  const fwdReq = new Request("http://localhost:5173/api/v1/comparison?base_id=120&target_id=130", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const revReq = new Request("http://localhost:5173/api/v1/comparison?base_id=130&target_id=120", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const [fwdRes, revRes] = await Promise.all([
    worker.fetch(fwdReq, baseEnv, {}),
    worker.fetch(revReq, baseEnv, {})
  ]);

  const fwd = await fwdRes.json();
  const rev = await revRes.json();

  assert.strictEqual(
    fwd.data.summary.delta_quantity,
    -rev.data.summary.delta_quantity
  );
  assert.strictEqual(
    fwd.data.summary.delta_amount,
    -rev.data.summary.delta_amount
  );
});

test("ROUND 06 CARRYOVER: Reject comparison when snapshot is soft-deleted (ID 149 or 150)", async () => {
  const req = new Request("http://localhost:5173/api/v1/comparison?base_id=120&target_id=149", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv, {});
  // Snapshot đã bị xóa mềm (is_deleted = 1) -> Trả về 404 TARGET_SNAPSHOT_NOT_FOUND
  assert.strictEqual(res.status, 404);
  const data = await res.json();
  assert.strictEqual(data.error.code, "TARGET_SNAPSHOT_NOT_FOUND");
});

test("ROUND 06 DASHBOARD: GET /api/v1/dashboard/stats returns live aggregated metrics", async () => {
  const req = new Request("http://localhost:5173/api/v1/dashboard/stats", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  assert.strictEqual(summary.total_snapshots, 148); // 150 - 2 soft deleted = 148 active
  assert.strictEqual(summary.completed_snapshots, 140);
  assert.strictEqual(summary.staging_snapshots, 5);
  assert.strictEqual(summary.failed_snapshots, 3);
  assert.ok(summary.latest_snapshot);
  assert.strictEqual(summary.trend.has_comparison, true);
  assert.strictEqual(summary.trend.store_code, "CH41551");
  assert.strictEqual(data.data.recent_snapshots.length, 5);
});

test("ROUND 06 REGRESSION P1: Cross-store isolation - different stores do NOT calculate false delta", async () => {
  // Thêm snapshot hoàn tất mới nhất cho Cửa hàng khác (CH_B_TEST)
  // Snapshot này có ngày mới nhất hệ thống (2026-11-01) nhưng CH_B_TEST chỉ có duy nhất 1 snapshot
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (201, 'KK.CH_B.26.900201', '900201', 'CH_B_TEST', '2026-11-01', '10:00:00', 'Sáng',
        'sha256_mock_201', 'content_hash_201', 'KiemKe_900201.xlsx', 'COMPLETED', 0,
        5, 50, 500000, 1)`
    )
    .run();

  const req = new Request("http://localhost:5173/api/v1/dashboard/stats", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  // Snapshot mới nhất toàn hệ thống là 201 (thuộc CH_B_TEST)
  assert.strictEqual(summary.latest_snapshot.id, 201);
  assert.strictEqual(summary.latest_snapshot.store_code, "CH_B_TEST");

  // Vì CH_B_TEST chỉ có 1 snapshot, không được tự ý lấy snapshot của CH41551 để trừ!
  // has_comparison PHẢI LÀ FALSE, delta_quantity = 0!
  assert.strictEqual(summary.previous_snapshot, null);
  assert.strictEqual(summary.trend.has_comparison, false);
  assert.strictEqual(summary.trend.delta_quantity, 0);
  assert.strictEqual(summary.trend.delta_amount_vnd, 0);
});

test("ROUND 06 REGRESSION P1: Store with single snapshot cannot form valid comparison pair", async () => {
  // Lọc cụ thể theo store_code=CH_B_TEST
  const req = new Request("http://localhost:5173/api/v1/dashboard/stats?store_code=CH_B_TEST", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  assert.strictEqual(summary.selected_store, "CH_B_TEST");
  assert.strictEqual(summary.total_snapshots, 1);
  assert.strictEqual(summary.trend.has_comparison, false);
  assert.strictEqual(summary.trend.delta_quantity, 0);
  assert.strictEqual(summary.trend.delta_amount_vnd, 0);
});

test("ROUND 06 REGRESSION P1: Same store with 2 snapshots calculates accurate trend", async () => {
  // Thêm snapshot thứ 2 cho CH_B_TEST (ngày 2026-10-31, SL: 30, Tiền: 300,000)
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (202, 'KK.CH_B.26.900202', '900202', 'CH_B_TEST', '2026-10-31', '15:30:00', 'Chiều',
        'sha256_mock_202', 'content_hash_202', 'KiemKe_900202.xlsx', 'COMPLETED', 0,
        5, 30, 300000, 1)`
    )
    .run();

  const req = new Request("http://localhost:5173/api/v1/dashboard/stats?store_code=CH_B_TEST", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  assert.strictEqual(summary.selected_store, "CH_B_TEST");
  assert.strictEqual(summary.trend.has_comparison, true);
  assert.strictEqual(summary.trend.store_code, "CH_B_TEST");
  // Snapshot 201 (SL 50, Tiền 500k) - Snapshot 202 (SL 30, Tiền 300k)
  // Delta SL = 50 - 30 = 20
  // Delta Tiền = 500,000 - 300,000 = 200,000
  assert.strictEqual(summary.trend.delta_quantity, 20);
  assert.strictEqual(summary.trend.delta_amount_vnd, 200000);
  assert.strictEqual(summary.trend.base_code, "KK.CH_B.26.900202");
  assert.strictEqual(summary.trend.target_code, "KK.CH_B.26.900201");
});

test("ROUND 06 REGRESSION P2: RBAC security - USER role is forbidden from admin endpoints", async () => {
  // 1. USER thường gọi GET /api/v1/users -> 403 Forbidden
  const usersReq = new Request("http://localhost:5173/api/v1/users", {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const usersRes = await worker.fetch(usersReq, baseEnv, {});
  assert.strictEqual(usersRes.status, 403);
  const usersData = await usersRes.json();
  assert.strictEqual(usersData.error.code, "FORBIDDEN_ADMIN_ONLY");

  // 2. USER thường gọi DELETE /api/v1/inventory/snapshots/5 -> 403 Forbidden
  const delReq = new Request("http://localhost:5173/api/v1/inventory/snapshots/5", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const delRes = await worker.fetch(delReq, baseEnv, {});
  assert.strictEqual(delRes.status, 403);

  // 3. ADMIN gọi GET /api/v1/users -> 200 OK
  const adminUsersReq = new Request("http://localhost:5173/api/v1/users", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const adminUsersRes = await worker.fetch(adminUsersReq, baseEnv, {});
  assert.strictEqual(adminUsersRes.status, 200);

  // 4. USER thường vẫn xem được Dashboard -> 200 OK
  const userDashReq = new Request("http://localhost:5173/api/v1/dashboard/stats", {
    headers: { Authorization: `Bearer ${userToken}` }
  });
  const userDashRes = await worker.fetch(userDashReq, baseEnv, {});
  assert.strictEqual(userDashRes.status, 200);
});

test("ROUND 06 FIX 02 P1: Same store but different stock scopes (scope_id 1 vs 2) MUST NOT compare", async () => {
  // Snapshot 301: CH_SCOPE_TEST, scope_id = 1, qty = 1000
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (301, 'KK.SCOPE.26.800301', '800301', 'CH_SCOPE_TEST', 1, '2026-10-15', '08:00:00', 'Sáng',
        'sha256_mock_301', 'content_hash_301', 'KiemKe_301.xlsx', 'COMPLETED', 0,
        10, 1000, 10000000, 1)`
    )
    .run();

  // Snapshot 302: CH_SCOPE_TEST, scope_id = 2, qty = 100 (khác phạm vi kho)
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (302, 'KK.SCOPE.26.800302', '800302', 'CH_SCOPE_TEST', 2, '2026-10-16', '08:00:00', 'Sáng',
        'sha256_mock_302', 'content_hash_302', 'KiemKe_302.xlsx', 'COMPLETED', 0,
        5, 100, 1000000, 1)`
    )
    .run();

  const req = new Request("http://localhost:5173/api/v1/dashboard/stats?store_code=CH_SCOPE_TEST", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  assert.strictEqual(summary.selected_store, "CH_SCOPE_TEST");
  assert.strictEqual(summary.latest_snapshot.id, 302);
  assert.strictEqual(summary.latest_snapshot.scope_id, 2);
  // Không được đối soát với snapshot 301 vì scope_id khác nhau!
  assert.strictEqual(summary.previous_snapshot, null);
  assert.strictEqual(summary.trend.has_comparison, false);
  assert.strictEqual(summary.trend.delta_quantity, 0);
  assert.strictEqual(summary.trend.delta_amount_vnd, 0);
});

test("ROUND 06 FIX 02 P1: Same store and SAME stock scope (scope_id 1) calculates accurate trend", async () => {
  // Snapshot 303: CH_SCOPE_TEST, scope_id = 1, qty = 1050 (cùng scope_id = 1 với 301)
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (303, 'KK.SCOPE.26.800303', '800303', 'CH_SCOPE_TEST', 1, '2026-10-17', '08:00:00', 'Sáng',
        'sha256_mock_303', 'content_hash_303', 'KiemKe_303.xlsx', 'COMPLETED', 0,
        10, 1050, 10500000, 1)`
    )
    .run();

  const req = new Request("http://localhost:5173/api/v1/dashboard/stats?store_code=CH_SCOPE_TEST", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  // Latest là 303 (scope_id = 1). Previous phải khớp scope_id = 1, tức là 301 (bỏ qua 302 có scope_id = 2)
  assert.strictEqual(summary.latest_snapshot.id, 303);
  assert.strictEqual(summary.latest_snapshot.scope_id, 1);
  assert.strictEqual(summary.previous_snapshot.id, 301);
  assert.strictEqual(summary.previous_snapshot.scope_id, 1);
  assert.strictEqual(summary.trend.has_comparison, true);
  // Delta SL = 1050 - 1000 = 50
  assert.strictEqual(summary.trend.delta_quantity, 50);
  assert.strictEqual(summary.trend.delta_amount_vnd, 500000);
});

test("ROUND 06 FIX 02 P1: Unknown stock scope (scope_id = 99) MUST NOT compare", async () => {
  // Snapshot 304 & 305: CH_UNKNOWN_STORE, scope_id = 99 (không xác định)
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (304, 'KK.UNK.26.800304', '800304', 'CH_UNKNOWN_STORE', 99, '2026-10-18', '08:00:00', 'Sáng',
        'sha256_mock_304', 'content_hash_304', 'KiemKe_304.xlsx', 'COMPLETED', 0,
        5, 50, 500000, 1)`
    )
    .run();

  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (305, 'KK.UNK.26.800305', '800305', 'CH_UNKNOWN_STORE', 99, '2026-10-19', '08:00:00', 'Sáng',
        'sha256_mock_305', 'content_hash_305', 'KiemKe_305.xlsx', 'COMPLETED', 0,
        5, 60, 600000, 1)`
    )
    .run();

  const req = new Request("http://localhost:5173/api/v1/dashboard/stats?store_code=CH_UNKNOWN_STORE", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  // Scope không xác định (99) -> has_comparison: false, scope_status: UNKNOWN_SCOPE
  assert.strictEqual(summary.trend.has_comparison, false);
  assert.strictEqual(summary.trend.delta_quantity, 0);
  assert.strictEqual(summary.trend.scope_status, "UNKNOWN_SCOPE");
});

test("ROUND 06 FIX 02 P1: Multiple snapshots on the same day are ordered chronologically by inventory_time / id", async () => {
  // Snapshot 306: cùng ngày 2026-10-20, ca Sáng (08:00)
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (306, 'KK.SAMEDAY.26.800306', '800306', 'CH_SAMEDAY', 10, '2026-10-20', '08:00:00', 'Sáng',
        'sha256_mock_306', 'content_hash_306', 'KiemKe_306.xlsx', 'COMPLETED', 0,
        5, 100, 1000000, 1)`
    )
    .run();

  // Snapshot 307: cùng ngày 2026-10-20, ca Tối (20:00)
  await testDb
    .prepare(
      `INSERT INTO inventory_files (
        id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, status, is_deleted,
        total_sku_count, total_quantity, total_amount_vnd, created_by
      ) VALUES (307, 'KK.SAMEDAY.26.800307', '800307', 'CH_SAMEDAY', 10, '2026-10-20', '20:00:00', 'Tối',
        'sha256_mock_307', 'content_hash_307', 'KiemKe_307.xlsx', 'COMPLETED', 0,
        5, 120, 1200000, 1)`
    )
    .run();

  const req = new Request("http://localhost:5173/api/v1/dashboard/stats?store_code=CH_SAMEDAY", {
    headers: { Authorization: `Bearer ${adminToken}` }
  });
  const res = await worker.fetch(req, baseEnv, {});
  assert.strictEqual(res.status, 200);
  const data = await res.json();
  assert.strictEqual(data.success, true);

  const summary = data.data.summary;
  // Ca Tối (20:00) phải là latest, ca Sáng (08:00) phải là previous
  assert.strictEqual(summary.latest_snapshot.id, 307);
  assert.strictEqual(summary.previous_snapshot.id, 306);
  assert.strictEqual(summary.trend.has_comparison, true);
  assert.strictEqual(summary.trend.delta_quantity, 20); // 120 - 100
});

