/**
 * Security: Ghi Nhật ký Kiểm toán Thao tác Người dùng (Audit Logging)
 * Tuân thủ bảo mật:
 * 1. Ghi nhận toàn bộ thao tác quan trọng: Đăng nhập thành công/thất bại, Đăng xuất, Đổi mật khẩu,
 *    Khởi tạo hệ thống (Bootstrap), Tạo người dùng, Cập nhật trạng thái, Đặt lại mật khẩu.
 * 2. Lưu trữ đầy đủ: user_id, action, target_type, target_id, details (JSON), ip_address, created_at.
 * 3. Bất biến (Append-only): Không cho phép chỉnh sửa hoặc xóa log kiểm toán.
 */

export interface AuditEventParams {
  userId?: number | null;
  action: string;
  targetType: string;
  targetId?: string | number | null;
  details?: Record<string, any> | null;
  ipAddress?: string | null;
}

export async function logAuditEvent(db: any, params: AuditEventParams): Promise<void> {
  if (!db || typeof db.prepare !== "function") {
    return;
  }

  try {
    const detailsStr = params.details ? JSON.stringify(params.details) : null;
    const targetIdStr = params.targetId != null ? String(params.targetId) : null;

    await db
      .prepare(
        `INSERT INTO audit_logs (user_id, action, target_type, target_id, details, ip_address, created_at)
         VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'utc'))`
      )
      .bind(
        params.userId ?? null,
        params.action,
        params.targetType,
        targetIdStr,
        detailsStr,
        params.ipAddress ?? null
      )
      .run();
  } catch (err: any) {
    // Không làm gián đoạn luồng nghiệp vụ chính nếu ghi log thất bại
    console.warn("[AUDIT_LOG_ERROR]:", err?.message || String(err));
  }
}
