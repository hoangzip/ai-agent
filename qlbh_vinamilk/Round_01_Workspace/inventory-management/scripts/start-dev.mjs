/**
 * Script: Khởi chạy Máy chủ Thử nghiệm Toàn diện (Fullstack Dev Server - Round 06)
 * File: scripts/start-dev.js
 *
 * Chức năng:
 * 1. Khởi tạo Cơ sở Dữ liệu Cloudflare D1 Local qua Miniflare.
 * 2. Thực thi Migration schema chuẩn 10 bảng.
 * 3. Nạp sẵn tài khoản Quản trị viên & Nhân viên (admin, user1 / Vinamilk@2026).
 * 4. Tự động nạp sẵn 4 file Excel kiểm kê thực tế vào DB (COMPLETED).
 * 5. Khởi chạy Backend Worker API trên cổng 8787.
 * 6. Khởi chạy Frontend React Web App qua Vite trên cổng 5173.
 */

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { createServer as createViteServer } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, "..");
const MIGRATION_PATH = path.resolve(ROOT_DIR, "database/migrations/0001_initial_schema.sql");
const REAL_DATA_DIR = path.resolve(ROOT_DIR, "../../Data Source/Kiem ke");

const REAL_FILES = [
  { name: "KiemKe_KK.CH41551.26.339000_20261009.xlsx", shift: "Sáng" },
  { name: "KiemKe_KK.CH41551.26.339513_20261009.xlsx", shift: "Chiều" },
  { name: "KiemKe_KK.CH41551.26.339931_20261010.xlsx", shift: "Tối" },
  { name: "KiemKe_KK.CH41551.26.340231_20261011.xlsx", shift: "Chiều" }
];

