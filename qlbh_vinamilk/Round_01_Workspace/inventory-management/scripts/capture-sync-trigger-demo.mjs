import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, "..");
const OUTPUT_IMAGE = path.resolve(ROOT_DIR, "reports/r07_sync_triggered_feedback.png");

async function cdpRequest(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = Math.floor(Math.random() * 1000000);
    const handler = (msg) => {
      const data = JSON.parse(msg.data);
      if (data.id === id) {
        ws.removeEventListener("message", handler);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function main() {
  const loginRes = await fetch("http://127.0.0.1:8787/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "Vinamilk@2026" })
  });
  const loginData = await loginRes.json();
  const token = loginData.data?.token;

  const chromeProcess = spawn(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    [
      "--headless",
      "--disable-gpu",
      "--remote-debugging-port=9227",
      "--window-size=1440,900",
      "--user-data-dir=/tmp/chrome_audit_sync_feedback"
    ]
  );

  await new Promise((r) => setTimeout(r, 1200));

  const listRes = await fetch("http://127.0.0.1:9227/json/list");
  const targets = await listRes.json();
  const pageTarget = targets.find((t) => t.type === "page") || targets[0];
  const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
  await new Promise((resolve) => ws.addEventListener("open", resolve));

  await cdpRequest(ws, "Page.enable");
  await cdpRequest(ws, "Network.enable");
  await cdpRequest(ws, "DOM.enable");
  await cdpRequest(ws, "Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false
  });

  await cdpRequest(ws, "Network.setCookie", {
    name: "vinamilk_session",
    value: token,
    domain: "localhost",
    path: "/",
    httpOnly: true
  });

  await cdpRequest(ws, "Page.navigate", { url: "http://localhost:5173/?tab=sync" });
  await new Promise((r) => setTimeout(r, 1500));

  await cdpRequest(ws, "Runtime.evaluate", {
    expression: `localStorage.setItem("vinamilk_auth_token", "${token}"); window.location.reload();`
  });
  await new Promise((r) => setTimeout(r, 2000));

  // Nhấn nút "Đồng bộ ngay"
  await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Đồng bộ ngay'));
      if (btn) btn.click();
    `
  });
  await new Promise((r) => setTimeout(r, 2500));

  const shot = await cdpRequest(ws, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUTPUT_IMAGE, Buffer.from(shot.data, "base64"));
  console.log("   ✔ Ảnh chụp feedback lưu tại:", OUTPUT_IMAGE);

  ws.close();
  chromeProcess.kill();
  process.exit(0);
}

main().catch((err) => {
  console.error("Lỗi:", err);
  process.exit(1);
});
