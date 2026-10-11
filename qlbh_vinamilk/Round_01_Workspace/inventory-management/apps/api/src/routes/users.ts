/**
 * Route Handler: Quản lý Người dùng (User Management - RBAC)
 * Tuân thủ bảo mật:
 * 1. Bắt buộc quyền Quản trị viên (ADMIN): USER thông thường gọi các API này nhận HTTP 403 FORBIDDEN.
 * 2. Bảo vệ Admin cuối cùng: Không bao giờ cho phép vô hiệu hóa (khóa) hoặc hạ quyền Quản trị viên hoạt động cuối cùng.
 * 3. Thu hồi phiên tức thì: Khi khóa tài khoản hoặc reset mật khẩu, toàn bộ phiên (sessions) của user lập tức bị revoke.
 * 4. Không dùng mật khẩu cố định '123456': Cho phép nhập mật khẩu đạt chuẩn (>= 8 ký tự) hoặc tự sinh mật khẩu ngẫu nhiên mạnh.
 * 5. Bắt buộc đặt cờ must_change_password = 1 đối với tài khoản mới và sau khi reset mật khẩu.
 * 6. Ghi nhật ký kiểm toán (audit_logs) đầy đủ.
 */

import {
  CreateUserRequestSchema,
  UpdateUserStatusRequestSchema,
  UpdateUserRequestSchema,
  ResetPasswordRequestSchema
} from "@inventory/shared";
import {
  hashPassword,
  generateSecureRandomPassword,
  isCommonPassword
} from "../security/password.js";
import { getClientIp } from "../security/rateLimit.js";
import { logAuditEvent } from "../security/audit.js";
import { authenticate } from "../middleware/auth.js";
import { createErrorResponse, createSuccessResponse } from "../middleware/errorHandler.js";

export async function handleListUsers(request: Request, env: any, requestId: string): Promise<Response> {
  const { errorResponse } = await authenticate(request, env, requestId, {
    requireRole: "ADMIN"
  });
  if (errorResponse) {
    return errorResponse;
  }

  const result = await env.DB.prepare(
    `SELECT id, username, role, full_name, must_change_password, is_active, created_at, updated_at
     FROM users
     ORDER BY id ASC`
  ).all();

  const users = (result.results || []).map((row: any) => ({
    id: row.id,
    username: row.username,
    role: row.role,
    full_name: row.full_name,
    must_change_password: Boolean(row.must_change_password),
    is_active: Boolean(row.is_active),
    created_at: row.created_at,
    updated_at: row.updated_at
  }));

  return createSuccessResponse(users, 200, { requestId });
}

export async function handleCreateUser(request: Request, env: any, requestId: string): Promise<Response> {
  const clientIp = getClientIp(request);
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    requireRole: "ADMIN"
  });
  if (errorResponse) {
    return errorResponse;
  }

  let body: any;
  try {
    body = await request.json();
  } catch {
    return createErrorResponse({
      status: 400,
      code: "INVALID_JSON",
      message: "Dữ liệu yêu cầu không đúng định dạng JSON.",
      requestId,
      env
    });
  }

  const parseResult = CreateUserRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu tạo người dùng không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  const { username, password, role, full_name } = parseResult.data;

  // Kiểm tra trùng lặp tên đăng nhập
  const existing = await env.DB.prepare("SELECT id FROM users WHERE username = ?")
    .bind(username)
    .first();

  if (existing) {
    return createErrorResponse({
      status: 409,
      code: "USERNAME_EXISTS",
      message: `Tên đăng nhập '${username}' đã tồn tại trong hệ thống. Vui lòng chọn tên khác.`,
      requestId,
      env
    });
  }

  // Mật khẩu: Sử dụng mật khẩu Admin chỉ định (đã qua schema validation) hoặc tự sinh mật khẩu ngẫu nhiên mạnh
  let tempPassword = password;
  if (!tempPassword || tempPassword.trim().length === 0) {
    tempPassword = generateSecureRandomPassword(12);
  } else {
    if (isCommonPassword(tempPassword)) {
      return createErrorResponse({
        status: 400,
        code: "WEAK_PASSWORD",
        message: "Mật khẩu tạm thời nằm trong danh sách không an toàn. Vui lòng chọn mật khẩu mạnh hơn.",
        requestId,
        env
      });
    }
  }

  const hashedPassword = await hashPassword(tempPassword);

  // Bắt buộc must_change_password = 1 cho tài khoản mới
  const insertResult = await env.DB.prepare(
    `INSERT INTO users (username, password_hash, role, full_name, must_change_password, is_active, created_at, updated_at)
     VALUES (?, ?, ?, ?, 1, 1, datetime('now', 'utc'), datetime('now', 'utc'))`
  )
    .bind(username, hashedPassword, role, full_name)
    .run();

  const idRow = await env.DB.prepare("SELECT last_insert_rowid() as id").first();
  const newUserId = idRow?.id || insertResult.meta?.last_row_id;

  // Ghi nhật ký kiểm toán
  await logAuditEvent(env.DB, {
    userId: auth!.user.id,
    action: "USER_CREATED",
    targetType: "USER",
    targetId: newUserId,
    details: { username, role, full_name },
    ipAddress: clientIp
  });

  return createSuccessResponse(
    {
      id: newUserId,
      username,
      role,
      full_name,
      temporary_password: tempPassword,
      must_change_password: true,
      is_active: true
    },
    201,
    { requestId, message: "Tạo người dùng mới thành công" }
  );
}

