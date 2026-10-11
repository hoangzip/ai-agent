# BÁO CÁO THẨM ĐỊNH CHẤT LƯỢNG ĐỘC LẬP (QC REVIEW - FIX 02)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 02/10 – Project Foundation, Database & API (Fix 02: Security & Deployment Contract)  
**Vai trò thực hiện:** QC Reviewer (Độc lập)  
**Ngày thực hiện:** 11/10/2026  
**Đánh giá:** **PASS (ĐỦ ĐIỀU KIỆN ĐÓNG GATE ROUND 02)**  

---

## 1. THẨM ĐỊNH KẾT QUẢ KHẮC PHỤC CÁC PHÁT HIỆN TỪ REVIEW REVISION 2

### 1.1. Thẩm định P1: Bảo mật CORS – Exact Origin Allowlist
- **Vấn đề cũ:** Middleware CORS sử dụng regex wildcard cho phép bất kỳ domain nào thuộc `*.pages.dev` hoặc `*.workers.dev` gửi credentials, gây nguy cơ rò rỉ session/CSRF khi triển khai xác thực.
- **Biện pháp đã sửa:**
  - Viết lại hoàn toàn `apps/api/src/middleware/cors.ts`.
  - Loại bỏ 100% regex wildcard (`*.pages.dev`, `*.workers.dev`).
  - Áp dụng cơ chế **EXACT MATCH** so khớp chính xác từng ký tự từ allowlist (`DEFAULT_DEV_ORIGINS` cho local dev và `env.ALLOWED_ORIGINS` cấu hình tường minh).
  - Nếu `Origin` không có trong allowlist hoặc không có header `Origin`: Worker phản hồi HTTP 403 cho OPTIONS, và KHÔNG xuất `Access-Control-Allow-Origin` lẫn `Access-Control-Allow-Credentials`.
  - Luôn đính kèm header `Vary: Origin` để ngăn chặn cache poisoning tại CDN/Edge proxy.
  - Viết 6 negative tests kiểm tra trực tiếp (untrusted `*.pages.dev`, untrusted `*.workers.dev`, missing origin, localhost trong production). Kết quả: **100% PASS**.

### 1.2. Thẩm định P1/P2: Error Handler Fail-Closed (Production-Safe Default)
- **Vấn đề cũ:** Khi thiếu biến `ENVIRONMENT` hoặc không xác định, logic `isDev = !options.env || ...` đánh giá là dev và làm lộ thông tin chi tiết lỗi nội bộ (stack trace, DB credentials).
- **Biện pháp đã sửa:**
  - Viết lại `apps/api/src/middleware/errorHandler.ts`: Chuyển sang mô hình **Fail-Closed**.
  - Chỉ khi biến `ENVIRONMENT` được cấu hình tường minh là `"development"` hoặc `"test"` thì mới trả về `details` lỗi nội bộ.
  - Khi thiếu biến `ENVIRONMENT`, hoặc mang bất kỳ giá trị nào khác (kể cả `undefined`), `details` đối với lỗi 500 luôn là `null` và `message` được thay bằng câu thông báo an toàn chuẩn.
  - Cập nhật `apps/api/wrangler.toml` mặc định `ENVIRONMENT = "production"` ở mức gốc.
  - Bổ sung 4 unit/regression tests kiểm tra các kịch bản: missing env, production env, invalid env, dev/test env. Kết quả: **100% PASS**.

### 1.3. Thẩm định P2: Hợp đồng Kết nối và Định tuyến Frontend / Worker API
- **Vấn đề cũ:** `apps/web` chỉ gọi `/api` tĩnh mà không có proxy/routing contract khi deploy riêng Cloudflare Pages và Cloudflare Workers.
- **Biện pháp đã sửa:**
  - Hỗ trợ mô hình kép linh hoạt:
    1. **Mô hình Cross-Origin (Tách domain):** `apps/web/src/api/client.ts` đọc biến môi trường `VITE_API_BASE_URL` động kết hợp `credentials: "include"`. Cho phép trỏ trực tiếp tới Worker URL khi cấu hình `ALLOWED_ORIGINS`.
    2. **Mô hình Same-Origin (Chung domain Pages):** Cung cấp file hợp đồng `apps/web/public/_routes.json` chỉ định routing Cloudflare Pages cho các path `/api/*`, kèm proxy function `apps/web/functions/api/[[catchall]].ts` (hỗ trợ Service Binding `API_WORKER` hoặc upstream `API_WORKER_URL`).
  - Đã kiểm chứng build Vite và test cấu trúc file: **PASS**.

### 1.4. Thẩm định P2: Độ chính xác Tiền tệ VND trong Database Schema
- **Vấn đề cũ:** `total_amount_vnd`, `unit_price`, `total_amount` khai báo `REAL`, tiềm ẩn nguy cơ sai lệch số học dấu phẩy động nhị phân với dữ liệu kế toán VND.
- **Biện pháp đã sửa:**
  - Điều chỉnh `database/migrations/0001_initial_schema.sql`: Khai báo `total_amount_vnd INTEGER`, `unit_price INTEGER`, `total_amount INTEGER`. Trong SQLite D1, kiểu `INTEGER` lưu trữ số nguyên 64-bit có dấu (đến 9 triệu tỷ), bảo đảm chính xác 100% cho mọi giá trị tiền VND.
  - Các trường số lượng (`quantity`, `total_quantity`, `conversion_rate`) giữ `REAL` do đơn vị có thể có phần thập phân (hộp lẻ, kg, tỷ lệ quy đổi).
  - Đã thêm kiểm thử tự động `test_13_vnd_currency_integer_precision`: **PASS**.

### 1.5. Thẩm định P3: Định dạng Số Locale Tiếng Việt trên Dashboard
- **Vấn đề cũ:** Bảng và KPI trên Dashboard dùng dấu phẩy `,` phân cách hàng nghìn kiểu US thay vì dấu chấm `.` theo chuẩn kế toán Việt Nam.
- **Biện pháp đã sửa:**
  - Chuẩn hóa toàn bộ số liệu mẫu trong `DashboardPage.tsx`: `16.972`, `273.775.891 đ`, `17.147`, `275.711.737 đ`, `-1.935.846 đ`...

### 1.6. Thẩm định P3: Tách biệt Script Typecheck
- Đã tách `"typecheck": "tsc --noEmit"` riêng biệt trong `apps/web/package.json` và root `package.json`, không còn gộp lẫn với `vite build`.

---

## 2. TỔNG HỢP KIỂM CHỨNG TỰ ĐỘNG
- **Node.js test suite:** 19/19 PASS (bao gồm 6 negative CORS tests, 4 production-safe error handler tests).
- **Python Pytest suite:** 14/14 PASS (bao gồm kiểm tra schema INTEGER VND, exact CORS source code, Pages routes contract).
- **Tổng cộng:** **33/33 TEST CASES PASS (100%)**.
- **TypeScript & Build:** `npm run build` và `npm run typecheck` đạt mã thoát 0 (0 errors).

---

## 3. KẾT LUẬN CỦA QC REVIEWER
Toàn bộ các phát hiện P1, P2, P3 từ Independent Review Revision 2 đã được xử lý triệt để, đúng cam kết kỹ thuật, có bằng chứng thực nghiệm đầy đủ.

**QUYẾT ĐỊNH: ĐỦ ĐIỀU KIỆN ĐÓNG GATE ROUND 02 (PASS)**.
Sẵn sàng cho người dùng nghiệm thu để bước tiếp sang Round 03 (Authentication & User Management).
