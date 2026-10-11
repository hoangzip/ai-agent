import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import worker from "../dist/index.js";
import { hashPassword, verifyPassword } from "../dist/security/password.js";
import { resetAllRateLimitsForTesting } from "../dist/security/rateLimit.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATION_PATH = path.resolve(__dirname, "../../../database/migrations/0001_initial_schema.sql");

async function setupTestDb(mfInstance) {
  const db = await mfInstance.getD1Database("DB");
  const sql = fs.readFileSync(MIGRATION_PATH, "utf8");
  const cleanSql = sql.replace(/--.*$/gm, "").trim();
  const statements = cleanSql.split(";").map((s) => s.trim()).filter((s) => s.length > 0);
  for (const stmt of statements) {
    await db.prepare(stmt).run();
  }
  return db;
}

let mf;
let testDb;
let baseEnv;

test.before(async () => {
  mf = new Miniflare({
    modules: true,
    script: "export default { fetch() { return new Response('ok'); } }",
    d1Databases: { DB: "test_db" }
  });
  testDb = await setupTestDb(mf);
  baseEnv = {
    DB: testDb,
    ENVIRONMENT: "test",
    ROUND: "03",
    APP_TIMEZONE: "Asia/Ho_Chi_Minh",
    ALLOWED_ORIGINS: "http://localhost:3000",
    BOOTSTRAP_TOKEN: "secret-bootstrap-key-999"
  };
});


test.after(async () => {
  if (mf) {
    await mf.dispose();
  }
});

// ====================================================================
// NHÓM 1: MÃ HÓA MẬT KHẨU PBKDF2 & CHỐNG BRUTE-FORCE
// ====================================================================

test("PBKDF2: hashPassword creates formatted pbkdf2 hash with 100000 iterations and salt", async () => {
  const hash = await hashPassword("supersecret123");
  assert.ok(hash.startsWith("pbkdf2:100000:"));
  const parts = hash.split(":");
  assert.strictEqual(parts.length, 4);
  assert.strictEqual(parts[2].length, 32); // 16-byte salt hex
  assert.strictEqual(parts[3].length, 64); // 32-byte hash hex
});

test("PBKDF2: distinct calls produce distinct salts for the same password", async () => {
  const hash1 = await hashPassword("samePassword");
  const hash2 = await hashPassword("samePassword");
  assert.notStrictEqual(hash1, hash2);
});

test("PBKDF2: verifyPassword correctly verifies matching password and rejects invalid", async () => {
  const hash = await hashPassword("CorrectP@ssw0rd");
  const isMatch = await verifyPassword("CorrectP@ssw0rd", hash);
  assert.strictEqual(isMatch, true);

  const isWrong = await verifyPassword("WrongPassword", hash);
  assert.strictEqual(isWrong, false);

  const isInvalidHash = await verifyPassword("CorrectP@ssw0rd", "invalid:hash");
  assert.strictEqual(isInvalidHash, false);
});

// ====================================================================
// NHÓM 2: BOOTSTRAP ADMIN AN TOÀN (P0 FIX)
// ====================================================================

test("SECURITY: POST /api/v1/auth/login does NOT auto-bootstrap admin on fresh DB", async () => {
  resetAllRateLimitsForTesting();
  const req = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: "123456"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);
  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.code, "INVALID_CREDENTIALS");

  // Đảm bảo không có admin nào được tạo ngầm
  const adminCount = await testDb.prepare("SELECT COUNT(*) as count FROM users WHERE role = 'ADMIN'").first();
  assert.strictEqual(adminCount.count, 0);
});

test("SECURITY: POST /api/v1/system/bootstrap is BLOCKED (403 BOOTSTRAP_DISABLED) when BOOTSTRAP_TOKEN is unconfigured", async () => {
  const envWithoutToken = { ...baseEnv, BOOTSTRAP_TOKEN: undefined };
  const req = new Request("http://localhost/api/v1/system/bootstrap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: "AdminSuperSecret@2026"
    })
  });

  const res = await worker.fetch(req, envWithoutToken);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "BOOTSTRAP_DISABLED");
});

test("SECURITY: POST /api/v1/system/bootstrap is REJECTED (401 INVALID_BOOTSTRAP_TOKEN) with wrong token", async () => {
  const envWithToken = { ...baseEnv, BOOTSTRAP_TOKEN: "secret-bootstrap-key-999" };
  const req = new Request("http://localhost/api/v1/system/bootstrap", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Bootstrap-Token": "wrong-token"
    },
    body: JSON.stringify({
      username: "admin",
      password: "AdminSuperSecret@2026"
    })
  });

  const res = await worker.fetch(req, envWithToken);
  assert.strictEqual(res.status, 401);
  const json = await res.json();
  assert.strictEqual(json.error.code, "INVALID_BOOTSTRAP_TOKEN");
});

