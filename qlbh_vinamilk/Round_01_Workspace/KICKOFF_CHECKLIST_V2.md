# CHECKLIST CHUẨN BỊ ROUND 01 — KHÔNG PHẢI BÁO CÁO ROUND ĐÃ CHẠY

Ngày chuẩn bị: 11/10/2026

## Đã có
- [x] Chốt Google Drive Folder ID: `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`
- [x] Chốt UI và báo cáo sử dụng tiếng Việt.
- [x] Chốt multi-agent theo vai trò; 10 Round và báo cáo ngắn.
- [x] Bốn file Excel nguồn được đóng gói trong Kickoff V2.
- [x] Kiểm chứng sơ bộ sheet, số dòng, số SKU, lượng tồn và biến động từ file nguồn.
- [x] Master Prompt hợp nhất.
- [x] Prompt Round 01 để giao Agent.

## Cần Agent thực hiện ở Round 01
- [ ] Lập `DATA_ANALYSIS.md`, `DATA_CONTRACT.md`, `SNAPSHOT_IDENTITY.md`.
- [ ] Viết parser/ref tests và chạy trên môi trường project thực.
- [ ] QC review và QA independent verification.
- [ ] Tạo duy nhất 01 ZIP Round 01 và SHA256 sidecar.
- [ ] Báo cáo PASS/PARTIAL/BLOCKED/FAIL bằng tiếng Việt.

## Kiểm tra sơ bộ trước Round (đã thực hiện tại đây)
- File 339000 (09/10): 432 SKU, 390 Kho hàng bán + 42 Kho vật phẩm KM, qty 16961, value 270739477 VND.
- File 339513 (09/10): 432 SKU, 390 Kho hàng bán + 42 Kho vật phẩm KM, qty 17090, value 272476003 VND.
- 339000 → 339513 (cùng ngày): matched 432, increased 19, decreased 58, qty +129, value +1736526 VND.
- 339513 → 339931: matched 432, 2 mã mới (02AO18 và 9NH277), increased 18, decreased 42, qty +57, value +3235734 VND.
- File 339931: `Kiem-ke`, 15 cột, 434 chi tiết, 17147 số lượng, 275711737 VND.
- File 340231: `Kiem-ke`, 15 cột, 434 chi tiết, 16972 số lượng, 273775891 VND.
- Mỗi file gồm 391 SKU Kho hàng bán và 43 SKU Kho hàng vật phẩm KM.
- So sánh: 434 mã+kho khớp, 28 giảm, 0 tăng, -175 số lượng, -1935846 VND.
- Các số này là preflight check, **không thay thế** tests/QC chính thức của Round 01.

## Còn chờ cho các Round sau (không chặn Round 01)
- Cấu hình xác thực và người vận hành Google Apps Script (Round 07).
- Cloudflare account và quyền triển khai (Round 10).
- GitHub repository + hành động deploy do người dùng cho phép (Round 10).
- Chuyển chia sẻ Google Drive sang Restricted sau khi bảo đảm connector có quyền riêng (khuyến nghị bảo mật).

## Nguyên tắc an toàn
- Không thay đổi database production, không thao tác Git, không chỉnh quyền Google Drive khi chưa có phê duyệt.
- Không đưa mật khẩu khởi tạo `123456` vào source code public; dùng thông tin tạm để setup an toàn và buộc đổi trước production.
