/**
 * Security: Quản lý Phiên (Session Management) và Cookie HttpOnly
 * Tuân thủ bảo mật:
 * 1. Khóa chính bảng `sessions`: Chỉ lưu trữ băm SHA-256 (`token_hash`), TUYỆT ĐỐI KHÔNG LƯU TOKEN BẢN RÕ.
 * 2. Token ngẫu nhiên: Sinh bằng crypto.randomUUID().
 * 3. Hỗ trợ kép: Đọc token từ Cookie HttpOnly (cho trình duyệt) hoặc Header Bearer Token (cho API/script client).
 * 4. Cookie flags an toàn: HttpOnly, SameSite=Lax, Path=/, Secure (khi production).
 */

export const SESSION_DURATION_SECONDS = 86400; // 24 giờ

/**
 * Băm token bản rõ bằng SHA-256 để lưu trữ an toàn trong DB
 */
export async function hashSessionToken(token: string): Promise<string> {
  const enc = new TextEncoder();
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(token));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Trích xuất Session Token từ Request (ưu tiên Bearer header, sau đó đến Cookie auth_token)
 */
export function extractSessionToken(request: Request): string | null {
  // 1. Kiểm tra Header Authorization
  const authHeader = request.headers.get("Authorization");
  if (authHeader && authHeader.startsWith("Bearer ")) {
    const bearerToken = authHeader.substring(7).trim();
    if (bearerToken.length > 0) {
      return bearerToken;
    }
  }

  // 2. Kiểm tra Cookie Header
  const cookieHeader = request.headers.get("Cookie");
  if (cookieHeader) {
    const cookies = cookieHeader.split(";");
    for (const cookie of cookies) {
      const [key, value] = cookie.trim().split("=");
      if (key === "auth_token" && value) {
        return decodeURIComponent(value);
      }
    }
  }

  return null;
}

/**
 * Kiểm tra xem môi trường có yêu cầu bật Secure cookie hay không
 * FAIL-SAFE: Mặc định luôn bật Secure trừ khi môi trường chỉ định rõ ràng là 'development' hoặc 'test'
 */
export function isSecureCookieRequired(env?: any): boolean {
  const envName = (env?.ENVIRONMENT || "").toLowerCase();
  return envName !== "development" && envName !== "test";
}

/**
 * Tạo giá trị Set-Cookie an toàn cho session
 */
export function createSessionCookie(
  token: string,
  maxAgeSeconds: number = SESSION_DURATION_SECONDS,
  env?: any
): string {
  const secure = isSecureCookieRequired(env);
  const secureFlag = secure ? "; Secure" : "";
  return `auth_token=${encodeURIComponent(token)}; Path=/; Max-Age=${maxAgeSeconds}; HttpOnly; SameSite=Lax${secureFlag}`;
}

/**
 * Tạo giá trị Set-Cookie để xóa phiên (Revoke) trên trình duyệt
 */
export function clearSessionCookie(env?: any): string {
  const secure = isSecureCookieRequired(env);
  const secureFlag = secure ? "; Secure" : "";
  return `auth_token=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax${secureFlag}`;
}

