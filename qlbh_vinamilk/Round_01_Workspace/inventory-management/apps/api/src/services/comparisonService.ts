/**
 * Service: Động cơ Đối soát & So sánh Tồn kho (Stock Comparison Engine)
 * Module: apps/api/src/services/comparisonService.ts (Round 05 Fix 01)
 *
 * Tiêu chuẩn & Quy tắc Nghiệp vụ Bắt buộc:
 * 1. Chỉ so sánh snapshot có trạng thái COMPLETED (cả A và B).
 *    Từ chối STAGING, FAILED, CONFLICT với mã lỗi 422 SNAPSHOT_NOT_COMPLETED.
 * 2. Biến động tồn kho giữa 2 snapshot:
 *    delta_quantity = B.quantity - A.quantity
 *    delta_amount = B.total_amount - A.total_amount
 *    TUYỆT ĐỐI KHÔNG dùng cột CHÊNH LỆCH có sẵn trong file Excel.
 * 3. Phân biệt rõ ràng:
 *    - NOT_PRESENT (Không xuất hiện ở B): Có ở A nhưng không có dòng nào ở B -> target_quantity = null, delta = null.
 *    - OUT_OF_STOCK (Hết tồn): Có dòng ở B và B.quantity = 0 (từ số dương giảm về 0) -> target_quantity = 0.
 *    - NEW_ADDED (Mới xuất hiện ở B): Chỉ có ở B, không có ở A.
 *    - INCREASED, DECREASED, NO_CHANGE.
 * 4. Phạm vi & Khóa tự nhiên:
 *    - So sánh giữa 2 snapshot khác cửa hàng tạo scope_warning rõ ràng.
 *    - Chuỗi lịch sử SKU tách delta theo (store_code, warehouse), không trừ chéo phạm vi.
 * 5. Xuất CSV:
 *    - Không giới hạn ở 1.000 dòng (fetchAll = true).
 *    - Chống tấn công Formula Injection (chèn ' trước =, +, -, @ trên các trường text).
 *    - Giữ UTF-8 BOM (\uFEFF) cho Excel tiếng Việt.
 */

import {
  ComparisonItem,
  ComparisonResponse,
  ComparisonStatus,
  ProductHistoryResponse,
  ProductHistoryPoint
} from "@inventory/shared";

export interface ComparisonFilterOptions {
  status?: ComparisonStatus | "ALL";
  category?: string;
  warehouse?: string;
  search?: string;
  page?: number;
  limit?: number;
  fetchAll?: boolean;
}

export class ComparisonServiceError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number = 400,
    public details?: any
  ) {
    super(message);
    this.name = "ComparisonServiceError";
  }
}

interface RawDbItem {
  id: number;
  file_id: number;
  row_index: number;
  stt: number;
  category: string;
  product_code: string;
  product_name: string;
  quantity: number;
  warehouse: string;
  unit_price: number;
  total_amount: number;
  package_unit: string | null;
  conversion_rate: number;
  loose_unit: string | null;
}

interface RawDbFile {
  id: number;
  full_code: string;
  ticket_number: string;
  store_code: string;
  inventory_date: string;
  inventory_time: string | null;
  shift: string;
  total_sku_count: number;
  total_quantity: number;
  total_amount_vnd: number;
  status: string;
  is_deleted: number;
}

/**
 * Khử mã độc công thức Spreadsheet (CSV Formula Injection Defense)
 * Vô hiệu hóa các ô văn bản bắt đầu bằng =, +, -, @ hoặc khoảng trắng/tab phía trước
 */
export function sanitizeCsvText(val: any): string {
  if (val === null || val === undefined) return '""';
  let str = String(val);
  if (/^\s*[=+\-@\t\r]/.test(str)) {
    str = "'" + str;
  }
  return `"${str.replace(/"/g, '""')}"`;
}

/**
 * Định dạng giá trị số cho CSV an toàn (không bị chèn nhầm dấu nháy vào số âm)
 */
export function formatCsvNumber(val: any): string {
  if (val === null || val === undefined) return '""';
  if (typeof val === "number") {
    return Number.isFinite(val) ? String(val) : '""';
  }
  const n = Number(val);
  return isNaN(n) ? '""' : String(n);
}

