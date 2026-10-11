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
export const APP_VERSION = "0.3.0";
export const GDRIVE_OFFICIAL_FOLDER_ID = "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk";
// 2. Enum phân loại
export const RoleEnum = z.enum(["ADMIN", "USER"]);
export const ShiftEnum = z.enum(["Sáng", "Chiều", "Tối", "Khác", "Chưa xác định"]);
export const SnapshotStatusEnum = z.enum(["STAGING", "COMPLETED", "FAILED", "CONFLICT"]);
export const SourceTypeEnum = z.enum(["MANUAL_UPLOAD", "GDRIVE_SYNC"]);
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
];
// 4. Schemas cho API Responses
export const ApiResponseSchema = (dataSchema) => z.object({
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
// 6. Schema Item Chi tiết
export const InventoryItemDetailSchema = z.object({
    id: z.number().int().positive().optional(),
    file_id: z.number().int().positive(),
    row_index: z.number().int().positive(),
    stt: z.number().int().positive(),
    category: z.string(),
    product_code: z.string(), // Phải giữ nguyên số 0 ở đầu chuỗi
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
// 7. Schemas cho Xác thực (Auth) & Quản lý người dùng (Users) - Round 03
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
export const LoginRequestSchema = z.object({
    username: z.string().trim().min(1, "Vui lòng nhập tên đăng nhập"),
    password: z.string().min(1, "Vui lòng nhập mật khẩu")
});
export const LoginResponseDataSchema = z.object({
    user: UserSchema,
    token: z.string(),
    expires_at: z.string()
});
export const ChangePasswordRequestSchema = z.object({
    current_password: z.string().min(1, "Vui lòng nhập mật khẩu hiện tại"),
    new_password: z
        .string()
        .min(6, "Mật khẩu mới phải có tối thiểu 6 ký tự")
        .max(100, "Mật khẩu mới quá dài")
});
export const CreateUserRequestSchema = z.object({
    username: z
        .string()
        .trim()
        .min(3, "Tên đăng nhập phải có ít nhất 3 ký tự")
        .max(50, "Tên đăng nhập tối đa 50 ký tự")
        .regex(/^[a-zA-Z0-9_.-]+$/, "Tên đăng nhập chỉ chứa chữ cái, số, dấu gạch nối hoặc gạch dưới"),
    password: z
        .string()
        .min(6, "Mật khẩu tạm thời tối thiểu 6 ký tự")
        .default("123456"),
    role: RoleEnum.default("USER"),
    full_name: z.string().trim().min(1, "Vui lòng nhập họ và tên").max(100),
    must_change_password: z.boolean().default(true)
});
export const UpdateUserStatusRequestSchema = z.object({
    is_active: z.boolean()
});
export const ResetPasswordRequestSchema = z.object({
    temp_password: z.string().min(6).optional().default("123456")
});
