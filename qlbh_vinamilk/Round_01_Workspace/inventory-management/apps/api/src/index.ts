/**
 * Cloudflare Worker Entry Point: apps/api/src/index.ts
 * Nền tảng API REST quản lý và đối soát tồn kho (Revision 2 - Fix Review)
 */

import { handleCors, appendCorsHeaders } from "./middleware/cors.js";
import { createErrorResponse } from "./middleware/errorHandler.js";
import { handleHealthCheck } from "./routes/health.js";
import { handleSystemInfo, handleBootstrap } from "./routes/system.js";
import { handleUnimplementedModule } from "./routes/stubs.js";
import {
  handleLogin,
  handleLogout,
  handleChangePassword,
  handleGetMe
} from "./routes/auth.js";
import {
  handleListUsers,
  handleCreateUser,
  handleUpdateUser,
  handleUpdateUserStatus,
  handleResetPassword
} from "./routes/users.js";
import {
  handlePreviewInventory,
  handleUploadInventory,
  handleListSnapshots,
  handleGetSnapshot,
  handleCommitSnapshot,
  handleDeleteSnapshot,
  handleDashboardStats
} from "./routes/inventory.js";
import {
  handleCompareSnapshots,
  handleGetProductHistory,
  handleExportComparison
} from "./routes/comparison.js";
import {
  handleGetSyncStatus,
  handleGetSyncRuns,
  handleTriggerSync,
  handleScheduledSync
} from "./routes/sync.js";
import { triggerSync } from "./services/syncService.js";


export interface Env {
  DB?: any; // Cloudflare D1 Database binding
  ENVIRONMENT?: string;
  ROUND?: string;
  APP_TIMEZONE?: string;
  ALLOWED_ORIGINS?: string;
}

function sanitizeRequestId(rawId: string | null): string {
  if (!rawId) {
    return crypto.randomUUID();
  }
  const trimmed = rawId.trim();
  // Giới hạn độ dài <= 64 ký tự và chỉ chứa ký tự an toàn
  if (trimmed.length > 0 && trimmed.length <= 64 && /^[a-zA-Z0-9_\-]+$/.test(trimmed)) {
    return trimmed;
  }
  return crypto.randomUUID();
}

