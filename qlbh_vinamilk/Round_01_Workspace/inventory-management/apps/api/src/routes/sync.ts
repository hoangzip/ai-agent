/**
 * Routes: Quản lý & Thực thi Đồng bộ Google Drive (Sync Routes - Round 07 Fix 01)
 * File: apps/api/src/routes/sync.ts
 */

import { Env } from "../index.js";
import { authenticate } from "../middleware/auth.js";
import { createSuccessResponse, createErrorResponse } from "../middleware/errorHandler.js";
import { getSyncStatus, getSyncRuns, triggerSync } from "../services/syncService.js";

/**
 * GET /api/v1/sync/status
 * Lấy trạng thái nguồn đồng bộ, driver mode và kiểm tra kết nối LIVE thực tế
 */
export async function handleGetSyncStatus(
  request: Request,
  env: Env,
  requestId: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }
  if (!auth) {
    return createErrorResponse({
      status: 401,
      code: "UNAUTHORIZED",
      message: "Yêu cầu đăng nhập để xem trạng thái đồng bộ.",
      requestId,
      env
    });
  }

  try {
    const status = await getSyncStatus(env.DB, env);
    return createSuccessResponse(status, 200, { requestId });
  } catch (err: any) {
    return createErrorResponse({
      status: 500,
      code: "SYNC_STATUS_ERROR",
      message: "Không thể lấy thông tin trạng thái đồng bộ: " + (err.message || String(err)),
      requestId,
      env
    });
  }
}

/**
 * GET /api/v1/sync/runs hoặc /api/v1/sync/history
 * Lấy lịch sử các đợt đồng bộ có phân trang
 */
export async function handleGetSyncRuns(
  request: Request,
  env: Env,
  requestId: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }
  if (!auth) {
    return createErrorResponse({
      status: 401,
      code: "UNAUTHORIZED",
      message: "Yêu cầu đăng nhập để xem lịch sử đồng bộ.",
      requestId,
      env
    });
  }

  const url = new URL(request.url);
  const page = parseInt(url.searchParams.get("page") || "1", 10);
  const limit = parseInt(url.searchParams.get("limit") || "20", 10);

  try {
    const result = await getSyncRuns(env.DB, { page, limit });
    return createSuccessResponse(result, 200, { requestId });
  } catch (err: any) {
    return createErrorResponse({
      status: 500,
      code: "SYNC_RUNS_ERROR",
      message: "Không thể lấy lịch sử đợt chạy đồng bộ: " + (err.message || String(err)),
      requestId,
      env
    });
  }
}

/**
 * POST /api/v1/sync/trigger hoặc /api/v1/sync/run
 * Kích hoạt đồng bộ tức thời từ Google Drive (có Concurrency Lock)
 */
export async function handleTriggerSync(
  request: Request,
  env: Env,
  requestId: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }
  if (!auth) {
    return createErrorResponse({
      status: 401,
      code: "UNAUTHORIZED",
      message: "Yêu cầu đăng nhập để kích hoạt đồng bộ.",
      requestId,
      env
    });
  }

  try {
    const syncReport = await triggerSync(env.DB, env, {
      triggeredBy: "MANUAL",
      userId: auth.user.id
    });

    return createSuccessResponse(
      syncReport,
      200,
      {
        requestId,
        message:
          syncReport.status === "COMPLETED"
            ? "Đồng bộ dữ liệu từ Google Drive hoàn tất thành công."
            : "Đồng bộ dữ liệu Google Drive hoàn tất (có file cảnh báo hoặc lỗi)."
      }
    );
  } catch (err: any) {
    if (err.code === "SYNC_ALREADY_RUNNING") {
      return createErrorResponse({
        status: 409,
        code: "SYNC_ALREADY_RUNNING",
        message: err.message,
        requestId,
        env
      });
    }

    return createErrorResponse({
      status: 500,
      code: "SYNC_TRIGGER_ERROR",
      message: "Không thể thực hiện đồng bộ Google Drive: " + (err.message || String(err)),
      requestId,
      env
    });
  }
}

/**
 * POST /api/v1/sync/scheduled hoặc /api/v1/sync/webhook
 * Điểm cuối cho scheduler định kỳ (Cloudflare Cron, Google Apps Script Webhook)
 */
export async function handleScheduledSync(
  request: Request,
  env: Env,
  requestId: string
): Promise<Response> {
  const authHeader = request.headers.get("Authorization");
  const webhookSecret = request.headers.get("X-Webhook-Secret");
  const origin = request.headers.get("Origin");

  // Kiểm tra Origin nếu request đến từ trình duyệt web (ngăn chặn tấn công từ bên ngoài)
  if (origin) {
    const allowedOrigins = (env.ALLOWED_ORIGINS || "http://localhost:3000,http://localhost:5173")
      .split(",")
      .map((o) => o.trim());
    if (!allowedOrigins.includes(origin)) {
      return createErrorResponse({
        status: 403,
        code: "FORBIDDEN_ORIGIN",
        message: "Nguồn gốc request (Origin) không được phép truy cập endpoint đồng bộ theo lịch.",
        requestId,
        env
      });
    }
  }

  // P1-01 FAIL-CLOSED: Bắt buộc phải có cấu hình SYNC_WEBHOOK_SECRET ngoài môi trường
  // Tuyệt đối không fallback sang BOOTSTRAP_TOKEN hay chuỗi hardcode
  const expectedSecret = (env as any).SYNC_WEBHOOK_SECRET;
  if (!expectedSecret || typeof expectedSecret !== "string" || expectedSecret.trim() === "") {
    return createErrorResponse({
      status: 401,
      code: "UNCONFIGURED_WEBHOOK_SECRET",
      message: "Chưa cấu hình biến môi trường SYNC_WEBHOOK_SECRET. Endpoint bị khóa bảo mật (Fail-closed).",
      requestId,
      env
    });
  }

  // Rút trích secret cung cấp từ header
  let providedSecret: string | null = null;
  if (webhookSecret) {
    providedSecret = webhookSecret.trim();
  } else if (authHeader) {
    if (authHeader.startsWith("Bearer ")) {
      providedSecret = authHeader.substring(7).trim();
    } else {
      providedSecret = authHeader.trim();
    }
  }

  if (!providedSecret) {
    return createErrorResponse({
      status: 401,
      code: "UNAUTHORIZED_CRON",
      message: "Thiếu thông tin xác thực webhook secret để kích hoạt lịch đồng bộ.",
      requestId,
      env
    });
  }

  if (providedSecret !== expectedSecret.trim()) {
    return createErrorResponse({
      status: 401,
      code: "INVALID_WEBHOOK_SECRET",
      message: "Webhook secret không hợp lệ.",
      requestId,
      env
    });
  }

  try {
    const syncReport = await triggerSync(env.DB, env, {
      triggeredBy: "SCHEDULED",
      userId: 1
    });

    return createSuccessResponse(syncReport, 200, {
      requestId,
      message: "Kích hoạt chu kỳ đồng bộ định kỳ thành công."
    });
  } catch (err: any) {
    if (err.code === "SYNC_ALREADY_RUNNING") {
      return createErrorResponse({
        status: 409,
        code: "SYNC_ALREADY_RUNNING",
        message: err.message,
        requestId,
        env
      });
    }

    return createErrorResponse({
      status: 500,
      code: "SCHEDULED_SYNC_ERROR",
      message: "Lỗi chu kỳ đồng bộ định kỳ: " + (err.message || String(err)),
      requestId,
      env
    });
  }
}
