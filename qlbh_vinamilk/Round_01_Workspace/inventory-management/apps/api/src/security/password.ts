/**
 * Security: Hashing và Xác thực Mật khẩu bằng Web Crypto API PBKDF2
 * Tuân thủ bảo mật:
 * 1. Chống brute-force: Sử dụng thuật toán PBKDF2 với HMAC-SHA-256 và 100.000 vòng lặp (iterations).
 * 2. Cryptographic Salt: Mỗi mật khẩu sinh một salt ngẫu nhiên 16 bytes (128-bit) riêng biệt.
 * 3. Không dùng SHA-256 thuần túy, không phụ thuộc thư viện native C/C++ ngoài runtime.
 * 4. So sánh hash theo cơ chế thời gian hằng định (Constant-time comparison) chống tấn công Timing Attack.
 */

const ITERATIONS = 100000;
const KEY_LENGTH_BYTES = 32; // 256 bits

function bufferToHex(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function hexToBuffer(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

/**
 * Băm mật khẩu bản rõ thành chuỗi lưu trữ an toàn:
 * Định dạng: pbkdf2:100000:<salt_hex>:<hash_hex>
 */
export async function hashPassword(password: string): Promise<string> {
  const enc = new TextEncoder();
  const salt = crypto.getRandomValues(new Uint8Array(16));

  const baseKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(password),
    { name: "PBKDF2" },
    false,
    ["deriveBits"]
  );

  const derivedBits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt,
      iterations: ITERATIONS,
      hash: "SHA-256"
    },
    baseKey,
    KEY_LENGTH_BYTES * 8
  );

  const saltHex = bufferToHex(salt);
  const hashHex = bufferToHex(derivedBits);

  return `pbkdf2:${ITERATIONS}:${saltHex}:${hashHex}`;
}

/**
 * Xác thực mật khẩu ứng viên với chuỗi hash đã lưu trong database
 */
export async function verifyPassword(password: string, storedHash: string): Promise<boolean> {
  if (!storedHash || typeof storedHash !== "string") {
    return false;
  }

  const parts = storedHash.split(":");
  if (parts.length !== 4 || parts[0] !== "pbkdf2") {
    return false;
  }

  const iterations = parseInt(parts[1], 10);
  if (isNaN(iterations) || iterations < 1000) {
    return false;
  }

  const salt = hexToBuffer(parts[2]);
  const expectedHash = hexToBuffer(parts[3]);

  const enc = new TextEncoder();
  const baseKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(password),
    { name: "PBKDF2" },
    false,
    ["deriveBits"]
  );

  const derivedBits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt,
      iterations,
      hash: "SHA-256"
    },
    baseKey,
    expectedHash.length * 8
  );

  const actualHash = new Uint8Array(derivedBits);

  if (actualHash.length !== expectedHash.length) {
    return false;
  }

  // Constant-time comparison chống Timing Attack
  let diff = 0;
  for (let i = 0; i < actualHash.length; i++) {
    diff |= actualHash[i] ^ expectedHash[i];
  }

  return diff === 0;
}

/**
 * Sinh mật khẩu tạm thời ngẫu nhiên có độ entropy cao (cryptographically secure)
 * Bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt
 */
export function generateSecureRandomPassword(length: number = 12): string {
  const charset = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*";
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  let result = "";
  for (let i = 0; i < length; i++) {
    result += charset[bytes[i] % charset.length];
  }
  return result;
}

/**
 * Kiểm tra xem mật khẩu có nằm trong danh sách đen mật khẩu phổ biến hay không
 */
export function isCommonPassword(password: string): boolean {
  const common = [
    "123456",
    "12345678",
    "123456789",
    "password",
    "password123",
    "admin123",
    "qwerty",
    "admin",
    "vinamilk",
    "vinamilk123"
  ];
  return common.includes(password.toLowerCase().trim());
}