export default {
  async fetch(request: Request, env: Env, ctx: any): Promise<Response> {
    // 1. Xử lý CORS Preflight
    const corsResponse = handleCors(request, env);
    if (corsResponse) {
      return corsResponse;
    }

    const requestId = sanitizeRequestId(request.headers.get("X-Request-ID"));
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    let response: Response;

    try {
      // 2. Health check route
      if ((path === "/api/health" || path === "/health") && method === "GET") {
        response = handleHealthCheck(request, env, requestId);
      }
      // 3. System info route (Async kiểm tra kết nối D1 thực tế)
      else if (path === "/api/v1/system/info" && method === "GET") {
        response = await handleSystemInfo(request, env, requestId);
      }
      // 3b. System bootstrap route (Khởi tạo tài khoản Quản trị viên an toàn ban đầu)
      else if (path === "/api/v1/system/bootstrap" && method === "POST") {
        response = await handleBootstrap(request, env, requestId);
      }
      // 3c. Dashboard stats route (Round 06)
      else if (
        (path === "/api/v1/dashboard/stats" || path === "/api/v1/inventory/dashboard-stats") &&
        method === "GET"
      ) {
        response = await handleDashboardStats(request, env, requestId);
      }
      // 4. Quản lý Chứng từ Kiểm kê (Round 04 - Core Engine)
      else if (
        (path === "/api/v1/inventory/preview" || path === "/api/v1/snapshots/preview") &&
        method === "POST"
      ) {
        response = await handlePreviewInventory(request, env, requestId);
      } else if (
        (path === "/api/v1/inventory/upload" || path === "/api/v1/snapshots/upload") &&
        method === "POST"
      ) {
        response = await handleUploadInventory(request, env, requestId);
      } else if (
        (path === "/api/v1/inventory/snapshots" ||
          path === "/api/v1/snapshots" ||
          path === "/api/snapshots") &&
        method === "GET"
      ) {
        response = await handleListSnapshots(request, env, requestId);
      } else if (
        /^\/api\/v1\/(inventory\/snapshots|snapshots)\/(\d+)\/commit$/.test(path) &&
        method === "POST"
      ) {
        const match = path.match(/^\/api\/v1\/(inventory\/snapshots|snapshots)\/(\d+)\/commit$/);
        const snapshotId = parseInt(match![2], 10);
        response = await handleCommitSnapshot(request, env, requestId, snapshotId);
      } else if (
        /^\/api\/v1\/(inventory\/snapshots|snapshots)\/(\d+)$/.test(path) &&
        method === "GET"
      ) {
        const match = path.match(/^\/api\/v1\/(inventory\/snapshots|snapshots)\/(\d+)$/);
        const snapshotId = parseInt(match![2], 10);
        response = await handleGetSnapshot(request, env, requestId, snapshotId);
      } else if (
        /^\/api\/v1\/(inventory\/snapshots|snapshots)\/(\d+)$/.test(path) &&
        method === "DELETE"
      ) {
        const match = path.match(/^\/api\/v1\/(inventory\/snapshots|snapshots)\/(\d+)$/);
        const snapshotId = parseInt(match![2], 10);
        response = await handleDeleteSnapshot(request, env, requestId, snapshotId);
      }
      // 5. Authentication routes (Round 03)
      else if (path === "/api/v1/auth/login" && method === "POST") {
        response = await handleLogin(request, env, requestId);
      } else if (path === "/api/v1/auth/logout" && method === "POST") {
        response = await handleLogout(request, env, requestId);
      } else if (path === "/api/v1/auth/change-password" && method === "POST") {
        response = await handleChangePassword(request, env, requestId);
      } else if (path === "/api/v1/auth/me" && method === "GET") {
        response = await handleGetMe(request, env, requestId);
      }
      // 6. User Management routes (Round 03 - Admin only)
      else if (path === "/api/v1/users" && method === "GET") {
        response = await handleListUsers(request, env, requestId);
      } else if (path === "/api/v1/users" && method === "POST") {
        response = await handleCreateUser(request, env, requestId);
      } else if (/^\/api\/v1\/users\/(\d+)\/status$/.test(path) && method === "PATCH") {
        const match = path.match(/^\/api\/v1\/users\/(\d+)\/status$/);
        const targetUserId = parseInt(match![1], 10);
        response = await handleUpdateUserStatus(request, env, requestId, targetUserId);
      } else if (/^\/api\/v1\/users\/(\d+)$/.test(path) && method === "PATCH") {
        const match = path.match(/^\/api\/v1\/users\/(\d+)$/);
        const targetUserId = parseInt(match![1], 10);
        response = await handleUpdateUser(request, env, requestId, targetUserId);
      } else if (/^\/api\/v1\/users\/(\d+)\/reset-password$/.test(path) && method === "POST") {
        const match = path.match(/^\/api\/v1\/users\/(\d+)\/reset-password$/);
        const targetUserId = parseInt(match![1], 10);
        response = await handleResetPassword(request, env, requestId, targetUserId);
      }
      // 5. Động cơ Đối soát Tồn kho (Comparison Engine) & Lịch sử SKU - Round 05
      else if (
        (path === "/api/v1/comparison/compare" ||
          path === "/api/v1/compare" ||
          path === "/api/v1/comparison") &&
        (method === "GET" || method === "POST")
      ) {
        response = await handleCompareSnapshots(request, env, requestId);
      } else if (path === "/api/v1/comparison/export" && method === "GET") {
        response = await handleExportComparison(request, env, requestId);
      } else if (
        /^\/api\/v1\/(?:comparison\/history|history)\/([^/]+)$/.test(path) &&
        method === "GET"
      ) {
        const match = path.match(/^\/api\/v1\/(?:comparison\/history|history)\/([^/]+)$/);
        const productCode = decodeURIComponent(match![1]);
        response = await handleGetProductHistory(request, env, requestId, productCode);
      }
      // 7. Đồng bộ Đám mây Google Drive (Google Drive Sync - Round 07)
      else if (path === "/api/v1/sync/status" && method === "GET") {
        response = await handleGetSyncStatus(request, env, requestId);
      } else if (
        (path === "/api/v1/sync/runs" || path === "/api/v1/sync/history") &&
        method === "GET"
      ) {
        response = await handleGetSyncRuns(request, env, requestId);
      } else if (
        (path === "/api/v1/sync/trigger" || path === "/api/v1/sync/run") &&
        method === "POST"
      ) {
        response = await handleTriggerSync(request, env, requestId);
      } else if (
        (path === "/api/v1/sync/scheduled" || path === "/api/v1/sync/cron") &&
        method === "POST"
      ) {
        response = await handleScheduledSync(request, env, requestId);
      } else if (path.startsWith("/api/v1/export")) {
        response = handleUnimplementedModule("Xuất Báo cáo (XLSX/CSV)", "Round 08", requestId);
      }
      // 6. 404 Route Not Found
      else {
        response = createErrorResponse({
          status: 404,
          code: "NOT_FOUND",
          message: `Endpoint không tồn tại: ${method} ${path}`,
          requestId,
          env
        });
      }
    } catch (err: any) {
      // 7. Global Catch 500 (Ghi log console nội bộ, che giấu chi tiết trong response production)
      console.error(`[INTERNAL_ERROR][${requestId}]:`, err);
      response = createErrorResponse({
        status: 500,
        code: "INTERNAL_SERVER_ERROR",
        message: "Lỗi máy chủ nội bộ trong quá trình xử lý yêu cầu",
        details: err?.message || String(err),
        requestId,
        env
      });
    }

    // Luôn gắn header CORS và Request ID vào response
    response.headers.set("X-Request-ID", requestId);
    return appendCorsHeaders(response, request, env);
  },

  /**
   * P1-01: Scheduled Handler cho Cloudflare Cron Trigger (Chạy định kỳ tự động mỗi 60 phút)
   */
  async scheduled(controller: any, env: Env, ctx: any): Promise<void> {
    const scheduledTime = controller?.scheduledTime ? new Date(controller.scheduledTime).toISOString() : new Date().toISOString();
    console.log(`[SCHEDULED_SYNC] Kích hoạt tiến trình đồng bộ tự động lúc ${scheduledTime}...`);
    try {
      const result = await triggerSync(env.DB, env, { triggeredBy: "SCHEDULED" });
      console.log(`[SCHEDULED_SYNC] Kết quả đồng bộ tự động:`, result.status, result.summary);
    } catch (err: any) {
      console.error(`[SCHEDULED_SYNC_ERROR]:`, err?.message || String(err));
    }
  }
};
