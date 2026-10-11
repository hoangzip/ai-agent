/**
 * Service: Nghiệp vụ Quản lý & Đối soát Chứng từ Kiểm kê (Inventory Service)
 * Module: apps/api/src/services/inventoryService.ts (Revision 2 - Fix 01 Data Integrity)
 *
 * Tiêu chuẩn kỹ thuật:
 * 1. Không công bố snapshot trước khi import hoàn chỉnh (R04-P1-01):
 *    - Luôn tạo snapshot với trạng thái STAGING.
 *    - Ghi chi tiết theo lô an toàn, có cơ chế bắt lỗi và rollback/cleanup (đánh dấu FAILED, xóa rác).
 *    - Xác thực lại số lượng dòng và tổng số liệu thực tế từ DB trước khi cho phép COMPLETED.
 * 2. Commit xác thực lại tính toàn vẹn từ DB (R04-P1-02):
 *    - commitSnapshot() truy vấn COUNT, SUM(quantity), SUM(total_amount) từ inventory_items.
 *    - Từ chối duyệt nếu dữ liệu DB bị thiếu dòng hoặc lệch tổng.
 * 3. Chống trùng lặp thông minh (R04-P1-03):
 *    - Trùng file nhị phân (file_sha256) -> ALREADY_IMPORTED.
 *    - Trùng mã chứng từ (full_code) với nội dung khác -> CONFLICT.
 *    - Khác mã chứng từ nhưng cùng dữ liệu tồn kho -> HỢP LỆ (Lưu độc lập bình thường).
 * 4. Quản lý danh sách, chi tiết 15 cột, xóa mềm và nhật ký kiểm toán.
 */

import { ParseResult } from "./excelParser.js";
import { logAuditEvent } from "../security/audit.js";

export interface SnapshotFilter {
  status?: string;
  store_code?: string;
  inventory_date?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
  shift?: string;
  page?: number;
  limit?: number;
}

export class InventoryServiceError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number = 400,
    public details?: any
  ) {
    super(message);
    this.name = "InventoryServiceError";
  }
}

/**
 * Lấy danh sách snapshots kèm bộ lọc và phân trang
 */
export async function listSnapshots(db: any, filter: SnapshotFilter = {}) {
  const page = Math.max(1, filter.page || 1);
  const limit = Math.min(100, Math.max(1, filter.limit || 20));
  const offset = (page - 1) * limit;

  const conditions: string[] = ["is_deleted = 0"];
  const params: any[] = [];

  if (filter.status) {
    conditions.push("status = ?");
    params.push(filter.status);
  }
  if (filter.store_code) {
    conditions.push("store_code = ?");
    params.push(filter.store_code);
  }
  if (filter.shift) {
    conditions.push("shift = ?");
    params.push(filter.shift);
  }
  if (filter.inventory_date) {
    conditions.push("inventory_date = ?");
    params.push(filter.inventory_date);
  }
  if (filter.start_date) {
    conditions.push("inventory_date >= ?");
    params.push(filter.start_date);
  }
  if (filter.end_date) {
    conditions.push("inventory_date <= ?");
    params.push(filter.end_date);
  }
  if (filter.search && filter.search.trim() !== "") {
    const term = `%${filter.search.trim()}%`;
    conditions.push("(full_code LIKE ? OR ticket_number LIKE ? OR store_code LIKE ? OR shift LIKE ? OR inventory_date LIKE ?)");
    params.push(term, term, term, term, term);
  }

  const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";

  // 1. Đếm tổng số bản ghi
  const countRow = await db
    .prepare(`SELECT COUNT(*) as total FROM inventory_files ${whereClause}`)
    .bind(...params)
    .first();
  const total = countRow ? Number(countRow.total) : 0;

  // 2. Lấy danh sách bản ghi phân trang
  const rows = await db
    .prepare(
      `SELECT id, full_code, ticket_number, store_code, inventory_date, inventory_time, shift,
              file_sha256, content_hash, source_filename, source_type, status,
              total_sku_count, total_quantity, total_amount_vnd, created_at, updated_at
       FROM inventory_files
       ${whereClause}
       ORDER BY inventory_date DESC, id DESC
       LIMIT ? OFFSET ?`
    )
    .bind(...params, limit, offset)
    .all();

  return {
    items: rows.results || [],
    pagination: {
      page,
      limit,
      total,
      total_pages: Math.ceil(total / limit)
    }
  };
}

