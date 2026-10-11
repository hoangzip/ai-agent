import test from "node:test";
import assert from "node:assert";
import worker from "../dist/index.js";
import { createErrorResponse } from "../dist/middleware/errorHandler.js";

const baseEnv = {
  ENVIRONMENT: "test",
  ROUND: "02",
  APP_TIMEZONE: "Asia/Ho_Chi_Minh"
};

// ====================================================================
// NHÓM 1: ROUTE CƠ BẢN VÀ THỰC THI NGHIỆP VỤ ROUND 02
// ====================================================================

test("GET /api/health returns 200 and status ok", async () => {
  const req = new Request("http://localhost/api/health", { method: "GET" });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.strictEqual(json.data.status, "ok");
  assert.ok(json.meta.requestId);
});

test("GET /api/v1/system/info without DB returns not_configured honestly", async () => {
  const req = new Request("http://localhost/api/v1/system/info", { method: "GET" });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.success, true);
  assert.ok(json.data.round.includes("05/10"));
  assert.strictEqual(json.data.database.status, "not_configured");
  assert.ok(json.data.features);
  assert.ok(json.data.modules);
});

test("GET /api/v1/system/info with working DB returns connected", async () => {
  const mockDb = {
    prepare: (query) => ({
      first: async () => ({ 1: 1 })
    })
  };
  const envWithDb = { ...baseEnv, DB: mockDb };
  const req = new Request("http://localhost/api/v1/system/info", { method: "GET" });
  const res = await worker.fetch(req, envWithDb);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.data.database.status, "connected");
});

test("GET /api/v1/system/info with failing DB returns unavailable", async () => {
  const failingDb = {
    prepare: (query) => ({
      first: async () => { throw new Error("D1 connection timeout"); }
    })
  };
  const envWithFailingDb = { ...baseEnv, DB: failingDb };
  const req = new Request("http://localhost/api/v1/system/info", { method: "GET" });
  const res = await worker.fetch(req, envWithFailingDb);
  assert.strictEqual(res.status, 200);

  const json = await res.json();
  assert.strictEqual(json.data.database.status, "unavailable");
});

test("GET /api/snapshots is implemented in Round 04 and requires auth (401 UNAUTHORIZED)", async () => {
  const req = new Request("http://localhost/api/snapshots", { method: "GET" });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);

  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.code, "UNAUTHORIZED");
});

test("GET /api/v1/snapshots is implemented in Round 04 and requires auth (401 UNAUTHORIZED)", async () => {
  const req = new Request("http://localhost/api/v1/snapshots", { method: "GET" });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 401);

  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.code, "UNAUTHORIZED");
});

test("X-Request-ID sanitization: replaces invalid/oversized client ID", async () => {
  const dangerousId = "BAD<script>alert(1)</script>" + "x".repeat(100);
  const req = new Request("http://localhost/api/health", {
    method: "GET",
    headers: { "X-Request-ID": dangerousId }
  });
  const res = await worker.fetch(req, baseEnv);
  const headerId = res.headers.get("X-Request-ID");
  assert.notStrictEqual(headerId, dangerousId);
  assert.match(headerId, /^[0-9a-f-]{36}$/);
});

test("GET /api/nonexistent returns 404 with structured error", async () => {
  const req = new Request("http://localhost/api/nonexistent", { method: "GET" });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 404);

  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.code, "NOT_FOUND");
});

// ====================================================================
// NHÓM 2: BẢO MẬT CORS VÀ EXACT ORIGIN ALLOWLIST (FIX P1 REVIEW)
// ====================================================================

test("OPTIONS /api/health with allowed dev origin returns 204, ACAO and Vary: Origin", async () => {
  const req = new Request("http://localhost/api/health", {
    method: "OPTIONS",
    headers: { "Origin": "http://localhost:3000" }
  });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 204);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), "http://localhost:3000");
  assert.strictEqual(res.headers.get("Access-Control-Allow-Credentials"), "true");
  assert.ok(res.headers.get("Vary")?.includes("Origin"));
});

test("OPTIONS /api/health with configured ALLOWED_ORIGINS accepts exact match", async () => {
  const envWithOrigin = {
    ...baseEnv,
    ENVIRONMENT: "production",
    ALLOWED_ORIGINS: "https://inventory.vinamilk.com, https://preview.inventory.pages.dev"
  };
  const req = new Request("http://localhost/api/health", {
    method: "OPTIONS",
    headers: { "Origin": "https://inventory.vinamilk.com" }
  });
  const res = await worker.fetch(req, envWithOrigin);
  assert.strictEqual(res.status, 204);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), "https://inventory.vinamilk.com");
  assert.strictEqual(res.headers.get("Access-Control-Allow-Credentials"), "true");
  assert.ok(res.headers.get("Vary")?.includes("Origin"));
});

