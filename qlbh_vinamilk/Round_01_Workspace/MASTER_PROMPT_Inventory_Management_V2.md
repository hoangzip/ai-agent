# MASTER IMPLEMENTATION PROMPT — QUẢN LÝ & ĐỐI SOÁT TỒN KHO

**Phiên bản:** 1.1 — Bổ sung 2 file ngày 09/10/2026  
**Mục tiêu:** Giao cho AI coding agent xây dựng ứng dụng web thật, không phải UI demo.  
**Ngôn ngữ người dùng:** Tiếng Việt 100%.  
**Quy trình:** 10 Round — mỗi Round là một phase — mỗi Round đúng một ZIP + một tệp checksum SHA256 nằm ngoài ZIP.

## 0. NGUYÊN TẮC BẮT BUỘC

1. Ưu tiên **độ chính xác dữ liệu → bảo mật → độ tin cậy → hiệu suất → trải nghiệm → hình thức**.
2. Bắt đầu bằng kiểm tra thư mục project thật, file nguồn thật, môi trường và quyền truy cập. Không giả lập kết quả test/deploy/sync.
3. Không tự ý commit, push, tạo PR, đổi branch hoặc yêu cầu Git log/diff làm bằng chứng. Thẩm định bằng **thư mục làm việc hiện tại**, logs, tests, release ZIP và sidecar SHA256. Có thể chuẩn bị dự án sẵn sàng để người dùng chủ động kết nối GitHub/Cloudflare sau.
4. Không tự chạy migration hoặc thay đổi/xóa dữ liệu **production** khi chưa được người dùng duyệt. Các thao tác thử nghiệm chỉ ở local/dev test database. Nếu bàn giao SQL có INSERT/UPDATE/DELETE, mặc định comment toàn bộ phần làm biến đổi dữ liệu và giải thích cách kích hoạt có kiểm soát.
5. Không hardcode tài khoản, password, token, private key, Drive credentials trong source code/public repository.
6. Không coi không chạy được do thiếu credential là PASS; ghi **BLOCKED** đúng phần chưa xác minh và tiếp tục các phần độc lập.
7. Không tự tạo mock output thay cho real test. Fixture dùng cho automated test phải đánh dấu rõ là synthetic.
8. Giới hạn free tier phải được đánh giá và đo thực tế; không tự kích hoạt dịch vụ trả phí.
9. Không biến 10 Round thành 10 lần lặp cùng một phase. Chỉ chuyển phase khi đáp ứng gate, hoặc có phê duyệt ngoại lệ.
10. Mọi màn hình tiếng Việt, ngày giờ hiển thị `dd/MM/yyyy HH:mm:ss`, timezone `Asia/Ho_Chi_Minh`; thời điểm lưu database ưu tiên UTC.

## 1. INPUT & DỮ LIỆU NGHIỆM THU

### 1.1. Tệp đính kèm
- `KiemKe_KK.CH41551.26.339000_20261009.xlsx`
- `KiemKe_KK.CH41551.26.339513_20261009.xlsx`
- `KiemKe_KK.CH41551.26.339931_20261010.xlsx`
- `KiemKe_KK.CH41551.26.340231_20261011.xlsx`
- Hai hình UI: Dashboard SaaS và danh sách chứng từ kiểm kê.
- Nếu project hiện có thư mục `Data Source/Kiem Ke`, chỉ đọc và kiểm tra; không được xóa/ghi đè các file gốc.

### 1.2. Cấu trúc Excel đã kiểm chứng
- Worksheet: `Kiem-ke`.
- Vùng nội dung: `A1:O434` cho hai file 09/10; `A1:O436` cho hai file 10/10 và 11/10.
- Dòng 1 là header, dòng 2 là **dòng tổng hợp**. Chi tiết bắt đầu từ dòng 3: có **432 sản phẩm** ở mỗi file 09/10; **434 sản phẩm** ở mỗi file 10–11/10. Không hardcode số dòng trong parser.
- 15 cột đúng thứ tự:
  1. `STT`
  2. `NGÀNH HÀNG`
  3. `MÃ SẢN PHẨM`
  4. `TÊN SẢN PHẨM`
  5. `SL TỒN KHO`
  6. `LOẠI KHO`
  7. `GIÁ (SAU VAT)`
  8. `THÀNH TIỀN`
  9. `SL PACKAGE KIỂM KÊ`
  10. `SL LẺ KIỂM KÊ`
  11. `TỔNG SL KIỂM KÊ`
  12. `CHÊNH LỆCH`
  13. `ĐVT PACKAGE`
  14. `QUY ĐỔI`
  15. `ĐVT LẺ`