/**
 * So sánh 2 snapshot bất kỳ
 */
export async function compareSnapshots(
  db: any,
  baseSnapshotId: number,
  targetSnapshotId: number,
  options: ComparisonFilterOptions = {}
): Promise<ComparisonResponse> {
  // 1. Kiểm tra sự tồn tại và trạng thái COMPLETED của Snapshot cơ sở (A)
  const baseHeader = (await db
    .prepare("SELECT * FROM inventory_files WHERE id = ? AND is_deleted = 0")
    .bind(baseSnapshotId)
    .first()) as RawDbFile | null;

  if (!baseHeader) {
    throw new ComparisonServiceError(
      "BASE_SNAPSHOT_NOT_FOUND",
      `Không tìm thấy Snapshot cơ sở (ID: ${baseSnapshotId}) hoặc snapshot đã bị xóa.`,
      404
    );
  }

  if (baseHeader.status !== "COMPLETED") {
    throw new ComparisonServiceError(
      "SNAPSHOT_NOT_COMPLETED",
      `Snapshot cơ sở '${baseHeader.full_code}' đang ở trạng thái '${baseHeader.status}'. Chỉ các snapshot có trạng thái 'COMPLETED' mới được phép tham gia so sánh đối soát.`,
      422,
      { snapshot_id: baseSnapshotId, status: baseHeader.status, full_code: baseHeader.full_code }
    );
  }

  // 2. Kiểm tra sự tồn tại và trạng thái COMPLETED của Snapshot đối soát (B)
  const targetHeader = (await db
    .prepare("SELECT * FROM inventory_files WHERE id = ? AND is_deleted = 0")
    .bind(targetSnapshotId)
    .first()) as RawDbFile | null;

  if (!targetHeader) {
    throw new ComparisonServiceError(
      "TARGET_SNAPSHOT_NOT_FOUND",
      `Không tìm thấy Snapshot đối soát (ID: ${targetSnapshotId}) hoặc snapshot đã bị xóa.`,
      404
    );
  }

  if (targetHeader.status !== "COMPLETED") {
    throw new ComparisonServiceError(
      "SNAPSHOT_NOT_COMPLETED",
      `Snapshot đối soát '${targetHeader.full_code}' đang ở trạng thái '${targetHeader.status}'. Chỉ các snapshot có trạng thái 'COMPLETED' mới được phép tham gia so sánh đối soát.`,
      422,
      { snapshot_id: targetSnapshotId, status: targetHeader.status, full_code: targetHeader.full_code }
    );
  }

  // 3. Cảnh báo phạm vi nếu 2 snapshot thuộc 2 cửa hàng khác nhau
  let scope_warning: string | null = null;
  if (baseHeader.store_code && targetHeader.store_code && baseHeader.store_code !== targetHeader.store_code) {
    scope_warning = `Cảnh báo phạm vi đối soát: Snapshot cơ sở thuộc cửa hàng '${baseHeader.store_code}', trong khi snapshot đối soát thuộc cửa hàng '${targetHeader.store_code}'. Hai chứng từ này thuộc hai điểm bán khác nhau, các chênh lệch số lượng phản ánh khác biệt cửa hàng chứ không phải biến động của cùng một kho.`;
  }

  // 4. Tải toàn bộ chi tiết sản phẩm của cả 2 snapshot
  const baseItemsQuery = await db
    .prepare(
      `SELECT * FROM inventory_items 
       WHERE file_id = ? 
       ORDER BY row_index ASC`
    )
    .bind(baseSnapshotId)
    .all();
  const baseItems: RawDbItem[] = (baseItemsQuery.results || []) as RawDbItem[];

  const targetItemsQuery = await db
    .prepare(
      `SELECT * FROM inventory_items 
       WHERE file_id = ? 
       ORDER BY row_index ASC`
    )
    .bind(targetSnapshotId)
    .all();
  const targetItems: RawDbItem[] = (targetItemsQuery.results || []) as RawDbItem[];

  // 5. Xây dựng bản đồ (Map) theo Khóa tự nhiên: product_code + '__' + warehouse
  const makeKey = (code: string, wh: string) => `${code.trim()}__${wh.trim()}`;

  const baseMap = new Map<string, RawDbItem>();
  for (const item of baseItems) {
    baseMap.set(makeKey(item.product_code, item.warehouse), item);
  }

  const targetMap = new Map<string, RawDbItem>();
  for (const item of targetItems) {
    targetMap.set(makeKey(item.product_code, item.warehouse), item);
  }

  // 6. Lấy tập hợp hợp nhất (Union) tất cả các khóa tự nhiên
  const allKeys = new Set<string>([...baseMap.keys(), ...targetMap.keys()]);

  const sortedKeys = Array.from(allKeys).sort((a, b) => {
    const [codeA, whA] = a.split("__");
    const [codeB, whB] = b.split("__");
    const cmpCode = codeA.localeCompare(codeB);
    return cmpCode !== 0 ? cmpCode : whA.localeCompare(whB);
  });

  // 7. Tính toán đối soát từng mặt hàng
  let matchedCount = 0;
  let increasedCount = 0;
  let decreasedCount = 0;
  let unchangedCount = 0;
  let newCount = 0;
  let outOfStockCount = 0;
  let notPresentCount = 0;
  let priceChangedCount = 0;

  const comparedList: ComparisonItem[] = [];

  for (const key of sortedKeys) {
    const itemA = baseMap.get(key);
    const itemB = targetMap.get(key);

    const refItem = itemB || itemA!;
    const product_code = refItem.product_code;
    const product_name = refItem.product_name;
    const category = refItem.category;
    const warehouse = refItem.warehouse;
    const package_unit = refItem.package_unit ?? null;
    const loose_unit = refItem.loose_unit ?? null;
    const conversion_rate = refItem.conversion_rate || 1.0;

    let base_quantity: number | null = itemA ? itemA.quantity : null;
    let target_quantity: number | null = itemB ? itemB.quantity : null;

    let delta_quantity: number | null = null;
    let delta_amount: number | null = null;
    let percentage_change: number | null = null;

    const base_unit_price = itemA ? itemA.unit_price : 0;
    const target_unit_price = itemB ? itemB.unit_price : 0;
    const price_diff = target_unit_price - base_unit_price;

    const base_total_amount = itemA ? itemA.total_amount : 0;
    const target_total_amount = itemB ? itemB.total_amount : 0;

    let status: ComparisonStatus;
    let status_label_vi: string;

    if (!itemA && itemB) {
      // Trường hợp 1: Chỉ có ở B, không có ở A -> Mới xuất hiện
      status = "NEW_ADDED";
      status_label_vi = "Mới xuất hiện ở kỳ B";
      base_quantity = null;
      target_quantity = itemB.quantity;
      delta_quantity = itemB.quantity;
      delta_amount = itemB.total_amount;
      percentage_change = null;
      newCount++;
    } else if (itemA && !itemB) {
      // Trường hợp 2: Có ở A nhưng hoàn toàn vắng mặt ở B (không có dòng nào)
      // TUYỆT ĐỐI KHÔNG khẳng định target_quantity = 0 hoặc Hết tồn!
      status = "NOT_PRESENT";
      status_label_vi = "Không xuất hiện ở kỳ B";
      base_quantity = itemA.quantity;
      target_quantity = null;
      delta_quantity = null;
      delta_amount = null;
      percentage_change = null;
      notPresentCount++;
    } else {
      // Trường hợp 3: Cả A và B đều có dòng dữ liệu (matched)
      matchedCount++;
      base_quantity = itemA!.quantity;
      target_quantity = itemB!.quantity;

      // QUY TẮC BẮT BUỘC: delta_quantity = B.quantity - A.quantity
      delta_quantity = Math.round((target_quantity - base_quantity) * 1000) / 1000;
      delta_amount = target_total_amount - base_total_amount;

      if (base_quantity > 0) {
        percentage_change = Math.round(((target_quantity - base_quantity) / base_quantity) * 10000) / 100;
      }

      if (itemA!.unit_price !== itemB!.unit_price) {
        priceChangedCount++;
      }

      if (delta_quantity > 0) {
        status = "INCREASED";
        status_label_vi = "Tăng tồn";
        increasedCount++;
      } else if (delta_quantity < 0) {
        decreasedCount++;
        if (target_quantity === 0) {
          // B có dòng và số lượng bằng 0 (từ có tồn giảm về 0)
          status = "OUT_OF_STOCK";
          status_label_vi = "Hết tồn (SL = 0)";
          outOfStockCount++;
        } else {
          status = "DECREASED";
          status_label_vi = "Giảm tồn";
        }
      } else {
        status = "NO_CHANGE";
        status_label_vi = "Không đổi";
        unchangedCount++;
      }
    }

    comparedList.push({
      product_code,
      product_name,
      category,
      warehouse,
      package_unit,
      loose_unit,
      conversion_rate,
      base_quantity,
      target_quantity,
      delta_quantity,
      percentage_change,
      base_unit_price,
      target_unit_price,
      price_diff,
      base_total_amount,
      target_total_amount,
      delta_amount,
      status,
      status_label_vi
    });
  }

  // 8. Xây dựng Top biến động (Rankings)
  const top_increased = [...comparedList]
    .filter((it) => it.delta_quantity !== null && it.delta_quantity > 0)
    .sort((a, b) => (b.delta_quantity || 0) - (a.delta_quantity || 0))
    .slice(0, 5);

  const top_decreased = [...comparedList]
    .filter((it) => it.delta_quantity !== null && it.delta_quantity < 0)
    .sort((a, b) => (a.delta_quantity || 0) - (b.delta_quantity || 0)) // âm nhiều nhất lên đầu
    .slice(0, 5);

  const top_value_increased = [...comparedList]
    .filter((it) => it.delta_amount !== null && it.delta_amount > 0)
    .sort((a, b) => (b.delta_amount || 0) - (a.delta_amount || 0))
    .slice(0, 5);

  const top_value_decreased = [...comparedList]
    .filter((it) => it.delta_amount !== null && it.delta_amount < 0)
    .sort((a, b) => (a.delta_amount || 0) - (b.delta_amount || 0))
    .slice(0, 5);

  // 9. Tổng hợp số liệu tổng quan (Summary)
  const delta_quantity_total =
    Math.round((targetHeader.total_quantity - baseHeader.total_quantity) * 1000) / 1000;
  const delta_amount_total = targetHeader.total_amount_vnd - baseHeader.total_amount_vnd;

  const summary = {
    base_snapshot: {
      id: baseHeader.id,
      full_code: baseHeader.full_code,
      ticket_number: baseHeader.ticket_number,
      store_code: baseHeader.store_code,
      inventory_date: baseHeader.inventory_date,
      shift: baseHeader.shift,
      total_sku_count: baseHeader.total_sku_count,
      total_quantity: baseHeader.total_quantity,
      total_amount_vnd: baseHeader.total_amount_vnd
    },
    target_snapshot: {
      id: targetHeader.id,
      full_code: targetHeader.full_code,
      ticket_number: targetHeader.ticket_number,
      store_code: targetHeader.store_code,
      inventory_date: targetHeader.inventory_date,
      shift: targetHeader.shift,
      total_sku_count: targetHeader.total_sku_count,
      total_quantity: targetHeader.total_quantity,
      total_amount_vnd: targetHeader.total_amount_vnd
    },
    total_sku_base: baseHeader.total_sku_count,
    total_sku_target: targetHeader.total_sku_count,
    total_sku_union: comparedList.length,
    matched_count: matchedCount,
    increased_count: increasedCount,
    decreased_count: decreasedCount,
    unchanged_count: unchangedCount,
    new_count: newCount,
    out_of_stock_count: outOfStockCount,
    not_present_count: notPresentCount,
    price_changed_count: priceChangedCount,
    base_total_quantity: baseHeader.total_quantity,
    target_total_quantity: targetHeader.total_quantity,
    delta_quantity: delta_quantity_total,
    base_total_amount: baseHeader.total_amount_vnd,
    target_total_amount: targetHeader.total_amount_vnd,
    delta_amount: delta_amount_total,
    scope_warning,
    top_increased,
    top_decreased,
    top_value_increased,
    top_value_decreased
  };

  // 10. Áp dụng bộ lọc cho danh sách chi tiết (Filtering)
  let filteredItems = comparedList;

  if (options.status && options.status !== "ALL") {
    if (options.status === "DECREASED") {
      filteredItems = filteredItems.filter((it) => it.status === "DECREASED" || it.status === "OUT_OF_STOCK");
    } else {
      filteredItems = filteredItems.filter((it) => it.status === options.status);
    }
  }

  if (options.category) {
    filteredItems = filteredItems.filter((it) => it.category === options.category);
  }

  if (options.warehouse) {
    filteredItems = filteredItems.filter((it) => it.warehouse === options.warehouse);
  }

  if (options.search) {
    const q = options.search.trim().toLowerCase();
    filteredItems = filteredItems.filter(
      (it) => it.product_code.toLowerCase().includes(q) || it.product_name.toLowerCase().includes(q)
    );
  }

  // 11. Phân trang (Pagination) - Hỗ trợ fetchAll = true không bị cắt dòng
  const total = filteredItems.length;
  let page = Math.max(1, options.page || 1);
  let limit = Math.max(1, Math.min(1000, options.limit || 50));
  let total_pages = Math.ceil(total / limit) || 1;
  let paginatedItems: ComparisonItem[];

  if (options.fetchAll) {
    page = 1;
    limit = total;
    total_pages = 1;
    paginatedItems = filteredItems;
  } else {
    const startIndex = (page - 1) * limit;
    paginatedItems = filteredItems.slice(startIndex, startIndex + limit);
  }

  return {
    summary,
    items: paginatedItems,
    pagination: {
      page,
      limit,
      total,
      total_pages
    }
  };
}

