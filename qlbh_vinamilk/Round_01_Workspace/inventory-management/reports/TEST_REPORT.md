# BÁO CÁO KIỂM THỬ TỰ ĐỘNG & VISUAL SMOKE TEST – ROUND 07 FIX 02

**Dự án:** Inventory Management – Stock Reconciliation Web App (Vinamilk)  
**Phạm vi:** Round 07/10 – Google Drive Auto-Sync Engine (FIX 02)  
**Thời điểm thực thi:** 2026-10-12  
**Môi trường:** Node.js v20.18.0 + Miniflare D1 SQLite + Python 3.11 (Pytest) + Headless Chrome 154  
**Kết quả tổng quan:** **199/199 KIỂM THỬ ĐẠT (100% PASS) + VISUAL SMOKE TEST PASS**  
**Trạng thái Tích hợp LIVE:** **BLOCKED_FOR_LIVE** (Chưa cấu hình quyền Google Service Account thực; mã nguồn tích hợp Live hoàn thiện với RS256 JWT sign & auto-refresh; TUYỆT ĐỐI KHÔNG TUYÊN BỐ KẾT NỐI LIVE PASS TOÀN DIỆN).

---

## 1. Tổng hợp kết quả thực thi kiểm thử

| Bộ kiểm thử | Tổng số test | Đạt (PASS) | Thất bại (FAIL) | Thời gian chạy |
|---|:---:|:---:|:---:|:---:|
| **Node.js Test Suite** (`apps/api/tests/*.test.js`) | **129** | **129** | **0** | **~5.95s** |
| - `api.test.js` (Hệ thống, CORS, Error Handling, Staging) | 19 | 19 | 0 | 0.05s |
| - `auth.test.js` (Authentication, PBKDF2, RBAC, Rate Limit) | 31 | 31 | 0 | 0.90s |
| - `inventory.test.js` (Excel Parser, Row 2 Math, Deduplication, Limits, Soft-Delete) | 23 | 23 | 0 | 2.95s |
| - `comparison.test.js` (Comparison Engine, 3 Baselines, History, Fix 01 Regressions) | 18 | 18 | 0 | 0.70s |
| - `round_06_dashboard_combobox.test.js` (Carryover P2 + Stock Scope Tests) | 14 | 14 | 0 | 0.30s |
| - `sync.test.js` (Fix 01 & Fix 02: Fail-Closed Webhook, Atomic Concurrency, Revision Conflict Injection, Partial Outcome, Pagination Limit, JWT Auth) | **24** | **24** | **0** | **~3.60s** |
| **Python Pytest Suite** (`tests/*.py`) | **70** | **70** | **0** | **~0.56s** |
| - `test_round_02.py` (Cơ sở kiến trúc & D1 schema, 9 menu tiếng Việt) | 14 | 14 | 0 | 0.12s |
| - `test_round_03.py` (Users, Sessions, RBAC) | 7 | 7 | 0 | 0.08s |
| - `test_round_04.py` (Excel 4 file thật, 15 cột, Dòng 2, SKU 0 đầu, D1) | 16 | 16 | 0 | 0.19s |
| - `test_round_05.py` (Ground Truth đối soát 3 cặp snapshot, ngữ nghĩa Fix 01) | 8 | 8 | 0 | 0.20s |
| - `test_round_06.py` (Combobox, Scope Isolation, RBAC, Trash, VN Labels) | 11 | 11 | 0 | 0.06s |
| - `test_round_07.py` (Fix 01 & Fix 02: Atomic Lock, Fail-Closed Webhook, Migration 0002, Service Account JWT, Pagination Limit, Partial Outcome) | **14** | **14** | **0** | **~0.05s** |
| **TỔNG CỘNG KIỂM THỬ TỰ ĐỘNG** | **199** | **199** | **0** | **~6.51s** |

---

## 2. Chi tiết các ca kiểm thử bổ sung của Fix 02 (Round 07)

### 2.1. Fail-Closed Scheduled Webhook (P1-01)
- **TEST:** Endpoint `POST /api/v1/sync/scheduled` trả về 401 `UNCONFIGURED_WEBHOOK_SECRET` nếu môi trường không cấu hình `SYNC_WEBHOOK_SECRET`.
- **TEST (Negative):** Chặn đứng request thiếu secret (401 `UNAUTHORIZED_CRON`), sai secret (401 `INVALID_WEBHOOK_SECRET`), hoặc cố tình sử dụng `BOOTSTRAP_TOKEN` (401 `INVALID_WEBHOOK_SECRET`).
- **TEST (Negative):** Chặn đứng request có Origin từ bên ngoài không tin cậy (403 `FORBIDDEN_ORIGIN`).
- **TEST (Positive):** Request mang header `X-Webhook-Secret` hoặc Bearer token trùng khớp với `SYNC_WEBHOOK_SECRET` thực thi đồng bộ thành công (200 OK, `triggered_by: "SCHEDULED"`).