- `SL TỒN KHO` dùng để so sánh snapshot. **Không** dùng `CHÊNH LỆCH` (trong Excel) làm chênh lệch giữa hai lần xuất.
- Mã sản phẩm, mã cửa hàng, mã chứng từ phải là **text**, bảo toàn ký tự `0` đầu chuỗi. Tiền VND sử dụng số chính xác; phép tính không được phát sinh lỗi floating-point.

### 1.3. Ground truth — BẮT BUỘC tự tái tạo từ Excel

| Snapshot | Ngày | Số SKU | Kho hàng bán | Kho vật phẩm KM | Tổng tồn | Tổng giá trị (VND) |
|---|---|---:|---:|---:|---:|---:|
| 339000 | 09/10/2026 | 432 | 390 | 42 | 16961 | 270739477 |
| 339513 | 09/10/2026 | 432 | 390 | 42 | 17090 | 272476003 |
| 339931 | 10/10/2026 | 434 | 391 | 43 | 17147 | 275711737 |
| 340231 | 11/10/2026 | 434 | 391 | 43 | 16972 | 273775891 |

**Acceptance comparison:**

| So sánh | Matched | Tăng | Giảm | New | Missing | Δ số lượng | Δ giá trị (VND) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 339000 → 339513 (cùng ngày) | 432 | 19 | 58 | 0 | 0 | +129 | +1736526 |
| 339513 → 339931 | 432 | 18 | 42 | 2 | 0 | +57 | +3235734 |
| 339931 → 340231 | 434 | 0 | 28 | 0 | 0 | -175 | -1935846 |

Hai SKU mới khi so 339513 → 339931: `02AO18` (`Kho hàng bán`) và `9NH277` (`Kho hàng vật phẩm KM`). Năm mã kiểm tra cặp 339931 → 340231: `07KD12` 113→89; `04FT32` 88→67; `07NH12` 56→37; `04EC33` 124→108; `07TR33` 94→82.

Mọi số liệu trong bảng là expected results cho automated tests, **không** hardcode vào parser/compare engine. Khi có khác biệt, báo lỗi bằng dữ liệu và log rõ ràng.

## 2. NGUỒN ĐỒNG BỘ GOOGLE DRIVE (ĐÃ CHỐT)

- Provider: **Google Drive** (không phải Microsoft OneDrive).
- Folder ID: `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`.
- URL: `https://drive.google.com/drive/folders/1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk?usp=sharing`.
- Tên folder: `Kiem ke hang hoa`.
- Bốn file Excel mẫu đã được đưa vào gói Kickoff V2; không giả định thư mục Google Drive luôn có đủ bốn file (hai file 09/10 hiện được cung cấp riêng).
- File gốc nằm trên Google Drive; backend **chỉ lưu dữ liệu đã chuẩn hóa + metadata/chỉ mục/checksum**, không lưu bản sao Excel gốc trên D1.
- Cho phép đồng bộ file Excel `.xlsx` và Google Sheets, có thể dùng các helper tạm trong Google Drive và phải dọn bản tạm sau xử lý.
- Có upload thủ công trên web **và** đồng bộ tự động, khử trùng dữ liệu chéo giữa hai nguồn.
- Đồng bộ theo lịch gợi ý 60 phút, có nút **Yêu cầu đồng bộ ngay** với trạng thái trung thực (đã yêu cầu / đang chờ / đang chạy / hoàn tất / lỗi).
- Phương án ưu tiên: Google Apps Script chạy dưới tài khoản được cấp quyền folder, chuẩn hóa và gửi batch có **HMAC + timestamp + anti-replay** qua API backend. Nếu hạn mức hoặc quyền kết nối không phù hợp, đánh giá và đề xuất phương án thay thế trong giới hạn miễn phí.
- Không yêu cầu folder phải public; khi connector vận hành ổn định, khuyến nghị đổi folder sang **Restricted** và cấp quyền riêng cho tài khoản đồng bộ.
- Không suy ra ngày/giờ kiểm kê từ Google Drive modified time.
- Không tự phục hồi snapshot đã bị Admin xóa mềm khi Drive sync gặp lại file.
- Sync có log lần chạy, retry/backoff, lock chống chạy đồng thời, dedup theo source ID/revision/checksum và trạng thái conflict rõ ràng.
- Secrets chỉ lưu trong cấu hình bảo mật của môi trường tương ứng, không nằm trong source hoặc giao diện client.

