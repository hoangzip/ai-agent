# HỢP ĐỒNG DỮ LIỆU EXCEL KIỂM KÊ (DATA CONTRACT)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Phiên bản Contract:** 1.0 (Round 01 Gate Standard)  
**Trạng thái:** Confirmed & Verified with 4 Live Excel Files  

---

## 1. MỤC ĐÍCH & PHẠM VI

Tài liệu này xác lập hợp đồng kỹ thuật chuẩn (Data Contract) áp dụng cho mọi nguồn nạp dữ liệu kiểm kê vào hệ thống, bao gồm:
1. **Upload thủ công (Manual Web Upload):** File `.xlsx` do người dùng tải lên từ giao diện web.
2. **Đồng bộ tự động (Google Drive Sync):** Script hoặc connector tự động đọc file `.xlsx` / Google Sheets từ folder chỉ định.
3. **Batch Ingestion API:** Payload dữ liệu chuẩn hóa gửi vào Backend Worker/Database D1.

Mọi bản ghi vi phạm cấu trúc hoặc quy tắc kiểm tra (validation rules) sẽ bị từ chối ở tầng nạp (staging) với thông báo lỗi cụ thể theo dòng/cột.

---

## 2. DATA DICTIONARY 15 CỘT CHUẨN HÓA

| Cột | Tên Cột Excel Gốc | Khóa Kỹ Thuật (Technical Key) | Kiểu Dữ Liệu | Nullable | Quy Tắc Kiểm Tra (Validation Rules) | Ví dụ Thực Tế | Ý Nghĩa Nghiệp Vụ |
|:---:|---|---|---|:---:|---|---|---|
| 1 | `STT` | `stt` | `INTEGER` | Không | Số nguyên dương >= 1 | `1`, `2`, `432` | Số thứ tự dòng trong báo cáo |
| 2 | `NGÀNH HÀNG` | `category` | `VARCHAR(50)` | Không | Chuỗi ký tự độ dài 1-50, không khoảng trắng thừa | `'A'`, `'S'`, `'B'` | Mã/Tên ngành hàng sản phẩm |
| 3 | `MÃ SẢN PHẨM` | `product_code` | `VARCHAR(50)` | Không | **Chuỗi Text bảo toàn số 0 đầu**, 2-30 ký tự [A-Z0-9] | `'02AA15'`, `'02AO18'`, `'9NH277'` | Mã SKU sản phẩm duy nhất |
| 4 | `TÊN SẢN PHẨM` | `product_name` | `VARCHAR(255)` | Không | Chuỗi ký tự mô tả tên sản phẩm, 1-255 ký tự | `'SB Dielac Alpha 1 HT 400g'` | Tên thương mại đầy đủ |
| 5 | `SL TỒN KHO` | `quantity` | `DECIMAL(12,4)` | Không | **Số thực >= 0**, không âm | `2.0`, `113.0`, `0.0` | **Số lượng tồn sổ sách dùng để so sánh** |
| 6 | `LOẠI KHO` | `warehouse` | `VARCHAR(100)` | Không | Không rỗng; thường là 'Kho hàng bán' hoặc 'Kho hàng vật phẩm KM' | `'Kho hàng bán'`, `'Kho hàng vật phẩm KM'` | Phân loại kho lưu trữ |
| 7 | `GIÁ (SAU VAT)` | `unit_price` | `DECIMAL(14,2)` | Không | Số thực >= 0; Đơn giá tính theo VND | `164268.00`, `0.00` | Đơn giá bán sau thuế |
| 8 | `THÀNH TIỀN` | `total_amount` | `DECIMAL(16,2)` | Không | Số thực >= 0; `total_amount = round(quantity * unit_price, 2)` | `328536.00`, `0.00` | Tổng giá trị tồn sổ sách |
| 9 | `SL PACKAGE KIỂM KÊ` | `audit_package_qty` | `DECIMAL(12,4)` | Không | Số thực >= 0 | `0.0`, `5.0` | Số lượng nguyên thùng kiểm đếm |
| 10 | `SL LẺ KIỂM KÊ` | `audit_loose_qty` | `DECIMAL(12,4)` | Không | Số thực >= 0 | `0.0`, `12.0` | Số lượng đơn vị lẻ kiểm đếm |
| 11 | `TỔNG SL KIỂM KÊ` | `audit_total_qty` | `DECIMAL(12,4)` | Không | Đánh giá công thức hoặc tính: `pkg * conv + loose` | `0.0`, `24.0` | Tổng số lượng thực tế kiểm đếm |
| 12 | `CHÊNH LỆCH` | `discrepancy` | `DECIMAL(12,4)` | Không | Đánh giá công thức hoặc tính: `audit_total - quantity` | `-2.0`, `0.0`, `5.0` | Chênh lệch thực tế vs sổ sách kỳ này |
| 13 | `ĐVT PACKAGE` | `package_unit` | `VARCHAR(20)` | Có | Chuỗi viết tắt đơn vị thùng/lốc | `'THU'`, `'LOC'`, `'HOP'` | Đơn vị đóng gói |
| 14 | `QUY ĐỔI` | `conversion_rate` | `DECIMAL(10,2)` | Không | Số thực > 0 (mặc định = 1 nếu không có bao gói) | `24.0`, `12.0`, `1.0` | Tỷ lệ quy đổi bao gói ra đơn vị lẻ |
| 15 | `ĐVT LẺ` | `loose_unit` | `VARCHAR(20)` | Có | Đơn vị tính cơ bản nhỏ nhất | `'Hộp'`, `'Chai'`, `'Gói'` | Đơn vị lẻ |

