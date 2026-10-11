/**
 * Middleware: CORS handling với EXACT Origin Allowlist
 * Tuân thủ bảo mật:
 * 1. Chỉ chấp nhận các origin khớp CHÍNH XÁC trong danh sách cho phép (không dùng wildcard *.pages.dev/*.workers.dev).
 * 2. Nếu Origin không hợp lệ hoặc không có Origin, KHÔNG xuất Access-Control-Allow-Origin và Access-Control-Allow-Credentials.
 * 3. Luôn gắn header "Vary: Origin" để các tầng proxy/CDN không cache nhầm header CORS giữa các client khác nhau.
 */

const DEFAULT_DEV_ORIGINS = [
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:5173",
  "http://127.0.0.1:5173"
];

export function getValidatedOrigin(request: Request, env?: any): string | null {
  const origin = request.headers.get("Origin");
  if (!origin) {
    return null;
  }

  const isDevOrTest = env?.ENVIRONMENT === "development" || env?.ENVIRONMENT === "test";

  // Danh sách origin được phép cấu hình từ biến môi trường
  const configuredOrigins: string[] = env?.ALLOWED_ORIGINS
    ? env.ALLOWED_ORIGINS.split(",").map((s: string) => s.trim()).filter(Boolean)
    : [];

  // Localhost chỉ được cho phép trong môi trường development/test
  const allowedSet = new Set<string>([
    ...(isDevOrTest ? DEFAULT_DEV_ORIGINS : []),
    ...configuredOrigins
  ]);

  // SO KHỚP CHÍNH XÁC (EXACT MATCH) - TUYỆT ĐỐI KHÔNG DÙNG REGEX WILDCARD
  if (allowedSet.has(origin)) {
    return origin;
  }

  return null;
}

export function handleCors(request: Request, env?: any): Response | null {
  if (request.method === "OPTIONS") {
    const validatedOrigin = getValidatedOrigin(request, env);

    // Nếu Origin không nằm trong allowlist, từ chối preflight (không cấp ACAO)
    if (!validatedOrigin) {
      return new Response(null, {
        status: 403,
        statusText: "Forbidden CORS Origin",
        headers: {
          "Vary": "Origin"
        }
      });
    }

    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": validatedOrigin,
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, X-Request-ID",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin"
      }
    });
  }
  return null;
}

export function appendCorsHeaders(response: Response, request: Request, env?: any): Response {
  const newHeaders = new Headers(response.headers);
  newHeaders.append("Vary", "Origin");

  const validatedOrigin = getValidatedOrigin(request, env);
  if (validatedOrigin) {
    newHeaders.set("Access-Control-Allow-Origin", validatedOrigin);
    newHeaders.set("Access-Control-Allow-Credentials", "true");
  } else {
    // Nếu origin không được phép, đảm bảo KHÔNG có header ACAO
    newHeaders.delete("Access-Control-Allow-Origin");
    newHeaders.delete("Access-Control-Allow-Credentials");
  }

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders
  });
}
