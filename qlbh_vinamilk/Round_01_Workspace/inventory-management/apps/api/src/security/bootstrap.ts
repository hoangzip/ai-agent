/**
 * Security: Bootstrap Quản trị viên (Admin Bootstrap) an toàn
 * Tuân thủ bảo mật:
 * 1. KHÔNG tự động bootstrap ngầm trong API đăng nhập (/login).
 * 2. Chỉ thực thi khi hệ thống hoàn toàn CHƯA CÓ Quản trị viên hoạt động nào.
 * 3. Mật khẩu không hardcode '123456'. Phải lấy từ secret/input hoặc tự sinh ngẫu nhiên mạnh.
 * 4. Băm bằng PBKDF2 100.000 vòng lặp trước khi lưu vào SQLite D1.
 * 5. Bắt buộc đổi mật khẩu ngay lần đầu: must_change_password = 1.
 * 6. Ghi log kiểm toán thao tác khởi tạo hệ thống.
 */

import { hashPassword, generateSecureRandomPassword, isCommonPassword } from "./password.js";
import { logAuditEvent } from "./audit.js";

export interface BootstrapResult {
  success: boolean;
  user?: {
    id: number;
    username: string;
    role: string;
    full_name: string;
    must_change_password: boolean;
  };
  temporaryPassword?: string;
  error?: string;
}

export async function bootstrapAdmin(
  db: any,
  options?: {
    username?: string;
    password?: string;
    fullName?: string;
    ipAddress?: string;
  }
): Promise<BootstrapResult> {
  if (!db || typeof db.prepare !== "function") {
    return { success: false, error: "Database D1 không khả dụng." };
  }

  // 1. Kiểm tra xem đã có Admin hoạt động nào chưa
  const existing = await db
    .prepare("SELECT COUNT(*) as count FROM users WHERE role = 'ADMIN' AND is_active = 1")
    .first();

  if (existing && existing.count > 0) {
    return {
      success: false,
      error: "Hệ thống đã có Quản trị viên hoạt động. Quy trình khởi tạo ban đầu đã bị vô hiệu hóa để bảo vệ an toàn."
    };
  }

  const username = (options?.username || "admin").trim();
  const fullName = (options?.fullName || "Quản trị viên hệ thống").trim();

  let tempPassword = options?.password;
  if (!tempPassword || tempPassword.trim().length === 0) {
    // Tự sinh mật khẩu an toàn ngẫu nhiên 16 ký tự
    tempPassword = generateSecureRandomPassword(16);
  } else {
    // Kiểm tra chính sách mật khẩu
    if (tempPassword.length < 8) {
      return { success: false, error: "Mật khẩu Admin phải có tối thiểu 8 ký tự." };
    }
    if (isCommonPassword(tempPassword)) {
      return { success: false, error: "Mật khẩu Admin nằm trong danh sách mật khẩu yếu, không an toàn." };
    }
  }

  const hashedPassword = await hashPassword(tempPassword);

  const insertResult = await db
    .prepare(
      `INSERT INTO users (username, password_hash, role, full_name, must_change_password, is_active, created_at, updated_at)
       VALUES (?, ?, 'ADMIN', ?, 1, 1, datetime('now', 'utc'), datetime('now', 'utc'))`
    )
    .bind(username, hashedPassword, fullName)
    .run();

  const idRow = await db.prepare("SELECT last_insert_rowid() as id").first();
  const newUserId = idRow?.id || insertResult.meta?.last_row_id || 1;

  // Ghi nhật ký kiểm toán
  await logAuditEvent(db, {
    userId: newUserId,
    action: "SYSTEM_BOOTSTRAP_ADMIN",
    targetType: "USER",
    targetId: newUserId,
    details: { username, role: "ADMIN", bootstrapped: true },
    ipAddress: options?.ipAddress || null
  });

  return {
    success: true,
    user: {
      id: newUserId,
      username,
      role: "ADMIN",
      full_name: fullName,
      must_change_password: true
    },
    temporaryPassword: tempPassword
  };
}
