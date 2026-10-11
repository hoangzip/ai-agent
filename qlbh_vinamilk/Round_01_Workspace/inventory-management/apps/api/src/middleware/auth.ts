/**
 * Middleware: Xác thực (Authentication) & Phân quyền (RBAC)
 * Tuân thủ bảo mật:
 * 1. Bắt buộc đăng nhập với mọi endpoint được bảo vệ (Trả về 401 UNAUTHORIZED).
 * 2. Phân quyền chặt chẽ: USER không thể gọi API dành riêng cho ADMIN (Trả về 403 FORBIDDEN).
 * 3. Chặn cưỡng chế cờ must_change_password: Nếu chưa đổi mật khẩu lần đầu, chặn 100% các API
 *    nghiệp vụ cho đến khi đổi mật khẩu thành công.
 * 4. Thu hồi phiên tức thì: Khi tài khoản bị khóa hoặc phiên bị revoked trong DB, từ chối ngay lập tức.
 */

import { extractSessionToken, hashSessionToken } from "../security/session.js";
import { createErrorResponse } from "./errorHandler.js";

export interface AuthContext {
  user: {
    id: number;
    username: string;
    role: "ADMIN" | "USER";
    full_name: string;
    must_change_password: boolean;
    is_active: boolean;
  };
  session: {
    id: string; // token_hash
    user_id: number;
    expires_at: string;
    revoked_at: string | null;
  };
  token: string;
}

export interface AuthOptions {
  requireRole?: "ADMIN" | "USER";
  allowMustChangePassword?: boolean;
}

