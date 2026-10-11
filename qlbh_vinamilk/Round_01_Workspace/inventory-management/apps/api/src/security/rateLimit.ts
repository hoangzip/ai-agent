/**
 * Security: Rate Limiting & Attempt Throttling cho Authentication
 * Tuân thủ bảo mật:
 * 1. Chống Brute-force & Denial of Service CPU: Giới hạn tối đa 5 lần thử sai trong 15 phút (900 giây).
 * 2. Lần thứ 6 trở đi trả về HTTP 429 Too Many Requests kèm Retry-After header.
 * 3. Tự động xóa bộ đếm khi đăng nhập thành công.
 * 4. Không làm lộ username (áp dụng theo IP / Client Identifier).
 */

interface RateLimitRecord {
  attempts: number;
  firstAttemptAt: number;
  lockedUntil: number;
}

const MAX_FAILED_ATTEMPTS = 5;
const WINDOW_SECONDS = 900; // 15 phút
const LOCKOUT_SECONDS = 900; // Khóa 15 phút nếu vượt quá

// Bộ nhớ in-memory cache cho Worker isolate & Node test
const memoryStore = new Map<string, RateLimitRecord>();

/**
 * Trích xuất định danh IP client từ request
 */
export function getClientIp(request: Request): string {
  const cfIp = request.headers.get("CF-Connecting-IP");
  if (cfIp) return cfIp.trim();

  const xff = request.headers.get("X-Forwarded-For");
  if (xff) {
    const first = xff.split(",")[0].trim();
    if (first) return first;
  }

  const clientIp = request.headers.get("X-Real-IP");
  if (clientIp) return clientIp.trim();

  return "127.0.0.1";
}

/**
 * Kiểm tra xem IP client có đang bị rate-limit hay không
 */
export async function checkLoginRateLimit(
  clientIp: string
): Promise<{ allowed: boolean; retryAfterSeconds: number; remainingAttempts: number }> {
  const now = Date.now();
  const record = memoryStore.get(clientIp);

  if (!record) {
    return { allowed: true, retryAfterSeconds: 0, remainingAttempts: MAX_FAILED_ATTEMPTS };
  }

  // Nếu đã hết hạn khóa/cửa sổ thời gian, reset
  if (record.lockedUntil > 0 && now >= record.lockedUntil) {
    memoryStore.delete(clientIp);
    return { allowed: true, retryAfterSeconds: 0, remainingAttempts: MAX_FAILED_ATTEMPTS };
  }

  if (record.lockedUntil > 0 && now < record.lockedUntil) {
    const retryAfter = Math.ceil((record.lockedUntil - now) / 1000);
    return { allowed: false, retryAfterSeconds: retryAfter, remainingAttempts: 0 };
  }

  // Cửa sổ trượt quá hạn
  if (now - record.firstAttemptAt > WINDOW_SECONDS * 1000) {
    memoryStore.delete(clientIp);
    return { allowed: true, retryAfterSeconds: 0, remainingAttempts: MAX_FAILED_ATTEMPTS };
  }

  if (record.attempts >= MAX_FAILED_ATTEMPTS) {
    const lockedUntil = now + LOCKOUT_SECONDS * 1000;
    record.lockedUntil = lockedUntil;
    return { allowed: false, retryAfterSeconds: LOCKOUT_SECONDS, remainingAttempts: 0 };
  }

  return {
    allowed: true,
    retryAfterSeconds: 0,
    remainingAttempts: Math.max(0, MAX_FAILED_ATTEMPTS - record.attempts)
  };
}

/**
 * Ghi nhận một lần đăng nhập thất bại
 */
export async function recordFailedLoginAttempt(
  clientIp: string
): Promise<{ remainingAttempts: number; isLocked: boolean }> {
  const now = Date.now();
  let record = memoryStore.get(clientIp);

  if (!record || now - record.firstAttemptAt > WINDOW_SECONDS * 1000) {
    record = {
      attempts: 1,
      firstAttemptAt: now,
      lockedUntil: 0
    };
    memoryStore.set(clientIp, record);
    return { remainingAttempts: MAX_FAILED_ATTEMPTS - 1, isLocked: false };
  }

  record.attempts += 1;

  if (record.attempts >= MAX_FAILED_ATTEMPTS) {
    record.lockedUntil = now + LOCKOUT_SECONDS * 1000;
    return { remainingAttempts: 0, isLocked: true };
  }

  return {
    remainingAttempts: Math.max(0, MAX_FAILED_ATTEMPTS - record.attempts),
    isLocked: false
  };
}

/**
 * Xóa rate limit khi đăng nhập thành công
 */
export async function clearLoginRateLimit(clientIp: string): Promise<void> {
  memoryStore.delete(clientIp);
}

/**
 * Reset toàn bộ (dành cho kiểm thử)
 */
export function resetAllRateLimitsForTesting(): void {
  memoryStore.clear();
}