## 3. BÀI TOÁN VÀ QUY TẮC SNAPSHOT

1. Một ngày có thể có nhiều file khác mã, có thể là sáng/chiều/tối hoặc các lần xuất khác nhau.
2. Có thể cùng cửa hàng/phạm vi hoặc các cửa hàng/phạm vi khác nhau; **không cộng các snapshot** chỉ vì cùng ngày.
3. Mỗi snapshot có internal ID, mã kiểm kê đầy đủ (ví dụ `KK.CH41551.26.340231`), số kiểm kê (`340231`), cửa hàng, loại kho/phạm vi, ngày, giờ, ca, metadata file, nguồn, checksum, trạng thái.
4. Ca kiểm kê: `Sáng`, `Chiều`, `Tối`, `Khác`, `Chưa xác định`; có thể sửa metadata với audit. Không tự gán ca chỉ bằng timestamp khi chưa xác nhận.
5. Nếu cùng mã kiểm kê + checksum tương đương → cảnh báo/skip bản trùng; cùng mã + nội dung khác → **CONFLICT**, không ghi đè âm thầm.
6. Nếu khác nguồn nhưng cùng snapshot → chống ghi trùng.
7. Sản phẩm trong snapshot lưu đầy đủ thông tin theo thời điểm xuất, không lấy catalog hiện tại ghi đè dữ liệu lịch sử.
8. Khóa so sánh tối thiểu là `mã sản phẩm + loại kho` trong phạm vi được chọn. Nếu cùng khóa trùng nhiều dòng, phải báo/đòi quy tắc nghiệp vụ; không tự gộp tùy tiện.
9. SKU không có trong file B được phân loại **Không xuất hiện** chứ không tự suy luận tồn B = 0.
10. So sánh khác phạm vi có cảnh báo không thể diễn giải như biến động xuất-nhập của cùng cửa hàng.

## 4. CHỨC NĂNG BẮT BUỘC

### 4.1. Đăng nhập và quản lý người dùng
- Bắt buộc đăng nhập để **xem, upload, đồng bộ, so sánh hoặc tải dữ liệu**. Không public API dữ liệu.
- **Chỉ Admin tạo tài khoản**, không có trang đăng ký công khai.
- Có login, logout, đổi mật khẩu, profile, khóa/mở khóa user, reset mật khẩu tạm, phân quyền API, logout/revoke sessions khi khóa.
- Bootstrap thông tin lần đầu: **username `admin`, mật khẩu tạm `123456`**. Mật khẩu này chỉ dùng cho môi trường setup local/private và phải **bắt buộc thay ngay lần đăng nhập đầu tiên**. Không được cho production hoạt động với mật khẩu mặc định; không hardcode password trong repo/fixture public; script setup chỉ lấy password qua secret/input bảo mật.
- Phân quyền: ADMIN xem/import/compare/export/sync, tạo-sửa-khóa user, sửa cấu hình sync, xóa mềm/khôi phục; USER xem/import/compare/export, tự đổi password; USER không có quyền xóa/khôi phục/quản trị.
- Không cho khóa tài khoản Admin hoạt động cuối cùng.
- Mật khẩu hash bằng thuật toán chống brute-force phù hợp, có salt, không dùng hash nhanh SHA-256 đơn thuần. Đo khả năng triển khai trong Cloudflare Free (cần báo blocker nếu không đáp ứng yêu cầu bảo mật).
- Cookie session HttpOnly, Secure, SameSite phù hợp; bảo vệ CSRF, rate-limit login, chống enumeration, session expiration, revoke; API kiểm tra quyền thực sự phía server, không chỉ ẩn nút frontend.

