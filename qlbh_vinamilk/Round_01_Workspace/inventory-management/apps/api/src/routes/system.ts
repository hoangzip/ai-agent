import { BootstrapAdminRequestSchema } from "@inventory/shared";
import { createSuccessResponse, createErrorResponse } from "../middleware/errorHandler.js";
import { bootstrapAdmin } from "../security/bootstrap.js";
import { getClientIp } from "../security/rateLimit.js";

export async function handleSystemInfo(request: Request, env: any, requestId: string): Promise<Response> {
  let dbStatus: "connected" | "not_configured" | "unavailable" = "not_configured";
  let dbMessage: string | undefined = "Chưa cấu hình D1 database binding trong môi trường hiện tại";

  if (env?.DB) {
    try {
      // Thực hiện kiểm tra kết nối D1 thực tế
      await env.DB.prepare("SELECT 1").first();
      dbStatus = "connected";
      dbMessage = undefined;
    } catch (err: any) {
      dbStatus = "unavailable";
      dbMessage = "D1 binding tồn tại nhưng không thể thực thi truy vấn kiểm tra";
    }
  }

  const systemData = {
    service: "inventory-management-backend",
    version: "0.4.0",
    round: "05/10 – Stock Reconciliation & Comparison Engine",
    environment: env?.ENVIRONMENT || "production",
    timezone: env?.APP_TIMEZONE || "Asia/Ho_Chi_Minh",
    timestamp: new Date().toISOString(),
    database: {
      provider: "Cloudflare D1 (SQLite Engine)",
      status: dbStatus,
      ...(dbMessage ? { message: dbMessage } : {})
    },
    modules: {
      auth: "ACTIVE",
      users: "ACTIVE",
      inventory_import: "ACTIVE",
      inventory_staging: "ACTIVE",
      comparison_engine: "ACTIVE",
      product_history: "ACTIVE",
      ui_dashboard: "ROUND_06_PLANNED",
      gdrive_sync: "ROUND_07_PLANNED",
      soft_delete: "ACTIVE"
    },
    features: {
      multi_snapshot_per_day: "SUPPORTED",
      natural_key_enforcement: "SUPPORTED",
      leading_zero_sku_preservation: "SUPPORTED",
      soft_delete_foundation: "SUPPORTED",
      audit_logging_schema: "SUPPORTED",
      zod_contract_validation: "SUPPORTED",
      pbkdf2_password_hashing: "SUPPORTED",
      session_token_hashing: "SUPPORTED",
      rbac_admin_user_enforcement: "SUPPORTED",
      mandatory_first_login_change_password: "SUPPORTED",
      auth_rate_limiting: "SUPPORTED",
      csrf_origin_protection: "SUPPORTED",
      excel_15_column_validation: "SUPPORTED",
      row2_summary_cross_check: "SUPPORTED",
      three_level_deduplication: "SUPPORTED",
      staging_to_completed_workflow: "SUPPORTED",
      batch_excel_import: "SUPPORTED",
      multipart_and_json_base64_upload: "SUPPORTED"
    }
  };

  return createSuccessResponse(systemData, 200, { requestId });
}

export async function handleBootstrap(request: Request, env: any, requestId: string): Promise<Response> {
  const clientIp = getClientIp(request);

  if (!env?.DB) {
    return createErrorResponse({
      status: 503,
      code: "DATABASE_UNAVAILABLE",
      message: "D1 database chưa sẵn sàng để thực hiện khởi tạo hệ thống.",
      requestId,
      env
    });
  }

  // 1. BẮT BUỘC SỬA LỖI P0: Không cho phép tạo Admin trái phép khi BOOTSTRAP_TOKEN thiếu hoặc chưa cấu hình
  const bootstrapToken = env?.BOOTSTRAP_TOKEN;
  if (!bootstrapToken || typeof bootstrapToken !== "string" || bootstrapToken.trim() === "") {
    return createErrorResponse({
      status: 403,
      code: "BOOTSTRAP_DISABLED",
      message: "Quy trình khởi tạo Admin ban đầu bị vô hiệu hóa vì BOOTSTRAP_TOKEN chưa được cấu hình trên máy chủ.",
      requestId,
      env
    });
  }

  const providedToken =
    request.headers.get("X-Bootstrap-Token") ||
    request.headers.get("X-Setup-Token") ||
    (request.headers.get("Authorization")?.startsWith("Bearer ")
      ? request.headers.get("Authorization")?.substring(7).trim()
      : null);

  if (!providedToken || providedToken !== bootstrapToken.trim()) {
    return createErrorResponse({
      status: 401,
      code: "INVALID_BOOTSTRAP_TOKEN",
      message: "Mã khóa khởi tạo ban đầu (Bootstrap Token) không chính xác hoặc bị thiếu.",
      requestId,
      env
    });
  }


  // 2. Parse body (tùy chọn)
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

  const parseResult = BootstrapAdminRequestSchema.safeParse(body);
  if (!parseResult.success) {
    return createErrorResponse({
      status: 400,
      code: "VALIDATION_ERROR",
      message: parseResult.error.errors[0]?.message || "Dữ liệu khởi tạo không hợp lệ.",
      details: parseResult.error.format(),
      requestId,
      env
    });
  }

  const result = await bootstrapAdmin(env.DB, {
    username: parseResult.data.username,
    password: parseResult.data.password || env?.ADMIN_INITIAL_PASSWORD,
    fullName: parseResult.data.full_name,
    ipAddress: clientIp
  });

  if (!result.success) {
    return createErrorResponse({
      status: 403,
      code: "BOOTSTRAP_ALREADY_COMPLETED",
      message: result.error || "Không thể thực hiện khởi tạo hệ thống.",
      requestId,
      env
    });
  }

  return createSuccessResponse(
    {
      user: result.user,
      temporary_password: result.temporaryPassword,
      must_change_password: true,
      message: "Khởi tạo tài khoản Quản trị viên thành công. Vui lòng lưu lại mật khẩu tạm này và đổi mật khẩu ở lần đăng nhập đầu tiên."
    },
    201,
    { requestId, message: "Khởi tạo hệ thống thành công" }
  );
}
