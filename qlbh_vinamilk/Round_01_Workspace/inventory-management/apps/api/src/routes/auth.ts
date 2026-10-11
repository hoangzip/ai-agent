/**
 * Route Handler: Authentication (Đăng nhập, Đăng xuất, Đổi mật khẩu, Profile)
 * Tuân thủ bảo mật:
 * 1. Chống Brute-force & DoS: Rate limiting tối đa 5 lần thử sai / 15 phút (HTTP 429).
 * 2. Chống User Enumeration: Sai user hoặc sai password đều trả về 401 với cùng thông điệp lỗi.
 *    Xác minh mật khẩu trước khi kiểm tra tài khoản bị khóa (chống rò rỉ trạng thái tài khoản).
 * 3. Phiên làm việc an toàn: Chỉ lưu băm SHA-256 của token trong D1, cấp Cookie HttpOnly & Bearer.
 * 4. Thu hồi phiên tức thì khi Đăng xuất: Đánh dấu revoked_at và xóa Cookie.
 * 5. Bắt buộc đổi mật khẩu lần đầu và kiểm tra blacklist mật khẩu yếu.
 * 6. Ghi nhật ký kiểm toán (audit_logs) đầy đủ.
 */

import {
  LoginRequestSchema,
  ChangePasswordRequestSchema
} from "@inventory/shared";
import { hashPassword, verifyPassword, isCommonPassword } from "../security/password.js";
import {
  createSessionCookie,
  clearSessionCookie,
  extractSessionToken,
  hashSessionToken,
  SESSION_DURATION_SECONDS
} from "../security/session.js";
import {
  checkLoginRateLimit,
  recordFailedLoginAttempt,
  clearLoginRateLimit,
  getClientIp
} from "../security/rateLimit.js";
import { logAuditEvent } from "../security/audit.js";
import { authenticate } from "../middleware/auth.js";
import { createErrorResponse, createSuccessResponse } from "../middleware/errorHandler.js";

export async function handleLogin(request: Request, env: any, requestId: string): Promise<Response> {
  const clientIp = getClientIp(request);

  if (!env?.DB) {
    return createErrorResponse({
      status: 503,
      code: "DATABASE_UNAVAILABLE",
      message: "D1 database chưa sẵn sàng để thực hiện xác thực.",
      requestId,
      env
    });
  }

  // 1. Kiểm tra Rate Limiting chống Brute Force (P1)
  const rateLimitStatus = await checkLoginRateLimit(clientIp);
  if (!rateLimitStatus.allowed) {
    const response = createErrorResponse({
      status: 429,
      code: "TOO_MANY_REQUESTS",
      message: `Quá nhiều lần đăng nhập không thành công. Vui lòng thử lại sau ${Math.ceil(rateLimitStatus.retryAfterSeconds / 60)} phút.`,
      requestId,
      env
    });
    response.headers.set("Retry-After", String(rateLimitStatus.retryAfterSeconds));
    return response;
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

  const parseResult = LoginRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu đăng nhập không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  const { username, password } = parseResult.data;

  // 2. Truy vấn người dùng
  const user = await env.DB.prepare(
    "SELECT id, username, password_hash, role, full_name, must_change_password, is_active FROM users WHERE username = ?"
  )
    .bind(username)
    .first();

  // CHỐNG USER ENUMERATION: Không tồn tại user -> ghi nhận thất bại và trả 401
  if (!user) {
    await recordFailedLoginAttempt(clientIp);
    await logAuditEvent(env.DB, {
      action: "LOGIN_FAILED_NONEXISTENT_USER",
      targetType: "AUTH",
      details: { attempted_username: username },
      ipAddress: clientIp
    });

    return createErrorResponse({
      status: 401,
      code: "INVALID_CREDENTIALS",
      message: "Tên đăng nhập hoặc mật khẩu không chính xác.",
      requestId,
      env
    });
  }

  // 3. Xác thực mật khẩu qua PBKDF2 TRƯỚC (ngăn enumeration trạng thái khóa tài khoản)
  const isValid = await verifyPassword(password, user.password_hash);
  if (!isValid) {
    await recordFailedLoginAttempt(clientIp);
    await logAuditEvent(env.DB, {
      userId: user.id,
      action: "LOGIN_FAILED_WRONG_PASSWORD",
      targetType: "AUTH",
      targetId: user.id,
      details: { username: user.username },
      ipAddress: clientIp
    });

    return createErrorResponse({
      status: 401,
      code: "INVALID_CREDENTIALS",
      message: "Tên đăng nhập hoặc mật khẩu không chính xác.",
      requestId,
      env
    });
  }

  // 4. Nếu mật khẩu đúng, bây giờ mới kiểm tra xem tài khoản có bị khóa hay không
  if (user.is_active === 0 || user.is_active === false) {
    await logAuditEvent(env.DB, {
      userId: user.id,
      action: "LOGIN_BLOCKED_ACCOUNT_LOCKED",
      targetType: "USER",
      targetId: user.id,
      details: { username: user.username },
      ipAddress: clientIp
    });

    return createErrorResponse({
      status: 403,
      code: "ACCOUNT_LOCKED",
      message: "Tài khoản của bạn đã bị khóa bởi Quản trị viên. Vui lòng liên hệ hỗ trợ.",
      requestId,
      env
    });
  }

  // 5. Đăng nhập thành công -> Xóa bộ đếm rate-limit cho client IP này
  await clearLoginRateLimit(clientIp);

  // 6. Khởi tạo phiên làm việc mới
  const rawToken = crypto.randomUUID();
  const tokenHash = await hashSessionToken(rawToken);
  const expiresAt = new Date(Date.now() + SESSION_DURATION_SECONDS * 1000).toISOString();

  await env.DB.prepare(
    "INSERT INTO sessions (id, user_id, expires_at, created_at) VALUES (?, ?, ?, datetime('now', 'utc'))"
  )
    .bind(tokenHash, user.id, expiresAt)
    .run();

  // Ghi nhật ký kiểm toán đăng nhập thành công
  await logAuditEvent(env.DB, {
    userId: user.id,
    action: "LOGIN_SUCCESS",
    targetType: "USER",
    targetId: user.id,
    details: { username: user.username, role: user.role },
    ipAddress: clientIp
  });

  const responseData = {
    user: {
      id: user.id,
      username: user.username,
      role: user.role,
      full_name: user.full_name,
      must_change_password: Boolean(user.must_change_password),
      is_active: Boolean(user.is_active)
    },
    token: rawToken,
    expires_at: expiresAt
  };

  const response = createSuccessResponse(responseData, 200, {
    requestId,
    message: "Đăng nhập thành công"
  });

  // Đính kèm Set-Cookie HttpOnly (fail-safe Secure)
  const cookieHeader = createSessionCookie(rawToken, SESSION_DURATION_SECONDS, env);
  response.headers.append("Set-Cookie", cookieHeader);

  return response;
}

export async function handleLogout(request: Request, env: any, requestId: string): Promise<Response> {
  const clientIp = getClientIp(request);
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    allowMustChangePassword: true
  });
  if (errorResponse) {
    return errorResponse;
  }

  if (env?.DB && auth?.session?.id) {
    try {
      await env.DB.prepare("UPDATE sessions SET revoked_at = datetime('now', 'utc') WHERE id = ?")
        .bind(auth.session.id)
        .run();

      await logAuditEvent(env.DB, {
        userId: auth.user.id,
        action: "LOGOUT",
        targetType: "USER",
        targetId: auth.user.id,
        ipAddress: clientIp
      });
    } catch (err) {
      console.warn("[LOGOUT_REVOKE_ERROR]:", err);
    }
  }

  const response = createSuccessResponse(
    { logged_out: true },
    200,
    { requestId, message: "Đăng xuất thành công" }
  );

  // Xóa Cookie trên trình duyệt
  response.headers.append("Set-Cookie", clearSessionCookie(env));
  return response;
}