/**
 * Lấy số liệu thống kê tổng quan hệ thống phục vụ Dashboard (Round 06 - Fix 01: Scope Isolation)
 */
export async function getDashboardStats(db: any, storeCode?: string | null) {
  // 0. Lấy danh sách tất cả các mã cửa hàng đang hoạt động trong hệ thống
  const storesRows = (await db
    .prepare(
      `SELECT DISTINCT store_code 
       FROM inventory_files 
       WHERE is_deleted = 0 AND store_code IS NOT NULL AND store_code != '' 
       ORDER BY store_code ASC`
    )
    .all())?.results || [];
  const availableStores: string[] = storesRows.map((r: any) => String(r.store_code));

  const filterStore = storeCode && storeCode.trim() !== "" ? storeCode.trim() : null;

  // 1. Thống kê theo trạng thái (có thể lọc theo cửa hàng nếu được chỉ định)
  let countsQuery = `SELECT 
      COUNT(*) as total,
      SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
      SUM(CASE WHEN status = 'STAGING' THEN 1 ELSE 0 END) as staging,
      SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
      SUM(CASE WHEN status = 'CONFLICT' THEN 1 ELSE 0 END) as conflict
     FROM inventory_files 
     WHERE is_deleted = 0`;
  const countsParams: any[] = [];
  if (filterStore) {
    countsQuery += ` AND store_code = ?`;
    countsParams.push(filterStore);
  }

  const countsRow = await db.prepare(countsQuery).bind(...countsParams).first();

  const total = Number(countsRow?.total || 0);
  const completed = Number(countsRow?.completed || 0);
  const staging = Number(countsRow?.staging || 0);
  const failed = Number(countsRow?.failed || 0);
  const conflict = Number(countsRow?.conflict || 0);

  // 2. Lấy 2 snapshot COMPLETED CÙNG CỬA HÀNG VÀ CÙNG PHẠM VI KHO (P1 Stock Scope Isolation - Round 06 Fix 02)
  // Tuyệt đối không lấy 2 snapshot khác cửa hàng hoặc khác phạm vi kho (scope_id) rồi tính delta chéo gây hiểu lầm.
  // Sắp xếp theo: inventory_date DESC, COALESCE(inventory_time, '') DESC, id DESC.
  let latest: any = null;
  let previous: any = null;

  // Lấy snapshot COMPLETED mới nhất (có thể lọc theo cửa hàng nếu được chỉ định)
  let latestQuery = `SELECT id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
              total_sku_count, total_quantity, total_amount_vnd, status, created_at
       FROM inventory_files
       WHERE is_deleted = 0 AND status = 'COMPLETED'`;
  const latestParams: any[] = [];
  if (filterStore) {
    latestQuery += ` AND store_code = ?`;
    latestParams.push(filterStore);
  }
  latestQuery += ` ORDER BY inventory_date DESC, COALESCE(inventory_time, '') DESC, id DESC LIMIT 1`;

  latest = await db.prepare(latestQuery).bind(...latestParams).first();

  if (latest && latest.store_code) {
    // Tìm snapshot COMPLETED liền trước ĐÚNG CÙNG CỬA HÀNG VÀ CÙNG PHẠM VI KHO với latest
    // Nếu latest.scope_id != null -> previous phải có cùng scope_id
    // Nếu latest.scope_id is null -> previous phải có scope_id is null (toàn cửa hàng)
    let prevQuery = `SELECT id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
              total_sku_count, total_quantity, total_amount_vnd, status, created_at
       FROM inventory_files
       WHERE is_deleted = 0 AND status = 'COMPLETED' AND store_code = ? AND id != ?`;
    const prevParams: any[] = [latest.store_code, latest.id];

    if (latest.scope_id !== null && latest.scope_id !== undefined) {
      prevQuery += ` AND scope_id = ?`;
      prevParams.push(latest.scope_id);
    } else {
      prevQuery += ` AND scope_id IS NULL`;
    }

    prevQuery += ` ORDER BY inventory_date DESC, COALESCE(inventory_time, '') DESC, id DESC LIMIT 1`;
    previous = await db.prepare(prevQuery).bind(...prevParams).first();
  }

  // Đảm bảo nghiêm ngặt: chỉ coi là có đối soát hợp lệ (has_comparison = true) khi:
  // 1. Cả 2 snapshot đều tồn tại
  // 2. Cả 2 snapshot cùng thuộc một store_code
  // 3. Cả 2 snapshot cùng thuộc một phạm vi kho (scope_id giống nhau, hoặc cả hai cùng null là toàn cửa hàng)
  // 4. scope_id không thuộc trạng thái không xác định (ví dụ: -1 hoặc 99 UNKNOWN)
  const isUnknownScope = Boolean(
    (latest && (latest.scope_id === -1 || latest.scope_id === 99)) ||
    (previous && (previous.scope_id === -1 || previous.scope_id === 99))
  );
  const isSameStore = Boolean(latest && previous && latest.store_code === previous.store_code);
  const isSameScope = Boolean(
    latest &&
    previous &&
    !isUnknownScope &&
    (latest.scope_id === previous.scope_id || (latest.scope_id == null && previous.scope_id == null))
  );
  const isValidComparison = Boolean(isSameStore && isSameScope && !isUnknownScope);

  let deltaQuantity = 0;
  let deltaAmountVnd = 0;
  if (isValidComparison && latest && previous) {
    deltaQuantity = Number(latest.total_quantity) - Number(previous.total_quantity);
    deltaAmountVnd = Number(latest.total_amount_vnd) - Number(previous.total_amount_vnd);
  }

  // Xây dựng thông điệp phạm vi bằng tiếng Việt phục vụ UI và kiểm toán
  let scopeStatus = "MATCHED";
  let scopeMessage = "";
  if (!latest) {
    scopeStatus = "NO_DATA";
    scopeMessage = "Chưa có chứng từ kiểm kê hoàn tất nào trong hệ thống.";
  } else if (!previous) {
    scopeStatus = "SINGLE_SNAPSHOT";
    scopeMessage = `Cửa hàng ${latest.store_code} hiện có 1 kỳ kiểm kê hoàn tất (${latest.full_code}). Cần thêm ít nhất một kỳ kiểm kê tiếp theo cùng phạm vi kho để tính biến động.`;
  } else if (!isSameStore) {
    scopeStatus = "DIFFERENT_STORE";
    scopeMessage = `Hai kỳ kiểm kê gần nhất thuộc hai cửa hàng khác nhau (${latest.store_code} vs ${previous.store_code}). Hệ thống không đối soát chéo giữa các cửa hàng.`;
  } else if (isUnknownScope) {
    scopeStatus = "UNKNOWN_SCOPE";
    scopeMessage = `Phạm vi kiểm kê chưa được xác định rõ ràng (${latest.store_code}). Hệ thống không tự ý đối soát biến động khi phạm vi không xác định.`;
  } else if (!isSameScope) {
    scopeStatus = "DIFFERENT_SCOPE";
    scopeMessage = `Hai kỳ kiểm kê thuộc cùng cửa hàng ${latest.store_code} nhưng khác phạm vi kho (${latest.scope_id != null ? `Kho #${latest.scope_id}` : 'Toàn cửa hàng'} vs ${previous.scope_id != null ? `Kho #${previous.scope_id}` : 'Toàn cửa hàng'}). Không đối soát giữa hai phạm vi kho khác nhau.`;
  } else {
    scopeStatus = "MATCHED";
    scopeMessage = `Đối soát hợp lệ giữa 2 kỳ kiểm kê cùng Cửa hàng ${latest.store_code}${latest.scope_id != null ? ` (Kho #${latest.scope_id})` : " (Toàn cửa hàng)"}.`;
  }

  // 3. Lấy 5 snapshot gần nhất cho bảng hoạt động
  let recentQuery = `SELECT id, full_code, ticket_number, store_code, scope_id, inventory_date, inventory_time, shift,
              total_sku_count, total_quantity, total_amount_vnd, status, created_at
       FROM inventory_files
       WHERE is_deleted = 0`;
  const recentParams: any[] = [];
  if (filterStore) {
    recentQuery += ` AND store_code = ?`;
    recentParams.push(filterStore);
  }
  recentQuery += ` ORDER BY inventory_date DESC, COALESCE(inventory_time, '') DESC, id DESC LIMIT 5`;

  const recentSnapshots = (await db.prepare(recentQuery).bind(...recentParams).all())?.results || [];

  return {
    summary: {
      total_snapshots: total,
      completed_snapshots: completed,
      staging_snapshots: staging,
      failed_snapshots: failed,
      conflict_snapshots: conflict,
      available_stores: availableStores,
      selected_store: filterStore,
      scope_store_code: latest?.store_code || filterStore || null,
      scope_id: latest?.scope_id ?? null,
      latest_snapshot: latest,
      previous_snapshot: previous,
      trend: {
        has_comparison: isValidComparison,
        store_code: isValidComparison ? latest.store_code : null,
        scope_id: isValidComparison ? latest.scope_id : null,
        scope_status: scopeStatus,
        scope_message: scopeMessage,
        delta_quantity: isValidComparison ? deltaQuantity : 0,
        delta_amount_vnd: isValidComparison ? deltaAmountVnd : 0,
        base_code: isValidComparison ? previous?.full_code : null,
        target_code: isValidComparison ? latest?.full_code : null
      }
    },
    recent_snapshots: recentSnapshots
  };
}

/**
 * Nhập khẩu một snapshot kiểm kê vào cơ sở dữ liệu với kiểm chứng toàn vẹn hai lớp
 */
export async function importSnapshot(
  db: any,
  parsed: ParseResult,
  options: {
    userId?: number;
    autoCommit?: boolean;
    ipAddress?: string;
    shift?: "Sáng" | "Chiều" | "Tối" | "Khác" | "Chưa xác định";
    inventory_time?: string | null;
    sourceType?: "MANUAL_UPLOAD" | "GDRIVE_SYNC";
    sourceFileId?: string;
    sourceRevision?: string;
  } = {}
) {
  // 1. Kiểm tra tính hợp lệ cơ bản của dữ liệu parse
  if (!parsed.isValid && parsed.errors.length > 0) {
    throw new InventoryServiceError(
      "INVALID_EXCEL_STRUCTURE",
      `File Excel không hợp lệ: ${parsed.errors.join("; ")}`,
      422,
      { errors: parsed.errors }
    );
  }

  // 2. Chống trùng lặp & Định danh Nghiệp vụ (Fix 02):
  // Định danh duy nhất của một sự kiện kiểm kê là Mã Chứng từ (full_code) trong phạm vi cửa hàng.
  // Tuyệt đối không dùng hash nhị phân (file_sha256) hay content_hash làm định danh toàn cục,
  // vì hai lần kiểm kê khác nhau (khác full_code) hoàn toàn có thể có tồn kho/nội dung file giống hệt nhau!
  const existingSnapshot = (await db
    .prepare(
      `SELECT id, full_code, ticket_number, store_code, file_sha256, content_hash, status, is_deleted, deleted_at, source_filename 
       FROM inventory_files 
       WHERE full_code = ?`
    )
    .bind(parsed.metadata.full_code)
    .first()) as {
    id: number;
    full_code: string;
    ticket_number: string;
    store_code: string;
    file_sha256: string;
    content_hash: string;
    status: string;
    is_deleted: number;
    deleted_at: string | null;
    source_filename: string;
  } | null;

  if (existingSnapshot) {
    // Trường hợp 1: Snapshot đã bị xóa mềm trước đó (is_deleted = 1)
    // Quy định Fix 02: Trả mã lỗi SNAPSHOT_SOFT_DELETED rõ ràng kèm gợi ý khôi phục,
    // ngăn chặn lỗi vi phạm ràng buộc UNIQUE của SQLite D1.
    if (existingSnapshot.is_deleted === 1) {
      throw new InventoryServiceError(
        "SNAPSHOT_SOFT_DELETED",
        `Chứng từ kiểm kê '${parsed.metadata.full_code}' đã tồn tại trong hệ thống nhưng đang ở trạng thái đã xóa mềm (thời điểm xóa: ${existingSnapshot.deleted_at || "trước đó"}). Vui lòng khôi phục snapshot từ thùng rác hoặc liên hệ Quản trị viên thay vì nạp mới.`,
        409,
        { existingSnapshot }
      );
    }

    // Trường hợp 2: Lần nạp trước bị FAILED -> Cho phép nạp lại (idempotent / retry an toàn)
    if (existingSnapshot.status === "FAILED") {
      await db.prepare("DELETE FROM inventory_items WHERE file_id = ?").bind(existingSnapshot.id).run();
      await db.prepare("DELETE FROM inventory_files WHERE id = ?").bind(existingSnapshot.id).run();
    } else {
      // Trường hợp 3: Snapshot đang active (STAGING hoặc COMPLETED)
      // Kiểm tra xem dữ liệu có trùng khớp hay không (trùng file nhị phân hoặc trùng băm nội dung chuẩn hóa)
      const isSameData =
        existingSnapshot.file_sha256 === parsed.file_sha256 ||
        existingSnapshot.content_hash === parsed.content_hash;

      if (isSameData) {
        // Cùng mã + cùng dữ liệu/binary -> ALREADY_IMPORTED (409)
        throw new InventoryServiceError(
          "ALREADY_IMPORTED",
          `Chứng từ kiểm kê '${parsed.metadata.full_code}' đã tồn tại trong hệ thống với nội dung tương đồng (${existingSnapshot.status}). Không cần tải lại.`,
          409,
          { existingSnapshot }
        );
      } else {
        // Cùng mã + dữ liệu khác nhau -> CONFLICT (409)
        throw new InventoryServiceError(
          "CONFLICT",
          `Mã chứng từ '${parsed.metadata.full_code}' đã tồn tại trong hệ thống nhưng nội dung dữ liệu khác nhau. Xung đột dữ liệu snapshot.`,
          409,
          { existingSnapshot }
        );
      }
    }
  }

  // Trường hợp 4: Khác mã full_code nhưng cùng binary (file_sha256) hoặc cùng content_hash:
  // Đây là trường hợp nghiệp vụ hợp lệ (ví dụ: kiểm kê ca khác nhau nhưng tồn kho không đổi, hoặc xuất file cùng thời điểm).
  // Hệ thống lưu độc lập snapshot mới mà KHÔNG chặn.

  // 4. Tạo header inventory_files - LUÔN LUÔN BẮT ĐẦU VỚI 'STAGING' ĐỂ BẢO VỆ TOÀN VẸN (R04-P1-01)
  const shiftVal = options.shift || parsed.metadata.shift || "Chưa xác định";
  const timeVal = options.inventory_time !== undefined ? options.inventory_time : (parsed.metadata.inventory_time ?? null);
  const sourceType = options.sourceType || "MANUAL_UPLOAD";
  const sourceFileId = options.sourceFileId ?? null;
  const sourceRevision = options.sourceRevision ?? null;

  const insertFileStmt = db
    .prepare(
      `INSERT INTO inventory_files (
        full_code, ticket_number, store_code, inventory_date, inventory_time, shift,
        file_sha256, content_hash, source_filename, source_type, source_file_id, source_revision,
        status, total_sku_count, total_quantity, total_amount_vnd,
        created_by, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'STAGING', ?, ?, ?, ?, datetime('now', 'utc'), datetime('now', 'utc'))`
    )
    .bind(
      parsed.metadata.full_code,
      parsed.metadata.ticket_number,
      parsed.metadata.store_code,
      parsed.metadata.inventory_date,
      timeVal ?? null,
      shiftVal,
      parsed.file_sha256,
      parsed.content_hash,
      parsed.metadata.source_filename,
      sourceType,
      sourceFileId,
      sourceRevision,
      parsed.total_sku_count,
      parsed.summary.calculated_quantity,
      parsed.summary.calculated_total_amount,
      options.userId ?? null
    );

  const fileResult = await insertFileStmt.run();
  const fileId = fileResult.meta?.last_row_id;
  if (!fileId) {
    throw new InventoryServiceError(
      "INSERT_FAILED",
      "Không thể lưu thông tin chứng từ vào cơ sở dữ liệu.",
      500
    );
  }

  // 5. Ghi chi tiết mặt hàng theo lô vào inventory_items kèm cơ chế bắt lỗi an toàn (R04-P1-01)
  const batchSize = 50;
  try {
    for (let i = 0; i < parsed.items.length; i += batchSize) {
      const batch = parsed.items.slice(i, i + batchSize);
      const itemStmts = batch.map((item) =>
        db
          .prepare(
            `INSERT INTO inventory_items (
              file_id, row_index, stt, category, product_code, product_name,
              quantity, warehouse, unit_price, total_amount,
              audit_package_qty, audit_loose_qty, audit_total_qty_formula,
              discrepancy_formula, package_unit, conversion_rate, loose_unit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
          )
          .bind(
            fileId,
            item.row_index,
            item.stt,
            item.category,
            item.product_code,
            item.product_name,
            item.quantity,
            item.warehouse,
            item.unit_price,
            item.total_amount,
            item.audit_package_qty,
            item.audit_loose_qty,
            item.audit_total_qty_formula,
            item.discrepancy_formula,
            item.package_unit,
            item.conversion_rate,
            item.loose_unit
          )
      );

      if (itemStmts.length > 0) {
        await db.batch(itemStmts);
      }
    }

    // Cập nhật bảng Danh mục sản phẩm (product_catalog)
    for (let i = 0; i < parsed.items.length; i += batchSize) {
      const batch = parsed.items.slice(i, i + batchSize);
      const catalogStmts = batch.map((item) =>
        db
          .prepare(
            `INSERT OR IGNORE INTO product_catalog (
              product_code, product_name, category, package_unit, conversion_rate, loose_unit
            ) VALUES (?, ?, ?, ?, ?, ?)`
          )
          .bind(
            item.product_code,
            item.product_name,
            item.category,
            item.package_unit,
            item.conversion_rate,
            item.loose_unit
          )
      );

      if (catalogStmts.length > 0) {
        await db.batch(catalogStmts);
      }
    }
  } catch (batchError: any) {
    // FAIL-SAFE CLEANUP: Nếu xảy ra lỗi khi ghi chi tiết, lập tức xóa các dòng rác và đánh dấu FAILED
    try {
      await db.prepare("DELETE FROM inventory_items WHERE file_id = ?").bind(fileId).run();
      await db.prepare("UPDATE inventory_files SET status = 'FAILED' WHERE id = ?").bind(fileId).run();
    } catch (cleanupErr) {
      console.error("[IMPORT_CLEANUP_ERROR]:", cleanupErr);
    }

    throw new InventoryServiceError(
      "ITEM_INSERT_FAILED",
      `Lỗi trong quá trình ghi dữ liệu chi tiết vào cơ sở dữ liệu: ${batchError.message || String(batchError)}. Snapshot được chuyển sang trạng thái FAILED.`,
      500,
      { fileId, originalError: batchError.message }
    );
  }

  // 6. XÁC MINH TOÀN VẸN TRỰC TIẾP TỪ CƠ SỞ DỮ LIỆU (R04-P1-01)
  const dbStats = await db
    .prepare(
      `SELECT COUNT(*) as item_count,
              COALESCE(SUM(quantity), 0) as total_qty,
              COALESCE(SUM(total_amount), 0) as total_amt
       FROM inventory_items
       WHERE file_id = ?`
    )
    .bind(fileId)
    .first();

  const actualCount = Number(dbStats?.item_count || 0);
  const actualQty = Number(dbStats?.total_qty || 0);
  const actualAmt = Math.round(Number(dbStats?.total_amt || 0));

  const isCountValid = actualCount === parsed.total_sku_count;
  const isQtyValid = Math.abs(actualQty - parsed.summary.calculated_quantity) < 0.001;
  const isAmtValid = Math.abs(actualAmt - parsed.summary.calculated_total_amount) <= 1;

  if (!isCountValid || !isQtyValid || !isAmtValid) {
    // Nếu kiểm tra số liệu DB thực tế không khớp -> Thu hồi, xóa items và đánh dấu FAILED
    await db.prepare("DELETE FROM inventory_items WHERE file_id = ?").bind(fileId).run();
    await db.prepare("UPDATE inventory_files SET status = 'FAILED' WHERE id = ?").bind(fileId).run();

    throw new InventoryServiceError(
      "DB_INTEGRITY_VERIFICATION_FAILED",
      `Dữ liệu lưu vào cơ sở dữ liệu không khớp với tính toán ban đầu ` +
      `(Thực tế: ${actualCount} dòng, ${actualQty} SL, ${actualAmt} VND; ` +
      `Kỳ vọng: ${parsed.total_sku_count} dòng, ${parsed.summary.calculated_quantity} SL, ${parsed.summary.calculated_total_amount} VND). Snapshot đã bị đánh dấu FAILED.`,
      500
    );
  }

  // 7. CHỈ ĐẶT 'COMPLETED' SAU KHI ĐÃ ĐỐI SOÁT VÀ XÁC MINH 100% THÀNH CÔNG (R04-P1-01)
  let finalStatus: "STAGING" | "COMPLETED" = "STAGING";
  if (options.autoCommit && parsed.summary.is_math_matched) {
    await db
      .prepare(
        `UPDATE inventory_files
         SET status = 'COMPLETED', updated_at = datetime('now', 'utc')
         WHERE id = ?`
      )
      .bind(fileId)
      .run();
    finalStatus = "COMPLETED";
  }

  // 8. Ghi nhật ký kiểm toán
  if (options.userId) {
    await logAuditEvent(db, {
      userId: options.userId,
      action: "IMPORT_INVENTORY_EXCEL",
      targetType: "INVENTORY_FILE",
      targetId: String(fileId),
      details: {
        full_code: parsed.metadata.full_code,
        ticket_number: parsed.metadata.ticket_number,
        total_sku_count: parsed.total_sku_count,
        total_quantity: parsed.summary.calculated_quantity,
        total_amount: parsed.summary.calculated_total_amount,
        status: finalStatus,
        source_filename: parsed.metadata.source_filename,
        autoCommit: Boolean(options.autoCommit)
      },
      ipAddress: options.ipAddress
    });
  }

  // 9. Trả về thông tin snapshot
  return {
    id: fileId,
    full_code: parsed.metadata.full_code,
    ticket_number: parsed.metadata.ticket_number,
    store_code: parsed.metadata.store_code,
    inventory_date: parsed.metadata.inventory_date,
    inventory_time: timeVal,
    shift: shiftVal,
    status: finalStatus,
    total_sku_count: parsed.total_sku_count,
    total_quantity: parsed.summary.calculated_quantity,
    total_amount_vnd: parsed.summary.calculated_total_amount,
    file_sha256: parsed.file_sha256,
    content_hash: parsed.content_hash,
    source_filename: parsed.metadata.source_filename,
    summary: parsed.summary
  };
}



/**
 * Lấy chi tiết một snapshot và danh sách sản phẩm
 */
export async function getSnapshotById(
  db: any,
  id: number,
  includeItems: boolean = true
) {
  const snapshot = await db
    .prepare(
      `SELECT id, full_code, ticket_number, store_code, inventory_date, inventory_time, shift,
              file_sha256, content_hash, source_filename, source_type, status,
              total_sku_count, total_quantity, total_amount_vnd, is_deleted, created_at, updated_at
       FROM inventory_files
       WHERE id = ? AND is_deleted = 0`
    )
    .bind(id)
    .first();

  if (!snapshot) {
    throw new InventoryServiceError(
      "SNAPSHOT_NOT_FOUND",
      `Không tìm thấy chứng từ kiểm kê có ID = ${id}.`,
      404
    );
  }

  let items: any[] = [];
  if (includeItems) {
    const itemsResult = await db
      .prepare(
        `SELECT id, row_index, stt, category, product_code, product_name,
                quantity, warehouse, unit_price, total_amount,
                audit_package_qty, audit_loose_qty, audit_total_qty_formula,
                discrepancy_formula, package_unit, conversion_rate, loose_unit
         FROM inventory_items
         WHERE file_id = ?
         ORDER BY row_index ASC`
      )
      .bind(id)
      .all();
    items = itemsResult.results || [];
  }

  return {
    snapshot,
    items
  };
}

/**
 * Duyệt snapshot: Chuyển trạng thái từ STAGING sang COMPLETED
 * ĐẢM BẢO XÁC THỰC LẠI TOÀN VẸN SỐ DÒNG VÀ TỔNG SỐ TỪ DB (R04-P1-02)
 */
export async function commitSnapshot(
  db: any,
  id: number,
  options: { userId?: number; ipAddress?: string } = {}
) {
  const snapshot = await db
    .prepare(
      `SELECT id, full_code, status, total_sku_count, total_quantity, total_amount_vnd
       FROM inventory_files
       WHERE id = ? AND is_deleted = 0`
    )
    .bind(id)
    .first();

  if (!snapshot) {
    throw new InventoryServiceError(
      "SNAPSHOT_NOT_FOUND",
      `Không tìm thấy chứng từ kiểm kê có ID = ${id}.`,
      404
    );
  }

  if (snapshot.status === "COMPLETED") {
    return {
      message: "Chứng từ kiểm kê này đã được duyệt trước đó.",
      snapshot
    };
  }

  if (snapshot.status === "CONFLICT" || snapshot.status === "FAILED") {
    throw new InventoryServiceError(
      "CANNOT_COMMIT_FAILED_SNAPSHOT",
      `Không thể duyệt chứng từ đang ở trạng thái ${snapshot.status}.`,
      400
    );
  }

  // KIỂM TRA ĐỐI SOÁT LẠI DỮ LIỆU TỪ BẢNG CHI TIẾT (R04-P1-02)
  const itemsStats = await db
    .prepare(
      `SELECT COUNT(*) as item_count,
              COALESCE(SUM(quantity), 0) as sum_quantity,
              COALESCE(SUM(total_amount), 0) as sum_amount
       FROM inventory_items
       WHERE file_id = ?`
    )
    .bind(id)
    .first();

  const actualItemCount = Number(itemsStats?.item_count || 0);
  const actualSumQty = Number(itemsStats?.sum_quantity || 0);
  const actualSumAmt = Math.round(Number(itemsStats?.sum_amount || 0));

  if (actualItemCount === 0) {
    throw new InventoryServiceError(
      "EMPTY_SNAPSHOT_ITEMS",
      `Không thể duyệt chứng từ không có bất kỳ dòng mặt hàng nào trong cơ sở dữ liệu.`,
      422,
      { fileId: id }
    );
  }

  if (actualItemCount !== snapshot.total_sku_count) {
    throw new InventoryServiceError(
      "ITEM_COUNT_MISMATCH",
      `Không thể duyệt chứng từ: Số dòng mặt hàng trong cơ sở dữ liệu (${actualItemCount}) không khớp với tóm tắt chứng từ (${snapshot.total_sku_count}). Dữ liệu có thể chưa được nạp đầy đủ.`,
      422,
      { fileId: id, actualItemCount, expectedCount: snapshot.total_sku_count }
    );
  }

  if (
    Math.abs(actualSumQty - snapshot.total_quantity) > 0.001 ||
    Math.abs(actualSumAmt - snapshot.total_amount_vnd) > 1
  ) {
    throw new InventoryServiceError(
      "TOTALS_MISMATCH",
      `Không thể duyệt chứng từ: Tổng số lượng hoặc thành tiền trong cơ sở dữ liệu không khớp với thông tin chứng từ (DB SL: ${actualSumQty}, Kỳ vọng: ${snapshot.total_quantity}; DB Tiền: ${actualSumAmt}, Kỳ vọng: ${snapshot.total_amount_vnd}).`,
      422,
      {
        fileId: id,
        actualSumQty,
        expectedQty: snapshot.total_quantity,
        actualSumAmt,
        expectedAmt: snapshot.total_amount_vnd
      }
    );
  }

  // Cập nhật trạng thái thành COMPLETED
  await db
    .prepare(
      `UPDATE inventory_files
       SET status = 'COMPLETED', updated_at = datetime('now', 'utc')
       WHERE id = ?`
    )
    .bind(id)
    .run();

  // Ghi nhật ký kiểm toán
  if (options.userId) {
    await logAuditEvent(db, {
      userId: options.userId,
      action: "COMMIT_INVENTORY_SNAPSHOT",
      targetType: "INVENTORY_FILE",
      targetId: String(id),
      details: {
        full_code: snapshot.full_code,
        previous_status: snapshot.status,
        new_status: "COMPLETED",
        verified_item_count: actualItemCount,
        verified_quantity: actualSumQty,
        verified_amount: actualSumAmt
      },
      ipAddress: options.ipAddress
    });
  }

  return {
    message: "Duyệt chứng từ kiểm kê thành công.",
    snapshot: {
      ...snapshot,
      status: "COMPLETED"
    }
  };
}

/**
 * Xóa mềm chứng từ kiểm kê
 */
export async function softDeleteSnapshot(
  db: any,
  id: number,
  options: { userId?: number; ipAddress?: string } = {}
) {
  const snapshot = await db
    .prepare(
      `SELECT id, full_code, status FROM inventory_files WHERE id = ? AND is_deleted = 0`
    )
    .bind(id)
    .first();

  if (!snapshot) {
    throw new InventoryServiceError(
      "SNAPSHOT_NOT_FOUND",
      `Không tìm thấy chứng từ kiểm kê có ID = ${id}.`,
      404
    );
  }

  await db
    .prepare(
      `UPDATE inventory_files
       SET is_deleted = 1, deleted_at = datetime('now', 'utc'), deleted_by = ?
       WHERE id = ?`
    )
    .bind(options.userId || null, id)
    .run();

  if (options.userId) {
    await logAuditEvent(db, {
      userId: options.userId,
      action: "DELETE_INVENTORY_SNAPSHOT",
      targetType: "INVENTORY_FILE",
      targetId: String(id),
      details: { full_code: snapshot.full_code },
      ipAddress: options.ipAddress
    });
  }

  return {
    message: "Đã xóa chứng từ kiểm kê thành công.",
    id
  };
}
