/**
 * Module: @inventory/shared
 * Định nghĩa dùng chung giữa Backend (API) và Frontend (Web):
 * - Hợp đồng dữ liệu 15 cột
 * - Zod schemas validation
 * - TypeScript types
 * - Hằng số & Bản dịch tiếng Việt
 */

import { z } from "zod";

// 1. Hằng số dự án
export const APP_NAME = "Vinamilk Inventory Management";
export const APP_VERSION = "0.4.0";
export const GDRIVE_OFFICIAL_FOLDER_ID = "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk";


// 2. Enum phân loại
export const RoleEnum = z.enum(["ADMIN", "USER"]);
export type Role = z.infer<typeof RoleEnum>;

export const ShiftEnum = z.enum(["Sáng", "Chiều", "Tối", "Khác", "Chưa xác định"]);
export type Shift = z.infer<typeof ShiftEnum>;

export const SnapshotStatusEnum = z.enum(["STAGING", "COMPLETED", "FAILED", "CONFLICT"]);
export type SnapshotStatus = z.infer<typeof SnapshotStatusEnum>;

export const SourceTypeEnum = z.enum(["MANUAL_UPLOAD", "GDRIVE_SYNC"]);
export type SourceType = z.infer<typeof SourceTypeEnum>;

// 3. 15 Cột Excel Tiêu chuẩn
export const EXCEL_COLUMNS = [
  { index: 1, key: "stt", label: "STT", type: "number" },
  { index: 2, key: "category", label: "NGÀNH HÀNG", type: "string" },
  { index: 3, key: "product_code", label: "MÃ SẢN PHẨM", type: "string" },
  { index: 4, key: "product_name", label: "TÊN SẢN PHẨM", type: "string" },
  { index: 5, key: "quantity", label: "SL TỒN KHO", type: "number" },
  { index: 6, key: "warehouse", label: "LOẠI KHO", type: "string" },
  { index: 7, key: "unit_price", label: "GIÁ (SAU VAT)", type: "number" },
  { index: 8, key: "total_amount", label: "THÀNH TIỀN", type: "number" },
  { index: 9, key: "audit_package_qty", label: "SL PACKAGE KIỂM KÊ", type: "number" },
  { index: 10, key: "audit_loose_qty", label: "SL LẺ KIỂM KÊ", type: "number" },
  { index: 11, key: "audit_total_qty", label: "TỔNG SL KIỂM KÊ", type: "formula" },
  { index: 12, key: "discrepancy", label: "CHÊNH LỆCH", type: "formula" },
  { index: 13, key: "package_unit", label: "ĐVT PACKAGE", type: "string" },
  { index: 14, key: "conversion_rate", label: "QUY ĐỔI", type: "number" },
  { index: 15, key: "loose_unit", label: "ĐVT LẺ", type: "string" }
] as const;

// 4. Schemas cho API Responses
export const ApiResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema.optional(),
    error: z.object({
      code: z.string(),
      message: z.string(),
      details: z.any().optional()
    }).optional(),
    meta: z.record(z.any()).optional()
  });

export const DatabaseInfoSchema = z.object({
  provider: z.string(),
  status: z.enum(["connected", "not_configured", "unavailable"]),
  message: z.string().optional()
});

export const SystemInfoSchema = z.object({
  service: z.string(),
  version: z.string(),
  round: z.string(),
  environment: z.string(),
  timezone: z.string(),
  timestamp: z.string(),
  database: DatabaseInfoSchema,
  modules: z.record(z.string(), z.string()),
  features: z.record(z.string(), z.string())
});
export type SystemInfo = z.infer<typeof SystemInfoSchema>;

// 5. Schema Snapshot
export const InventoryFileSchema = z.object({
  id: z.number().int().positive(),
  full_code: z.string(),
  ticket_number: z.string(),
  store_code: z.string(),
  inventory_date: z.string(),
  inventory_time: z.string().nullable().optional(),
  shift: ShiftEnum,
  file_sha256: z.string(),
  content_hash: z.string(),
  source_filename: z.string(),
  source_type: SourceTypeEnum,
  source_file_id: z.string().nullable().optional(),
  source_revision: z.string().nullable().optional(),
  status: SnapshotStatusEnum,
  total_sku_count: z.number().int().nonnegative(),
  total_quantity: z.number().nonnegative(),
  total_amount_vnd: z.number().nonnegative(),
  is_deleted: z.boolean(),
  created_at: z.string()
});
export type InventoryFile = z.infer<typeof InventoryFileSchema>;