/**
 * Tra cứu Lịch sử Biến động theo SKU qua chuỗi thời gian của các snapshot
 * Tách biệt phạm vi: Không tính delta chéo giữa các cửa hàng hoặc kho khác nhau
 */
export async function getProductHistory(
  db: any,
  productCode: string,
  warehouse?: string,
  storeCode?: string
): Promise<ProductHistoryResponse> {
  const cleanCode = productCode.trim();

  // 1. Lấy thông tin cơ bản của sản phẩm
  const sampleItem = (await db
    .prepare(
      `SELECT product_code, product_name, category 
       FROM inventory_items 
       WHERE product_code = ? 
       LIMIT 1`
    )
    .bind(cleanCode)
    .first()) as { product_code: string; product_name: string; category: string } | null;

  if (!sampleItem) {
    throw new ComparisonServiceError(
      "PRODUCT_NOT_FOUND",
      `Không tìm thấy mặt hàng với mã SKU '${cleanCode}' trong bất kỳ đợt kiểm kê nào.`,
      404
    );
  }

  // 2. Truy vấn tất cả snapshot theo thứ tự thời gian tăng dần
  let query = `
    SELECT 
      f.id as snapshot_id,
      f.store_code,
      f.full_code,
      f.ticket_number,
      f.inventory_date,
      f.inventory_time,
      f.shift,
      i.warehouse,
      i.quantity,
      i.unit_price,
      i.total_amount
    FROM inventory_files f
    INNER JOIN inventory_items i ON f.id = i.file_id
    WHERE f.is_deleted = 0 
      AND f.status = 'COMPLETED'
      AND i.product_code = ?
  `;

  const binds: any[] = [cleanCode];
  if (storeCode) {
    query += " AND f.store_code = ?";
    binds.push(storeCode);
  }
  if (warehouse) {
    query += " AND i.warehouse = ?";
    binds.push(warehouse);
  }

  query += " ORDER BY f.inventory_date ASC, f.inventory_time ASC, f.id ASC";

  const rowsResult = await db.prepare(query).bind(...binds).all();
  const rows = rowsResult.results || [];

  // 3. Tính toán chênh lệch bước (delta)
  // ĐẶC BIỆT: Phân nhóm theo (store_code, warehouse), TUYỆT ĐỐI không tính delta chéo giữa các cửa hàng hoặc kho
  const history: ProductHistoryPoint[] = [];
  const prevMap = new Map<string, { qty: number; amt: number }>();

  for (const r of rows) {
    const qty = Number(r.quantity);
    const amt = Number(r.total_amount);
    const groupKey = `${r.store_code || "STORE"}__${r.warehouse}`;

    const prev = prevMap.get(groupKey);
    const deltaQty = prev !== undefined ? Math.round((qty - prev.qty) * 1000) / 1000 : null;
    const deltaAmt = prev !== undefined ? amt - prev.amt : null;

    history.push({
      snapshot_id: Number(r.snapshot_id),
      store_code: r.store_code ? String(r.store_code) : undefined,
      full_code: String(r.full_code),
      ticket_number: String(r.ticket_number),
      inventory_date: String(r.inventory_date),
      inventory_time: r.inventory_time ? String(r.inventory_time) : null,
      shift: String(r.shift),
      warehouse: String(r.warehouse),
      quantity: qty,
      unit_price: Number(r.unit_price),
      total_amount: amt,
      delta_quantity: deltaQty,
      delta_amount: deltaAmt
    });

    prevMap.set(groupKey, { qty, amt });
  }

  return {
    product_code: sampleItem.product_code,
    product_name: sampleItem.product_name,
    category: sampleItem.category,
    history
  };
}