async function main() {
  console.log("========================================================================");
  console.log("  VINAMILK INVENTORY MANAGEMENT SYSTEM - KHỞI ĐỘNG DEV DEMO (ROUND 06)  ");
  console.log("========================================================================");

  // 1. Khởi tạo Miniflare & D1 Database
  console.log("1. Đang khởi tạo cơ sở dữ liệu Cloudflare D1...");
  const mf = new Miniflare({
    modules: true,
    script: "export default { fetch() {} }",
    d1Databases: ["DB"]
  });

  const db = await mf.getD1Database("DB");

  // 2. Thực thi migrations
  console.log("2. Đang thực thi migrations cơ sở dữ liệu...");
  const sql = fs.readFileSync(MIGRATION_PATH, "utf8");
  const cleanSql = sql.replace(/--.*$/gm, "").trim();
  const statements = cleanSql.split(";").map((s) => s.trim()).filter((s) => s.length > 0);
  for (const stmt of statements) {
    await db.prepare(stmt).run();
  }

  // 3. Nạp sẵn tài khoản người dùng
  console.log("3. Đang thiết lập tài khoản đăng nhập mẫu...");
  const { hashPassword } = await import("../apps/api/dist/security/password.js");
  const passHash = await hashPassword("Vinamilk@2026");

  await db
    .prepare(
      `INSERT OR REPLACE INTO users (id, username, password_hash, role, full_name, must_change_password, is_active)
       VALUES (1, 'admin', ?, 'ADMIN', 'Quản trị viên Hệ thống', 0, 1),
              (2, 'user1', ?, 'USER', 'Nhân viên Kiểm kê Kho', 0, 1)`
    )
    .bind(passHash, passHash)
    .run();

  // 4. Nạp sẵn 4 file Excel kiểm kê thật
  console.log("4. Đang nạp dữ liệu kiểm kê thực tế từ 4 file Excel nguồn...");
  const { parseInventoryExcel } = await import("../apps/api/dist/services/excelParser.js");
  const { importSnapshot } = await import("../apps/api/dist/services/inventoryService.js");

  for (const item of REAL_FILES) {
    const filePath = path.join(REAL_DATA_DIR, item.name);
    if (fs.existsSync(filePath)) {
      try {
        const buffer = fs.readFileSync(filePath);
        const parsed = await parseInventoryExcel(buffer, item.name, { shift: item.shift });
        if (parsed.isValid) {
          await importSnapshot(db, parsed, {
            userId: 1,
            autoCommit: true,
            shift: item.shift,
            ipAddress: "127.0.0.1"
          });
          console.log(`   ✔ Đã nạp thành công: ${parsed.metadata.full_code} (${item.shift})`);
        }
      } catch (err) {
        console.warn(`   ⚠ Không thể nạp ${item.name}:`, err.message);
      }
    }
  }

  // 5. Khởi chạy Backend Worker API HTTP Server trên cổng 8787
  console.log("5. Đang khởi chạy máy chủ Backend API (Port 8787)...");
  const worker = (await import("../apps/api/dist/index.js")).default;
  const env = {
    DB: db,
    ENVIRONMENT: "development",
    ROUND: "06",
    APP_TIMEZONE: "Asia/Ho_Chi_Minh",
    ALLOWED_ORIGINS: "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
  };

  const apiServer = http.createServer(async (req, res) => {
    try {
      const url = "http://" + (req.headers.host || "127.0.0.1:8787") + req.url;
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const body = ["GET", "HEAD"].includes(req.method || "") ? undefined : Buffer.concat(chunks);

      const webReq = new Request(url, {
        method: req.method,
        headers: req.headers,
        body
      });

      const webRes = await worker.fetch(webReq, env, {});
      res.statusCode = webRes.status;
      for (const [k, v] of webRes.headers.entries()) {
        res.setHeader(k, v);
      }
      const resBuf = Buffer.from(await webRes.arrayBuffer());
      res.end(resBuf);
    } catch (err) {
      console.error("Lỗi xử lý API request:", err);
      res.statusCode = 500;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ success: false, error: { message: String(err) } }));
    }
  });

  await new Promise((resolve) => apiServer.listen(8787, "127.0.0.1", resolve));
  console.log("   ✔ Backend API Server đang chạy tại: http://127.0.0.1:8787");

  // 6. Khởi chạy Frontend React Web App qua Vite trên cổng 5173
  console.log("6. Đang khởi chạy máy chủ Frontend Web App (Port 5173)...");
  const viteServer = await createViteServer({
    configFile: path.resolve(ROOT_DIR, "apps/web/vite.config.ts"),
    root: path.resolve(ROOT_DIR, "apps/web"),
    server: {
      port: 5173,
      host: "0.0.0.0",
      allowedHosts: true
    }
  });

  await viteServer.listen();
  console.log("   ✔ Frontend Web App đang chạy tại : http://localhost:5173");

  // 7. Khởi chạy Scheduler nền tự động đồng bộ theo chu kỳ 60 phút (P1-01)
  const SYNC_INTERVAL_MS = 60 * 60 * 1000;
  console.log("7. Khởi tạo Scheduler tự động quét định kỳ (Chu kỳ: 60 phút / Time-driven)...");
  const autoSyncTimer = setInterval(async () => {
    try {
      console.log(`\n[AUTO_SYNC_SCHEDULER] Kích hoạt chu kỳ quét tự động...`);
      const { triggerSync } = await import("../apps/api/dist/services/syncService.js");
      const res = await triggerSync(db, env, { triggeredBy: "SCHEDULED" });
      console.log(`[AUTO_SYNC_SCHEDULER] Kết quả: Trạng thái ${res.status}, Nạp mới ${res.summary.files_imported}, Bỏ qua ${res.summary.files_skipped}.`);
    } catch (err) {
      console.error(`[AUTO_SYNC_SCHEDULER_ERROR]:`, err?.message || String(err));
    }
  }, SYNC_INTERVAL_MS);

  const cleanup = async () => {
    console.log("\nĐang tắt máy chủ thử nghiệm...");
    try {
      clearInterval(autoSyncTimer);
      await viteServer.close();
      apiServer.close();
      await mf.dispose();
      console.log("Đã dừng an toàn.");
      process.exit(0);
    } catch (e) {
      process.exit(0);
    }
  };

  process.on("SIGINT", cleanup);
  process.on("SIGTERM", cleanup);
}

main().catch((err) => {
  console.error("Lỗi khởi chạy server:", err);
  process.exit(1);
});