// 6. Schema Item Chi tiết
export const InventoryItemDetailSchema = z.object({
  id: z.number().int().positive().optional(),
  file_id: z.number().int().positive().optional(),
  row_index: z.number().int().positive(),
  stt: z.number().int().positive(),
  category: z.string(),
  product_code: z.string(), // Phải giữ nguyên số 0 ở đầu chuỗi (e.g. '02AA15')
  product_name: z.string(),
  quantity: z.number().nonnegative(),
  warehouse: z.string(),
  unit_price: z.number().nonnegative(),
  total_amount: z.number().nonnegative(),
  audit_package_qty: z.number().default(0),
  audit_loose_qty: z.number().default(0),
  audit_total_qty_formula: z.string().nullable().optional(),
  discrepancy_formula: z.string().nullable().optional(),
  package_unit: z.string().nullable().optional(),
  conversion_rate: z.number().positive().default(1.0),
  loose_unit: z.string().nullable().optional()
});
export type InventoryItemDetail = z.infer<typeof InventoryItemDetailSchema>;

// 6b. Schemas cho Nạp File & Kiểm tra Dòng 2 (Round 04)
export const Row2SummarySchema = z.object({
  total_quantity: z.number().nonnegative(),
  total_amount_vnd: z.number().nonnegative()
});
export type Row2Summary = z.infer<typeof Row2SummarySchema>;

export const ParsedExcelDataSchema = z.object({
  full_code: z.string(),
  ticket_number: z.string(),
  store_code: z.string(),
  inventory_date: z.string(),
  inventory_time: z.string().nullable().optional(),
  shift: ShiftEnum.default("Chưa xác định"),
  file_sha256: z.string(),
  content_hash: z.string(),
  source_filename: z.string(),
  total_sku_count: z.number().int().positive(),
  total_quantity: z.number().nonnegative(),
  total_amount_vnd: z.number().nonnegative(),
  summary_row_2: Row2SummarySchema,
  has_discrepancy: z.boolean(),
  discrepancy_details: z.object({
    qty_diff: z.number(),
    amount_diff: z.number()
  }).optional(),
  items: z.array(InventoryItemDetailSchema)
});
export type ParsedExcelData = z.infer<typeof ParsedExcelDataSchema>;

export const SnapshotFilterQuerySchema = z.object({
  status: SnapshotStatusEnum.optional(),
  store_code: z.string().optional(),
  date_from: z.string().optional(),
  date_to: z.string().optional(),
  shift: ShiftEnum.optional(),
  search: z.string().optional(),
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().positive().max(100).default(20)
});
export type SnapshotFilterQuery = z.infer<typeof SnapshotFilterQuerySchema>;

/**
 * Helper: Phân tích định danh chứng từ từ tên file Excel
 * Mẫu tên file: KiemKe_KK.CH41551.26.339000_20261009.xlsx hoặc KK.CH41551.26.339000.xlsx
 */
export function parseSnapshotFilename(filename: string): {
  full_code: string;
  store_code: string;
  ticket_number: string;
  inventory_date: string;
} | null {
  const cleanName = filename.replace(/\.xlsx$/i, "").trim();

  // Pattern: KiemKe_KK.<store>.<yy>.<ticket>_<yyyymmdd>
  const matchWithDate = cleanName.match(
    /(?:KiemKe_)?(KK\.([A-Z0-9]+)\.\d{2}\.(\d+))_(\d{4})(\d{2})(\d{2})/i
  );
  if (matchWithDate) {
    const full_code = matchWithDate[1].toUpperCase();
    const store_code = matchWithDate[2].toUpperCase();
    const ticket_number = matchWithDate[3];
    const inventory_date = `${matchWithDate[4]}-${matchWithDate[5]}-${matchWithDate[6]}`;
    return { full_code, store_code, ticket_number, inventory_date };
  }

  // Pattern không có ngày ở đuôi: KK.<store>.<yy>.<ticket>
  const matchStandard = cleanName.match(/(?:KiemKe_)?(KK\.([A-Z0-9]+)\.\d{2}\.(\d+))/i);
  if (matchStandard) {
    const full_code = matchStandard[1].toUpperCase();
    const store_code = matchStandard[2].toUpperCase();
    const ticket_number = matchStandard[3];
    const today = new Date().toISOString().split("T")[0];
    return { full_code, store_code, ticket_number, inventory_date: today };
  }

  return null;
}


// 7. Schemas cho Xác thực (Auth) & Quản lý người dùng (Users) - Round 03
export const COMMON_PASSWORDS_BLACKLIST = [
  "123456",
  "12345678",
  "123456789",
  "password",
  "password123",
  "admin123",
  "qwerty",
  "admin",
  "vinamilk",
  "vinamilk123"
] as const;

