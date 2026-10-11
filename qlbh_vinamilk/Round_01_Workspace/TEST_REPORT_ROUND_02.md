# BÁO CÁO KIỂM THỬ CHẤT LƯỢNG ROUND 02 (TEST REPORT - FIX 02)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 02/10 – Project Foundation, Database & API (Fix 02: Security & Deployment Contract)  
**Vai trò thực hiện:** QA Tester & Security Reviewer  
**Thời điểm thực thi:** 11/10/2026 17:25:00 +07:00  
**Hệ điều hành / Runtime:** Darwin (macOS arm64) / Node.js v20.18.0 / Python 3.11.0  
**Kết quả tổng thể:** **33/33 TEST CASES ĐẠT (100% PASS)**  

---

## 1. BẢNG TỔNG HỢP KIỂM THỬ THEO PHÁT HIỆN REVIEW ĐỘC LẬP (REVISION 2)

| Hạng mục phát hiện | Giải pháp thực tế | Test Case xác minh | Kết quả |
|---|---|---|:---:|
| **P1: CORS Wildcard & Credentials** | Loại bỏ hoàn toàn wildcard `*.pages.dev`/`*.workers.dev`. Chỉ cho phép EXACT origins trong allowlist. Gắn `Vary: Origin`. Negative tests kiểm tra origin lạ bị từ chối 403 trên OPTIONS và không có ACAO trên GET. | `apps/api/tests/api.test.js` (6 tests: allowed dev, allowed configured, negative untrusted pages.dev, negative untrusted workers.dev, negative no origin, negative prod localhost) | **PASS** |
| **P1/P2: Error Handler Fail-Open** | Mặc định Production-Safe (Fail-closed). Nếu `ENVIRONMENT` không có hoặc không phải explicit `"development"`/`"test"`, `details` lỗi 500 bị che giấu hoàn toàn (`null`). `wrangler.toml` mặc định `ENVIRONMENT="production"`. | `apps/api/tests/api.test.js` (4 tests: missing env, production env, invalid env, dev/test env) | **PASS** |
| **P2: UI/Worker Deployment Contract** | Cung cấp hợp đồng kép: (1) `VITE_API_BASE_URL` động cho cross-origin + `credentials: "include"`, (2) Cloudflare Pages `_routes.json` và Pages Function proxy `/api/*` cho same-origin routing. | `apps/web/public/_routes.json`<br>`apps/web/functions/api/[[catchall]].ts`<br>`test_14_cloudflare_pages_routes_contract` | **PASS** |
| **P2: Số liệu Tiền VND Schema** | Cột `total_amount_vnd`, `unit_price`, `total_amount` được chuẩn hóa thành `INTEGER` trong SQLite D1, tránh hoàn toàn sai số dấu phẩy động nhị phân. Các cột số lượng giữ `REAL`. | `0001_initial_schema.sql`<br>`test_13_vnd_currency_integer_precision` | **PASS** |
| **P3: Định dạng số tiếng Việt (Locale vi-VN)** | Toàn bộ số lượng và số tiền trên Dashboard mockup được chuyển sang định dạng phân cách hàng nghìn bằng dấu chấm (`.`) theo chuẩn tiếng Việt (`16.972`, `273.775.891 đ`, `-1.935.846 đ`). | `apps/web/src/pages/DashboardPage.tsx` | **PASS** |
| **P3: Tách script typecheck độc lập** | Thêm `"typecheck": "tsc --noEmit"` cho web và root `package.json`, tách biệt việc typecheck kiểm tra kiểu với việc đóng gói build Vite. | `package.json`, `apps/web/package.json` | **PASS** |
| **D1 Connection Status** | Trả về trung thực: `not_configured`, `connected`, `unavailable`. | `apps/api/tests/api.test.js` | **PASS** |
| **Snapshots Stubs 501** | `/api/snapshots` và `/api/v1/snapshots` trả 501 `NOT_IMPLEMENTED`. | `apps/api/tests/api.test.js` | **PASS** |
| **Bảo toàn số 0 đầu SKU** | Mã SKU chuỗi `TEXT` giữ nguyên `'02AA15'`. | `test_06_product_code_string_with_leading_zeros` | **PASS** |
| **Xóa mềm (Soft Delete)** | `is_deleted = 1` được loại khỏi active query. | `test_07_soft_delete_support` | **PASS** |
| **Quét chống rò rỉ secrets** | Quét toàn bộ codebase: 0 secrets, 0 private keys. | `test_08_no_secrets_leaked_in_codebase` | **PASS** |

---

## 2. NHẬT KÝ THỰC THI THỰC TẾ (REAL EXECUTION LOGS)