test("CORS NEGATIVE TEST: OPTIONS with untrusted *.pages.dev is REJECTED (403, NO ACAO)", async () => {
  const envWithOrigin = {
    ...baseEnv,
    ENVIRONMENT: "production",
    ALLOWED_ORIGINS: "https://trusted.vinamilk.com"
  };
  const req = new Request("http://localhost/api/health", {
    method: "OPTIONS",
    headers: { "Origin": "https://untrusted.pages.dev" }
  });
  const res = await worker.fetch(req, envWithOrigin);
  assert.strictEqual(res.status, 403);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), null);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Credentials"), null);
  assert.ok(res.headers.get("Vary")?.includes("Origin"));
});

test("CORS NEGATIVE TEST: OPTIONS with untrusted *.workers.dev is REJECTED (403, NO ACAO)", async () => {
  const envWithOrigin = {
    ...baseEnv,
    ENVIRONMENT: "production",
    ALLOWED_ORIGINS: "https://trusted.vinamilk.com"
  };
  const req = new Request("http://localhost/api/health", {
    method: "OPTIONS",
    headers: { "Origin": "https://untrusted.workers.dev" }
  });
  const res = await worker.fetch(req, envWithOrigin);
  assert.strictEqual(res.status, 403);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), null);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Credentials"), null);
});

test("CORS NEGATIVE TEST: GET request with untrusted origin does NOT receive ACAO or credentials", async () => {
  const envWithOrigin = {
    ...baseEnv,
    ENVIRONMENT: "production",
    ALLOWED_ORIGINS: "https://trusted.vinamilk.com"
  };
  const req = new Request("http://localhost/api/health", {
    method: "GET",
    headers: { "Origin": "https://untrusted.pages.dev" }
  });
  const res = await worker.fetch(req, envWithOrigin);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), null);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Credentials"), null);
  assert.ok(res.headers.get("Vary")?.includes("Origin"));
});

test("CORS NEGATIVE TEST: Request without Origin header does NOT receive ACAO or credentials", async () => {
  const req = new Request("http://localhost/api/health", { method: "GET" });
  const res = await worker.fetch(req, baseEnv);
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), null);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Credentials"), null);
  assert.ok(res.headers.get("Vary")?.includes("Origin"));
});

test("CORS NEGATIVE TEST: Localhost is rejected in production environment", async () => {
  const prodEnv = {
    ENVIRONMENT: "production",
    ROUND: "02"
    // ALLOWED_ORIGINS does not include localhost
  };
  const req = new Request("http://localhost/api/health", {
    method: "OPTIONS",
    headers: { "Origin": "http://localhost:3000" }
  });
  const res = await worker.fetch(req, prodEnv);
  assert.strictEqual(res.status, 403);
  assert.strictEqual(res.headers.get("Access-Control-Allow-Origin"), null);
});

// ====================================================================
// NHÓM 3: FAIL-CLOSED PRODUCTION-SAFE ERROR HANDLER (FIX P1/P2 REVIEW)
// ====================================================================

test("ERROR HANDLER: Missing ENVIRONMENT hides internal 500 error details (fail-closed default)", async () => {
  const res = createErrorResponse({
    status: 500,
    message: "Lỗi nội bộ có chứa mật khẩu db",
    details: "Sensitive stack trace with DB secrets: user=admin pass=supersecret",
    env: undefined // KHÔNG CÓ BIẾN ENVIRONMENT
  });
  assert.strictEqual(res.status, 500);

  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.code, "INTERNAL_SERVER_ERROR");
  assert.strictEqual(json.error.details, null); // DETAILS BỊ CHE GIẤU HOÀN TOÀN
  assert.strictEqual(json.error.message, "Lỗi máy chủ nội bộ trong quá trình xử lý yêu cầu");
});

test("ERROR HANDLER: Production ENVIRONMENT hides internal 500 error details", async () => {
  const res = createErrorResponse({
    status: 500,
    message: "Database crash",
    details: "SQLSTATE[HY000]: General error: 1045 Access denied for user",
    env: { ENVIRONMENT: "production" }
  });
  assert.strictEqual(res.status, 500);

  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.details, null);
  assert.strictEqual(json.error.message, "Lỗi máy chủ nội bộ trong quá trình xử lý yêu cầu");
});

test("ERROR HANDLER: Unknown/invalid ENVIRONMENT hides internal 500 error details", async () => {
  const res = createErrorResponse({
    status: 500,
    message: "Unknown env error",
    details: "Traceback error line 42",
    env: { ENVIRONMENT: "staging_public_testing" } // Không phải explicit development/test
  });
  assert.strictEqual(res.status, 500);

  const json = await res.json();
  assert.strictEqual(json.success, false);
  assert.strictEqual(json.error.details, null);
});

test("ERROR HANDLER: Explicit development/test ENVIRONMENT reveals details for debugging", async () => {
  const devRes = createErrorResponse({
    status: 500,
    message: "Debuggable dev error",
    details: "Detailed callstack info for developers",
    env: { ENVIRONMENT: "development" }
  });
  const devJson = await devRes.json();
  assert.strictEqual(devJson.error.details, "Detailed callstack info for developers");

  const testRes = createErrorResponse({
    status: 500,
    message: "Debuggable test error",
    details: "Detailed test assertion message",
    env: { ENVIRONMENT: "test" }
  });
  const testJson = await testRes.json();
  assert.strictEqual(testJson.error.details, "Detailed test assertion message");
});
