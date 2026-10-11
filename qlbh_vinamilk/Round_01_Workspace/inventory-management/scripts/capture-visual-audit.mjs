import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPORTS_DIR = path.resolve(__dirname, "../reports");

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
  // 1. Lấy token trực tiếp từ backend API
  const adminLoginRes = await fetch("http://127.0.0.1:8787/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "Vinamilk@2026" })
  });
  const adminLogin = await adminLoginRes.json();
  const adminToken = adminLogin.data?.token;

  const userLoginRes = await fetch("http://127.0.0.1:8787/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "user1", password: "Vinamilk@2026" })
  });
  const userLogin = await userLoginRes.json();
  const userToken = userLogin.data?.token;

  console.log("Got tokens: admin =", !!adminToken, ", user =", !!userToken);

  const targetsRes = await fetch("http://127.0.0.1:9222/json/list");
  const targets = await targetsRes.json();
  const pageTarget = targets.find((t) => t.type === "page") || targets[0];
  const pageWsUrl = pageTarget.webSocketDebuggerUrl;

  const ws = new WebSocket(pageWsUrl);
  await new Promise((resolve) => ws.addEventListener("open", resolve));

  await cdpRequest(ws, "Page.enable");
  await cdpRequest(ws, "DOM.enable");
  await cdpRequest(ws, "Network.enable");

  // Viewport máy tính để bàn chuẩn 1440x900
  await cdpRequest(ws, "Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false
  });

  // Điều hướng đến http://localhost:5173/
  console.log("Navigating to http://localhost:5173/ ...");
  await cdpRequest(ws, "Page.navigate", { url: "http://localhost:5173/" });
  await new Promise((r) => setTimeout(r, 1500));

  // Thiết lập cookie auth_token cho ADMIN và reload
  console.log("Setting Admin cookie via document.cookie...");
  await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      document.cookie = "auth_token=${adminToken}; path=/; max-age=86400";
      window.location.reload();
    `
  });
  await new Promise((r) => setTimeout(r, 2500));

  // Kiểm tra stylesheet và phần tử UI thực của ADMIN Dashboard
  const adminEval = await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      (() => {
        const header = document.querySelector('header');
        const aside = document.querySelector('aside');
        const kpis = document.querySelectorAll('.grid > div');
        const banner = document.querySelector('.bg-gradient-to-r');
        const combobox = document.querySelector('select');
        return {
          headerText: header ? header.innerText.replace(/\\n/g, ' | ') : 'NO_HEADER',
          hasSidebar: !!aside,
          sidebarDisplay: aside ? window.getComputedStyle(aside).display : '',
          kpiCount: kpis.length,
          hasBanner: !!banner,
          comboboxValue: combobox ? combobox.value : ''
        };
      })()
    `,
    returnByValue: true
  });
  console.log("Admin Dashboard Elements:", adminEval.result.value);

  const adminShot = await cdpRequest(ws, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(REPORTS_DIR, "r06_fix02_admin_dashboard.png"), Buffer.from(adminShot.data, "base64"));
  console.log("Saved reports/r06_fix02_admin_dashboard.png");

  // Chọn cửa hàng CH41551 để kiểm tra P2 Header Context
  console.log("Selecting store CH41551...");
  await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      (() => {
        const select = document.querySelector('select');
        if (select) {
          select.value = 'CH41551';
          select.dispatchEvent(new Event('change', { bubbles: true }));
        }
      })()
    `
  });
  await new Promise((r) => setTimeout(r, 1200));

  const storeEval = await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      (() => {
        const header = document.querySelector('header');
        return header ? header.innerText.replace(/\\n/g, ' | ') : '';
      })()
    `,
    returnByValue: true
  });
  console.log("Header with Store Selected:", storeEval.result.value);

  const storeShot = await cdpRequest(ws, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(REPORTS_DIR, "r06_fix02_store_selected.png"), Buffer.from(storeShot.data, "base64"));
  console.log("Saved reports/r06_fix02_store_selected.png");

  // 2. Chuyển sang USER DASHBOARD (Kiểm tra RBAC)
  console.log("Switching to USER cookie...");
  await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      document.cookie = "auth_token=${userToken}; path=/; max-age=86400";
      window.location.reload();
    `
  });
  await new Promise((r) => setTimeout(r, 2500));

  const userEval = await cdpRequest(ws, "Runtime.evaluate", {
    expression: `
      (() => {
        const aside = document.querySelector('aside');
        const text = aside ? aside.innerText : '';
        const hasAdminUsers = text.includes('Quản lý người dùng');
        const hasTrash = text.includes('Thùng rác');
        const header = document.querySelector('header');
        return {
          hasAdminUsers,
          hasTrash,
          headerText: header ? header.innerText.replace(/\\n/g, ' | ') : ''
        };
      })()
    `,
    returnByValue: true
  });
  console.log("User Dashboard RBAC Evaluation:", userEval.result.value);

  const userShot = await cdpRequest(ws, "Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(REPORTS_DIR, "r06_fix02_user_dashboard.png"), Buffer.from(userShot.data, "base64"));
  console.log("Saved reports/r06_fix02_user_dashboard.png");

  ws.close();
  console.log("All visual audit screenshots captured successfully!");
}

main().catch(console.error);
