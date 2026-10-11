/**
 * Service: Bộ phân tích và trích xuất file Excel kiểm kê Vinamilk
 * Module: apps/api/src/services/excelParser.ts (Revision 2 - Fix 01 Data Integrity)
 *
 * Tiêu chuẩn kỹ thuật:
 * 1. Giới hạn tài nguyên an toàn cho Cloudflare Workers (File <= 10MB, Dòng <= 5,000).
 * 2. Xác thực 15 cột tiêu chuẩn ở Dòng 1.
 * 3. Trích xuất dòng tóm tắt nghiệp vụ Dòng 2 (Row 2 Summary): E2 (SL tồn kho), H2 (Thành tiền).
 * 4. Trích xuất chi tiết sản phẩm từ Dòng 3:
 *    - Bảo toàn định dạng Text cho Mã sản phẩm (giữ nguyên số 0 ở đầu, vd: '02AA15').
 *    - Kiểm tra số hợp lệ (Strict Numeric Parsing): Không tự ý ép chuỗi sai về 0 hoặc 1.
 *    - Phát hiện trùng lặp SKU (product_code, warehouse) ngay trong file trước khi ghi DB.
 * 5. Đối soát toán học độc lập với Dòng 2.
 * 6. Tính toán mã băm kép:
 *    - file_sha256: Băm nhị phân toàn vẹn của file gốc.
 *    - content_hash: Băm chuỗi dữ liệu chuẩn hóa của danh sách mặt hàng để đối soát.
 */

import * as XLSX from "xlsx";
import { parseSnapshotFilename } from "@inventory/shared";

export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
export const MAX_ROWS_PER_FILE = 5000;

export interface ParsedItem {
  row_index: number;
  stt: number;
  category: string;
  product_code: string;
  product_name: string;
  quantity: number;
  warehouse: string;
  unit_price: number;
  total_amount: number;
  audit_package_qty: number;
  audit_loose_qty: number;
  audit_total_qty_formula: string;
  discrepancy_formula: string;
  package_unit: string;
  conversion_rate: number;
  loose_unit: string;
}

export interface ParseResult {
  isValid: boolean;
  errors: string[];
  metadata: {
    full_code: string;
    ticket_number: string;
    store_code: string;
    inventory_date: string;
    inventory_time?: string | null;
    shift: "Sáng" | "Chiều" | "Tối" | "Khác" | "Chưa xác định";
    source_filename: string;
  };
  summary: {
    row2_quantity: number;
    row2_total_amount: number;
    calculated_quantity: number;
    calculated_total_amount: number;
    quantity_diff: number;
    amount_diff: number;
    is_math_matched: boolean;
  };
  total_sku_count: number;
  file_sha256: string;
  content_hash: string;
  items: ParsedItem[];
}

export interface ParseOptions {
  shift?: "Sáng" | "Chiều" | "Tối" | "Khác" | "Chưa xác định";
  inventory_time?: string | null;
  store_code?: string;
}

// 15 Tiêu đề cột chuẩn hóa mong đợi ở Dòng 1
const EXPECTED_HEADERS = [
  "STT",
  "NGÀNH HÀNG",
  "MÃ SẢN PHẨM",
  "TÊN SẢN PHẨM",
  "SL TỒN KHO",
  "LOẠI KHO",
  "GIÁ (SAU VAT)",
  "THÀNH TIỀN",
  "SL PACKAGE KIỂM KÊ",
  "SL LẺ KIỂM KÊ",
  "TỔNG SL KIỂM KÊ",
  "CHÊNH LỆCH",
  "ĐVT PACKAGE",
  "QUY ĐỔI",
  "ĐVT LẺ"
];

/**
 * Tính mã băm SHA-256 từ Uint8Array hoặc ArrayBuffer
 */
