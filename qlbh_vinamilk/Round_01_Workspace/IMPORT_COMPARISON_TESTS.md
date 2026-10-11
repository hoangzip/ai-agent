# ĐẶC TẢ KIỂM THỬ IMPORT VÀ SO SÁNH TỒN KHO (IMPORT & COMPARISON TESTS)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 01/10  
**Tài liệu:** Import & Comparison Test Scenarios and Expected Results  

---

## 1. MỤC TIÊU KIỂM THỬ

Xác nhận độ chính xác tuyệt đối của bộ máy phân tích cú pháp (Parser) và công cụ đối soát tồn kho (Comparator) trên 100% dữ liệu Excel thật từ Vinamilk và các trường hợp kiểm thử biên (Edge Cases / Synthetic Fixtures).

---

## 2. KỊCH BẢN KIỂM THỬ TRÊN 4 FILE THẬT (MANDATORY BASELINE)

### Kịch bản 1: Đọc và xác thực cấu trúc 4 snapshot thực tế

| Test Case ID | Mục tiêu kiểm tra | Dữ liệu đầu vào | Kết quả kỳ vọng (Expected Output) |
|---|---|---|---|
| `TC-REAL-01` | Đọc file 339000 (09/10/2026) | `KiemKe_KK.CH41551.26.339000_20261009.xlsx` | Chi tiết: 432 dòng; Kho hàng bán: 390; Kho KM: 42; Tổng tồn: 16,961; Tổng tiền: 270,739,477 VND. Dòng 2 khớp 100%. |
| `TC-REAL-02` | Đọc file 339513 (09/10/2026) | `KiemKe_KK.CH41551.26.339513_20261009.xlsx` | Chi tiết: 432 dòng; Kho hàng bán: 390; Kho KM: 42; Tổng tồn: 17,090; Tổng tiền: 272,476,003 VND. Dòng 2 khớp 100%. |
| `TC-REAL-03` | Đọc file 339931 (10/10/2026) | `KiemKe_KK.CH41551.26.339931_20261010.xlsx` | Chi tiết: 434 dòng; Kho hàng bán: 391; Kho KM: 43; Tổng tồn: 17,147; Tổng tiền: 275,711,737 VND. Dòng 2 khớp 100%. |
| `TC-REAL-04` | Đọc file 340231 (11/10/2026) | `KiemKe_KK.CH41551.26.340231_20261011.xlsx` | Chi tiết: 434 dòng; Kho hàng bán: 391; Kho KM: 43; Tổng tồn: 16,972; Tổng tiền: 273,775,891 VND. Dòng 2 khớp 100%. |
| `TC-REAL-05` | Bảo toàn số 0 đầu mã SKU | Cả 4 file | 358-359 SKU bắt đầu bằng số 0 (vd `'02AA15'`) được lưu dưới dạng chuỗi `str`, không bị cắt thành số `2AA15`. |

---

### Kịch bản 2: Đối soát 3 cặp snapshot kiểm kê chuẩn (Baseline Comparisons)

#### Cặp 1: So sánh 2 file cùng ngày 09/10/2026 (`339000` $\rightarrow$ `339513`)
- **Ý nghĩa:** Biến động trong ngày (Intra-day), ví dụ giữa 2 ca hoặc 2 lần xuất kho.
- **Kỳ vọng:**
  - `Matched`: 432 SKU
  - `Tăng`: 19 SKU
  - `Giảm`: 58 SKU
  - `Không đổi`: 355 SKU
  - `Mới xuất hiện`: 0 SKU
  - `Không xuất hiện`: 0 SKU
  - $\Delta$ Số lượng: **+129**
  - $\Delta$ Giá trị: **+1,736,526 VND**

#### Cặp 2: So sánh ngày 09/10 $\rightarrow$ 10/10 (`339513` $\rightarrow$ `339931`)
- **Ý nghĩa:** Phát hiện sản phẩm mới nhập kho trong ngày tiếp theo.
- **Kỳ vọng:**
  - `Matched`: 432 SKU
  - `Tăng`: 18 SKU
  - `Giảm`: 42 SKU
  - `Không đổi`: 372 SKU
  - `Mới xuất hiện`: **2 SKU**, gồm:
    1. `02AO18` tại `Kho hàng bán`
    2. `9NH277` tại `Kho hàng vật phẩm KM`
  - `Không xuất hiện`: 0 SKU
  - $\Delta$ Số lượng: **+57**
  - $\Delta$ Giá trị: **+3,235,734 VND**

