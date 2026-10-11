# BIÊN BẢN RÀ SOÁT CHẤT LƯỢNG ĐỘC LẬP (QC REVIEW)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 01/10  
**Vai trò thực hiện:** QC Reviewer (Độc lập)  
**Ngày thực hiện:** 11/10/2026  
**Đánh giá tổng thể:** **PASS (ĐẠT)**  

---

## 1. PHẠM VI RÀ SOÁT & TIÊU CHÍ ĐÁNH GIÁ

QC Reviewer đã tiến hành rà soát độc lập toàn bộ các hạng mục công việc và sản phẩm bàn giao do Data Engineer và QA Tester thực hiện trong Round 01 theo các tiêu chuẩn:
1. **Tính chân thực của dữ liệu (Data Authenticity):** Dữ liệu được đọc trực tiếp từ 4 file Excel thật, không chế tạo kết quả.
2. **Độ đầy đủ của Hợp đồng dữ liệu (Data Contract Completeness):** Đủ 15 cột, vị trí header, summary row, phân biệt rõ `SL TỒN KHO` vs `CHÊNH LỆCH`.
3. **Mô hình Snapshot Identity:** Giải quyết bài toán nhiều file/ngày, khác ca, khác cửa hàng, dedup nội dung và chống xung đột ghi đè âm thầm.
4. **Độ an toàn mã nguồn:** Không hardcode dữ liệu, không rò rỉ secrets, không thực hiện thao tác Git ops hoặc ghi đè file nguồn.
5. **Độ bao phủ của Automated Tests:** Đầy đủ baseline 4 file, 3 cặp so sánh, và các edge cases bắt buộc.

---

## 2. KẾT QUẢ ĐỐI SOÁT CHI TIẾT THEO TIÊU CHÍ GATE

| Hạng mục rà soát | Tiêu chí Gate | Kết quả thẩm định | Trạng thái |
|---|---|---|:---:|
| **Xác minh file nguồn** | Đủ 4 file Excel trong `Data Source/Kiem Ke`, có SHA256 và kích thước chính xác. | Đủ 4 file, SHA256 và size khớp 100% bản lưu trữ. | **PASS** |
| **Phân tích 15 cột** | Phân tích kiểu dữ liệu, null rate, công thức, bảo toàn chuỗi số 0 đầu. | Đã phân tích chi tiết. Phát hiện cột 11 & 12 là công thức; 358-359 SKU bắt đầu bằng 0 được bảo toàn. | **PASS** |
| **Tái lập Baseline** | Khớp 100% bảng số liệu Ground Truth 4 file và 3 cặp so sánh. | Cả 4 file (432, 432, 434, 434 dòng) và 3 cặp so sánh (+129, +57, -175 SL) khớp chính xác tuyệt đối. | **PASS** |
| **Định danh Snapshot** | Khóa `(product_code, warehouse)`, quy tắc đa snapshot/ngày, không tự gộp. | `SnapshotIdentity` phân tách rõ ràng; không cộng dồn snapshot cùng ngày. | **PASS** |
| **Xử lý Xung đột & Trùng lặp** | Ma trận NEW, ALREADY_IMPORTED, DUPLICATE, CONFLICT, SOFT_DELETED. | Đã xây dựng và kiểm thử độc lập, không cho phép phục hồi tự động snapshot đã xóa mềm khi Drive sync quét lại. | **PASS** |
| **Bảo vệ biên & Phép chia 0** | Tránh `ZeroDivisionError` khi SL A = 0; SKU mất không tự gán = 0. | `pct_qty_change = None` khi A = 0; missing SKU được đánh dấu `NOT_APPEARED`. | **PASS** |
| **Automated Tests** | Chạy kiểm thử tự động độc lập có log thật. | 19/19 test cases chạy thành công trên pytest. | **PASS** |

---

## 3. CÁC ĐIỂM LƯU Ý & KHUYẾN NGHỊ CHO CÁC ROUND TIẾP THEO

1. **Chuẩn bị Schema Database (Round 02):**
   - Khóa tự nhiên `(product_code, warehouse)` phải được đưa vào ràng buộc UNIQUE hoặc chỉ mục hỗn hợp (composite index) trong bảng `inventory_items` của Cloudflare D1.
   - Cần lưu riêng trường `unit_price` và `total_amount` dưới dạng số nguyên (VND không dùng cent, nhưng nên lưu dưới dạng số thực `REAL` hoặc số nguyên `INTEGER` trong SQLite) để đảm bảo không bị sai số dấu phẩy động.
2. **Quy trình nạp Google Drive (Round 07):**
   - Cần đảm bảo Apps Script hoặc connector chỉ đọc và gửi payload chuẩn hóa đã xác thực qua HMAC, không truyền file nhị phân lớn vượt ngưỡng bộ nhớ Worker của Cloudflare Free Tier.
3. **Phân quyền và bảo mật (Round 03):**
   - Nghiêm cấm public API import và so sánh khi chưa đăng nhập.
   - Giữ nguyên nguyên tắc mật khẩu tạm `123456` chỉ dùng ở môi trường test và bắt buộc đổi ngay ở lần đăng nhập đầu tiên.

---

## 4. QUYẾT ĐỊNH CỦA QC REVIEWER

**KẾT LUẬN: ĐẠT (PASS)**. Bộ tài liệu kỹ thuật, parser chuẩn hóa, và kết quả kiểm thử tự động của Round 01 đáp ứng đầy đủ và nghiêm ngặt mọi điều kiện tiên quyết (Gate) đã đề ra. Khuyến nghị Orchestrator phê duyệt đóng gói Round 01.
