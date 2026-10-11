# ROUND 01 PROMPT — PHÂN TÍCH EXCEL & DATA CONTRACT

**Dự án:** Inventory Management — Web quản lý/đối soát tồn kho.  
**Round hiện tại:** 01/10.  
**Owner:** Data Engineer.  
**Reviewer:** QC Reviewer (độc lập).  
**Verifier:** QA Tester (độc lập).  
**Coordinator:** Orchestrator.  
**Ngôn ngữ báo cáo/tài liệu bàn giao:** Tiếng Việt.

## 1. INPUT ĐÃ ĐƯỢC CHỐT

- File A: `KiemKe_KK.CH41551.26.339000_20261009.xlsx`.
- File B: `KiemKe_KK.CH41551.26.339513_20261009.xlsx`.
- File C: `KiemKe_KK.CH41551.26.339931_20261010.xlsx`.
- File D: `KiemKe_KK.CH41551.26.340231_20261011.xlsx`.
- Vị trí chuẩn trong workspace: `Data Source/Kiem Ke/` (có dấu cách).
- Folder Google Drive chính thức: `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`.
- URL: `https://drive.google.com/drive/folders/1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk?usp=sharing`.
- Phạm vi nghiệp vụ: nhiều file/ngày; nhiều lần xuất trong cùng store hoặc khác store/stock scope; có ca Sáng/Chiều/Tối/Khác/Chưa xác định.
- Cần manual upload lẫn Google Drive sync; Round 01 chỉ phân tích hợp đồng dữ liệu, **chưa triển khai sync**.
- UI về sau phải 100% tiếng Việt.

## 2. CÂU HỎI CẦN CHỐT & FILE CẦN GỬI

**Không có câu hỏi bắt buộc để bắt đầu Round 01.**

Bốn file Excel trong Kickoff V2 đã đủ để xác minh baseline. Phải phân tích cả 2 file cùng ngày 09/10. Nếu working directory không có file, báo cụ thể đường dẫn thiếu và **BLOCKED**; không tự bịa dữ liệu.

Các thông số chỉ cần ở Round sau: Google Script owner/credentials, Cloudflare account, GitHub URL. Không yêu cầu hoặc lưu mật khẩu/tokens trong báo cáo.

## 3. SKILLS & TEAM

- Orchestrator: `writing-plans`, `executing-plans`.
- Data Engineer: `test-driven-development`, `systematic-debugging`.
- QC: `requesting-code-review`, `receiving-code-review` (áp dụng vào quy trình nhận/xử lý nhận xét).
- QA: `verification-before-completion`.
- Release: `finishing-a-development-branch` chỉ sử dụng phần review/release, tuyệt đối không Git operations.
- Nếu không có các skill đó, ghi `unavailable`, thực hiện checklist tương đương. Không tự nhận đã cài skill.

## 4. NHIỆM VỤ DATA ENGINEER

1. Liệt kê file thật, checksum SHA256, kích thước, tên sheet, số dòng/cột, header, kiểu dữ liệu của từng cột và tỷ lệ null; so sánh schema giữa cả bốn file.
2. Phân tích chính xác 15 cột Excel và vị trí dòng header/tổng hợp/sản phẩm. Xác định mọi giá trị công thức (nếu có), kiểu lưu numeric/text, hàng/cột ẩn nếu ảnh hưởng import.
3. Chuẩn hóa data dictionary 15 cột: tên gốc, technical key, datatype, nullable, validation rule, ví dụ, semantic meaning.
4. Tách rõ `SL TỒN KHO` (snapshot quantity) với `CHÊNH LỆCH` (source worksheet field), không nhầm hai khái niệm.
5. Đề xuất mô hình snapshot identity: mã đầy đủ, mã ngắn, store code, ngày, ca, scope, source id, checksum; phân biệt source metadata và actual inventory time.
6. Đề xuất uniqueness/natural key và chính sách `DUPLICATE`, `CONFLICT`, `NEW`, `ALREADY_IMPORTED`, `SOFT_DELETED`.
7. Viết parser/normalizer độc lập có thể tái sử dụng cho Round 04, hoặc chỉ tạo parser reference kèm automated tests nếu dự án chưa có framework. Không yêu cầu làm hoàn chỉnh UI/API/database ở Round này.
8. Tính kiểm tra độc lập từ bốn file; so tổng của row detail với summary row; đối chiếu SKU theo `(product_code, stock_type)`.
9. Liệt kê edge cases, validation errors, tolerance/precision của số lượng/tiền, missing SKU, sản phẩm trùng kho, cùng ngày nhiều mã.
10. Đề xuất contract giữa Drive sync/parser/backend batch ingestion, **không** kết nối production API khi chưa có quyền.

## 5. MANDATORY BASELINE (GATE) — BỐN FILE THẬT

| Snapshot | Date | Chi tiết | Kho hàng bán | Kho vật phẩm KM | Tổng SL tồn | Tổng thành tiền VND |
|---|---|---:|---:|---:|---:|---:|
| 339000 | 09/10/2026 | 432 | 390 | 42 | 16961 | 270739477 |
| 339513 | 09/10/2026 | 432 | 390 | 42 | 17090 | 272476003 |
| 339931 | 10/10/2026 | 434 | 391 | 43 | 17147 | 275711737 |
| 340231 | 11/10/2026 | 434 | 391 | 43 | 16972 | 273775891 |

