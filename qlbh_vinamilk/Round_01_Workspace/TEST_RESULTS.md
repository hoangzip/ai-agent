# KẾT QUẢ KIỂM THỬ TỰ ĐỘNG ROUND 01 (TEST RESULTS)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Round:** 01/10  
**Vai trò thực hiện:** QA Tester (Độc lập)  
**Thời điểm thực thi:** 11/10/2026 16:29:00 +07:00  
**Hệ điều hành / Runtime:** Darwin (macOS) / Python 3.11.0 / pytest 9.1.1  

---

## 1. TỔNG HỢP KẾT QUẢ KIỂM THỬ

- **Tổng số ca kiểm thử:** 19/19
- **Số ca ĐẠT (PASSED):** **19**
- **Số ca THẤT BẠI (FAILED):** **0**
- **Số ca BỎ QUA (SKIPPED):** **0**
- **Tỷ lệ thành công:** **100%**
- **Thời gian thực thi:** 0.58s

---

## 2. NHẬT KÝ THỰC THI THỰC TẾ (REAL EXECUTION LOG)

```
$ python3 -m pytest -v --tb=short

============================= test session starts ==============================
platform darwin -- Python 3.11.0, pytest-9.1.1, pluggy-1.6.0 -- /Library/Frameworks/Python.framework/Versions/3.11/bin/python3
cachedir: .pytest_cache
rootdir: /Users/hoangtq13/AI-agent/Gemini/qlbh_vinamilk/Round_01_Workspace
collecting ... collected 19 items

tests/test_baseline.py::test_files_exist_and_readable PASSED             [  5%]
tests/test_baseline.py::test_parse_339000_ground_truth PASSED            [ 10%]
tests/test_baseline.py::test_parse_339513_ground_truth PASSED            [ 15%]
tests/test_baseline.py::test_parse_339931_ground_truth PASSED            [ 21%]
tests/test_baseline.py::test_parse_340231_ground_truth PASSED            [ 26%]
tests/test_baseline.py::test_leading_zero_sku_preserved PASSED           [ 31%]
tests/test_baseline.py::test_comparison_pair_1_same_day PASSED           [ 36%]
tests/test_baseline.py::test_comparison_pair_2_new_skus PASSED           [ 42%]
tests/test_baseline.py::test_comparison_pair_3_and_sample_skus PASSED    [ 47%]
tests/test_baseline.py::test_snapshot_identity_extraction PASSED         [ 52%]
tests/test_edge_cases.py::test_edge_division_by_zero_and_zero_quantity PASSED [ 57%]
tests/test_edge_cases.py::test_edge_missing_and_new_sku_classification PASSED [ 63%]
tests/test_edge_cases.py::test_edge_price_changed_quantity_unchanged PASSED [ 68%]
tests/test_edge_cases.py::test_edge_same_sku_in_two_different_warehouses PASSED [ 73%]
tests/test_edge_cases.py::test_validation_error_duplicate_sku_in_same_warehouse PASSED [ 78%]
tests/test_edge_cases.py::test_validation_error_negative_quantity PASSED [ 84%]
tests/test_edge_cases.py::test_validation_error_missing_header PASSED    [ 89%]
tests/test_edge_cases.py::test_validation_error_summary_mismatch PASSED  [ 94%]
tests/test_edge_cases.py::test_identity_dedup_and_conflict_policies PASSED [100%]

=============================== warnings summary ===============================
tests/test_baseline.py::test_parse_339000_ground_truth
tests/test_baseline.py::test_parse_339513_ground_truth
tests/test_baseline.py::test_parse_339931_ground_truth
tests/test_baseline.py::test_parse_340231_ground_truth
tests/test_baseline.py::test_leading_zero_sku_preserved
tests/test_baseline.py::test_comparison_pair_1_same_day
tests/test_baseline.py::test_comparison_pair_2_new_skus
tests/test_baseline.py::test_comparison_pair_3_and_sample_skus
  /Users/hoangtq13/Library/Python/3.11/lib/python/site-packages/openpyxl/styles/stylesheet.py:237: UserWarning: Workbook contains no default style, apply openpyxl's default
    warn("Workbook contains no default style, apply openpyxl's default")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 19 passed, 8 warnings in 0.58s ========================
```

---

## 3. ĐỐI CHIẾU CHI TIẾT GROUND TRUTH MANDATORY GATE

| Hạng mục kiểm tra | Giá trị kỳ vọng | Giá trị thực tế đo được | Kết quả |
|---|---|---|:---:|
| **Snapshot 339000 (09/10)** | 432 SKU (390 bán + 42 KM), SL 16,961, Tiền 270,739,477 | 432 SKU (390 bán + 42 KM), SL 16,961.0, Tiền 270,739,477.0 | **PASS** |
| **Snapshot 339513 (09/10)** | 432 SKU (390 bán + 42 KM), SL 17,090, Tiền 272,476,003 | 432 SKU (390 bán + 42 KM), SL 17,090.0, Tiền 272,476,003.0 | **PASS** |
| **Snapshot 339931 (10/10)** | 434 SKU (391 bán + 43 KM), SL 17,147, Tiền 275,711,737 | 434 SKU (391 bán + 43 KM), SL 17,147.0, Tiền 275,711,737.0 | **PASS** |
| **Snapshot 340231 (11/10)** | 434 SKU (391 bán + 43 KM), SL 16,972, Tiền 273,775,891 | 434 SKU (391 bán + 43 KM), SL 16,972.0, Tiền 273,775,891.0 | **PASS** |
| **So sánh 339000 $\rightarrow$ 339513 (Cùng ngày)** | Khớp 432, Tăng 19, Giảm 58, $\Delta$SL +129, $\Delta$Tiền +1,736,526 | Khớp 432, Tăng 19, Giảm 58, $\Delta$SL +129.0, $\Delta$Tiền +1,736,526.0 | **PASS** |
| **So sánh 339513 $\rightarrow$ 339931** | Khớp 432, Tăng 18, Giảm 42, Mới 2, $\Delta$SL +57, $\Delta$Tiền +3,235,734 | Khớp 432, Tăng 18, Giảm 42, Mới 2, $\Delta$SL +57.0, $\Delta$Tiền +3,235,734.0 | **PASS** |
| **So sánh 339931 $\rightarrow$ 340231** | Khớp 434, Tăng 0, Giảm 28, $\Delta$SL -175, $\Delta$Tiền -1,935,846 | Khớp 434, Tăng 0, Giảm 28, $\Delta$SL -175.0, $\Delta$Tiền -1,935,846.0 | **PASS** |
| **5 mã SKU mẫu 339931 $\rightarrow$ 340231** | `07KD12` -24, `04FT32` -21, `07NH12` -19, `04EC33` -16, `07TR33` -12 | Trùng khớp 100% từng số lượng tồn và biến động | **PASS** |
| **2 SKU mới 339513 $\rightarrow$ 339931** | `02AO18` (bán), `9NH277` (KM) | Nhận diện chính xác 2 mã và đúng loại kho | **PASS** |
| **Bảo toàn số 0 đầu mã** | Chuỗi giữ nguyên `'0'` đầu | `'02AA15'`, `'02AO18'`, v.v. giữ nguyên định dạng str | **PASS** |

---

## 4. KẾT LUẬN CỦA QA TESTER

Bộ test hoàn toàn độc lập, không hardcode kết quả tính toán, chạy trực tiếp trên file Excel nguồn và fixture giả lập. Tất cả 19 ca kiểm thử đều **PASS**. Đủ điều kiện kỹ thuật để nghiệm thu bước kiểm thử.