export async function handleChangePassword(request: Request, env: any, requestId: string): Promise<Response> {
  const clientIp = getClientIp(request);

  // Cho phép gọi khi must_change_password = true để đổi mật khẩu lần đầu
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    allowMustChangePassword: true
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

  const parseResult = ChangePasswordRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu đổi mật khẩu không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  const { current_password, new_password } = parseResult.data;

  if (isCommonPassword(new_password)) {
    return createErrorResponse({
      status: 400,
      code: "WEAK_PASSWORD",
      message: "Mật khẩu mới quá đơn giản hoặc nằm trong danh sách không an toàn. Vui lòng chọn mật khẩu mạnh hơn.",
      requestId,
      env
    });
  }

  // Lấy hash hiện tại trong database
  const user = await env.DB.prepare("SELECT password_hash FROM users WHERE id = ?")
    .bind(auth!.user.id)
    .first();

  if (!user) {
    return createErrorResponse({
      status: 404,
      code: "USER_NOT_FOUND",
      message: "Người dùng không tồn tại.",
      requestId,
      env
    });
  }

  const isOldMatch = await verifyPassword(current_password, user.password_hash);
  if (!isOldMatch) {
    return createErrorResponse({
      status: 400,
      code: "INVALID_CURRENT_PASSWORD",
      message: "Mật khẩu hiện tại không chính xác.",
      requestId,
      env
    });
  }

  if (current_password === new_password) {
    return createErrorResponse({
      status: 400,
      code: "PASSWORD_UNCHANGED",
      message: "Mật khẩu mới phải khác với mật khẩu hiện tại.",
      requestId,
      env
    });
  }

  const newHash = await hashPassword(new_password);

  // Cập nhật mật khẩu mới và xóa cờ must_change_password
  await env.DB.prepare(
    "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = datetime('now', 'utc') WHERE id = ?"
  )
    .bind(newHash, auth!.user.id)
    .run();

  // Ghi nhật ký kiểm toán
  await logAuditEvent(env.DB, {
    userId: auth!.user.id,
    action: "PASSWORD_CHANGED",
    targetType: "USER",
    targetId: auth!.user.id,
    details: { must_change_password_cleared: true },
    ipAddress: clientIp
  });

  return createSuccessResponse(
    {
      updated: true,
      must_change_password: false
    },
    200,
    {
      requestId,
      message: "Đổi mật khẩu thành công. Bạn có thể sử dụng tất cả tính năng của hệ thống."
    }
  );
}

export async function handleGetMe(request: Request, env: any, requestId: string): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    allowMustChangePassword: true
  });
  if (errorResponse) {
    return errorResponse;
  }

  return createSuccessResponse(auth!.user, 200, { requestId });
}
