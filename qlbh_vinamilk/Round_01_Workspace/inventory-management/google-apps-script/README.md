# HƯỚNG DẪN THIẾT LẬP SCHEDULER TỰ ĐỘNG ĐỒNG BỘ GOOGLE DRIVE (60 PHÚT)

Tài liệu này cung cấp giải pháp lập lịch (Scheduler) chạy bền vững, miễn phí 100% trong hạn mức Free Tier để đáp ứng yêu cầu P1-01 của Round 07 Fix 01.

---

## Giải pháp 1: Cloudflare Workers Cron Triggers (Khuyến nghị)
Hệ thống đã cấu hình sẵn trong [apps/api/wrangler.toml](file:///Users/hoangtq13/AI-agent/Gemini/qlbh_vinamilk/Round_01_Workspace/inventory-management/apps/api/wrangler.toml):
```toml
[triggers]
crons = ["0 * * * *"] # Tự động kích hoạt mỗi giờ (phút thứ 0)
```
- **Xử lý:** Cloudflare sẽ tự động gọi hàm `scheduled` trong [apps/api/src/index.ts](file:///Users/hoangtq13/AI-agent/Gemini/qlbh_vinamilk/Round_01_Workspace/inventory-management/apps/api/src/index.ts) để chạy `triggerSync(db, env, { triggeredBy: 'SCHEDULED' })`.
- **Hạn mức:** Cloudflare Workers Free cho phép tối đa 3 cron triggers miễn phí hoàn toàn.

---

## Giải pháp 2: Google Apps Script Time-Driven Trigger
Nếu muốn chạy trực tiếp từ chính tài khoản Google Drive sở hữu thư mục `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`:
1. Truy cập [script.google.com](https://script.google.com/) và tạo Project mới: `Vinamilk Inventory Auto-Sync`.
2. Dán mã nguồn từ [Code.gs](file:///Users/hoangtq13/AI-agent/Gemini/qlbh_vinamilk/Round_01_Workspace/inventory-management/google-apps-script/Code.gs).
3. Cập nhật `API_BASE_URL` trong file `Code.gs`.
4. Cấu hình bảo mật qua Script Properties (không lưu secret trong code):
   - Vào **Project Settings (Cài đặt dự án)** -> cuộn đến mục **Script Properties (Thuộc tính tập lệnh)**.
   - Nhấn **Add script property**:
     - Property: `SYNC_WEBHOOK_SECRET`
     - Value: `<chuỗi bí mật khớp với Cloudflare Secret SYNC_WEBHOOK_SECRET>`
   - Nhấn **Save script properties**.
5. Chạy hàm `setupHourlyTrigger()` một lần để khởi tạo lịch Time-driven trigger chạy mỗi 1 giờ.
- **Hạn mức:** Google Apps Script Free Tier cho phép tối đa 90 phút thời gian thực thi/ngày và 20.000 lượt gọi UrlFetch/ngày (nhu cầu 24 lần gọi/ngày chỉ chiếm 0.12% quota).

---

## Giải pháp 3: Local Dev Server Background Scheduler
Khi chạy máy chủ thử nghiệm cục bộ qua lệnh `npm run dev`:
- Script [scripts/start-dev.mjs](file:///Users/hoangtq13/AI-agent/Gemini/qlbh_vinamilk/Round_01_Workspace/inventory-management/scripts/start-dev.mjs) tự động khởi tạo background timer chạy chu kỳ theo đúng `sync_interval_minutes` (mặc định 60 phút) và ghi log chi tiết kết quả.
