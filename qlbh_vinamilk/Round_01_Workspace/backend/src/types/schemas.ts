/**
 * File: backend/src/types/schemas.ts
 * Đặc tả kiểu dữ liệu (TypeScript) và Zod Schemas cho API Skeleton dự án Inventory Management.
 * Tuân thủ Data Contract 15 cột và Snapshot Identity.
 */

import { z } from "zod";

// 1. Phân loại ca kiểm kê
export const ShiftEnum = z.enum(["Sáng", "Chiều", "Tối", "Khác", "Chưa xác định"]);
export type Shift = z.infer<typeof ShiftEnum>;

// 2. Schema truy vấn danh sách snapshot (Pagination & Filter)
export const SnapshotQuerySchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().positive().max(100).default(20),
  store_code: z.string().optional(),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Định dạng ngày phải là YYYY-MM-DD").optional(),
  shift: ShiftEnum.optional(),
  include_deleted: z.coerce.boolean().default(false)
});
export type SnapshotQuery = z.infer<typeof SnapshotQuerySchema>;

// 3. Schema bản ghi Snapshot Metadata
export const SnapshotMetadataSchema = z.object({
  id: z.number().int().positive(),
  full_code: z.string(),
  ticket_number: z.string(),
  store_code: z.string(),
  inventory_date: z.string(),
  shift: ShiftEnum,
  file_sha256: z.string(),
  content_hash: z.string(),
  source_filename: z.string(),
  source_type: z.enum(["MANUAL_UPLOAD", "GDRIVE_SYNC"]),
  status: z.enum(["STAGING", "COMPLETED", "FAILED", "CONFLICT"]),
  total_sku_count: z.number().int().nonnegative(),
  total_quantity: z.number().nonnegative(),
  total_amount_vnd: z.number().nonnegative(),
  is_deleted: z.boolean(),
  created_at: z.string()
});
export type SnapshotMetadata = z.infer<typeof SnapshotMetadataSchema>;

// 4. Schema dòng sản phẩm chi tiết (Inventory Item) 15 cột
export const InventoryItemSchema = z.object({
  id: z.number().int().positive().optional(),
  snapshot_id: z.number().int().positive(),
  row_index: z.number().int().positive(),
  stt: z.number().int().positive(),
  category: z.string().min(1),
  product_code: z.string().min(1), // Giữ nguyên số 0 đầu chuỗi
  product_name: z.string().min(1),
  quantity: z.number().nonnegative(),
  warehouse: z.string().min(1),
  unit_price: z.number().nonnegative(),
  total_amount: z.number().nonnegative(),
  audit_package_qty: z.number().nonnegative().default(0),
  audit_loose_qty: z.number().nonnegative().default(0),
  audit_total_qty_formula: z.string().nullable().optional(),
  discrepancy_formula: z.string().nullable().optional(),
  package_unit: z.string().nullable().optional(),
  conversion_rate: z.number().positive().default(1.0),
  loose_unit: z.string().nullable().optional()
});
export type InventoryItem = z.infer<typeof InventoryItemSchema>;

// 5. Schema yêu cầu so sánh 2 snapshot
export const CompareRequestSchema = z.object({
  snapshot_a_id: z.number().int().positive({ message: "ID snapshot A không hợp lệ" }),
  snapshot_b_id: z.number().int().positive({ message: "ID snapshot B không hợp lệ" })
});
export type CompareRequest = z.infer<typeof CompareRequestSchema>;

// 6. Schema kết quả so sánh
export const CompareResponseSchema = z.object({
  summary: z.object({
    snapshot_a: z.string(),
    snapshot_b: z.string(),
    matched_count: z.number(),
    increased_count: z.number(),
    decreased_count: z.number(),
    unchanged_count: z.number(),
    new_count: z.number(),
    not_appeared_count: z.number(),
    total_delta_quantity: z.number(),
    total_delta_value: z.number()
  }),
  details: z.array(z.object({
    product_code: z.string(),
    warehouse: z.string(),
    product_name: z.string(),
    status: z.enum(["INCREASED", "DECREASED", "UNCHANGED", "NEW", "NOT_APPEARED"]),
    qty_a: z.number().nullable(),
    qty_b: z.number().nullable(),
    diff_qty: z.number(),
    pct_qty_change: z.number().nullable(),
    price_a: z.number().nullable(),
    price_b: z.number().nullable(),
    val_a: z.number().nullable(),
    val_b: z.number().nullable(),
    diff_val: z.number(),
    pct_val_change: z.number().nullable()
  }))
});
