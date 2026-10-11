"""
Module: tests/test_baseline.py
Kiểm thử tự động bắt buộc đối với 4 file Excel thật và 3 cặp so sánh baseline.
Tuân thủ toàn bộ số liệu Ground Truth đã quy định trong Round 01 & Master Prompt.
"""

import os
import pytest
from src.parser import InventoryExcelParser
from src.comparator import InventoryComparator
from src.identity import SnapshotIdentity

DATA_DIR = "Data Source/Kiem Ke"
FILE_339000 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.339000_20261009.xlsx")
FILE_339513 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.339513_20261009.xlsx")
FILE_339931 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.339931_20261010.xlsx")
FILE_340231 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.340231_20261011.xlsx")


def test_files_exist_and_readable():
    """Xác minh sự hiện diện của đầy đủ 4 file Excel thật."""
    for f in [FILE_339000, FILE_339513, FILE_339931, FILE_340231]:
        assert os.path.exists(f), f"File không tồn tại: {f}"
        assert os.path.getsize(f) > 0, f"File rỗng: {f}"


def test_parse_339000_ground_truth():
    """Kiểm tra file 339000 (09/10/2026)."""
    parser = InventoryExcelParser(FILE_339000)
    data = parser.parse()

    assert data["metadata"]["detail_count"] == 432
    assert data["stock_counts"]["Kho hàng bán"] == 390
    assert data["stock_counts"]["Kho hàng vật phẩm KM"] == 42
    assert data["calculated_totals"]["total_quantity"] == 16961.0
    assert data["calculated_totals"]["total_amount"] == 270739477.0

    # Đối chiếu summary row dòng 2
    assert data["summary_row"]["declared_quantity"] == 16961.0
    assert data["summary_row"]["declared_total_amount"] == 270739477.0


def test_parse_339513_ground_truth():
    """Kiểm tra file 339513 (09/10/2026)."""
    parser = InventoryExcelParser(FILE_339513)
    data = parser.parse()

    assert data["metadata"]["detail_count"] == 432
    assert data["stock_counts"]["Kho hàng bán"] == 390
    assert data["stock_counts"]["Kho hàng vật phẩm KM"] == 42
    assert data["calculated_totals"]["total_quantity"] == 17090.0
    assert data["calculated_totals"]["total_amount"] == 272476003.0

    # Đối chiếu summary row dòng 2
    assert data["summary_row"]["declared_quantity"] == 17090.0
    assert data["summary_row"]["declared_total_amount"] == 272476003.0


def test_parse_339931_ground_truth():
    """Kiểm tra file 339931 (10/10/2026)."""
    parser = InventoryExcelParser(FILE_339931)
    data = parser.parse()

    assert data["metadata"]["detail_count"] == 434
    assert data["stock_counts"]["Kho hàng bán"] == 391
    assert data["stock_counts"]["Kho hàng vật phẩm KM"] == 43
    assert data["calculated_totals"]["total_quantity"] == 17147.0
    assert data["calculated_totals"]["total_amount"] == 275711737.0

    # Đối chiếu summary row dòng 2
    assert data["summary_row"]["declared_quantity"] == 17147.0
    assert data["summary_row"]["declared_total_amount"] == 275711737.0


def test_parse_340231_ground_truth():
    """Kiểm tra file 340231 (11/10/2026)."""
    parser = InventoryExcelParser(FILE_340231)
    data = parser.parse()

    assert data["metadata"]["detail_count"] == 434
    assert data["stock_counts"]["Kho hàng bán"] == 391
    assert data["stock_counts"]["Kho hàng vật phẩm KM"] == 43
    assert data["calculated_totals"]["total_quantity"] == 16972.0
    assert data["calculated_totals"]["total_amount"] == 273775891.0

    # Đối chiếu summary row dòng 2
    assert data["summary_row"]["declared_quantity"] == 16972.0
    assert data["summary_row"]["declared_total_amount"] == 273775891.0


def test_leading_zero_sku_preserved():
    """Bảo toàn số 0 ở đầu mã SKU dạng chuỗi."""
    parser = InventoryExcelParser(FILE_339000)
    data = parser.parse()
    skus = [it["product_code"] for it in data["items"]]

    # Kiểm tra các mã bắt đầu bằng số 0
    zero_prefixed = [s for s in skus if s.startswith("0")]
    assert len(zero_prefixed) > 0
    assert "02AA15" in zero_prefixed
    assert isinstance(zero_prefixed[0], str)


