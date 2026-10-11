/**
 * Routes: Quản lý & Thực thi Đối soát Tồn kho (Comparison Routes)
 * Module: apps/api/src/routes/comparison.ts (Round 05)
 */

import { authenticate } from "../middleware/auth.js";
import { createSuccessResponse, createErrorResponse } from "../middleware/errorHandler.js";
import {
  compareSnapshots,
  getProductHistory,
  exportComparisonCsv,
  ComparisonServiceError,
  ComparisonFilterOptions
} from "../services/comparisonService.js";
import { ComparisonStatus } from "@inventory/shared";

/**
 * Endpoint: POST /api/v1/comparison/compare hoặc GET /api/v1/comparison?base_id=...&target_id=...
 */
export async function handleCompareSnapshots(
  request: Request,
  env: any,
  requestId: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) return errorResponse;

  const url = new URL(request.url);
  let baseId: number | undefined;
  let targetId: number | undefined;
  let options: ComparisonFilterOptions = {};

  if (request.method === "POST") {
    try {
      const body = (await request.json()) as any;
      baseId = Number(body.base_id || body.baseSnapshotId || body.snapshot_a);
      targetId = Number(body.target_id || body.targetSnapshotId || body.snapshot_b);
      options = {
        status: body.status,
        category: body.category,
        warehouse: body.warehouse,
        search: body.search,
        page: body.page ? Number(body.page) : 1,
        limit: body.limit ? Number(body.limit) : 50
      };
    } catch {
      return createErrorResponse({
        status: 400,
        code: "INVALID_JSON_BODY",
        message: "Dữ liệu yêu cầu JSON không hợp lệ.",
        requestId,
        env
      });
    }
  } else {
    // GET method: lấy từ URL Search Params
    const baseParam = url.searchParams.get("base_id") || url.searchParams.get("snapshot_a");
    const targetParam = url.searchParams.get("target_id") || url.searchParams.get("snapshot_b");

    if (baseParam) baseId = Number(baseParam);
    if (targetParam) targetId = Number(targetParam);

    options = {
      status: (url.searchParams.get("status") as ComparisonStatus) || undefined,
      category: url.searchParams.get("category") || undefined,
      warehouse: url.searchParams.get("warehouse") || undefined,
      search: url.searchParams.get("search") || undefined,
      page: url.searchParams.has("page") ? Number(url.searchParams.get("page")) : 1,
      limit: url.searchParams.has("limit") ? Number(url.searchParams.get("limit")) : 50
    };
  }

  if (!baseId || isNaN(baseId) || !targetId || isNaN(targetId)) {
    return createErrorResponse({
      status: 400,
      code: "MISSING_SNAPSHOT_IDS",
      message: "Vui lòng cung cấp đầy đủ mã định danh base_id và target_id để đối soát.",
      requestId,
      env
    });
  }

  try {
    const result = await compareSnapshots(env.DB, baseId, targetId, options);
    return createSuccessResponse(result, 200, { requestId });
  } catch (err: any) {
    if (err instanceof ComparisonServiceError) {
      return createErrorResponse({
        status: err.status,
        code: err.code,
        message: err.message,
        details: err.details,
        requestId,
        env
      });
    }
    return createErrorResponse({
      status: 500,
      code: "COMPARISON_FAILED",
      message: `Lỗi trong quá trình đối soát tồn kho: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}

/**
 * Endpoint: GET /api/v1/comparison/history/:product_code (hoặc /api/v1/history/:sku)
 */
export async function handleGetProductHistory(
  request: Request,
  env: any,
  requestId: string,
  productCode: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) return errorResponse;

  const url = new URL(request.url);
  const warehouse = url.searchParams.get("warehouse") || undefined;
  const storeCode = url.searchParams.get("store_code") || url.searchParams.get("store") || undefined;

  try {
    const result = await getProductHistory(env.DB, productCode, warehouse, storeCode);
    return createSuccessResponse(result, 200, { requestId });
  } catch (err: any) {
    if (err instanceof ComparisonServiceError) {
      return createErrorResponse({
        status: err.status,
        code: err.code,
        message: err.message,
        details: err.details,
        requestId,
        env
      });
    }
    return createErrorResponse({
      status: 500,
      code: "HISTORY_FAILED",
      message: `Lỗi tra cứu lịch sử SKU: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}

/**
 * Endpoint: GET /api/v1/comparison/export?base_id=...&target_id=...
 */
export async function handleExportComparison(
  request: Request,
  env: any,
  requestId: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) return errorResponse;

  const url = new URL(request.url);
  const baseId = Number(url.searchParams.get("base_id") || url.searchParams.get("snapshot_a"));
  const targetId = Number(url.searchParams.get("target_id") || url.searchParams.get("snapshot_b"));

  if (!baseId || isNaN(baseId) || !targetId || isNaN(targetId)) {
    return createErrorResponse({
      status: 400,
      code: "MISSING_SNAPSHOT_IDS",
      message: "Vui lòng cung cấp base_id và target_id để xuất báo cáo.",
      requestId,
      env
    });
  }

  const options: ComparisonFilterOptions = {
    status: (url.searchParams.get("status") as ComparisonStatus) || undefined,
    category: url.searchParams.get("category") || undefined,
    warehouse: url.searchParams.get("warehouse") || undefined,
    search: url.searchParams.get("search") || undefined
  };

  try {
    const csvContent = await exportComparisonCsv(env.DB, baseId, targetId, options);
    const filename = `BaoCao_DoiSoat_${baseId}_vs_${targetId}.csv`;

    return new Response(csvContent, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="${filename}"`,
        "X-Request-ID": requestId
      }
    });
  } catch (err: any) {
    if (err instanceof ComparisonServiceError) {
      return createErrorResponse({
        status: err.status,
        code: err.code,
        message: err.message,
        details: err.details,
        requestId,
        env
      });
    }
    return createErrorResponse({
      status: 500,
      code: "EXPORT_FAILED",
      message: `Lỗi xuất báo cáo đối soát: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}
