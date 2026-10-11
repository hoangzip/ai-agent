# PROMPT KHỞI ĐỘNG ROUND 02 — FOUNDATION, D1 SCHEMA & API SKELETON

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round tiếp theo:** 02/10  
**Owner:** Backend Developer  
**Reviewer:** QC Reviewer  
**Verifier:** QA Tester  
**Coordinator:** Orchestrator  
**Ngôn ngữ:** Tiếng Việt 100%  

---

## 1. MỤC TIÊU ROUND 02

Xây dựng nền móng kiến trúc backend và cơ sở dữ liệu trên Cloudflare D1 (SQLite), định nghĩa schema và migrations tuân thủ trọn vẹn Hợp đồng dữ liệu (Data Contract) và mô hình Snapshot Identity đã chốt ở Round 01.

---

## 2. NỘI DUNG PROMPT GỬI CHO AGENT

```markdown
Bạn là Backend Developer (dưới sự điều phối của Orchestrator) của dự án Inventory Management.
Round 01 đã PASS với Data Contract 15 cột và Snapshot Identity đã được nghiệm thu.
Hãy bắt đầu thực hiện Round 02/10: Foundation, D1 Schema & API Skeleton.

Nhiệm vụ chính:
1. Thiết lập cấu trúc dự án fullstack chuẩn: React + TypeScript (Frontend) và Cloudflare Workers / Pages Functions (Backend) hoặc monorepo tương thích.
2. Xây dựng migration schema cho Cloudflare D1 (SQLite) đáp ứng đầy đủ:
   - `users`, `sessions` (an toàn, mật khẩu băm, không hardcode password production)
   - `stores`, `stock_scopes`
   - `inventory_snapshots` (metadata: full_code, store_code, ticket_number, date, shift, file_sha256, content_hash, is_deleted)
   - `inventory_items` (khóa tự nhiên product_code + warehouse, số lượng, giá sau VAT, thành tiền, cột kiểm kê, đơn vị quy đổi)
   - `audit_logs`, `import_staging`
   - Thiết lập chỉ mục (indexes) và ràng buộc UNIQUE hợp lý.
3. Tạo API skeleton cơ bản (TypeScript / Zod validation) cho:
   - Health check / Ping
   - Danh sách snapshots (có lọc theo ngày, store, phân trang server-side)
   - Chi tiết snapshot và items
   - Khung API so sánh 2 snapshot
4. Viết unit/integration tests cho migrations và API skeleton, chạy thử nghiệm trên môi trường local dev D1 test database.
5. QC rà soát độc lập và QA kiểm thử với logs thực tế.
6. Tuân thủ nguyên tắc an toàn: Không thực hiện Git ops, không chạy migrations trên production database, chỉ bàn giao các file SQL kèm comment kiểm soát.
7. Đóng gói kết quả Round 02 vào duy nhất 01 ZIP và tạo file checksum SHA256 ngoài ZIP.

Dừng lại sau khi báo cáo kết quả Round 02 để tôi review/chấp thuận trước khi chuyển Round 03.
```