const bootstrapHeaders = {
  "Content-Type": "application/json",
  "X-Bootstrap-Token": "secret-bootstrap-key-999"
};

test("POST /api/v1/system/bootstrap: rejects weak password", async () => {
  const req = new Request("http://localhost/api/v1/system/bootstrap", {
    method: "POST",
    headers: bootstrapHeaders,
    body: JSON.stringify({
      username: "admin",
      password: "123456" // nằm trong blacklist
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 400);
  const json = await res.json();
  assert.strictEqual(json.success, false);
});

let bootstrapTempPassword;

test("POST /api/v1/system/bootstrap: securely creates initial Admin with strong password when BOOTSTRAP_TOKEN matches", async () => {
  const req = new Request("http://localhost/api/v1/system/bootstrap", {
    method: "POST",
    headers: bootstrapHeaders,
    body: JSON.stringify({
      username: "admin",
      password: "AdminSuperSecret@2026",
      full_name: "Quản trị viên khởi tạo"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 201);
  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.strictEqual(json.data.user.username, "admin");
  assert.strictEqual(json.data.user.role, "ADMIN");
  assert.strictEqual(json.data.must_change_password, true);
  bootstrapTempPassword = json.data.temporary_password;
  assert.strictEqual(bootstrapTempPassword, "AdminSuperSecret@2026");
});

test("SECURITY: Subsequent bootstrap call is BLOCKED with 403 BOOTSTRAP_ALREADY_COMPLETED", async () => {
  const req = new Request("http://localhost/api/v1/system/bootstrap", {
    method: "POST",
    headers: bootstrapHeaders,
    body: JSON.stringify({
      username: "hacker_admin",
      password: "HackerPassword@2026"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "BOOTSTRAP_ALREADY_COMPLETED");
});



// ====================================================================
// NHÓM 3: RATE LIMITING & CHỐNG BRUTE FORCE (P1 FIX)
// ====================================================================

test("POST /api/v1/auth/login: rejects wrong credentials with anti-enumeration message", async () => {
  resetAllRateLimitsForTesting();
  const req = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "CF-Connecting-IP": "198.51.100.1"
    },
    body: JSON.stringify({
      username: "admin",
      password: "wrong_password_1"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);
  const json = await res.json();
  assert.strictEqual(json.error.code, "INVALID_CREDENTIALS");
  assert.strictEqual(json.error.message, "Tên đăng nhập hoặc mật khẩu không chính xác.");
});

test("RATE LIMITING: 5 consecutive failed logins trigger HTTP 429 TOO_MANY_REQUESTS", async () => {
  resetAllRateLimitsForTesting();
  const attackerIp = "203.0.113.50";

  for (let i = 1; i <= 5; i++) {
    const req = new Request("http://localhost/api/v1/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "CF-Connecting-IP": attackerIp
      },
      body: JSON.stringify({
        username: "admin",
        password: `wrong_pass_${i}`
      })
    });
    const res = await worker.fetch(req, baseEnv);
    assert.strictEqual(res.status, 401);
  }

  // Lần thứ 6: Bị Rate-limit 429
  const blockedReq = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "CF-Connecting-IP": attackerIp
    },
    body: JSON.stringify({
      username: "admin",
      password: "any_password"
    })
  });
  const blockedRes = await worker.fetch(blockedReq, baseEnv);
  assert.strictEqual(blockedRes.status, 429);
  assert.ok(blockedRes.headers.get("Retry-After"));
  const blockedJson = await blockedRes.json();
  assert.strictEqual(blockedJson.error.code, "TOO_MANY_REQUESTS");
  assert.ok(blockedJson.error.message.includes("Quá nhiều lần đăng nhập"));

  // IP khác vẫn truy cập bình thường
  const normalReq = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "CF-Connecting-IP": "203.0.113.99"
    },
    body: JSON.stringify({
      username: "admin",
      password: bootstrapTempPassword
    })
  });
  const normalRes = await worker.fetch(normalReq, baseEnv);
  assert.strictEqual(normalRes.status, 200);
});

// ====================================================================
// NHÓM 4: BẮT BUỘC ĐỔI MẬT KHẨU LẦN ĐẦU (MUST_CHANGE_PASSWORD)
// ====================================================================

let adminToken;

test("Login admin with bootstrap password -> must_change_password=true and HttpOnly cookie", async () => {
  resetAllRateLimitsForTesting();
  const req = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "admin",
      password: bootstrapTempPassword
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.strictEqual(json.data.user.must_change_password, true);
  adminToken = json.data.token;

  // Kiểm tra Cookie
  const cookie = res.headers.get("Set-Cookie");
  assert.ok(cookie);
  assert.ok(cookie.includes("HttpOnly"));
  assert.ok(cookie.includes("SameSite=Lax"));
});

test("SECURITY: Protected API blocks admin with must_change_password=1", async () => {
  const req = new Request("http://localhost/api/v1/users", {
    method: "GET",
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "PASSWORD_CHANGE_REQUIRED");
});

test("POST /api/v1/auth/change-password: rejects weak blacklisted password", async () => {
  const req = new Request("http://localhost/api/v1/auth/change-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      current_password: bootstrapTempPassword,
      new_password: "password123"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 400);
});

test("POST /api/v1/auth/change-password: successfully updates to strong password", async () => {
  const req = new Request("http://localhost/api/v1/auth/change-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      current_password: bootstrapTempPassword,
      new_password: "AdminFinalPassword#2026"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.strictEqual(json.data.must_change_password, false);
});

test("Admin now accesses protected /api/v1/users after changing password", async () => {
  const req = new Request("http://localhost/api/v1/users", {
    method: "GET",
    headers: { Authorization: `Bearer ${adminToken}` }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.strictEqual(json.data.length, 1);
});

// ====================================================================
// NHÓM 5: CSRF & ORIGIN PROTECTION (P1 FIX)
// ====================================================================

test("CSRF REJECTION: Cookie-authenticated unsafe POST with missing Origin is REJECTED (403)", async () => {
  // Request dùng Cookie mà không có Bearer token, không có Origin header
  const req = new Request("http://localhost/api/v1/auth/logout", {
    method: "POST",
    headers: {
      Cookie: `auth_token=${adminToken}`
      // Không có Origin / Referer
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "CSRF_PROTECTION_FAILED");
});

test("CSRF REJECTION: Cookie-authenticated unsafe POST with untrusted Origin is REJECTED (403)", async () => {
  const req = new Request("http://localhost/api/v1/auth/logout", {
    method: "POST",
    headers: {
      Cookie: `auth_token=${adminToken}`,
      Origin: "https://evil-attacker.com"
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "CSRF_PROTECTION_FAILED");
});

test("CSRF PASS: Cookie-authenticated unsafe POST with trusted Origin SUCCEEDS", async () => {
  // Thay vì logout làm mất session admin, test đổi tên user profile
  const req = new Request("http://localhost/api/v1/users/1", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Cookie: `auth_token=${adminToken}`,
      Origin: "http://localhost:3000" // Trusted origin
    },
    body: JSON.stringify({ full_name: "Quản trị viên cấp cao" })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.strictEqual(json.data.full_name, "Quản trị viên cấp cao");
});

test("CSRF BYPASS: Bearer Token M2M requests do not require Origin", async () => {
  // Bearer token cho API clients / scripts không bị chặn CSRF
  const req = new Request("http://localhost/api/v1/users/1", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
      // Không có Cookie, không có Origin
    },
    body: JSON.stringify({ full_name: "Quản trị viên hệ thống" })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
});

// ====================================================================
// NHÓM 6: QUẢN LÝ NGƯỜI DÙNG (USERS), RBAC & AUDIT LOGS
// ====================================================================

let standardUserId;
let standardTempPassword;
let standardUserToken;

test("POST /api/v1/users: Admin creates user with random strong password and must_change_password=1", async () => {
  const req = new Request("http://localhost/api/v1/users", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({
      username: "kiemke_01",
      full_name: "Nhân viên kiểm kho 01",
      role: "USER"
      // Không truyền password -> hệ thống tự sinh ngẫu nhiên mạnh
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 201);
  const json = await res.json();
  assert.strictEqual(json.data.username, "kiemke_01");
  assert.strictEqual(json.data.must_change_password, true);
  assert.ok(json.data.temporary_password);
  assert.ok(json.data.temporary_password.length >= 12);
  standardUserId = json.data.id;
  standardTempPassword = json.data.temporary_password;
});

test("Standard user logs in and updates password", async () => {
  resetAllRateLimitsForTesting();
  const loginReq = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "kiemke_01",
      password: standardTempPassword
    })
  });
  const loginRes = await worker.fetch(loginReq, baseEnv);
  const loginJson = await loginRes.json();
  assert.strictEqual(loginRes.status, 200);
  standardUserToken = loginJson.data.token;

  // Đổi mật khẩu
  const chgReq = new Request("http://localhost/api/v1/auth/change-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${standardUserToken}`
    },
    body: JSON.stringify({
      current_password: standardTempPassword,
      new_password: "UserSecurePassword@2026"
    })
  });
  const chgRes = await worker.fetch(chgReq, baseEnv);
  assert.strictEqual(chgRes.status, 200);
});

test("RBAC: Standard user cannot call Admin endpoints (403 FORBIDDEN_ADMIN_ONLY)", async () => {
  const req = new Request("http://localhost/api/v1/users", {
    method: "GET",
    headers: { Authorization: `Bearer ${standardUserToken}` }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "FORBIDDEN_ADMIN_ONLY");
});

test("DEADLOCK PREVENTION: Admin cannot demote the last active Admin account", async () => {
  const req = new Request("http://localhost/api/v1/users/1", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({ role: "USER" })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 400);
  const json = await res.json();
  assert.strictEqual(json.error.code, "CANNOT_DEMOTE_LAST_ADMIN");
});

test("DEADLOCK PREVENTION: Admin cannot lock the last active Admin account", async () => {
  const req = new Request("http://localhost/api/v1/users/1/status", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({ is_active: false })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 400);
  const json = await res.json();
  assert.strictEqual(json.error.code, "CANNOT_LOCK_LAST_ADMIN");
});

test("LOCKOUT & SESSION REVOCATION: Admin locks standard user -> sessions revoked immediately", async () => {
  const req = new Request(`http://localhost/api/v1/users/${standardUserId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({ is_active: false })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  // Phiên của user bị từ chối ngay lập tức
  const testSessionReq = new Request("http://localhost/api/v1/auth/me", {
    method: "GET",
    headers: { Authorization: `Bearer ${standardUserToken}` }
  });
  const testSessionRes = await worker.fetch(testSessionReq, baseEnv);
  assert.strictEqual(testSessionRes.status, 401);
});

test("ANTI-ENUMERATION ON LOCKED ACCOUNT: Wrong password on locked account returns 401 (not 403)", async () => {
  resetAllRateLimitsForTesting();
  const req = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "kiemke_01",
      password: "incorrect_password"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);
  const json = await res.json();
  // Không được báo ACCOUNT_LOCKED khi chưa đúng mật khẩu!
  assert.strictEqual(json.error.code, "INVALID_CREDENTIALS");
});

test("Correct password on locked account returns 403 ACCOUNT_LOCKED", async () => {
  resetAllRateLimitsForTesting();
  const req = new Request("http://localhost/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: "kiemke_01",
      password: "UserSecurePassword@2026"
    })
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 403);
  const json = await res.json();
  assert.strictEqual(json.error.code, "ACCOUNT_LOCKED");
});

test("RESET PASSWORD: Admin resets password -> generates strong password and revokes all sessions", async () => {
  const req = new Request(`http://localhost/api/v1/users/${standardUserId}/reset-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${adminToken}`
    },
    body: JSON.stringify({})
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const json = await res.json();
  assert.strictEqual(json.data.must_change_password, true);
  assert.strictEqual(json.data.sessions_revoked, true);
  assert.ok(json.data.temporary_password);
  assert.ok(json.data.temporary_password.length >= 12);
});

test("AUDIT LOGS: audit_logs table contains recorded security events", async () => {
  const logs = await testDb.prepare("SELECT action, target_type FROM audit_logs ORDER BY id ASC").all();
  assert.ok(logs.results.length >= 5);
  const actions = logs.results.map((r) => r.action);
  assert.ok(actions.includes("SYSTEM_BOOTSTRAP_ADMIN"));
  assert.ok(actions.includes("LOGIN_SUCCESS"));
  assert.ok(actions.includes("PASSWORD_CHANGED"));
  assert.ok(actions.includes("USER_CREATED"));
});

test("POST /api/v1/auth/logout: revokes session and clears cookie", async () => {
  const req = new Request("http://localhost/api/v1/auth/logout", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${adminToken}`
    }
  });

  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  const cookie = res.headers.get("Set-Cookie");
  assert.ok(cookie.includes("Max-Age=0"));
});
