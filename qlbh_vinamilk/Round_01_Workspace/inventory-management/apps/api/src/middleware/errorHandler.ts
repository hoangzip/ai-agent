/**
 * Middleware: Chuẩn hóa Error Handling và phản hồi lỗi API
 * Tuân thủ bảo mật:
 * - Mặc định PRODUCTION-SAFE: Nếu thiếu biến `ENVIRONMENT` hoặc mang giá trị không xác định,
 *   toàn bộ chi tiết lỗi nội bộ (stack trace, DB errors, credentials) bị che giấu hoàn toàn.
 * - Chỉ cho phép hiển thị chi tiết lỗi khi biến ENVIRONMENT được cấu hình TƯỜNG MINH là "development" hoặc "test".
 */

export interface ApiErrorOptions {
  status?: number;
  code?: string;
  message: string;
  details?: any;
  requestId?: string;
  env?: any;
}

export function createErrorResponse(options: ApiErrorOptions): Response {
  const status = options.status || 500;
  const envName = options.env?.ENVIRONMENT;

  // FAIL-CLOSED: Chỉ true khi và chỉ khi ENVIRONMENT được đặt rõ ràng là development hoặc test
  const isExplicitDevOrTest = envName === "development" || envName === "test";

  // Bảo vệ thông tin nhạy cảm cho lỗi 500 (Internal Server Error)
  let safeDetails: any = null;
  let safeMessage = options.message;

  if (status === 500 || status >= 502) {
    if (isExplicitDevOrTest) {
      safeDetails = options.details || null;
    } else {
      // Production-safe: che giấu toàn bộ details nội bộ đối với lỗi server (500, 502, 503...)
      safeDetails = null;
      safeMessage = "Lỗi máy chủ nội bộ trong quá trình xử lý yêu cầu";
    }
  } else {
    // Với lỗi nghiệp vụ 4xx hoặc 501 Not Implemented (thông tin lộ trình Round có chủ đích), giữ lại details
    safeDetails = options.details || null;
  }

  const body = {
    success: false,
    error: {
      code: options.code || (status >= 500 ? "INTERNAL_SERVER_ERROR" : "BAD_REQUEST"),
      message: safeMessage,
      details: safeDetails
    },
    meta: {
      requestId: options.requestId || crypto.randomUUID(),
      timestamp: new Date().toISOString()
    }
  };

  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8"
    }
  });
}

export function createSuccessResponse<T>(data: T, status: number = 200, meta?: any): Response {
  const body = {
    success: true,
    data,
    meta: {
      timestamp: new Date().toISOString(),
      ...meta
    }
  };

  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8"
    }
  });
}
