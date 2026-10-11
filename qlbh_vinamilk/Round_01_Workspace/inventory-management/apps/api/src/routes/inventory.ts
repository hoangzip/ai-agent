/**
 * Route Handlers: Quản lý Chứng từ Kiểm kê (Inventory Snapshots API)
 * Module: apps/api/src/routes/inventory.ts (Revision 2 - Fix 01 Data Integrity)
 *
 * Endpoints:
 * 1. POST   /api/v1/inventory/preview         - Xem trước và xác thực dữ liệu Excel KHÔNG ghi vào DB
 * 2. POST   /api/v1/inventory/upload          - Tải lên và nạp dữ liệu vào Staging (hỗ trợ multipart & JSON base64)
 * 3. GET    /api/v1/inventory/snapshots       - Lấy danh sách snapshot (lọc theo ngày, mã cửa hàng, trạng thái)
 * 4. GET    /api/v1/inventory/snapshots/:id   - Lấy chi tiết snapshot và danh sách 15 cột mặt hàng
 * 5. POST   /api/v1/inventory/snapshots/:id/commit - Duyệt chứng từ: Chuyển STAGING sang COMPLETED (kiểm tra lại DB)
 * 6. DELETE /api/v1/inventory/snapshots/:id   - Xóa mềm chứng từ (Soft Delete, Admin only)
 */

import { authenticate } from "../middleware/auth.js";
import { createErrorResponse, createSuccessResponse } from "../middleware/errorHandler.js";
import { getClientIp } from "../security/rateLimit.js";
import { parseInventoryExcel, MAX_FILE_SIZE_BYTES } from "../services/excelParser.js";
import {
  importSnapshot,
  listSnapshots,
  getSnapshotById,
  commitSnapshot,
  softDeleteSnapshot,
  getDashboardStats,
  InventoryServiceError
} from "../services/inventoryService.js";

const MAX_FILES_PER_BATCH = 10;

interface UploadItem {
  filename: string;
  buffer: ArrayBuffer;
  autoCommit?: boolean;
  shift?: "Sáng" | "Chiều" | "Tối" | "Khác" | "Chưa xác định";
  inventory_time?: string | null;
  store_code?: string;
}

/**
 * Trích xuất tệp tin và metadata từ Request (Multipart hoặc JSON)
 */