/**
 * Xuất dữ liệu đối soát ra định dạng CSV (UTF-8 BOM)
 * Đạt chuẩn:
 * 1. Không cắt dòng (fetchAll = true, xuất toàn bộ số lượng SKU).
 * 2. Chống công thức Excel (Formula Injection Defense).
 * 3. Hợp đồng dữ liệu null cho SKU không xuất hiện.
 */
export async function exportComparisonCsv(
  db: any,
  baseSnapshotId: number,
  targetSnapshotId: number,
  options: ComparisonFilterOptions = {}
): Promise<string> {
  // Lấy toàn bộ danh sách không bị giới hạn phân trang
  const result = await compareSnapshots(db, baseSnapshotId, targetSnapshotId, {
    ...options,
    fetchAll: true
  });

  const headers = [
    "STT",
    "Ngành hàng",
    "Mã sản phẩm",
    "Tên sản phẩm",
    "Loại kho",
    "ĐVT Package",
    "Quy đổi",
    "ĐVT Lẻ",
    `Tồn Kho A (${result.summary.base_snapshot.ticket_number})`,
    `Tồn Kho B (${result.summary.target_snapshot.ticket_number})`,
    "Biến động SL (B - A)",
    "% Biến động",
    "Đơn giá A (VND)",
    "Đơn giá B (VND)",
    "Chênh lệch Đơn giá",
    "Thành tiền A (VND)",
    "Thành tiền B (VND)",
    "Biến động Tiền (VND)",
    "Trạng thái"
  ];

  const rows = result.items.map((it, idx) => [
    idx + 1,
    sanitizeCsvText(it.category),
    sanitizeCsvText(it.product_code),
    sanitizeCsvText(it.product_name),
    sanitizeCsvText(it.warehouse),
    sanitizeCsvText(it.package_unit || ""),
    formatCsvNumber(it.conversion_rate),
    sanitizeCsvText(it.loose_unit || ""),
    it.base_quantity !== null ? formatCsvNumber(it.base_quantity) : '""',
    it.target_quantity !== null ? formatCsvNumber(it.target_quantity) : '""',
    it.delta_quantity !== null ? formatCsvNumber(it.delta_quantity) : '""',
    it.percentage_change !== null ? `${it.percentage_change}%` : "-",
    formatCsvNumber(it.base_unit_price),
    formatCsvNumber(it.target_unit_price),
    formatCsvNumber(it.price_diff),
    formatCsvNumber(it.base_total_amount),
    formatCsvNumber(it.target_total_amount),
    it.delta_amount !== null ? formatCsvNumber(it.delta_amount) : '""',
    sanitizeCsvText(it.status_label_vi)
  ]);

  const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\r\n");

  // Thêm UTF-8 BOM để Excel hiển thị đúng dấu tiếng Việt
  return "\uFEFF" + csvContent;
}
