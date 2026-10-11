# ĐỀ XUẤT PROMPT CHO ROUND 08/10 – XUẤT BÁO CÁO KIỂM KÊ & ĐỐI SOÁT (XLSX / CSV)

> **LƯU Ý QUAN TRỌNG:** TÀI LIỆU NÀY DÀNH CHO ROUND 08. HIỆN TẠI HỆ THỐNG ĐÃ HOÀN THÀNH VÀ DỪNG GATE TẠI ROUND 07 ĐỂ CHỜ NGƯỜI DÙNG NGHIỆM THU ĐỘC LẬP. TUYỆT ĐỐI KHÔNG TỰ Ý BẮT ĐẦU ROUND 08 KHI CHƯA CÓ LỆNH.

## 1. Bối cảnh & Kết quả Kế thừa từ Round 07
- Round 07 đã hoàn thành xuất sắc kiến trúc Dual-Driver cho Google Drive Synchronization (Simulation Driver + Live Driver) tuân thủ 100% mục 10 Master Prompt.
- Động cơ đồng bộ tự động `syncService` quét thư mục `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`, tích hợp engine Round 04, bảo toàn tính lũy đẳng (Idempotency) không nhân đôi dữ liệu.
- Trang giao diện `SyncPage.tsx` chuyên biệt với thẻ thông tin Thư mục Drive, nút "Đồng bộ ngay", 4 thẻ KPI và bảng lịch sử đợt chạy trực quan.
- Toàn bộ 178 ca kiểm thử tích hợp và hồi quy đạt 100% PASS.

## 2. Mục tiêu Trọng tâm Round 08
- **Reporting & Export Engine (XLSX / CSV):**
  - Xuất báo cáo chứng từ kiểm kê chi tiết theo 15 cột tiêu chuẩn ra file Excel (.xlsx).
  - Xuất báo cáo kết quả đối soát tồn kho (Bảng chênh lệch B - A) ra file Excel đa sheet (.xlsx) kèm công thức tính toán và tô màu trực quan (Tăng tồn: Xanh, Giảm tồn: Đỏ, Khớp: Xám).
  - Xuất báo cáo phân tích theo ngành hàng / danh mục sản phẩm.
  - Hỗ trợ xuất file định dạng CSV chuẩn UTF-8 có BOM chống lỗi font tiếng Việt trong Excel.
  - Bộ lọc tùy biến linh hoạt theo thời gian, cửa hàng, ngành hàng và trạng thái chênh lệch.
  - Tích hợp bảo mật: Chống tấn công Spreadsheet Formula Injection (CSV injection), kiểm soát tải file theo quyền người dùng và ghi nhật ký kiểm toán.