async function extractUploadItems(
  request: Request,
  requestId: string,
  env: any
): Promise<{ items?: UploadItem[]; errorResponse?: Response }> {
  const contentType = request.headers.get("content-type") || "";
  const itemsToProcess: UploadItem[] = [];

  if (contentType.includes("multipart/form-data")) {
    const formData = await request.formData();
    const autoCommit = formData.get("auto_commit") === "true";
    const shift = (formData.get("shift") as any) || undefined;
    const inventory_time = (formData.get("inventory_time") as string) || undefined;
    const store_code = (formData.get("store_code") as string) || undefined;

    const files: { name: string; arrayBuffer: () => Promise<ArrayBuffer> }[] = [];
    for (const [key, value] of formData.entries()) {
      const fileCandidate = value as any;
      if (
        fileCandidate &&
        typeof fileCandidate === "object" &&
        typeof fileCandidate.name === "string" &&
        typeof fileCandidate.arrayBuffer === "function" &&
        (fileCandidate.name.endsWith(".xlsx") || fileCandidate.name.endsWith(".xls"))
      ) {
        files.push(fileCandidate);
      }
    }

    if (files.length === 0) {
      return {
        errorResponse: createErrorResponse({
          status: 400,
          code: "MISSING_EXCEL_FILE",
          message: "Vui lòng chọn ít nhất một file Excel (.xlsx) để tải lên.",
          requestId,
          env
        })
      };
    }

    if (files.length > MAX_FILES_PER_BATCH) {
      return {
        errorResponse: createErrorResponse({
          status: 400,
          code: "TOO_MANY_FILES",
          message: `Không được tải lên quá ${MAX_FILES_PER_BATCH} tệp tin trong một lượt.`,
          requestId,
          env
        })
      };
    }

    for (const file of files) {
      const buffer = await file.arrayBuffer();
      if (buffer.byteLength > MAX_FILE_SIZE_BYTES) {
        return {
          errorResponse: createErrorResponse({
            status: 413,
            code: "PAYLOAD_TOO_LARGE",
            message: `Tệp '${file.name}' (${(buffer.byteLength / 1024 / 1024).toFixed(1)} MB) vượt quá dung lượng tối đa cho phép (${MAX_FILE_SIZE_BYTES / 1024 / 1024} MB).`,
            requestId,
            env
          })
        };
      }

      itemsToProcess.push({
        filename: file.name,
        buffer,
        autoCommit,
        shift,
        inventory_time,
        store_code
      });
    }
  } else if (contentType.includes("application/json")) {
    const body: any = await request.json();
    const autoCommit = Boolean(body.auto_commit);
    const globalShift = body.shift;
    const globalTime = body.inventory_time;
    const globalStore = body.store_code;

    if (Array.isArray(body.files)) {
      if (body.files.length > MAX_FILES_PER_BATCH) {
        return {
          errorResponse: createErrorResponse({
            status: 400,
            code: "TOO_MANY_FILES",
            message: `Không được tải lên quá ${MAX_FILES_PER_BATCH} tệp tin trong một lượt.`,
            requestId,
            env
          })
        };
      }

      for (const fileItem of body.files) {
        if (!fileItem.filename || !fileItem.content_base64) continue;
        const binaryString = atob(fileItem.content_base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        if (bytes.byteLength > MAX_FILE_SIZE_BYTES) {
          return {
            errorResponse: createErrorResponse({
              status: 413,
              code: "PAYLOAD_TOO_LARGE",
              message: `Tệp '${fileItem.filename}' vượt quá dung lượng tối đa cho phép 10MB.`,
              requestId,
              env
            })
          };
        }

        itemsToProcess.push({
          filename: fileItem.filename,
          buffer: bytes.buffer,
          autoCommit: Boolean(fileItem.auto_commit ?? autoCommit),
          shift: fileItem.shift || globalShift,
          inventory_time: fileItem.inventory_time || globalTime,
          store_code: fileItem.store_code || globalStore
        });
      }
    } else if (body.filename && body.content_base64) {
      const binaryString = atob(body.content_base64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      if (bytes.byteLength > MAX_FILE_SIZE_BYTES) {
        return {
          errorResponse: createErrorResponse({
            status: 413,
            code: "PAYLOAD_TOO_LARGE",
            message: `Tệp '${body.filename}' vượt quá dung lượng tối đa cho phép 10MB.`,
            requestId,
            env
          })
        };
      }

      itemsToProcess.push({
        filename: body.filename,
        buffer: bytes.buffer,
        autoCommit,
        shift: body.shift || globalShift,
        inventory_time: body.inventory_time || globalTime,
        store_code: body.store_code || globalStore
      });
    } else {
      return {
        errorResponse: createErrorResponse({
          status: 400,
          code: "INVALID_JSON_PAYLOAD",
          message: "Yêu cầu JSON cần chứa 'filename' và 'content_base64', hoặc mảng 'files'.",
          requestId,
          env
        })
      };
    }
  } else {
    return {
      errorResponse: createErrorResponse({
        status: 415,
        code: "UNSUPPORTED_MEDIA_TYPE",
        message: "Chỉ hỗ trợ Content-Type là 'multipart/form-data' hoặc 'application/json'.",
        requestId,
        env
      })
    };
  }

  if (itemsToProcess.length === 0) {
    return {
      errorResponse: createErrorResponse({
        status: 400,
        code: "EMPTY_UPLOAD_LIST",
        message: "Không tìm thấy dữ liệu file Excel hợp lệ để xử lý.",
        requestId,
        env
      })
    };
  }

  return { items: itemsToProcess };
}

/**
 * Xử lý xem trước file Excel (Preview - không ghi vào DB) (R04-P2-03)
 */
export async function handlePreviewInventory(
  request: Request,
  env: any,
  requestId: string
): Promise<Response> {
  const { errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }

  try {
    const { items, errorResponse: extractErr } = await extractUploadItems(request, requestId, env);
    if (extractErr) return extractErr;
    if (!items || items.length === 0) {
      return createErrorResponse({
        status: 400,
        code: "NO_FILES",
        message: "Không có file nào được cung cấp.",
        requestId,
        env
      });
    }

    const previews = [];
    for (const item of items) {
      const parsed = await parseInventoryExcel(item.buffer, item.filename, {
        shift: item.shift,
        inventory_time: item.inventory_time,
        store_code: item.store_code
      });

      previews.push({
        filename: item.filename,
        isValid: parsed.isValid,
        errors: parsed.errors,
        metadata: parsed.metadata,
        summary: parsed.summary,
        total_sku_count: parsed.total_sku_count,
        file_sha256: parsed.file_sha256,
        content_hash: parsed.content_hash,
        preview_items: parsed.items.slice(0, 50) // Trả về tối đa 50 dòng mẫu để preview
      });
    }

    return createSuccessResponse(
      previews.length === 1 ? previews[0] : { previews },
      200,
      { requestId }
    );
  } catch (error: any) {
    return createErrorResponse({
      status: 500,
      code: "PREVIEW_ERROR",
      message: `Lỗi trong quá trình phân tích xem trước file: ${error.message || String(error)}`,
      requestId,
      env
    });
  }
}

/**
 * Xử lý tải lên file Excel kiểm kê (đơn hoặc đa tệp)
 */
export async function handleUploadInventory(
  request: Request,
  env: any,
  requestId: string
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }

  const clientIp = getClientIp(request);

  try {
    const { items, errorResponse: extractErr } = await extractUploadItems(request, requestId, env);
    if (extractErr) return extractErr;
    if (!items) {
      return createErrorResponse({
        status: 400,
        code: "EMPTY_UPLOAD_LIST",
        message: "Không tìm thấy dữ liệu file.",
        requestId,
        env
      });
    }

    // 2. Xử lý từng file
    const results = [];
    for (const item of items) {
      try {
        const parsed = await parseInventoryExcel(item.buffer, item.filename, {
          shift: item.shift,
          inventory_time: item.inventory_time,
          store_code: item.store_code
        });

        if (!parsed.isValid) {
          results.push({
            filename: item.filename,
            success: false,
            error: {
              code: "EXCEL_VALIDATION_FAILED",
              message: parsed.errors.join("; "),
              details: { errors: parsed.errors, summary: parsed.summary }
            }
          });
          continue;
        }

        const savedSnapshot = await importSnapshot(env.DB, parsed, {
          userId: auth?.user.id,
          autoCommit: item.autoCommit,
          ipAddress: clientIp,
          shift: item.shift,
          inventory_time: item.inventory_time
        });

        results.push({
          filename: item.filename,
          success: true,
          snapshot: savedSnapshot
        });
      } catch (err: any) {
        if (err instanceof InventoryServiceError) {
          results.push({
            filename: item.filename,
            success: false,
            error: {
              code: err.code,
              message: err.message,
              details: err.details,
              status: err.status
            }
          });
        } else {
          results.push({
            filename: item.filename,
            success: false,
            error: {
              code: "SERVER_ERROR",
              message: err.message || "Lỗi xử lý tệp tin Excel.",
              status: 500
            }
          });
        }
      }
    }

    // 3. Trả về kết quả
    const allSuccess = results.every((r) => r.success);
    const anySuccess = results.some((r) => r.success);

    // Nếu chỉ tải 1 file và lỗi -> trả về status lỗi tương ứng
    if (results.length === 1 && !results[0].success) {
      const err = results[0].error || {
        code: "EXCEL_IMPORT_FAILED",
        message: "Nhập tệp Excel thất bại.",
        details: undefined,
        status: 400
      };
      const statusCode =
        err.status ||
        (err.code === "ALREADY_IMPORTED" ||
        err.code === "DUPLICATE_CONTENT" ||
        err.code === "CONFLICT" ||
        err.code === "SNAPSHOT_SOFT_DELETED"
          ? 409
          : err.code === "EXCEL_VALIDATION_FAILED"
          ? 422
          : 400);

      return createErrorResponse({
        status: statusCode,
        code: err.code,
        message: err.message,
        details: err.details,
        requestId,
        env
      });
    }

    const httpStatus = allSuccess ? 201 : anySuccess ? 207 : 400;

    return createSuccessResponse(
      {
        total_files: results.length,
        successful_count: results.filter((r) => r.success).length,
        failed_count: results.filter((r) => !r.success).length,
        results
      },
      httpStatus,
      { requestId }
    );
  } catch (error: any) {
    return createErrorResponse({
      status: 500,
      code: "UPLOAD_INTERNAL_ERROR",
      message: `Lỗi trong quá trình tiếp nhận file: ${error.message || String(error)}`,
      requestId,
      env
    });
  }
}

/**
 * Lấy danh sách snapshot
 */
export async function handleListSnapshots(
  request: Request,
  env: any,
  requestId: string
): Promise<Response> {
  const { errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }

  const url = new URL(request.url);
  const status = url.searchParams.get("status") || undefined;
  const store_code = url.searchParams.get("store_code") || undefined;
  const inventory_date = url.searchParams.get("inventory_date") || undefined;
  const start_date = url.searchParams.get("start_date") || undefined;
  const end_date = url.searchParams.get("end_date") || undefined;
  const search = url.searchParams.get("search") || url.searchParams.get("q") || undefined;
  const shift = url.searchParams.get("shift") || undefined;
  const page = parseInt(url.searchParams.get("page") || "1", 10);
  const limit = parseInt(url.searchParams.get("limit") || "20", 10);

  try {
    const data = await listSnapshots(env.DB, {
      status,
      store_code,
      inventory_date,
      start_date,
      end_date,
      search,
      shift,
      page,
      limit
    });

    return createSuccessResponse(data, 200, { requestId });
  } catch (err: any) {
    return createErrorResponse({
      status: 500,
      code: "LIST_SNAPSHOTS_ERROR",
      message: `Lỗi truy vấn danh sách chứng từ: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}

/**
 * Lấy số liệu thống kê tổng quan hệ thống cho Dashboard (Round 06)
 */
export async function handleDashboardStats(
  request: Request,
  env: any,
  requestId: string
): Promise<Response> {
  const { errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }

  try {
    const url = new URL(request.url);
    const storeCode = url.searchParams.get("store_code") || undefined;
    const stats = await getDashboardStats(env.DB, storeCode);
    return createSuccessResponse(stats, 200, { requestId });
  } catch (err: any) {
    return createErrorResponse({
      status: 500,
      code: "DASHBOARD_STATS_ERROR",
      message: `Lỗi truy vấn số liệu thống kê Dashboard: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}

/**
 * Lấy chi tiết snapshot theo ID
 */
export async function handleGetSnapshot(
  request: Request,
  env: any,
  requestId: string,
  id: number
): Promise<Response> {
  const { errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }

  const url = new URL(request.url);
  const includeItems = url.searchParams.get("include_items") !== "false";

  try {
    const data = await getSnapshotById(env.DB, id, includeItems);
    return createSuccessResponse(data, 200, { requestId });
  } catch (err: any) {
    if (err instanceof InventoryServiceError) {
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
      code: "GET_SNAPSHOT_ERROR",
      message: `Lỗi lấy thông tin chứng từ: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}

/**
 * Duyệt snapshot: STAGING -> COMPLETED (Xác thực lại toàn vẹn dữ liệu DB)
 */
export async function handleCommitSnapshot(
  request: Request,
  env: any,
  requestId: string,
  id: number
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId);
  if (errorResponse) {
    return errorResponse;
  }

  const clientIp = getClientIp(request);

  try {
    const result = await commitSnapshot(env.DB, id, {
      userId: auth?.user.id,
      ipAddress: clientIp
    });

    return createSuccessResponse(result, 200, { requestId });
  } catch (err: any) {
    if (err instanceof InventoryServiceError) {
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
      code: "COMMIT_SNAPSHOT_ERROR",
      message: `Lỗi duyệt chứng từ: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}

/**
 * Xóa mềm chứng từ kiểm kê (Chỉ Admin)
 */
export async function handleDeleteSnapshot(
  request: Request,
  env: any,
  requestId: string,
  id: number
): Promise<Response> {
  const { auth, errorResponse } = await authenticate(request, env, requestId, {
    requireRole: "ADMIN"
  });
  if (errorResponse) {
    return errorResponse;
  }

  const clientIp = getClientIp(request);

  try {
    const result = await softDeleteSnapshot(env.DB, id, {
      userId: auth?.user.id,
      ipAddress: clientIp
    });

    return createSuccessResponse(result, 200, { requestId });
  } catch (err: any) {
    if (err instanceof InventoryServiceError) {
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
      code: "DELETE_SNAPSHOT_ERROR",
      message: `Lỗi xóa chứng từ: ${err.message || String(err)}`,
      requestId,
      env
    });
  }
}