### 4.2. Danh sách kiểm kê
- Trang tiếng Việt với tìm kiếm mã kiểm kê, ngày, ca, cửa hàng, loại kho, trạng thái, nguồn.
- Các cột: Ngày/giờ, Mã kiểm kê, Cửa hàng/phạm vi, Ca, SKU, Tổng tồn, Tổng giá trị, Nguồn, Người import, Trạng thái, Thao tác.
- Hỗ trợ xem snapshot, chọn để so sánh, chỉnh sửa metadata, xóa mềm (Admin).

### 4.3. Import Excel
- Kéo-thả/chọn nhiều `.xlsx` cùng lúc; đọc file và preview, tự trích mã từ filename, cho sửa ngày/giờ/ca/cửa hàng/phạm vi.
- Validate worksheet, header, summary row, product code, numeric values, mã trùng, quy đổi, totals, checksum, content-version conflict.
- Staging/batch: dữ liệu đang import chưa hiện cho người dùng cuối; commit trạng thái `Completed` chỉ khi tất cả bản ghi hợp lệ. Có cleanup/retry.
- Nếu lỗi, báo theo dòng/cột, không silently truncate/skip.

### 4.4. So sánh hai snapshot bất kỳ
- Bộ chọn snapshot A, snapshot B, hiển thị ngày-giờ-ca-mã-cửa hàng/phạm vi.
- Cùng ngày hoặc khác ngày, cùng ca hoặc khác ca, cùng/khác cửa hàng.
- Công thức: `chênh số lượng = tồn B - tồn A`, `chênh giá trị = thành tiền B - thành tiền A`, `% = (B-A)/A*100` khi A != 0; A=0 hiển thị ký hiệu phù hợp.
- Phân loại: Tăng/Giảm/Không đổi/Mới xuất hiện/Không xuất hiện; tách logic thay đổi số lượng và giá trị nếu giá bán khác nhau.
- KPI và bảng sản phẩm, tìm kiếm, lọc, sort tăng/giảm lớn, phân trang, tải Excel/CSV.

### 4.5. Tổng quan
- SKU, số lượng, giá trị của snapshot/phạm vi **được chọn rõ ràng**, biến động gần nhất, top SKU biến động, xu hướng tồn, danh sách file mới.
- Không cộng các lần kiểm kê lịch sử thành tổng tồn hiện tại.

### 4.6. Lịch sử SKU
- Tra cứu mã, cửa hàng/phạm vi, biểu đồ theo nhiều snapshot trong một ngày, giá và số lượng từng thời điểm.

### 4.7. Xóa mềm và khôi phục
- Admin được phép xóa mềm sau modal xác nhận mã/Ngày/SKU; lưu `deleted_at`, `deleted_by`, lý do nếu có.
- Ẩn snapshot đã xóa khỏi Dashboard, danh sách, so sánh active. Có màn hình Thùng rác và Restore cho Admin.
- USER gọi API xóa/khôi phục → `403`, và phải có test.
- Không triển khai hard delete trong phiên bản đầu.

### 4.8. Xuất dữ liệu
- XLSX, CSV; giữ mã SKU kiểu text và số lượng/tiền kiểu số; export đúng bộ lọc, tránh formula injection từ dữ liệu text không tin cậy.

## 5. GIAO DIỆN 100% TIẾNG VIỆT