export async function computeSha256(data: ArrayBuffer | Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Hàm phân tích số học nghiêm ngặt (Strict Numeric Parser)
 * Không tự động chuyển chuỗi chữ cái/sai định dạng thành 0 hoặc 1
 */
function parseStrictNumber(
  cell: any,
  rowNumber: number,
  columnName: string,
  options: {
    required?: boolean;
    defaultValue?: number;
    min?: number;
    isInteger?: boolean;
  } = {}
): { value: number; error?: string } {
  if (!cell || cell.v === undefined || cell.v === null || String(cell.v).trim() === "") {
    if (options.required) {
      return { value: 0, error: `Dòng ${rowNumber} [${columnName}]: Dữ liệu bắt buộc không được để trống.` };
    }
    return { value: options.defaultValue ?? 0 };
  }

  let numVal: number;
  if (typeof cell.v === "number") {
    numVal = cell.v;
  } else {
    const strVal = String(cell.v).trim().replace(/,/g, "");
    numVal = Number(strVal);
    if (isNaN(numVal)) {
      return {
        value: 0,
        error: `Dòng ${rowNumber} [${columnName}]: Giá trị '${cell.v}' không phải là định dạng số hợp lệ.`
      };
    }
  }

  if (options.min !== undefined && numVal < options.min) {
    return {
      value: numVal,
      error: `Dòng ${rowNumber} [${columnName}]: Giá trị ${numVal} không được nhỏ hơn ${options.min}.`
    };
  }

  if (options.isInteger) {
    numVal = Math.round(numVal);
  }

  return { value: numVal };
}

/**
 * Phân tích nội dung file Excel kiểm kê từ Buffer
 */
export async function parseInventoryExcel(
  buffer: ArrayBuffer | Uint8Array,
  filename: string,
  options: ParseOptions = {}
): Promise<ParseResult> {
  const errors: string[] = [];
  const items: ParsedItem[] = [];

  // 1. Kiểm tra kích thước file
  const byteLength = buffer.byteLength;
  if (byteLength > MAX_FILE_SIZE_BYTES) {
    return {
      isValid: false,
      errors: [
        `Dung lượng tệp tin (${(byteLength / 1024 / 1024).toFixed(2)} MB) vượt quá giới hạn cho phép ${MAX_FILE_SIZE_BYTES / 1024 / 1024} MB.`
      ],
      metadata: {
        full_code: filename.replace(/\.xlsx$/i, "").toUpperCase(),
        ticket_number: "CHƯA_RÕ",
        store_code: options.store_code || "CH41551",
        inventory_date: new Date().toISOString().split("T")[0],
        inventory_time: options.inventory_time || null,
        shift: options.shift || "Chưa xác định",
        source_filename: filename
      },
      summary: {
        row2_quantity: 0,
        row2_total_amount: 0,
        calculated_quantity: 0,
        calculated_total_amount: 0,
        quantity_diff: 0,
        amount_diff: 0,
        is_math_matched: false
      },
      total_sku_count: 0,
      file_sha256: "",
      content_hash: "",
      items: []
    };
  }

  // 2. Tính toán file_sha256 nhị phân
  const file_sha256 = await computeSha256(buffer);

  // 3. Nhận diện metadata từ tên file & options
  const parsedMeta = parseSnapshotFilename(filename);
  const metadata = {
    full_code: parsedMeta?.full_code || filename.replace(/\.xlsx$/i, "").toUpperCase(),
    ticket_number: parsedMeta?.ticket_number || "CHƯA_RÕ",
    store_code: options.store_code || parsedMeta?.store_code || "CH41551",
    inventory_date: parsedMeta?.inventory_date || new Date().toISOString().split("T")[0],
    inventory_time: options.inventory_time || null,
    shift: options.shift || ("Chưa xác định" as const),
    source_filename: filename
  };

  if (!parsedMeta) {
    errors.push(`Tên file '${filename}' không tuân thủ mẫu chuẩn (VD: KiemKe_KK.CH41551.26.339000_20261009.xlsx)`);
  }

  // 4. Đọc workbook bằng SheetJS
  let workbook: XLSX.WorkBook;
  try {
    workbook = XLSX.read(buffer, { type: "buffer", cellFormula: true });
  } catch (err: any) {
    return {
      isValid: false,
      errors: [`Không thể đọc định dạng file Excel: ${err.message || String(err)}`],
      metadata,
      summary: {
        row2_quantity: 0,
        row2_total_amount: 0,
        calculated_quantity: 0,
        calculated_total_amount: 0,
        quantity_diff: 0,
        amount_diff: 0,
        is_math_matched: false
      },
      total_sku_count: 0,
      file_sha256,
      content_hash: "",
      items: []
    };
  }

  const sheetName = workbook.SheetNames[0];
  if (!sheetName) {
    errors.push("File Excel không có bất kỳ sheet nào.");
    return {
      isValid: false,
      errors,
      metadata,
      summary: {
        row2_quantity: 0,
        row2_total_amount: 0,
        calculated_quantity: 0,
        calculated_total_amount: 0,
        quantity_diff: 0,
        amount_diff: 0,
        is_math_matched: false
      },
      total_sku_count: 0,
      file_sha256,
      content_hash: "",
      items: []
    };
  }

  const worksheet = workbook.Sheets[sheetName];
  if (!worksheet || !worksheet["!ref"]) {
    errors.push(`Sheet '${sheetName}' rỗng hoặc không có dữ liệu.`);
    return {
      isValid: false,
      errors,
      metadata,
      summary: {
        row2_quantity: 0,
        row2_total_amount: 0,
        calculated_quantity: 0,
        calculated_total_amount: 0,
        quantity_diff: 0,
        amount_diff: 0,
        is_math_matched: false
      },
      total_sku_count: 0,
      file_sha256,
      content_hash: "",
      items: []
    };
  }

  const range = XLSX.utils.decode_range(worksheet["!ref"]);
  const totalRowsInRange = range.e.r - range.s.r + 1;
  if (totalRowsInRange > MAX_ROWS_PER_FILE) {
    errors.push(
      `Số lượng dòng trong file (${totalRowsInRange}) vượt quá hạn mức tối đa cho phép (${MAX_ROWS_PER_FILE} dòng).`
    );
  }

  // 5. Kiểm tra 15 cột tiêu chuẩn ở Dòng 1 (r = 0 trong 0-indexed)
  for (let c = 0; c < 15; c++) {
    const cellAddress = XLSX.utils.encode_cell({ r: 0, c });
    const cell = worksheet[cellAddress];
    const headerValue = cell && cell.v !== undefined ? String(cell.v).trim().toUpperCase() : "";
    const expectedHeader = EXPECTED_HEADERS[c];

    if (!headerValue.includes(expectedHeader)) {
      errors.push(
        `Cột ${c + 1} không khớp chuẩn: mong đợi chứa '${expectedHeader}', thực tế nhận được '${headerValue}'`
      );
    }
  }

  // 6. Trích xuất dòng tóm tắt Dòng 2 (r = 1 trong 0-indexed)
  const cellE2 = worksheet["E2"]; // Cột 5: SL TỒN KHO
  const cellH2 = worksheet["H2"]; // Cột 8: THÀNH TIỀN

  const parseE2 = parseStrictNumber(cellE2, 2, "SL TỒN KHO (Dòng 2)", { defaultValue: 0, min: 0 });
  if (parseE2.error) errors.push(parseE2.error);
  const row2_quantity = parseE2.value;

  const parseH2 = parseStrictNumber(cellH2, 2, "THÀNH TIỀN (Dòng 2)", { defaultValue: 0, min: 0, isInteger: true });
  if (parseH2.error) errors.push(parseH2.error);
  const row2_total_amount = parseH2.value;

  // 7. Phân tích chi tiết từng dòng mặt hàng từ Dòng 3 (r = 2) đến hết range
  let sumQuantity = 0;
  let sumTotalAmount = 0;
  const seenSkus = new Map<string, number>(); // Kiểm tra SKU trùng theo (product_code, warehouse)

  for (let r = 2; r <= range.e.r; r++) {
    const rowNumber = r + 1; // 1-indexed (3, 4, 5...)

    // Lấy ô Mã sản phẩm (Cột C, index 2)
    const cellProductCode = worksheet[XLSX.utils.encode_cell({ r, c: 2 })];
    if (
      !cellProductCode ||
      cellProductCode.v === undefined ||
      cellProductCode.v === null ||
      String(cellProductCode.v).trim() === ""
    ) {
      // Dòng trống hoặc kết thúc dữ liệu
      continue;
    }

    // Bảo toàn dạng chuỗi cho Mã sản phẩm (giữ nguyên số 0 ở đầu)
    const rawCodeVal = cellProductCode.w || cellProductCode.v;
    const product_code = String(rawCodeVal).trim();

    // STT (Cột 1, index 0)
    const cellSTT = worksheet[XLSX.utils.encode_cell({ r, c: 0 })];
    const parseSTT = parseStrictNumber(cellSTT, rowNumber, "STT", {
      defaultValue: items.length + 1,
      min: 1,
      isInteger: true
    });
    const stt = parseSTT.value;

    // NGÀNH HÀNG (Cột 2, index 1)
    const cellCategory = worksheet[XLSX.utils.encode_cell({ r, c: 1 })];
    const category = cellCategory && cellCategory.v !== undefined ? String(cellCategory.v).trim() : "KHÁC";

    // TÊN SẢN PHẨM (Cột 4, index 3)
    const cellProductName = worksheet[XLSX.utils.encode_cell({ r, c: 3 })];
    const product_name = cellProductName && cellProductName.v !== undefined ? String(cellProductName.v).trim() : "";
    if (!product_name) {
      errors.push(`Dòng ${rowNumber} [${product_code}]: Tên sản phẩm không được để trống.`);
    }

    // LOẠI KHO (Cột 6, index 5)
    const cellWarehouse = worksheet[XLSX.utils.encode_cell({ r, c: 5 })];
    const warehouse = cellWarehouse && cellWarehouse.v !== undefined ? String(cellWarehouse.v).trim() : "Kho hàng bán";

    // Kiểm tra trùng lặp SKU (product_code, warehouse) trong cùng một file
    const skuKey = `${product_code}|${warehouse}`;
    if (seenSkus.has(skuKey)) {
      const firstRow = seenSkus.get(skuKey);
      errors.push(
        `Dòng ${rowNumber}: Trùng lặp mặt hàng với mã '${product_code}' trong '${warehouse}' (đã xuất hiện ở dòng ${firstRow}).`
      );
    } else {
      seenSkus.set(skuKey, rowNumber);
    }

    // SL TỒN KHO (Cột 5, index 4) - Bắt buộc số, min 0
    const cellQty = worksheet[XLSX.utils.encode_cell({ r, c: 4 })];
    const parseQty = parseStrictNumber(cellQty, rowNumber, "SL TỒN KHO", { required: true, min: 0 });
    if (parseQty.error) errors.push(parseQty.error);
    const quantity = parseQty.value;

    // GIÁ (SAU VAT) (Cột 7, index 6) - Bắt buộc số nguyên, min 0
    const cellPrice = worksheet[XLSX.utils.encode_cell({ r, c: 6 })];
    const parsePrice = parseStrictNumber(cellPrice, rowNumber, "GIÁ (SAU VAT)", {
      required: true,
      min: 0,
      isInteger: true
    });
    if (parsePrice.error) errors.push(parsePrice.error);
    const unit_price = parsePrice.value;

    // THÀNH TIỀN (Cột 8, index 7) - Bắt buộc số nguyên, min 0
    const cellAmt = worksheet[XLSX.utils.encode_cell({ r, c: 7 })];
    const parseAmt = parseStrictNumber(cellAmt, rowNumber, "THÀNH TIỀN", {
      required: true,
      min: 0,
      isInteger: true
    });
    if (parseAmt.error) errors.push(parseAmt.error);
    const total_amount = parseAmt.value;

    // SL PACKAGE KIỂM KÊ (Cột 9, index 8)
    const cellPkgQty = worksheet[XLSX.utils.encode_cell({ r, c: 8 })];
    const parsePkgQty = parseStrictNumber(cellPkgQty, rowNumber, "SL PACKAGE KIỂM KÊ", { defaultValue: 0, min: 0 });
    if (parsePkgQty.error) errors.push(parsePkgQty.error);
    const audit_package_qty = parsePkgQty.value;

    // SL LẺ KIỂM KÊ (Cột 10, index 9)
    const cellLooseQty = worksheet[XLSX.utils.encode_cell({ r, c: 9 })];
    const parseLooseQty = parseStrictNumber(cellLooseQty, rowNumber, "SL LẺ KIỂM KÊ", { defaultValue: 0, min: 0 });
    if (parseLooseQty.error) errors.push(parseLooseQty.error);
    const audit_loose_qty = parseLooseQty.value;

    // TỔNG SL KIỂM KÊ CÔNG THỨC (Cột 11, index 10)
    const cellTotalQty = worksheet[XLSX.utils.encode_cell({ r, c: 10 })];
    const audit_total_qty_formula = cellTotalQty?.f ? `=${cellTotalQty.f}` : String(cellTotalQty?.v || 0);

    // CHÊNH LỆCH CÔNG THỨC (Cột 12, index 11)
    const cellDiscrepancy = worksheet[XLSX.utils.encode_cell({ r, c: 11 })];
    const discrepancy_formula = cellDiscrepancy?.f ? `=${cellDiscrepancy.f}` : String(cellDiscrepancy?.v || 0);

    // ĐVT PACKAGE (Cột 13, index 12)
    const cellPkgUnit = worksheet[XLSX.utils.encode_cell({ r, c: 12 })];
    const package_unit = cellPkgUnit && cellPkgUnit.v !== undefined ? String(cellPkgUnit.v).trim() : "";

    // QUY ĐỔI (Cột 14, index 13) - Bắt buộc số > 0
    const cellConvRate = worksheet[XLSX.utils.encode_cell({ r, c: 13 })];
    const parseConvRate = parseStrictNumber(cellConvRate, rowNumber, "QUY ĐỔI", {
      defaultValue: 1.0,
      min: 0.0001
    });
    if (parseConvRate.error) errors.push(parseConvRate.error);
    const conversion_rate = parseConvRate.value;

    // ĐVT LẺ (Cột 15, index 14)
    const cellLooseUnit = worksheet[XLSX.utils.encode_cell({ r, c: 14 })];
    const loose_unit = cellLooseUnit && cellLooseUnit.v !== undefined ? String(cellLooseUnit.v).trim() : "";

    sumQuantity += quantity;
    sumTotalAmount += total_amount;

    items.push({
      row_index: rowNumber,
      stt,
      category,
      product_code,
      product_name,
      quantity,
      warehouse,
      unit_price,
      total_amount,
      audit_package_qty,
      audit_loose_qty,
      audit_total_qty_formula,
      discrepancy_formula,
      package_unit,
      conversion_rate,
      loose_unit
    });
  }

  if (items.length === 0) {
    errors.push("File không chứa bất kỳ dòng sản phẩm nào từ Dòng 3.");
  }

  // 8. Đối soát toán học với Dòng 2 (Mathematical Cross-check)
  const quantity_diff = Math.abs(sumQuantity - row2_quantity);
  const amount_diff = Math.abs(sumTotalAmount - row2_total_amount);
  const is_math_matched = quantity_diff <= 0.001 && amount_diff <= 1;

  if (!is_math_matched) {
    errors.push(
      `Số liệu tổng không khớp Dòng 2: SL chênh lệch ${quantity_diff} (Tổng dòng: ${sumQuantity}, Dòng 2: ${row2_quantity}); ` +
      `Tiền chênh lệch ${amount_diff} VND (Tổng dòng: ${sumTotalAmount}, Dòng 2: ${row2_total_amount})`
    );
  }

  // 9. Tính toán canonical content_hash
  const sortedItems = [...items].sort((a, b) => {
    const codeCmp = a.product_code.localeCompare(b.product_code);
    return codeCmp !== 0 ? codeCmp : a.warehouse.localeCompare(b.warehouse);
  });

  const contentCanonicalString = sortedItems
    .map(
      (item) =>
        `${item.product_code}:${item.warehouse}:${item.quantity}:${item.unit_price}:${item.total_amount}:${item.conversion_rate}`
    )
    .join("\n");

  const encoder = new TextEncoder();
  const content_hash = await computeSha256(encoder.encode(contentCanonicalString));

  return {
    isValid: errors.length === 0,
    errors,
    metadata,
    summary: {
      row2_quantity,
      row2_total_amount,
      calculated_quantity: sumQuantity,
      calculated_total_amount: sumTotalAmount,
      quantity_diff,
      amount_diff,
      is_math_matched
    },
    total_sku_count: items.length,
    file_sha256,
    content_hash,
    items
  };
}