Kết quả so sánh theo `(product_code, stock_type)`:

| A → B | Matched | Tăng | Giảm | Mới | Không xuất hiện | ΔSL | ΔGiá trị |
|---|---:|---:|---:|---:|---:|---:|---:|
| 339000 → 339513 | 432 | 19 | 58 | 0 | 0 | +129 | +1736526 |
| 339513 → 339931 | 432 | 18 | 42 | 2 | 0 | +57 | +3235734 |
| 339931 → 340231 | 434 | 0 | 28 | 0 | 0 | -175 | -1935846 |

Hai mã mới 09/10 → 10/10: `02AO18` (`Kho hàng bán`), `9NH277` (`Kho hàng vật phẩm KM`).

Ví dụ 10/10 → 11/10: `07KD12` 113→89; `04FT32` 88→67; `07NH12` 56→37; `04EC33` 124→108; `07TR33` 94→82.

Số liệu này chỉ là expected values; không hardcode kết quả. **Trường hợp cùng ngày hai file khác mã là test nghiệp vụ bắt buộc.**

## 6. MANDATORY TESTS

- Parse 4 file thật, đọc đúng sheet `Kiem-ke`, header, summary row; 09/10 có 432 dòng detail/file, 10–11/10 có 434 dòng detail/file.
- Test cùng ngày khác mã: 339000 → 339513, kết quả +129 tồn và +1.736.526 VND.
- Test trường hợp có 2 SKU mới từ 339513 → 339931, không coi missing là qty=0.
- Kiểm tra mã sản phẩm bảo toàn string và số 0 đầu mã.
- Check subtotal theo kho, quantity, value.
- Tự tính matched/new/missing/increased/decreased.
- Cùng mã SKU ở 2 loại kho xử lý là 2 khóa khác nhau.
- Với fixture synthetic: 2 file cùng ngày khác mã, cùng mã khác checksum, missing SKU, new SKU, quantity=0, duplicate SKU/kho, invalid quantity, missing header, blank row, invalid product code, đổi đơn giá nhưng số lượng không đổi.
- Test rõ boundary khi A=0 để tránh phép chia 0.
- Không viết logic test gọi một hàm tự cung cấp expected data bằng cùng thuật toán không độc lập.

## 7. BỘ HỒ SƠ BÀN GIAO ROUND 01

Trong **01 ZIP duy nhất** (không đưa credential hoặc file nội bộ nhạy cảm ngoài phạm vi được phép), tối thiểu có:

1. `DATA_ANALYSIS.md` — phát hiện thực tế từ Excel.
2. `DATA_CONTRACT.md` — data dictionary, chuẩn hóa, types, validation.
3. `SNAPSHOT_IDENTITY.md` — khóa, dedup, conflict, metadata.
4. `IMPORT_COMPARISON_TESTS.md` — scenarios và expected results.
5. Parser/reference tests + test fixtures được phép chia sẻ.
6. `TEST_RESULTS.md` — commands + output thật, số pass/fail.
7. `QC_REVIEW.md` — review độc lập, vấn đề cần sửa.
8. `ROUND_REPORT.md` — tóm tắt cuối Round bằng tiếng Việt.
9. `AGENT_RESPONSE.md` — tổng hợp nội dung đã làm.
10. `ROUND_MANIFEST.json` — trạng thái, file bàn giao, hash, issues.
11. `NEXT_ROUND_PROMPT.md` — dự thảo Round 02 nếu gate PASS.

Tạo `Round_01_Excel_Data_Contract.zip` từ **live working folder**; tạo `Round_01_Excel_Data_Contract.zip.sha256` ở **ngoài ZIP**; xác minh checksum.

Không yêu cầu Git evidence. Không commit/push/PR/branch. Không chạy migrations hoặc query thay đổi database production.

## 8. PASS GATE

Chỉ PASS khi:
- Bốn file đã được đọc trực tiếp và dữ liệu thực tế có bằng chứng.
- 15 cột, tổng cho 4 file và 3 cặp comparison baseline khớp toàn bộ.
- Data Contract và snapshot identity giải quyết nhiều file/ngày, khác store/scope, nhiều ca, source dedup.
- Automated tests cho parser/reference thành công và có logs.
- QC đã review, QA đã xác minh độc lập.
- ZIP + SHA sidecar tồn tại và kiểm tra được.

Nếu thiếu bằng chứng, đánh dấu `PARTIAL`/`BLOCKED`/`FAIL` đúng thực tế; không tự chuyển sang Round 02.

## 9. BÁO CÁO SAU ROUND (NGẮN)

```
Round 01 – Phân tích Excel & Data Contract
Trạng thái: PASS / PARTIAL / BLOCKED / FAIL
Đã hoàn thành: [tối đa 3 điểm]
Kiểm thử: [X/Y PASS, lỗi cụ thể]
QC: [PASS hoặc NEED FIX]
Tồn đọng: [0 hoặc tối đa 3 điểm]
Package: Round_01_Excel_Data_Contract.zip
SHA256: Round_01_Excel_Data_Contract.zip.sha256
Round tiếp theo: Round 02 – Foundation (chỉ khi đủ điều kiện)
```

**BẮT ĐẦU:** Examine inputs → Data analysis → Contract → Tests → QC/QA → Report → Package. Không làm UI demo thay cho Round 01.