- Tham khảo hình SaaS Dashboard đã gửi: nền trắng/xám nhạt, sidebar, KPI cards, bảng dữ liệu gọn; primary tham khảo `#7046D4`, font `Inter`.
- React + TypeScript + Vite + Tailwind + shadcn/ui, TanStack Table/Query, Recharts.
- Sidebar: `Tổng quan`, `Danh sách kiểm kê`, `Nhập file Excel`, `So sánh tồn kho`, `Lịch sử sản phẩm`, `Đồng bộ Google Drive`, `Quản lý người dùng` (Admin), `Thùng rác` (Admin), `Cài đặt`.
- Mọi text nhìn thấy bởi người dùng đều là tiếng Việt, kể cả trạng thái và validation. Source code/API có thể dùng tiếng Anh.
- Desktop-first, mobile không vỡ bố cục; loading, empty state, toast, phân trang, search debounce.

## 6. KIẾN TRÚC ƯU TIÊN VÀ TÍNH KHẢ THI

- Frontend: React / TypeScript / Vite.
- Backend: Cloudflare Workers hoặc Pages Functions, TypeScript, Zod.
- Database: Cloudflare D1 (SQLite), migration có version.
- Đồng bộ: Google Apps Script / Drive API / API batch ingestion.
- GitHub + Cloudflare free tier khi người dùng kết nối và cho phép deploy.
- Kiểm tra CPU/requests của Cloudflare Free, D1 rows-read/write/storage và quotas Google Apps Script. Tải Excel và parse/convert lớn không mặc nhiên đưa vào Worker request; ưu tiên parse client-side cho upload thủ công hoặc Apps Script cho đồng bộ.
- Tách auth/sessions và API ingest theo nguyên tắc least privilege; không khai lộ secret ở frontend.
- Server-side pagination, indexed query, không N+1, comparison set-based hoặc Map hash join, không load toàn bộ lịch sử về client.
- Chạy test hiệu năng với dữ liệu giả lập riêng 100 và 1.000 snapshot; báo đo thật, không bịa số.

## 7. DATA MODEL TỐI THIỂU

Thiết kế migrations cho các nhóm:

- `users`, `sessions` (hoặc cấu trúc session tương đương an toàn)
- `stores`, `stock_scopes`
- `inventory_files` (thực chất mỗi record là metadata của snapshot)
- `inventory_items`
- `product_catalog` (nếu cần)
- `import_jobs`, `import_staging` hoặc cơ chế atomic-publish tương đương
- `sync_sources`, `sync_runs`, `sync_file_state`, `sync_commands`
- `audit_logs`

Các trường nghiệp vụ phải có: mã chứng từ, ngày/giờ/ca, store/scope, checksum, provenance, status, created/imported timestamps, SKU+stock type, số lượng, giá, thành tiền, cột kiểm kê khác, soft-delete, người thao tác.

Tạo uniqueness/index dựa trên cửa hàng + mã kiểm kê + version hợp lý. Không dùng tên sản phẩm để xác định uniqueness. Quản lý xung đột theo checksum và nguồn dữ liệu.

**CẢNH BÁO:** Các yêu cầu schema này **chỉ là đặc tả**; không tự ý chạy thay đổi database production. Migrations phải được review trước deployment. Không đưa câu lệnh thay đổi dữ liệu đang hoạt động vào tài liệu mà không comment/đánh dấu rõ.

## 8. MULTI-AGENT RACI

**Orchestrator / Project Lead:** sở hữu master plan, phân chia round, giao scope, tích hợp, manifest, đưa quyết định PASS/PARTIAL/BLOCKED/FAIL có bằng chứng, xuất report cuối Round.

**Data Engineer:** phân tích cấu trúc Excel, parser, data contract, định danh snapshot, dữ liệu chuẩn hóa, Google Drive Sync, checksum/idempotency.

**Backend Developer:** API, Cloudflare/D1 schema, migration, auth, RBAC, import state, comparison engine, audit.

**Frontend Developer:** toàn bộ UI tiếng Việt, component design system, dashboard, import, compare, lịch sử, user management.

**QC Reviewer:** rà soát độc lập nghiệp vụ, data model, security assumptions, code review, scope/requirements; không tự cho PASS chỉ dựa vào báo cáo Dev.

