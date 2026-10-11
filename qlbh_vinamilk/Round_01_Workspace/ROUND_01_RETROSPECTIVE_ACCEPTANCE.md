# HỒ SƠ NGHIỆM THU HỒI TỐ ROUND 01
## RETROSPECTIVE ACCEPTANCE – NGHIỆM THU KẾ THỪA TỪ ROUND 04

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Phạm vi:** Round 01/10 – Phân tích Excel & Data Contract  
**Hình thức:** Retrospective Acceptance (Nghiệm thu kế thừa kết quả thực tế từ Round 04)  
**Ngày phê duyệt:** 11/10/2026 (Phê duyệt chính thức bởi Người dùng)  
**Trạng thái chính thức:** **PASS (INHERITED FROM ROUND 04)**  

---

### 1. Bối cảnh & Căn cứ Nghiệm thu Kế thừa

- **Lịch sử:** Tại thời điểm bắt đầu Round 02, dự án đã chuyển tiếp khi Round 01 chưa có biên bản nghiệm thu độc lập chính thức. Người dùng đã thống nhất hoãn để tập trung phát triển hệ thống và kiểm chứng bằng thực tế.
- **Căn cứ kế thừa:** Toàn bộ đặc tả Hợp đồng dữ liệu (Data Contract) 15 cột, quy tắc đối soát Dòng 2 tổng hợp, bảo toàn mã SKU có số 0 ở đầu, và mô hình định danh Snapshot từ tên file đã được mã hóa đầy đủ trong mã nguồn TypeScript / D1 và được kiểm chứng tự động **100% PASS trên 4 file Excel thật** tại Round 04.
- **Phân biệt bằng chứng:** Bằng chứng nghiệm thu kế thừa này dựa trên 110/110 automated tests thực tế tại Round 04, phân biệt rõ ràng với biên bản QC cũ của Round 01. Không tạo kết quả kiểm thử giả mạo hay thay đổi mã nguồn đã nghiệm thu.

---

### 2. Bảng Đối chiếu Hợp đồng Dữ liệu (Traceability Matrix)

| STT | Yêu cầu Data Contract Round 01 | File Source Triển khai Hiện thực | Test Case Tự động Xác minh (100% PASS) | Trạng thái |
|:---:|---|---|---|:---:|
| **1** | Hợp đồng 15 cột chuẩn hóa & Cấu trúc sheet `Kiem-ke` | `packages/shared/src/index.ts`<br>`apps/api/src/services/excelParser.ts` | `apps/api/tests/inventory.test.js` (PARSER tests)<br>`tests/test_round_04.py` (`test_parse_4_real_files`) | **PASS** |
| **2** | Bảo toàn số 0 ở đầu mã SKU dạng chuỗi văn bản (vd: `02AA15`, `02AO18`) | `apps/api/src/services/excelParser.ts`<br>`database/migrations/0001_initial_schema.sql` | `apps/api/tests/inventory.test.js` (Preserve SKU)<br>`tests/test_round_04.py` (`test_preserve_leading_zero_sku`) | **PASS** |
| **3** | Đối soát toán học Dòng 2 tổng hợp ($E_2, H_2$) với Dòng 3..N | `apps/api/src/services/excelParser.ts` | `apps/api/tests/inventory.test.js` (Summary Math)<br>`tests/test_round_04.py` (`test_row_2_summary_math_diff`) | **PASS** |
| **4** | Mô hình định danh Snapshot (`full_code`, `ticket_number`, `store_code`, `inventory_date`) | `packages/shared/src/index.ts`<br>`apps/api/src/services/inventoryService.ts` | `apps/api/tests/inventory.test.js` (Filename parse)<br>`tests/test_round_04.py` (`test_snapshot_filename_parsing`) | **PASS** |
| **5** | Đa snapshot cùng ngày không bị ghi đè hay cộng dồn (`339000` & `339513`) | `apps/api/src/services/inventoryService.ts`<br>`database/migrations/0001_initial_schema.sql` | `apps/api/tests/inventory.test.js` (Fix 02 same buffer)<br>`tests/test_round_04.py` (`test_same_day_distinct_snapshots`) | **PASS** |
| **6** | Phân biệt SL Tồn kho sổ sách vs Cột 12 Chênh lệch kiểm kê nội bộ | `database/migrations/0001_initial_schema.sql`<br>`apps/api/src/services/excelParser.ts` | `tests/test_round_04.py` (`test_distinguish_stock_quantity_vs_internal_discrepancy`) | **PASS** |
| **7** | Ma trận Idempotency & Xử lý trùng lặp / xung đột / xóa mềm | `apps/api/src/services/inventoryService.ts` | `apps/api/tests/inventory.test.js` (ALREADY_IMPORTED, CONFLICT, SNAPSHOT_SOFT_DELETED) | **PASS** |

---

### 3. Bảng Tổng hợp Trạng thái Dự án Toàn diện

* **Round 01:** **PASS (Inherited from Round 04)**
* **Round 02:** **PASS**
* **Round 03:** **PASS (MVP)**
* **Round 04:** **PASS (MVP)**
* **Round 05:** **READY TO START (Stock Comparison Engine)**