---

## 3. QUY ĐỊNH CẤU TRÚC DÒNG & BẢNG TÍNH

1. **Dòng Header (Row 1):**
   - Bắt buộc chứa đủ 15 cột theo đúng thứ tự và nhãn chuẩn hóa.
   - Nếu thứ tự cột đảo lộn hoặc thiếu cột, parser phải từ chối ngay lập tức (`REJECT_INVALID_HEADER`).
2. **Dòng Tổng hợp (Row 2):**
   - Cột 5 (`SL TỒN KHO`) chứa tổng số lượng tồn của toàn bộ chứng từ.
   - Cột 8 (`THÀNH TIỀN`) chứa tổng thành tiền của toàn bộ chứng từ.
   - Cột 11 chứa công thức `=SUM(K3:K...)` và Cột 12 chứa công thức `=K2-E2`.
   - **Quy tắc đối soát nội bộ:** Tổng tính toán từ các dòng chi tiết (Row 3 đến Row N) bắt buộc phải khớp 100% với giá trị ghi tại Row 2. Nếu sai lệch vượt quá ngưỡng sai số (tolerance > 0.0001 với SL hoặc > 1 VND với tiền), hệ thống cảnh báo hoặc từ chối nạp.
3. **Dòng Chi tiết (Row 3 đến Row N):**
   - Mỗi dòng đại diện cho một SKU tại một loại kho xác định.
   - Các dòng trống hoàn toàn (tất cả 15 cột đều rỗng) được tự động bỏ qua.
   - Bất kỳ dòng nào có dữ liệu không hoàn chỉnh (ví dụ: có mã nhưng thiếu loại kho, hoặc có số lượng âm) sẽ kích hoạt lỗi validation.

---

## 4. KHÓA TỰ NHIÊN & TÍNH TOÀN VẸN DỮ LIỆU

1. **Khóa tự nhiên của sản phẩm trong một Snapshot:**
   $$\text{Item Natural Key} = (\text{product\_code}, \text{warehouse})$$
   - Cùng một `product_code` xuất hiện ở `Kho hàng bán` và `Kho hàng vật phẩm KM` là **hai bản ghi hoàn toàn tách biệt**, không được cộng dồn.
   - Nếu trong cùng một file xuất hiện trùng lặp khóa tự nhiên $(\text{product\_code}, \text{warehouse})$, parser báo lỗi vi phạm `DUPLICATE_KEY_IN_FILE`.
2. **Bảo toàn định dạng chuỗi của Mã sản phẩm:**
   - Trường `product_code` là chuỗi văn bản thuần túy.
   - Nghiêm cấm ép kiểu về số nguyên làm mất các chữ số `0` ở đầu (ví dụ: `'02AA15'`, `'07KD12'`).
3. **Chống lỗi làm tròn dấu phẩy động (Floating-point Issues):**
   - Đơn giá và thành tiền theo tiền đồng Việt Nam (VND).
   - Mọi phép tính chênh lệch thành tiền và cộng dồn được làm tròn 2 chữ số thập phân (`round(val, 2)`), trước khi hiển thị số nguyên trên giao diện người dùng.

---

## 5. HỢP ĐỒNG GIAO TIẾP GIỮA CÁC THÀNH PHẦN (SYSTEM INTERFACE CONTRACT)

```
[Google Drive .xlsx / Web Manual Upload]
                 │
                 ▼
     [Excel Parser & Normalizer]
      - Validate Header (15 cols)
      - Validate Row 2 Summary
      - Extract String SKUs (Keep leading 0s)
      - Key: (product_code, warehouse)
      - Content SHA256 Hashing
                 │
                 ▼
     [Ingestion Batch Payload]
      {
        "snapshot_metadata": {
          "full_code": "KK.CH41551.26.339000",
          "ticket_number": "339000",
          "store_code": "CH41551",
          "inventory_date": "2026-10-09",
          "shift": "Sáng" | "Chiều" | "Tối" | "Khác" | "Chưa xác định",
          "file_sha256": "...",
          "content_hash": "...",
          "total_sku_count": 432,
          "declared_quantity": 16961.0,
          "declared_total_amount": 270739477.0
        },
        "items": [
          { "stt": 1, "product_code": "02AA15", "warehouse": "Kho hàng bán", "quantity": 2.0, ... }
        ]
      }
                 │
                 ▼
     [Backend Staging & Ingestion Policy]
      - Check Existing: NEW / DUPLICATE / CONFLICT / ALREADY_IMPORTED / SOFT_DELETED
      - Atomic Commit to D1
```