**QA Tester:** thiết kế và chạy unit/integration/E2E/security negative tests, regression, dataset acceptance, làm bằng chứng PASS/FAIL.

**Security & DevOps:** bảo vệ thông tin xác thực, secrets, kiểm tra authorization, quotas, xây deployment guide, chạy deployment chỉ khi người dùng cấp quyền.

Nếu framework coding agent không có multi-agent thực sự, thực hiện **role-based passes tách biệt**, có biên bản từng vai trò. Không tuyên bố nhiều agent độc lập đã chạy nếu không có bằng chứng.

Mỗi Round có **1 agent owner**, 1 QC reviewer, 1 QA verifier (có thể là cùng runtime nhưng vai trò/tệp review khác nhau); khóa ownership thư mục để tránh sửa file cùng lúc.

## 9. SKILLS BẮT BUỘC KIỂM TRA / ĐỀ XUẤT

Superpowers nếu môi trường đã cài: `writing-plans`, `executing-plans`, `systematic-debugging`, `test-driven-development`, `requesting-code-review`, `receiving-code-review`, `verification-before-completion`, `finishing-a-development-branch`.

Nêu rõ skill nào **available/used/unavailable** ở báo cáo; nếu không có, làm workflow tương đương nhưng không giả lập cài đặt. Skill `finishing-a-development-branch` nếu sử dụng phải áp dụng phần QA/release, **không thực hiện Git branch ops** trái quy tắc folder-only.

Đề xuất custom project skills với checklist và fixture:
- `inventory-excel-parser` — schema, header, tổng hợp, numeric, sku.
- `snapshot-identity-dedup` — store/scope/date/code/hash, conflicts.
- `inventory-compare` — matched/missing/new, quantity/value, changing price.
- `gdrive-sync` — polling, auth, batch, retry, idempotency.
- `cloudflare-d1` — schema, index, quotas, atomic-publish.
- `auth-rbac-security` — first login/change password, sessions, API 403.
- `inventory-acceptance-tests` — 4 file thật + edge cases.

## 10. 10 ROUNDS (MỖI ROUND = MỘT PHASE)

| Round | Nội dung | Owner | Gate bắt buộc |
|---|---|---|---|
| 01 | Phân tích Excel, data contract, baseline tests | Data Engineer | 4 file thật đọc đúng; đủ 15 cột; totals/deltas khớp |
| 02 | Project foundation, D1 schema, API skeleton, test harness | Backend Dev | Build, migration dev, smoke tests |
| 03 | Auth, Admin bootstrap an toàn, user management, RBAC | Backend + Security | Login/change password, 403, session revocation |
| 04 | Excel import/manual upload, batch, dedup, validation | Data Engineer | Import test, errors, idempotency |
| 05 | Snapshot comparison & product history | Backend Dev | Dataset acceptance + edge cases |
| 06 | UI 100% Việt, dashboard, CRUD hiển thị, compare | Frontend Dev | E2E UI, no production mock |
| 07 | Google Drive auto/manual sync | Data Engineer | Real connection nếu có quyền, logs, dedup |
| 08 | Soft-delete/restore/audit | Backend + Security | Admin-only, restore, deleted skip sync |
| 09 | QC+QA tích hợp, security, regression, performance | QA Tester | Test report và fixes verified |
| 10 | Config Cloudflare/GitHub, production/handover | DevOps | Live deploy nếu có quyền, URL thật và smoke test |

Thiếu credentials Round 07/10 → ghi BLOCKED phần live, không tạo thành công giả; có thể hoàn thiện code + mock/fixture tests và xin quyền bổ sung.

## 11. QUY TRÌNH BẮT BUỘC SAU MỖI ROUND

**Analyze → Plan → Safe Implement → Validate → Independent QC Review → Fix & Regression → Update Manifest → Generate One ZIP + External SHA → Report → Prepare Next Prompt**.