export const UserSchema = z.object({
  id: z.number().int().positive(),
  username: z.string().min(3).max(50),
  role: RoleEnum,
  full_name: z.string().min(1).max(100),
  must_change_password: z.boolean(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string().optional()
});
export type User = z.infer<typeof UserSchema>;

export const LoginRequestSchema = z.object({
  username: z.string().trim().min(1, "Vui lòng nhập tên đăng nhập"),
  password: z.string().min(1, "Vui lòng nhập mật khẩu")
});
export type LoginRequest = z.infer<typeof LoginRequestSchema>;

export const LoginResponseDataSchema = z.object({
  user: UserSchema,
  token: z.string(),
  expires_at: z.string()
});
export type LoginResponseData = z.infer<typeof LoginResponseDataSchema>;

export const ChangePasswordRequestSchema = z.object({
  current_password: z.string().min(1, "Vui lòng nhập mật khẩu hiện tại"),
  new_password: z
    .string()
    .min(8, "Mật khẩu mới phải có tối thiểu 8 ký tự")
    .max(100, "Mật khẩu mới quá dài")
    .refine((val) => !COMMON_PASSWORDS_BLACKLIST.includes(val.toLowerCase() as any), {
      message: "Mật khẩu mới quá đơn giản hoặc nằm trong danh sách không an toàn. Vui lòng chọn mật khẩu mạnh hơn."
    })
});
export type ChangePasswordRequest = z.infer<typeof ChangePasswordRequestSchema>;

export const CreateUserRequestSchema = z.object({
  username: z
    .string()
    .trim()
    .min(3, "Tên đăng nhập phải có ít nhất 3 ký tự")
    .max(50, "Tên đăng nhập tối đa 50 ký tự")
    .regex(/^[a-zA-Z0-9_.-]+$/, "Tên đăng nhập chỉ chứa chữ cái, số, dấu gạch nối hoặc gạch dưới"),
  password: z
    .string()
    .min(8, "Mật khẩu tạm thời phải có tối thiểu 8 ký tự")
    .refine((val) => !COMMON_PASSWORDS_BLACKLIST.includes(val.toLowerCase() as any), {
      message: "Mật khẩu tạm thời nằm trong danh sách không an toàn. Vui lòng chọn mật khẩu mạnh hơn."
    })
    .optional(),
  role: RoleEnum.default("USER"),
  full_name: z.string().trim().min(1, "Vui lòng nhập họ và tên").max(100),
  must_change_password: z.boolean().default(true)
});
export type CreateUserRequest = z.infer<typeof CreateUserRequestSchema>;

export const UpdateUserStatusRequestSchema = z.object({
  is_active: z.boolean()
});
export type UpdateUserStatusRequest = z.infer<typeof UpdateUserStatusRequestSchema>;

export const UpdateUserRequestSchema = z.object({
  full_name: z.string().trim().min(1, "Họ và tên không được để trống").max(100).optional(),
  role: RoleEnum.optional()
});
export type UpdateUserRequest = z.infer<typeof UpdateUserRequestSchema>;

export const ResetPasswordRequestSchema = z.object({
  temp_password: z
    .string()
    .min(8, "Mật khẩu tạm thời phải có tối thiểu 8 ký tự")
    .refine((val) => !COMMON_PASSWORDS_BLACKLIST.includes(val.toLowerCase() as any), {
      message: "Mật khẩu tạm thời nằm trong danh sách không an toàn."
    })
    .optional()
});
export type ResetPasswordRequest = z.infer<typeof ResetPasswordRequestSchema>;

export const BootstrapAdminRequestSchema = z.object({
  username: z.string().trim().min(3).max(50).default("admin"),
  password: z
    .string()
    .min(8, "Mật khẩu Admin phải có tối thiểu 8 ký tự")
    .refine((val) => !COMMON_PASSWORDS_BLACKLIST.includes(val.toLowerCase() as any), {
      message: "Mật khẩu Admin quá đơn giản hoặc nằm trong danh sách không an toàn."
    })
    .optional(),
  full_name: z.string().trim().min(1).max(100).default("Quản trị viên hệ thống")
});
export type BootstrapAdminRequest = z.infer<typeof BootstrapAdminRequestSchema>;

// 8. Schemas cho Đối soát Tồn kho (Comparison Engine - Round 05 Fix 01)
export const ComparisonStatusEnum = z.enum([
  "NO_CHANGE",    // Không đổi / Khớp (B.qty = A.qty)
  "INCREASED",    // Tăng tồn (B.qty > A.qty)
  "DECREASED",    // Giảm tồn (B.qty < A.qty)
  "NEW_ADDED",    // Mới xuất hiện (Chỉ có ở B)
  "OUT_OF_STOCK", // Hết tồn (Có dòng tại B nhưng SL = 0)
  "NOT_PRESENT"   // Không xuất hiện (Chỉ có ở A, hoàn toàn vắng mặt ở B)
]);
export type ComparisonStatus = z.infer<typeof ComparisonStatusEnum>;

export const ComparisonItemSchema = z.object({
  product_code: z.string(),
  product_name: z.string(),
  category: z.string(),
  warehouse: z.string(),
  package_unit: z.string().nullable().optional(),
  loose_unit: z.string().nullable().optional(),
  conversion_rate: z.number().default(1.0),
  base_quantity: z.number().nullable().default(0),
  target_quantity: z.number().nullable().default(0),
  delta_quantity: z.number().nullable(), // B.quantity - A.quantity (QUY TẮC BẮT BUỘC, null nếu không xuất hiện)
  percentage_change: z.number().nullable(), // null nếu base_quantity = 0 hoặc missing
  base_unit_price: z.number().default(0),
  target_unit_price: z.number().default(0),
  price_diff: z.number().default(0),
  base_total_amount: z.number().default(0),
  target_total_amount: z.number().default(0),
  delta_amount: z.number().nullable(), // B.total_amount - A.total_amount
  status: ComparisonStatusEnum,
  status_label_vi: z.string()
});
export type ComparisonItem = z.infer<typeof ComparisonItemSchema>;

export const ComparisonSummarySchema = z.object({
  base_snapshot: z.object({
    id: z.number(),
    full_code: z.string(),
    ticket_number: z.string(),
    store_code: z.string().optional(),
    inventory_date: z.string(),
    shift: z.string(),
    total_sku_count: z.number(),
    total_quantity: z.number(),
    total_amount_vnd: z.number()
  }),
  target_snapshot: z.object({
    id: z.number(),
    full_code: z.string(),
    ticket_number: z.string(),
    store_code: z.string().optional(),
    inventory_date: z.string(),
    shift: z.string(),
    total_sku_count: z.number(),
    total_quantity: z.number(),
    total_amount_vnd: z.number()
  }),
  total_sku_base: z.number(),
  total_sku_target: z.number(),
  total_sku_union: z.number(),
  matched_count: z.number(),
  increased_count: z.number(),
  decreased_count: z.number(),
  unchanged_count: z.number(),
  new_count: z.number(),
  out_of_stock_count: z.number(),
  not_present_count: z.number().default(0),
  price_changed_count: z.number(),
  base_total_quantity: z.number(),
  target_total_quantity: z.number(),
  delta_quantity: z.number(),
  base_total_amount: z.number(),
  target_total_amount: z.number(),
  delta_amount: z.number(),
  scope_warning: z.string().nullable().optional(),
  top_increased: z.array(ComparisonItemSchema).default([]),
  top_decreased: z.array(ComparisonItemSchema).default([]),
  top_value_increased: z.array(ComparisonItemSchema).default([]),
  top_value_decreased: z.array(ComparisonItemSchema).default([])
});
export type ComparisonSummary = z.infer<typeof ComparisonSummarySchema>;

export const ComparisonResponseSchema = z.object({
  summary: ComparisonSummarySchema,
  items: z.array(ComparisonItemSchema),
  pagination: z.object({
    page: z.number(),
    limit: z.number(),
    total: z.number(),
    total_pages: z.number()
  })
});
export type ComparisonResponse = z.infer<typeof ComparisonResponseSchema>;

export const ProductHistoryPointSchema = z.object({
  snapshot_id: z.number(),
  store_code: z.string().optional(),
  full_code: z.string(),
  ticket_number: z.string(),
  inventory_date: z.string(),
  inventory_time: z.string().nullable().optional(),
  shift: z.string(),
  warehouse: z.string(),
  quantity: z.number(),
  unit_price: z.number(),
  total_amount: z.number(),
  delta_quantity: z.number().nullable(),
  delta_amount: z.number().nullable()
});
export type ProductHistoryPoint = z.infer<typeof ProductHistoryPointSchema>;

export const ProductHistoryResponseSchema = z.object({
  product_code: z.string(),
  product_name: z.string(),
  category: z.string(),
  history: z.array(ProductHistoryPointSchema)
});
export type ProductHistoryResponse = z.infer<typeof ProductHistoryResponseSchema>;