export async function authenticate(
  request: Request,
  env: any,
  requestId: string,
  options?: AuthOptions
): Promise<{ auth?: AuthContext; errorResponse?: Response }> {
  const authHeader = request.headers.get("Authorization");
  const isBearerAuth = Boolean(authHeader && authHeader.startsWith("Bearer "));

  // CSRF PROTECTION: Nếu xác thực bằng Cookie (từ trình duyệt) đối với các phương thức thay đổi trạng thái (POST/PUT/PATCH/DELETE)
  // Bắt buộc xác minh Origin/Referer phải thuộc allowlist.
  if (!isBearerAuth) {
    const unsafeMethods = ["POST", "PUT", "PATCH", "DELETE"];
    if (unsafeMethods.includes(request.method.toUpperCase())) {
      const origin = request.headers.get("Origin");
      const referer = request.headers.get("Referer");

      let requestOrigin: string | null = null;
      if (origin) {
        try {
          requestOrigin = new URL(origin).origin;
        } catch {
          requestOrigin = null;
        }
      } else if (referer) {
        try {
          requestOrigin = new URL(referer).origin;
        } catch {
          requestOrigin = null;
        }
      }

      if (!requestOrigin) {
        return {
          errorResponse: createErrorResponse({
            status: 403,
            code: "CSRF_PROTECTION_FAILED",
            message: "Yêu cầu bị từ chối do thiếu thông tin Origin/Referer xác thực nguồn gốc trình duyệt.",
            requestId,
            env
          })
        };
      }

      const isDevOrTest = env?.ENVIRONMENT === "development" || env?.ENVIRONMENT === "test";
      const configuredOrigins: string[] = env?.ALLOWED_ORIGINS
        ? env.ALLOWED_ORIGINS.split(",").map((s: string) => s.trim()).filter(Boolean)
        : [];
      const defaultDev = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
      ];
      const allowedSet = new Set<string>([
        ...(isDevOrTest ? defaultDev : []),
        ...configuredOrigins
      ]);

      if (!allowedSet.has(requestOrigin)) {
        return {
          errorResponse: createErrorResponse({
            status: 403,
            code: "CSRF_PROTECTION_FAILED",
            message: "Yêu cầu bị từ chối do nguồn gốc (Origin) không nằm trong danh sách tin cậy.",
            requestId,
            env
          })
        };
      }
    }
  }

  const token = extractSessionToken(request);
  if (!token) {
    return {
      errorResponse: createErrorResponse({
        status: 401,
        code: "UNAUTHORIZED",
        message: "Yêu cầu đăng nhập để truy cập tài nguyên này. Vui lòng cung cấp Cookie hoặc Bearer Token.",
        requestId,
        env
      })
    };
  }

  if (!env?.DB) {
    return {
      errorResponse: createErrorResponse({
        status: 503,
        code: "DATABASE_UNAVAILABLE",
        message: "Cơ sở dữ liệu xác thực chưa sẵn sàng.",
        requestId,
        env
      })
    };
  }


  const tokenHash = await hashSessionToken(token);

  let record: any = null;
  try {
    record = await env.DB.prepare(
      `SELECT s.id as session_id, s.user_id, s.expires_at, s.revoked_at,
              u.id as user_id, u.username, u.role, u.full_name, u.must_change_password, u.is_active
       FROM sessions s
       JOIN users u ON s.user_id = u.id
       WHERE s.id = ?`
    )
      .bind(tokenHash)
      .first();
  } catch (err: any) {
    return {
      errorResponse: createErrorResponse({
        status: 500,
        code: "AUTH_QUERY_ERROR",
        message: "Lỗi truy vấn phiên làm việc.",
        details: err?.message,
        requestId,
        env
      })
    };
  }

  // 1. Kiểm tra phiên tồn tại
  if (!record) {
    return {
      errorResponse: createErrorResponse({
        status: 401,
        code: "INVALID_SESSION",
        message: "Phiên làm việc không tồn tại hoặc đã bị đăng xuất.",
        requestId,
        env
      })
    };
  }

  // 2. Kiểm tra phiên đã bị thu hồi (Revoked)
  if (record.revoked_at) {
    return {
      errorResponse: createErrorResponse({
        status: 401,
        code: "SESSION_REVOKED",
        message: "Phiên làm việc này đã bị thu hồi. Vui lòng đăng nhập lại.",
        requestId,
        env
      })
    };
  }

  // 3. Kiểm tra hạn phiên (Expiration)
  const expiresAt = new Date(record.expires_at).getTime();
  if (isNaN(expiresAt) || expiresAt < Date.now()) {
    return {
      errorResponse: createErrorResponse({
        status: 401,
        code: "SESSION_EXPIRED",
        message: "Phiên làm việc đã hết hạn. Vui lòng đăng nhập lại.",
        requestId,
        env
      })
    };
  }

  // 4. Kiểm tra tài khoản có bị khóa không
  if (record.is_active === 0 || record.is_active === false) {
    return {
      errorResponse: createErrorResponse({
        status: 403,
        code: "ACCOUNT_LOCKED",
        message: "Tài khoản của bạn đã bị khóa bởi Quản trị viên.",
        requestId,
        env
      })
    };
  }

  // 5. Kiểm tra cờ bắt buộc đổi mật khẩu lần đầu (must_change_password)
  const mustChange = Boolean(record.must_change_password);
  if (mustChange && !options?.allowMustChangePassword) {
    return {
      errorResponse: createErrorResponse({
        status: 403,
        code: "PASSWORD_CHANGE_REQUIRED",
        message: "Tài khoản đang sử dụng mật khẩu tạm thời. Bắt buộc phải đổi mật khẩu lần đầu trước khi tiếp tục.",
        details: {
          must_change_password: true,
          action_required: "POST /api/v1/auth/change-password"
        },
        requestId,
        env
      })
    };
  }

  // 6. Kiểm tra quyền RBAC (Role-Based Access Control)
  if (options?.requireRole === "ADMIN" && record.role !== "ADMIN") {
    return {
      errorResponse: createErrorResponse({
        status: 403,
        code: "FORBIDDEN_ADMIN_ONLY",
        message: "Quyền truy cập bị từ chối. Thao tác này chỉ dành riêng cho Quản trị viên (ADMIN).",
        requestId,
        env
      })
    };
  }

  const authContext: AuthContext = {
    user: {
      id: record.user_id,
      username: record.username,
      role: record.role,
      full_name: record.full_name,
      must_change_password: mustChange,
      is_active: Boolean(record.is_active)
    },
    session: {
      id: record.session_id,
      user_id: record.user_id,
      expires_at: record.expires_at,
      revoked_at: record.revoked_at
    },
    token
  };

  return { auth: authContext };
}