- Một Round duy nhất một ZIP từ **live folder** chứa code artifacts/tài liệu + `AGENT_RESPONSE.md`, `ROUND_REPORT.md`, `QC_REVIEW.md`, `TEST_RESULTS.md`, `ROUND_MANIFEST.json`, `NEXT_ROUND_PROMPT.md` nếu sẵn sàng.
- Không kèm credential/session/private key/user data nhạy cảm. File Excel mẫu không được mặc định đặt vào repository public hay release công khai; kiểm thử bằng bản private hoặc fixture đã được chấp thuận.
- SHA256 sidecar **ở ngoài ZIP**, kiểm tra lại checksum bằng công cụ độc lập.
- Không yêu cầu Git log/commit/PR/diff làm evidence.
- Trạng thái: `PASS` / `PARTIAL` / `BLOCKED` / `FAIL` phải phản ánh bằng chứng thực.
- Round chưa PASS không mặc định tiếp tục Round sau khi có blocker nghiêm trọng.

### MẪU BÁO CÁO TIẾNG VIỆT (ĐỌC ĐƯỢC TRONG 30 GIÂY)
```
Round XX – [Tên giai đoạn]
Trạng thái: PASS / PARTIAL / BLOCKED / FAIL
Hoàn thành: [tối đa 3 mục]
Kiểm thử: [X/Y PASS; nêu test thất bại]
QC: [PASS / NEED FIX + lỗi quan trọng]
Tồn đọng: [0 hoặc mô tả ngắn]
Package: [tên ZIP] | SHA256: [tên file sidecar]
Round tiếp theo: [mã + tên + điều kiện bắt đầu]
```

## 12. MANDATORY EDGE TESTS

1. Hai file cùng ngày khác mã/ca.
2. Hai file cùng ngày khác cửa hàng, kho hoặc scope.
3. Trùng tên file, cùng ID nhưng checksum khác.
4. Drive và manual upload cùng một chứng từ.
5. Missing/new SKU; SKU xuất hiện nhiều kho.
6. Số lượng bằng 0; phần trăm chia 0; thay đổi giá không đổi lượng.
7. Trùng mã trong cùng kho; file thiếu header; dòng trống; numeric lỗi; file trống.
8. Import lỗi giữa các batch; retry; concurrency.
9. Người không đăng nhập gọi API; USER gọi DELETE/RESTORE hoặc Admin API phải nhận 401/403 thích hợp.
10. Admin mặc định không được tồn tại trên production với mật khẩu `123456`; bắt buộc đổi pass lần đầu; khóa user phải revoke session.
11. Admin cuối cùng không bị khóa; audit chính xác.
12. File đã xóa không tự re-import khi Drive sync gặp lại.
13. Chống spreadsheet formula injection/XSS qua product names.
14. Thư mục Google Drive không truy cập được, quota, retry, token/signature invalid/replay.
15. Comparison performance và pagination khi nhiều snapshot.

## 13. DELIVERABLE CUỐI DỰ ÁN

- Source code và cấu trúc thư mục có thể chạy được.
- `README.md` tiếng Việt; hướng dẫn Admin/User.
- `DATA_CONTRACT.md`, schema/migrations an toàn, API docs.
- Hướng dẫn Google Drive Sync, cấu hình Google Apps Script trigger và secrets.
- Hướng dẫn Cloudflare D1 / Pages/Workers, deploy từ GitHub.
- Test fixtures + automation scripts + actual test reports.
- Security review + free-tier assessment + known limitations.
- Bản final ZIP + external SHA256, báo cáo nghiệm thu và production URL **chỉ nếu có bằng chứng deploy thật**.

## 14. BẮT ĐẦU THỰC THI

Bắt đầu bằng **ROUND 01**. Đọc prompt riêng `ROUND_01_PROMPT_Excel_Data_Contract.md`. Không bỏ qua Round 01 và không đi xây UI trước khi xác minh data contract.

Round 01 **không** được sửa database production, không tự commit/push, không thiết lập chia sẻ Drive rộng hơn. Nếu có đủ file, tiến hành kiểm tra, tái tạo baseline, viết hợp đồng dữ liệu và tests, gửi package Round 01 khi hoàn thành.