### 2.2. Atomic Concurrency Lease Lock & Phục hồi Stale Lease (P1-02)
- **TEST (Concurrency thực sự):** Hai request kích hoạt đồng bộ đồng thời (`Promise.all`) qua `testDb` với bảng khóa `sync_locks`:
  - Request 1: Giành được khóa thành công, thực thi nhập dữ liệu (200 OK).
  - Request 2: Bị chặn ngay lập tức tại tầng DB (409 Conflict, `SYNC_ALREADY_RUNNING`).
- **TEST (Stale Lease Recovery):** Khi đợt chạy trước gặp sự cố làm treo lock quá hạn (sau 600s), request sau tự động thu hồi khóa (conditional UPDATE) và tiếp tục thực thi an toàn.
- **TEST (Worker Crash Midway):** Khi Worker gặp ngoại lệ bất ngờ giữa chừng, khối `finally` luôn đảm bảo gọi `releaseSyncLock`, giải phóng khóa cho các lượt chạy tiếp theo.

### 2.3. Revision Conflict Mock Driver Injection (P2-03)
- **TEST:** Hỗ trợ Dependency Injection cho phép truyền mock driver vào `triggerSync()`.
- **TEST:** Nạp snapshot ban đầu, sau đó tiêm mock driver với file có cùng Drive ID nhưng mang `version = "REVISION_v2_MODIFIED_CONTENT"`.
- **TEST:** Xác minh kết quả phát hiện chính xác `files_conflict = 1`, `files_imported = 0`, `outcome = 'CONFLICT'`, chi tiết có lý do `xung đột phiên bản`. Snapshot lịch sử được bảo toàn tuyệt đối, không bị ghi đè.

### 2.4. Trạng thái Partial Outcome Nhất quán (P2-01)
- **TEST:** Tiêm driver mô phỏng trả về 1 file Excel hợp lệ và 1 file rác/hỏng.
- **TEST:** Kết quả trả về `outcome = 'PARTIAL'`, `status = 'FAILED'`, `files_failed = 1`.
- **TEST:** Cơ sở dữ liệu bảng `sync_runs` lưu trữ trường `outcome = 'PARTIAL'` và `error_message` ghi nhận rõ nguyên nhân lỗi để phục vụ retry.

### 2.5. Giới hạn An toàn Phân trang Google Drive API (P2-02)
- **TEST:** Giả lập Google Drive API trả về `nextPageToken` liên tục qua 20 trang.
- **TEST:** `LiveGoogleDriveDriver.listFiles()` ném ngoại lệ rõ ràng khi vượt ngưỡng 20 trang / 2.000 file (`Vượt quá giới hạn phân trang an toàn...`), không âm thầm cắt bớt dữ liệu coi là đầy đủ.

### 2.6. Xác thực Google Service Account bằng Web Crypto Native (P1-03)
- **TEST:** Mã hóa và ký JWT chuẩn RS256 PKCS#8 bằng `crypto.subtle` native, tự động lấy OAuth2 token ngắn hạn từ Google mà không phụ thuộc thư viện bên ngoài.
- **TEST:** Khi thiếu credentials, hệ thống duy trì trạng thái minh bạch `BLOCKED_FOR_LIVE`, không giả mạo kết nối LIVE.

---

## 3. Chính sách Migration Cơ sở Dữ liệu

- **File Migration:** `database/migrations/0002_sync_concurrency_lock.sql`
- **Môi trường đã áp dụng:** Đã nạp và kiểm thử thành công trên database local/test (Miniflare SQLite).
- **Môi trường Cloudflare D1 Production:** **HOÀN TOÀN CHƯA THỰC THI**. Chờ Quản trị viên/Người dùng xem xét và phê duyệt theo quy trình nghiêm ngặt.

---

## 4. Quyết định Gate & Bàn giao

- **Kết luận:** **PARTIAL – HOLD (HOÀN TẤT FIX 02, DỪNG CHỜ NGHIỆM THU).**
- **Trạng thái LIVE:** **BLOCKED_FOR_LIVE** (Chờ Người dùng cấp quyền Service Account trong môi trường triển khai thực tế).
- **Gói bàn giao:** 1 file ZIP `Round_07_Google_Drive_Sync.zip` kèm file `Round_07_Google_Drive_Sync.zip.sha256` đặt bên ngoài ZIP.
- **Quy tắc chuyển round:** **DỪNG TẠI ROUND 07 FIX 02. TUYỆT ĐỐI KHÔNG TỰ Ý CHUYỂN SANG ROUND 08.**