#### Cặp 3: So sánh ngày 10/10 $\rightarrow$ 11/10 (`339931` $\rightarrow$ `340231`)
- **Ý nghĩa:** Biến động xuất bán thông thường, kiểm tra chi tiết từng mã giảm.
- **Kỳ vọng:**
  - `Matched`: 434 SKU
  - `Tăng`: 0 SKU
  - `Giảm`: 28 SKU
  - `Không đổi`: 406 SKU
  - `Mới xuất hiện`: 0 SKU
  - `Không xuất hiện`: 0 SKU
  - $\Delta$ Số lượng: **-175**
  - $\Delta$ Giá trị: **-1,935,846 VND**
  - **Kiểm chứng 5 mã SKU mẫu:**
    1. `07KD12` (`Kho hàng bán`): 113 $\rightarrow$ 89 ($\Delta = -24$)
    2. `04FT32` (`Kho hàng bán`): 88 $\rightarrow$ 67 ($\Delta = -21$)
    3. `07NH12` (`Kho hàng bán`): 56 $\rightarrow$ 37 ($\Delta = -19$)
    4. `04EC33` (`Kho hàng bán`): 124 $\rightarrow$ 108 ($\Delta = -16$)
    5. `07TR33` (`Kho hàng bán`): 94 $\rightarrow$ 82 ($\Delta = -12$)

---

## 3. KỊCH BẢN KIỂM THỬ TRƯỜNG HỢP BIÊN & PHÒNG NGỪA RỦI RO (EDGE CASES)

| Test Case ID | Tình huống kiểm thử | Hành vi kỳ vọng |
|---|---|---|
| `TC-EDGE-01` | Số lượng tồn tại Snapshot A = 0 | Phép tính `% chênh lệch` không phát sinh ngoại lệ chia cho 0 (`ZeroDivisionError`), trả về `None` an toàn. |
| `TC-EDGE-02` | SKU có trong A nhưng biến mất khỏi B | Phân loại trạng thái là `NOT_APPEARED` (Không xuất hiện), **tuyệt đối không tự gán tồn B = 0**. |
| `TC-EDGE-03` | SKU mới chỉ xuất hiện tại B | Phân loại trạng thái là `NEW` (Mới xuất hiện), delta SL = +SL(B). |
| `TC-EDGE-04` | Đơn giá thay đổi nhưng số lượng tồn giữ nguyên | Ghi nhận chênh lệch thành tiền trong khi `diff_qty = 0`, phân loại trong danh sách `price_changed_qty_same`. |
| `TC-EDGE-05` | Cùng 1 mã SKU nằm ở cả 2 loại kho | Xử lý thành 2 bản ghi độc lập dựa trên khóa `(product_code, warehouse)`. Biến động của mỗi kho được tính riêng. |
| `TC-VAL-01` | Trùng mã SKU trong cùng một kho trong 1 file | Parser ném ngoại lệ `ExcelValidationError: Trùng lặp khóa tự nhiên`. Ngăn chặn nạp dữ liệu rác. |
| `TC-VAL-02` | File chứa số lượng tồn âm | Parser ném ngoại lệ `ExcelValidationError: SL tồn kho không được âm`. |
| `TC-VAL-03` | Cấu trúc thiếu cột / sai tên cột header | Parser ném ngoại lệ `ExcelParseError: Cấu trúc 15 cột không khớp`. |
| `TC-VAL-04` | Số liệu dòng tổng hợp (Dòng 2) không khớp tổng chi tiết | Parser ném ngoại lệ `ExcelValidationError: Lệch tổng số lượng tồn`. |
| `TC-ID-01` | Chính sách Snapshot Ingestion: NEW | Phát hiện chứng từ mới, cấp phép nạp. |
| `TC-ID-02` | Chính sách Snapshot Ingestion: ALREADY_IMPORTED | Phát hiện file nhị phân trùng khớp SHA256, báo đã nạp thành công trước đó. |
| `TC-ID-03` | Chính sách Snapshot Ingestion: DUPLICATE | Khác binary hash (do lưu lại file) nhưng content hash trùng khớp 100%, bỏ qua và cảnh báo trùng lặp. |
| `TC-ID-04` | Chính sách Snapshot Ingestion: CONFLICT | Cùng mã chứng từ nhưng content hash khác nhau, từ chối ghi đè, báo trạng thái `CONFLICT`. |
| `TC-ID-05` | Chính sách Snapshot Ingestion: SOFT_DELETED | Chứng từ đã bị Admin xóa mềm, từ chối tự động phục hồi khi Drive Sync quét lại file. |
