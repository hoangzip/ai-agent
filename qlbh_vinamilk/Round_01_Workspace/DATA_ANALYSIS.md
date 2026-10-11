# BÁO CÁO PHÂN TÍCH DỮ LIỆU EXCEL KIỂM KÊ (DATA ANALYSIS)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 01/10  
**Vai trò thực hiện:** Data Engineer  
**Ngày thực hiện:** 11/10/2026  
**Môi trường:** Local Workspace (`Round_01_Workspace`)  

---

## 1. TỔNG QUAN TẬP DỮ LIỆU THẬT

Hệ thống đã nhận diện và phân tích trực tiếp 04 file Excel định dạng `.xlsx` trong thư mục `Data Source/Kiem Ke/`:

| Tên File | Dung lượng | SHA256 Checksum | Ngày kiểm kê (tên file) | Mã chứng từ |
|---|---:|---|:---:|:---:|
| `KiemKe_KK.CH41551.26.339000_20261009.xlsx` | 43,672 B | `e4c7da094f08ebcfe048d4779711c54cd185c9b5bc790b34c6fd012d3d65d99f` | 09/10/2026 | `KK.CH41551.26.339000` |
| `KiemKe_KK.CH41551.26.339513_20261009.xlsx` | 43,663 B | `ecab3594af91af10f6a54122dfed58c2925473979232888d1ca91865d8e1bc51` | 09/10/2026 | `KK.CH41551.26.339513` |
| `KiemKe_KK.CH41551.26.339931_20261010.xlsx` | 43,822 B | `a1f97fbadf0f121a5fa2b7ad399d50cb6cf9751caa7d4f7d3cbb690ae4f92259` | 10/10/2026 | `KK.CH41551.26.339931` |
| `KiemKe_KK.CH41551.26.340231_20261011.xlsx` | 43,822 B | `1fdba7e9caacbded77ff196977f57251692fee8ec2ab5ff281a3e58dc8facd7d` | 11/10/2026 | `KK.CH41551.26.340231` |

Tất cả 4 file đều được tạo bởi engine `Apache POI` (hệ thống xuất dữ liệu ERP nội bộ). Không có sheet ẩn, không có dòng/cột ẩn gây ảnh hưởng dữ liệu.

---

## 2. CẤU TRÚC WORKSHEET & VÙNG DỮ LIỆU

- **Tên Worksheet:** Duy nhất 01 sheet tên `Kiem-ke` trong cả 4 file.
- **Kích thước vùng dữ liệu:**
  - File 339000 & 339513: Vùng `A1:O434` (Tổng 434 dòng, 15 cột).
  - File 339931 & 340231: Vùng `A1:O436` (Tổng 436 dòng, 15 cột).
- **Phân bổ các dòng:**
  - **Dòng 1:** Dòng tiêu đề cột (Header) gồm chính xác 15 cột.
  - **Dòng 2:** Dòng tổng hợp (Summary Row) chứa số lượng tổng và thành tiền tổng của toàn bộ chứng từ.
  - **Dòng 3 trở đi:** Các dòng chi tiết sản phẩm kiểm kê (Detail Rows).
    - 09/10/2026 (339000 & 339513): chính xác **432 sản phẩm**.
    - 10/10/2026 (339931): chính xác **434 sản phẩm** (xuất hiện thêm 2 SKU mới).
    - 11/10/2026 (340231): chính xác **434 sản phẩm**.

---

## 3. PHÂN TÍCH CHI TIẾT 15 CỘT EXCEL