export async function handleUpdateUser(
  request: Request,
  env: any,
  requestId: string,
  targetUserId: number
): Promise<Response> {
  const clientIp = getClientIp(request);
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    requireRole: "ADMIN"
  });
  if (errorResponse) {
    return errorResponse;
  }

  let body: any;
  try {
    body = await request.json();
  } catch {
    return createErrorResponse({
      status: 400,
      code: "INVALID_JSON",
      message: "Dữ liệu yêu cầu không đúng định dạng JSON.",
      requestId,
      env
    });
  }

  const parseResult = UpdateUserRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu cập nhật người dùng không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  const targetUser = await env.DB.prepare("SELECT id, username, role, full_name, is_active FROM users WHERE id = ?")
    .bind(targetUserId)
    .first();

  if (!targetUser) {
    return createErrorResponse({
      status: 404,
      code: "USER_NOT_FOUND",
      message: "Người dùng cần cập nhật không tồn tại.",
      requestId,
      env
    });
  }

  const { full_name, role } = parseResult.data;

  // BẢO VỆ ADMIN HOẠT ĐỘNG CUỐI CÙNG: Không cho phép hạ quyền Admin cuối cùng xuống USER
  if (role && role === "USER" && targetUser.role === "ADMIN") {
    const activeAdminCountRow = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM users WHERE role = 'ADMIN' AND is_active = 1"
    ).first();

    const activeAdminCount = activeAdminCountRow?.count || 0;
    if (activeAdminCount <= 1) {
      return createErrorResponse({
        status: 400,
        code: "CANNOT_DEMOTE_LAST_ADMIN",
        message: "Không thể hạ quyền Quản trị viên hoạt động cuối cùng của hệ thống.",
        requestId,
        env
      });
    }
  }

  const updatedFullName = full_name !== undefined ? full_name : targetUser.full_name;
  const updatedRole = role !== undefined ? role : targetUser.role;

  await env.DB.prepare(
    "UPDATE users SET full_name = ?, role = ?, updated_at = datetime('now', 'utc') WHERE id = ?"
  )
    .bind(updatedFullName, updatedRole, targetUserId)
    .run();

  await logAuditEvent(env.DB, {
    userId: auth!.user.id,
    action: "USER_UPDATED",
    targetType: "USER",
    targetId: targetUserId,
    details: { full_name: updatedFullName, role: updatedRole },
    ipAddress: clientIp
  });

  return createSuccessResponse(
    {
      id: targetUserId,
      username: targetUser.username,
      full_name: updatedFullName,
      role: updatedRole
    },
    200,
    { requestId, message: "Cập nhật thông tin người dùng thành công" }
  );
}