### Nhật ký 1: Node.js API & Security Regression Suite (19/19 PASS)
```
$ node --test apps/api/tests/api.test.js

✔ GET /api/health returns 200 and status ok (22.567416ms)
✔ GET /api/v1/system/info without DB returns not_configured honestly (0.346625ms)
✔ GET /api/v1/system/info with working DB returns connected (0.300542ms)
✔ GET /api/v1/system/info with failing DB returns unavailable (0.315292ms)
✔ GET /api/snapshots returns 501 NOT_IMPLEMENTED (not 404) (0.33775ms)
✔ GET /api/v1/snapshots returns 501 NOT_IMPLEMENTED (0.225333ms)
✔ X-Request-ID sanitization: replaces invalid/oversized client ID (0.2185ms)
✔ GET /api/nonexistent returns 404 with structured error (0.327125ms)
✔ OPTIONS /api/health with allowed dev origin returns 204, ACAO and Vary: Origin (0.232833ms)
✔ OPTIONS /api/health with configured ALLOWED_ORIGINS accepts exact match (0.221959ms)
✔ CORS NEGATIVE TEST: OPTIONS with untrusted *.pages.dev is REJECTED (403, NO ACAO) (0.123458ms)
✔ CORS NEGATIVE TEST: OPTIONS with untrusted *.workers.dev is REJECTED (403, NO ACAO) (0.125417ms)
✔ CORS NEGATIVE TEST: GET request with untrusted origin does NOT receive ACAO or credentials (0.185ms)
✔ CORS NEGATIVE TEST: Request without Origin header does NOT receive ACAO or credentials (0.157542ms)
✔ CORS NEGATIVE TEST: Localhost is rejected in production environment (0.06575ms)
✔ ERROR HANDLER: Missing ENVIRONMENT hides internal 500 error details (fail-closed default) (0.159459ms)
✔ ERROR HANDLER: Production ENVIRONMENT hides internal 500 error details (0.245208ms)
✔ ERROR HANDLER: Unknown/invalid ENVIRONMENT hides internal 500 error details (0.248459ms)
✔ ERROR HANDLER: Explicit development/test ENVIRONMENT reveals details for debugging (0.229041ms)
ℹ tests 19
ℹ suites 0
ℹ pass 19
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 89.853083
```

### Nhật ký 2: Python Pytest D1 Schema & Architecture Regression Suite (14/14 PASS)
```
$ python3 -m pytest -q tests/test_round_02.py
..............                                                           [100%]
14 passed in 0.09s
```

Chi tiết 14 test cases:
1. `test_01_migration_file_exists`: File migration tồn tại và dung lượng hợp lệ.
2. `test_02_database_has_all_10_tables`: 10 bảng D1 theo kiến trúc.
3. `test_03_database_has_required_indexes`: 10 index tối ưu hóa hiệu năng.
4. `test_04_inventory_files_schema_enhancements`: Các trường metadata nguồn và `status='STAGING'`.
5. `test_05_support_multiple_snapshots_on_same_date`: Hỗ trợ snapshot cùng ngày (339000 & 339513).
6. `test_06_product_code_string_with_leading_zeros`: Mã SKU chuỗi không mất số 0 đầu.
7. `test_07_soft_delete_support`: Hỗ trợ xóa mềm an toàn.
8. `test_08_no_secrets_leaked_in_codebase`: Không rò rỉ bí mật trong toàn bộ repo.
9. `test_09_dashboard_has_transparent_sample_data_warning`: Cảnh báo dữ liệu mẫu minh bạch.
10. `test_10_hygiene_files_exist`: `.gitignore` và `.env.example` tồn tại.
11. `test_11_frontend_files_and_vietnamese_localization`: 9 menu tiếng Việt chuẩn.
12. `test_12_cors_exact_origin_and_no_wildcards`: CORS không dùng regex wildcard, có `Vary: Origin`.
13. `test_13_vnd_currency_integer_precision`: `total_amount_vnd`, `unit_price`, `total_amount` là `INTEGER`.
14. `test_14_cloudflare_pages_routes_contract`: Hợp đồng định tuyến Pages `_routes.json` và proxy function.

### Nhật ký 3: Build Monorepo (Shared + API + Web)
```
$ npm run build

> inventory-management@1.0.0 build
> npm run build:shared && npm run build:api && npm run build:web

> @inventory/shared@1.0.0 build
> tsc

> @inventory/api@1.0.0 build
> tsc

> @inventory/web@1.0.0 build
> tsc && vite build

vite v5.4.21 building for production...
✓ 1623 modules transformed.
dist/index.html                   0.79 kB │ gzip:  0.48 kB
dist/assets/index-CCTIr78D.css   16.60 kB │ gzip:  3.82 kB
dist/assets/index-Dq2HQq6B.js   199.50 kB │ gzip: 61.93 kB
✓ built in 843ms
```

### Nhật ký 4: Typecheck Monorepo
```
$ npm run typecheck

> inventory-management@1.0.0 typecheck
> npm --workspace=@inventory/shared run build && npm --workspace=@inventory/api run typecheck && npm --workspace=@inventory/web run typecheck

> @inventory/shared@1.0.0 build
> tsc

> @inventory/api@1.0.0 typecheck
> tsc --noEmit

> @inventory/web@1.0.0 typecheck
> tsc --noEmit
```

---

## 3. KẾT LUẬN NGHIỆM THU
Tất cả 100% phát hiện từ Review Độc lập Revision 2 (P1 CORS, P1 Error Handler, P2 Deployment Contract, P2 VND Currency INTEGER, P3 Locale vi-VN, P3 Typecheck) đã được xử lý triệt để, có kiểm chứng hồi quy tự động 33/33 PASS.