| Cột | Tên Cột Gốc | Kiểu Dữ Liệu Thực Tế | Null Rate | Dòng 2 (Summary) | Dòng 3+ (Detail) & Ví dụ | Tính chất / Công thức |
|:---:|---|---|:---:|---|---|---|
| 1 | `STT` | Numeric / Integer | 0.0% | Ô trống (`None`) | 1, 2, 3... | Số thứ tự tăng dần |
| 2 | `NGÀNH HÀNG` | String | 0.0% | Ô trống (`None`) | 'A', 'S', 'B'... | Phân loại ngành hàng |
| 3 | `MÃ SẢN PHẨM` | String (Alpha-Numeric) | 0.0% | Ô trống (`None`) | '02AA15', '02AO18', '9NH277' | **BẮT BUỘC giữ số 0 đầu chuỗi** |
| 4 | `TÊN SẢN PHẨM` | String | 0.0% | Ô trống (`None`) | 'SB Dielac Alpha 1 HT 400g' | Tên mô tả sản phẩm |
| 5 | `SL TỒN KHO` | Numeric (Float/Int) | 0.0% | Giá trị số tổng SL tồn (vd: 16961.0) | 2.0, 5.0, 10.0... | **Giá trị dùng để so sánh tồn kho** |
| 6 | `LOẠI KHO` | String | 0.0% | Ô trống (`None`) | 'Kho hàng bán', 'Kho hàng vật phẩm KM' | Phân loại vị trí kho |
| 7 | `GIÁ (SAU VAT)` | Numeric (Float/Int) | 0.0% | Ô trống (`None`) | 164268.0, 258822.0... | Đơn giá sau thuế (VND) |
| 8 | `THÀNH TIỀN` | Numeric (Float/Int) | 0.0% | Giá trị số tổng thành tiền (vd: 270739477.0) | 328536.0, 1294110.0... | = `SL TỒN KHO` * `GIÁ (SAU VAT)` |
| 9 | `SL PACKAGE KIỂM KÊ` | Numeric (Float/Int) | 0.0% | Ô trống (`None`) | 0.0, 1.0, 2.0... | Số lượng bao gói thực tế kiểm đếm |
| 10 | `SL LẺ KIỂM KÊ` | Numeric (Float/Int) | 0.0% | Ô trống (`None`) | 0.0, 5.0, 12.0... | Số lượng đơn vị lẻ thực tế kiểm đếm |
| 11 | `TỔNG SL KIỂM KÊ` | Formula (Text) / Numeric | 0.0% | `=SUM(K3:K434)` / `=SUM(K3:K436)` | `=I3*N3+J3` | Công thức: Package * Quy đổi + Lẻ |
| 12 | `CHÊNH LỆCH` | Formula (Text) / Numeric | 0.0% | `=K2-E2` | `=K3-E3` | Công thức: Tổng kiểm kê - SL Tồn kho |
| 13 | `ĐVT PACKAGE` | String | 0.0% | Ô trống (`None`) | 'THU', 'LOC', 'HOP'... | Đơn vị tính bao gói |
| 14 | `QUY ĐỔI` | Numeric (Float/Int) | 0.0% | Ô trống (`None`) | 24.0, 12.0, 48.0... | Hệ số quy đổi ra đơn vị lẻ |
| 15 | `ĐVT LẺ` | String | 0.0% | Ô trống (`None`) | 'Hộp', 'Chai', 'Gói'... | Đơn vị tính cơ bản |

---

## 4. QUAN SÁT NGHIỆP VỤ QUAN TRỌNG

1. **Khái niệm SL TỒN KHO vs CHÊNH LỆCH:**
   - Cột 5 `SL TỒN KHO` là số dư sổ sách tại thời điểm xuất file kiểm kê. Đây là trường bắt buộc dùng để so sánh giữa các snapshot.
   - Cột 12 `CHÊNH LỆCH` là chênh lệch giữa số kiểm đếm thực tế (cột 11) và sổ sách (cột 5) trong chính kỳ kiểm kê đó. Không được nhầm lẫn cột này với biến động giữa 2 lần xuất khác nhau.
2. **Công thức và tính toán:**
   - Cột 11 và Cột 12 ở các dòng chi tiết luôn chứa công thức Excel: `K{r} = I{r}*N{r} + J{r}` và `L{r} = K{r} - E{r}`.
   - Cột 8 `THÀNH TIỀN` lưu giá trị số trực tiếp, và được kiểm chứng 100% khớp với phép tính `SL TỒN KHO * GIÁ (SAU VAT)` trên toàn bộ 1,732 dòng chi tiết của cả 4 file.
3. **Phân bổ theo loại kho:**
   - Cả 4 file phân tách rõ ràng 2 loại kho:
     - `Kho hàng bán`: chiếm đa số (390 SKU trong 09/10, 391 SKU trong 10-11/10).
     - `Kho hàng vật phẩm KM`: chiếm phần còn lại (42 SKU trong 09/10, 43 SKU trong 10-11/10).
   - Khóa định danh dòng chi tiết là cặp `(MÃ SẢN PHẨM, LOẠI KHO)`.
4. **Bảo toàn số 0 đầu mã:**
   - Có đến 358-359 mã sản phẩm bắt đầu bằng ký tự `0` (ví dụ: `02AA15`, `02AO18`, `07KD12`). Nếu đọc dưới dạng số nguyên sẽ bị mất số 0 đầu, gây sai lệch mã toàn bộ hệ thống. Parser bắt buộc phải xử lý string thuần túy.