export async function handleUpdateUserStatus(
  request: Request,
  env: any,
  requestId: string,
  targetUserId: number
): Promise<Response> {
  const clientIp = getClientIp(request);
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    requireRole: "ADMIN"
  });
  if (errorResponse) {
    return errorResponse;
  }

  let body: any;
  try {
    body = await request.json();
  } catch {
    return createErrorResponse({
      status: 400,
      code: "INVALID_JSON",
      message: "Dữ liệu yêu cầu không đúng định dạng JSON.",
      requestId,
      env
    });
  }

  const parseResult = UpdateUserStatusRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu trạng thái không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  const { is_active } = parseResult.data;

  const targetUser = await env.DB.prepare("SELECT id, username, role, is_active FROM users WHERE id = ?")
    .bind(targetUserId)
    .first();

  if (!targetUser) {
    return createErrorResponse({
      status: 404,
      code: "USER_NOT_FOUND",
      message: "Người dùng cần cập nhật không tồn tại.",
      requestId,
      env
    });
  }

  // BẢO VỆ ADMIN HOẠT ĐỘNG CUỐI CÙNG: Không cho phép khóa Admin cuối cùng
  if (!is_active && targetUser.role === "ADMIN") {
    const activeAdminCountRow = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM users WHERE role = 'ADMIN' AND is_active = 1"
    ).first();

    const activeAdminCount = activeAdminCountRow?.count || 0;
    if (activeAdminCount <= 1) {
      return createErrorResponse({
        status: 400,
        code: "CANNOT_LOCK_LAST_ADMIN",
        message: "Không thể khóa tài khoản Quản trị viên hoạt động cuối cùng của hệ thống.",
        requestId,
        env
      });
    }
  }

  // Cập nhật trạng thái
  await env.DB.prepare(
    "UPDATE users SET is_active = ?, updated_at = datetime('now', 'utc') WHERE id = ?"
  )
    .bind(is_active ? 1 : 0, targetUserId)
    .run();

  // THU HỒI PHIÊN TỨC THÌ (REVOCATION): Nếu khóa tài khoản, revoke toàn bộ session của user đó ngay
  if (!is_active) {
    await env.DB.prepare(
      "UPDATE sessions SET revoked_at = datetime('now', 'utc') WHERE user_id = ? AND revoked_at IS NULL"
    )
      .bind(targetUserId)
      .run();
  }

  // Ghi nhật ký kiểm toán
  await logAuditEvent(env.DB, {
    userId: auth!.user.id,
    action: is_active ? "USER_UNLOCKED" : "USER_LOCKED",
    targetType: "USER",
    targetId: targetUserId,
    details: { is_active, sessions_revoked: !is_active },
    ipAddress: clientIp
  });

  return createSuccessResponse(
    {
      id: targetUserId,
      username: targetUser.username,
      is_active,
      sessions_revoked: !is_active
    },
    200,
    {
      requestId,
      message: is_active ? "Đã mở khóa tài khoản thành công" : "Đã khóa tài khoản và thu hồi toàn bộ phiên hoạt động"
    }
  );
}

export async function handleResetPassword(
  request: Request,
  env: any,
  requestId: string,
  targetUserId: number
): Promise<Response> {
  const clientIp = getClientIp(request);
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    requireRole: "ADMIN"
  });
  if (errorResponse) {
    return errorResponse;
  }

  let body: any = {};
  try {
    const text = await request.text();
    if (text.trim().length > 0) {
      body = JSON.parse(text);
    }
  } catch {
    return createErrorResponse({
      status: 400,
      code: "INVALID_JSON",
      message: "Dữ liệu yêu cầu không đúng định dạng JSON.",
      requestId,
      env
    });
  }

  const parseResult = ResetPasswordRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu đặt lại mật khẩu không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  // Nếu Admin không cung cấp mật khẩu tạm -> Sinh mật khẩu ngẫu nhiên mạnh
  let tempPassword = parseResult.data.temp_password;
  if (!tempPassword || tempPassword.trim().length === 0) {
    tempPassword = generateSecureRandomPassword(12);
  } else {
    if (isCommonPassword(tempPassword)) {
      return createErrorResponse({
        status: 400,
        code: "WEAK_PASSWORD",
        message: "Mật khẩu tạm thời nằm trong danh sách không an toàn. Vui lòng chọn mật khẩu mạnh hơn.",
        requestId,
        env
      });
    }
  }

  const targetUser = await env.DB.prepare("SELECT id, username FROM users WHERE id = ?")
    .bind(targetUserId)
    .first();

  if (!targetUser) {
    return createErrorResponse({
      status: 404,
      code: "USER_NOT_FOUND",
      message: "Người dùng cần đặt lại mật khẩu không tồn tại.",
      requestId,
      env
    });
  }

  const hashedPassword = await hashPassword(tempPassword);

  // Cập nhật mật khẩu tạm và bắt buộc must_change_password = 1
  await env.DB.prepare(
    "UPDATE users SET password_hash = ?, must_change_password = 1, updated_at = datetime('now', 'utc') WHERE id = ?"
  )
    .bind(hashedPassword, targetUserId)
    .run();

  // THU HỒI PHIÊN TỨC THÌ (REVOCATION): Revoke toàn bộ session cũ của user này
  await env.DB.prepare(
    "UPDATE sessions SET revoked_at = datetime('now', 'utc') WHERE user_id = ? AND revoked_at IS NULL"
  )
    .bind(targetUserId)
    .run();

  // Ghi nhật ký kiểm toán
  await logAuditEvent(env.DB, {
    userId: auth!.user.id,
    action: "USER_PASSWORD_RESET",
    targetType: "USER",
    targetId: targetUserId,
    details: { must_change_password_set: true, sessions_revoked: true },
    ipAddress: clientIp
  });

  return createSuccessResponse(
    {
      id: targetUserId,
      username: targetUser.username,
      temporary_password: tempPassword,
      must_change_password: true,
      sessions_revoked: true
    },
    200,
    {
      requestId,
      message: "Đặt lại mật khẩu thành công. Toàn bộ phiên làm việc cũ đã bị thu hồi."
    }
  );
}