def test_comparison_pair_1_same_day():
    """
    Test bắt buộc: So sánh 2 file cùng ngày 09/10/2026:
    339000 -> 339513:
    Matched: 432, Tăng: 19, Giảm: 58, Không đổi: 355, Mới: 0, Không xuất hiện: 0
    ΔSL = +129, ΔGiá trị = +1,736,526 VND
    """
    snap_a = InventoryExcelParser(FILE_339000).parse()
    snap_b = InventoryExcelParser(FILE_339513).parse()
    cmp = InventoryComparator(snap_a, snap_b).compare()
    summary = cmp["summary"]

    assert summary["matched_count"] == 432
    assert summary["increased_count"] == 19
    assert summary["decreased_count"] == 58
    assert summary["unchanged_count"] == 355
    assert summary["new_count"] == 0
    assert summary["not_appeared_count"] == 0
    assert summary["total_delta_quantity"] == 129.0
    assert summary["total_delta_value"] == 1736526.0


def test_comparison_pair_2_new_skus():
    """
    Test bắt buộc: So sánh 339513 -> 339931:
    Matched: 432, Tăng: 18, Giảm: 42, Không đổi: 372
    Mới: 2 ('02AO18' ở Kho hàng bán, '9NH277' ở Kho hàng vật phẩm KM)
    ΔSL = +57, ΔGiá trị = +3,235,734 VND
    """
    snap_a = InventoryExcelParser(FILE_339513).parse()
    snap_b = InventoryExcelParser(FILE_339931).parse()
    cmp = InventoryComparator(snap_a, snap_b).compare()
    summary = cmp["summary"]

    assert summary["matched_count"] == 432
    assert summary["increased_count"] == 18
    assert summary["decreased_count"] == 42
    assert summary["unchanged_count"] == 372
    assert summary["new_count"] == 2
    assert summary["not_appeared_count"] == 0
    assert summary["total_delta_quantity"] == 57.0
    assert summary["total_delta_value"] == 3235734.0

    # Kiểm tra chính xác 2 mã SKU mới
    new_keys = set(tuple(k) for k in cmp["new_keys"])
    expected_new = {("02AO18", "Kho hàng bán"), ("9NH277", "Kho hàng vật phẩm KM")}
    assert new_keys == expected_new


def test_comparison_pair_3_and_sample_skus():
    """
    Test bắt buộc: So sánh 339931 -> 340231:
    Matched: 434, Tăng: 0, Giảm: 28, Không đổi: 406, Mới: 0, Không xuất hiện: 0
    ΔSL = -175, ΔGiá trị = -1,935,846 VND
    Kiểm tra 5 mã mẫu:
    07KD12: 113 -> 89 (-24)
    04FT32: 88 -> 67 (-21)
    07NH12: 56 -> 37 (-19)
    04EC33: 124 -> 108 (-16)
    07TR33: 94 -> 82 (-12)
    """
    snap_a = InventoryExcelParser(FILE_339931).parse()
    snap_b = InventoryExcelParser(FILE_340231).parse()
    cmp = InventoryComparator(snap_a, snap_b).compare()
    summary = cmp["summary"]

    assert summary["matched_count"] == 434
    assert summary["increased_count"] == 0
    assert summary["decreased_count"] == 28
    assert summary["unchanged_count"] == 406
    assert summary["new_count"] == 0
    assert summary["not_appeared_count"] == 0
    assert summary["total_delta_quantity"] == -175.0
    assert summary["total_delta_value"] == -1935846.0

    # 5 mã SKU mẫu
    details_map = {
        (d["product_code"], d["warehouse"]): d for d in cmp["details"]
    }
    sample_checks = {
        "07KD12": (113.0, 89.0, -24.0),
        "04FT32": (88.0, 67.0, -21.0),
        "07NH12": (56.0, 37.0, -19.0),
        "04EC33": (124.0, 108.0, -16.0),
        "07TR33": (94.0, 82.0, -12.0)
    }

    for sku, (expected_a, expected_b, expected_diff) in sample_checks.items():
        key = (sku, "Kho hàng bán")
        assert key in details_map
        d = details_map[key]
        assert d["qty_a"] == expected_a
        assert d["qty_b"] == expected_b
        assert d["diff_qty"] == expected_diff


def test_snapshot_identity_extraction():
    """Kiểm tra trích xuất metadata và định danh snapshot từ tên file thật."""
    id339000 = SnapshotIdentity("KiemKe_KK.CH41551.26.339000_20261009.xlsx")
    assert id339000.doc_prefix == "KK"
    assert id339000.store_code == "CH41551"
    assert id339000.ticket_number == "339000"
    assert id339000.inventory_date == "2026-10-09"
    assert id339000.full_code == "KK.CH41551.26.339000"
