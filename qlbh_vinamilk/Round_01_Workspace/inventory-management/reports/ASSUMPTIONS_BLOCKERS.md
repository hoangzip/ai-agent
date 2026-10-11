# BÁO CÁO GIẢ ĐỊNH & ĐIỂM CHẶN (ASSUMPTIONS & BLOCKERS – ROUND 07 FIX 02)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 07/10 – Google Drive Auto-Sync Engine (FIX 02)  
**Quyết định Nghiệm thu:** **PARTIAL – HOLD (DỪNG TẠI ROUND 07 FIX 02, CHƯA CHUYỂN ROUND 08)**  
**Tình trạng Kết nối LIVE:** **BLOCKED_FOR_LIVE** (Chưa cấu hình quyền truy cập Google Service Account thực; mã nguồn tích hợp Live hoàn thiện với RS256 JWT sign & auto-refresh; tuyệt đối KHÔNG giả mạo kết nối LIVE).  
**Ngày cập nhật:** 12/10/2026  

---

## 1. KẾT QUẢ TRIỂN KHAI PHẠM VI FIX 02

| Mã lỗi | Mức độ | Vấn đề từ Đánh giá Độc lập (Fix 01 Review) | Giải pháp & Kết quả triển khai Fix 02 | Trạng thái |
|---|:---:|---|---|:---:|
| **P1-01** | Bắt buộc | Secret dự phòng biết trước (`BOOTSTRAP_TOKEN` / hardcode `"vinamilk-cron-secret"`). | **Fail-closed scheduled webhook:**<br>1. Loại bỏ 100% fallback sang `BOOTSTRAP_TOKEN` hoặc secret mặc định.<br>2. Bắt buộc có biến môi trường `SYNC_WEBHOOK_SECRET`; nếu thiếu trả 401 `UNCONFIGURED_WEBHOOK_SECRET`.<br>3. Kiểm tra bảo mật đa tầng: thiếu auth (401), sai secret (401), Origin từ bên ngoài không tin cậy (403 `FORBIDDEN_ORIGIN`).<br>4. Google Apps Script (`Code.gs`) đọc secret từ Script Properties (`PropertiesService.getScriptProperties().getProperty("SYNC_WEBHOOK_SECRET")`), không lưu secret trong mã nguồn. | **HOÀN THÀNH** |
| **P1-02** | Bắt buộc | Khóa chống chạy đồng thời không nguyên tử (SELECT trước INSERT gây race condition). | **Atomic Concurrency Lease Lock:**<br>1. Thiết kế bảng khóa nguyên tử `sync_locks` với `source_id PRIMARY KEY`.<br>2. Thu nhận khóa qua `INSERT ... ON CONFLICT DO NOTHING` kết hợp conditional update cho phép thu hồi stale lease an toàn sau 600s.<br>3. Giải phóng khóa bằng token ngẫu nhiên nguyên tử và đảm bảo gọi trong khối `finally` khi Worker crash midway.<br>4. Tạo file migration `database/migrations/0002_sync_concurrency_lock.sql` (chỉ chạy local/test, **chưa thực thi trên D1 production**).<br>5. Đã kiểm thử `Promise.all` đồng thời thực sự (1 request PASS, 1 request từ chối 409). | **HOÀN THÀNH** |
| **P1-03** | Bắt buộc | Quy trình cấp quyền LIVE chưa hoàn chỉnh; tài liệu chưa khớp code; nguy cơ token tĩnh. | **Chuẩn hóa xác thực LIVE End-to-End:**<br>1. Triển khai phương án Service Account tự cấp mới: Worker dùng Web Crypto native (`crypto.subtle` RS256 PKCS#8) ký JWT trực tiếp gửi tới `https://oauth2.googleapis.com/token` để nhận short-lived access token.<br>2. Hỗ trợ cơ chế token caching và tự động refresh khi thời gian sống dưới 5 phút.<br>3. Cập nhật tài liệu khớp 100% với code: hỗ trợ `GDRIVE_SERVICE_ACCOUNT_KEY` (JSON credentials) và `GDRIVE_ACCESS_TOKEN`.<br>4. Duy trì trạng thái minh bạch `BLOCKED_FOR_LIVE` khi chưa cấu hình quyền; không giả mạo LIVE. | **HOÀN THÀNH (BLOCKED_FOR_LIVE)** |
| **P2-01** | Cần xử lý | Trạng thái Partial outcome chưa được lưu trữ và thể hiện nhất quán. | **Thống nhất Partial Outcome:**<br>1. Bổ sung trường `outcome` ('SUCCESS' \| 'PARTIAL' \| 'FAILED' \| 'CONFLICT') trong bảng `sync_runs`.<br>2. API trả về trường `outcome` rõ ràng.<br>3. UI hiển thị trực quan huy hiệu `Một phần (PARTIAL)` trong bảng lịch sử đợt đồng bộ khi có file lỗi kèm file thành công/bỏ qua.<br>4. Không đánh dấu completed khi có lỗi file. | **HOÀN THÀNH** |
| **P2-02** | Cần xử lý | Phân trang có giới hạn cắt ngầm 20 trang / 2.000 file không cảnh báo. | **Giới hạn an toàn & Báo lỗi phân trang:**<br>1. Tại trang thứ 20, nếu Google Drive vẫn còn `nextPageToken`, hệ thống ném ngoại lệ an toàn `Vượt quá giới hạn phân trang an toàn (tối đa 20 trang / 2.000 file)...`<br>2. Tuyệt đối không âm thầm coi kết quả bị cắt bớt là đầy đủ. | **HOÀN THÀNH** |
| **P2-03** | Cần xử lý | Thử nghiệm revision thực tế chưa đầy đủ (chưa tiêm driver mock đổi revision). | **Dependency Injection cho Driver Mock:**<br>1. Cho phép tiêm `driver` tùy biến vào `triggerSync()`.<br>2. Bổ sung unit test tiêm mock driver với `version = 'REVISION_v2_MODIFIED_CONTENT'`, kiểm chứng hệ thống phát hiện chính xác `files_conflict = 1`, `outcome = 'CONFLICT'`, không ghi đè và không skip âm thầm. | **HOÀN THÀNH** |

---

## 2. CHÍNH SÁCH THAY ĐỔI CƠ SỞ DỮ LIỆU & QUY TRÌNH PHÊ DUYỆT D1 PRODUCTION

Tuân thủ nghiêm ngặt chỉ đạo của Người dùng: **"Nếu cần thay đổi cấu trúc database để bổ sung khóa đồng bộ, Agent chỉ được chuẩn bị migration và kiểm thử trên database local/test. Chưa thực thi thay đổi trên D1 production khi chưa có phê duyệt của bạn."**

1. **File Migration đã chuẩn bị:** `database/migrations/0002_sync_concurrency_lock.sql`
   - Tạo bảng khóa nguyên tử: `sync_locks(source_id PRIMARY KEY, lock_token, acquired_at, expires_at)`
   - Bổ sung cột lưu trữ kết quả: `ALTER TABLE sync_runs ADD COLUMN outcome TEXT DEFAULT 'SUCCESS';`
2. **Môi trường thực thi hiện tại:**
   - Đã nạp và kiểm thử thành công trên SQLite / Miniflare Test Database trong toàn bộ 199 bài test tự động.
   - **HOÀN TOÀN CHƯA THỰC THI** trên cơ sở dữ liệu Cloudflare D1 Production (`npx wrangler d1 execute ... --remote`).
3. **Quy trình Phê duyệt & Kế hoạch Rollback:**
   - **Bước 1:** Quản trị viên/Người dùng xem xét và phê duyệt file migration `0002_sync_concurrency_lock.sql`.
   - **Bước 2 (Chỉ chạy sau phê duyệt):**
     ```bash
     npx wrangler d1 execute vinamilk-inventory-db --remote --file=database/migrations/0002_sync_concurrency_lock.sql
     ```
   - **Kế hoạch Rollback (nếu cần):**
     ```sql
     DROP TABLE IF EXISTS sync_locks;
     -- Lưu ý: SQLite/D1 không hỗ trợ DROP COLUMN trên các phiên bản cũ, 
     -- nhưng cột outcome có giá trị mặc định 'SUCCESS' không gây ảnh hưởng tới các truy vấn cũ.
     ```

---

## 3. TÌNH TRẠNG KẾT NỐI GOOGLE DRIVE (LIVE vs SIMULATION)

1. **Simulation Mode (Khả dụng 100%):**
   - Đọc trực tiếp 4 file fixture Excel chuẩn từ thư mục `fixtures/Kiem ke/` đại diện cho Thư mục Google Drive `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`.
   - Toàn bộ 199 bài test tự động (129 Node.js + 70 Python pytest) đều **PASS 100%**.
   - Bảo toàn đầy đủ logic nghiệp vụ Ground Truth từ Round 04, 05, 06.

2. **Live Integration (Trạng thái: BLOCKED_FOR_LIVE):**
   - **Nguyên nhân:** Dự án chưa được cấu hình Google Service Account private key JSON hoặc OAuth2 Access Token thực tế cho thư mục Google Drive.
   - **Quy trình kết nối riêng cho Quản trị viên (khi sẵn sàng):**
     ```bash
     # Cấu hình Service Account Key JSON (đã tích hợp Web Crypto RS256 JWT sign & auto-refresh)
     wrangler secret put GDRIVE_SERVICE_ACCOUNT_KEY
     
     # Hoặc cấu hình OAuth2 Access Token ngắn hạn
     wrangler secret put GDRIVE_ACCESS_TOKEN
     
     # Cấu hình Secret cho Webhook theo lịch
     wrangler secret put SYNC_WEBHOOK_SECRET
     ```
   - **Cam kết an ninh:** Tuyệt đối không yêu cầu Người dùng nhập credentials trong chat. Không giả mạo log hoặc kết nối LIVE khi chưa có quyền thực tế.

---

## 4. QUYẾT ĐỊNH GATE NGHIỆM THU

- **Trạng thái:** **PARTIAL – HOLD**.
- **Hành động:** Dừng tại Round 07 Fix 02. Đóng gói mã nguồn ZIP và SHA256 ngoài ZIP để Người dùng tiếp tục nghiệm thu.
- **Cam kết:** **CHƯA CHUYỂN SANG ROUND 08** cho đến khi các lỗi chặn được khắc phục hoàn toàn và có quyết định nghiệm thu tiếp theo của Người dùng.
