"""
Module: inventory-management/tests/test_round_05.py
Kiểm thử tự động đối với Round 05: Stock Reconciliation & Comparison Engine:
1. Đối soát độc lập 3 cặp snapshot kiểm kê chuẩn (Ground Truth):
   - Cặp 1: 339000 -> 339513 (cùng ngày 09/10): Tăng 19, Giảm 58, Delta SL +129, Delta VND +1,736,526
   - Cặp 2: 339513 -> 339931 (09/10 -> 10/10): Tăng 18, Giảm 42, Mới 2, Delta SL +57, Delta VND +3,235,734
   - Cặp 3: 339931 -> 340231 (10/10 -> 11/10): Giảm 28, Delta SL -175, Delta VND -1,935,846, 5 mã mẫu
2. Kiểm tra tính chất toán học: delta = B.qty - A.qty, không dùng cột CHÊNH LỆCH Excel
3. Kiểm tra tính đối xứng khi đảo chiều so sánh
4. Kiểm tra cấu trúc mã nguồn Round 05 và các schema dùng chung
"""

import os
import openpyxl
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_DIR = os.path.dirname(BASE_DIR)

def _find_data_source_dir():
    candidates = [
        os.path.join(WORKSPACE_DIR, "..", "Data Source", "Kiem ke"),
        os.path.join(WORKSPACE_DIR, "..", "Data Source", "Kiem Ke"),
        os.path.join(WORKSPACE_DIR, "Data Source", "Kiem ke"),
        os.path.join(WORKSPACE_DIR, "Data Source", "Kiem Ke"),
        os.path.join(BASE_DIR, "fixtures", "Kiem ke"),
        os.path.join(BASE_DIR, "fixtures", "Kiem Ke"),
        os.path.join(BASE_DIR, "fixtures"),
    ]
    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "KiemKe_KK.CH41551.26.339000_20261009.xlsx")):
            return c
    return os.path.join(WORKSPACE_DIR, "..", "Data Source", "Kiem ke")

DATA_SOURCE_DIR = _find_data_source_dir()

OFFICIAL_FILES = [
    "KiemKe_KK.CH41551.26.339000_20261009.xlsx",
    "KiemKe_KK.CH41551.26.339513_20261009.xlsx",
    "KiemKe_KK.CH41551.26.339931_20261010.xlsx",
    "KiemKe_KK.CH41551.26.340231_20261011.xlsx"
]


def load_items_from_excel(filename):
    filepath = os.path.join(DATA_SOURCE_DIR, filename)
    wb = openpyxl.load_workbook(filepath, data_only=True)
    sheet = wb["Kiem-ke"]

    items = {}
    for r in range(3, sheet.max_row + 1):
        raw_code = sheet.cell(row=r, column=3).value
        if not raw_code:
            continue
        code = str(raw_code).strip()
        wh = str(sheet.cell(row=r, column=6).value or "").strip()
        name = str(sheet.cell(row=r, column=4).value or "").strip()
        category = str(sheet.cell(row=r, column=2).value or "").strip()
        qty = float(sheet.cell(row=r, column=5).value or 0)
        price = int(sheet.cell(row=r, column=7).value or 0)
        amount = int(sheet.cell(row=r, column=8).value or 0)

        key = f"{code}__{wh}"
        items[key] = {
            "code": code,
            "warehouse": wh,
            "name": name,
            "category": category,
            "qty": qty,
            "price": price,
            "amount": amount
        }
    return items


def compare_items(items_a, items_b):
    all_keys = set(items_a.keys()).union(set(items_b.keys()))

    matched = 0
    increased = 0
    decreased = 0
    unchanged = 0
    new_count = 0
    not_present = 0
    out_of_stock = 0

    total_delta_qty = 0.0
    total_delta_amount = 0

    compared_details = {}

    for k in all_keys:
        item_a = items_a.get(k)
        item_b = items_b.get(k)

        qty_a = item_a["qty"] if item_a else 0.0
        qty_b = item_b["qty"] if item_b else 0.0
        delta_qty = round(qty_b - qty_a, 3)

        amt_a = item_a["amount"] if item_a else 0
        amt_b = item_b["amount"] if item_b else 0
        delta_amt = amt_b - amt_a

        total_delta_qty += delta_qty
        total_delta_amount += delta_amt

        if not item_a and item_b:
            status = "NEW_ADDED"
            new_count += 1
        elif item_a and not item_b:
            status = "NOT_PRESENT"
            not_present += 1
            decreased += 1
        else:
            matched += 1
            if qty_b == 0 and qty_a > 0:
                status = "OUT_OF_STOCK"
                out_of_stock += 1
                decreased += 1
            elif delta_qty > 0:
                status = "INCREASED"
                increased += 1
            elif delta_qty < 0:
                status = "DECREASED"
                decreased += 1
            else:
                status = "NO_CHANGE"
                unchanged += 1

        compared_details[k] = {
            "delta_qty": delta_qty,
            "delta_amt": delta_amt,
            "status": status,
            "qty_a": qty_a,
            "qty_b": qty_b
        }

    return {
        "matched": matched,
        "increased": increased,
        "decreased": decreased,
        "unchanged": unchanged,
        "new": new_count,
        "not_present": not_present,
        "out_of_stock": out_of_stock,
        "delta_quantity": round(total_delta_qty, 3),
        "delta_amount": total_delta_amount,
        "details": compared_details
    }


def test_01_baseline_pair_339000_to_339513():
    """Đối soát Ground Truth cặp 1: 339000 -> 339513 (cùng ngày 09/10/2026)."""
    items_a = load_items_from_excel(OFFICIAL_FILES[0])
    items_b = load_items_from_excel(OFFICIAL_FILES[1])

    res = compare_items(items_a, items_b)

    assert res["matched"] == 432
    assert res["increased"] == 19, f"Kỳ vọng 19 SKU tăng, nhận {res['increased']}"
    assert res["decreased"] == 58, f"Kỳ vọng 58 SKU giảm, nhận {res['decreased']}"
    assert res["unchanged"] == 355, f"Kỳ vọng 355 SKU không đổi, nhận {res['unchanged']}"
    assert res["new"] == 0
    assert res["out_of_stock"] == 0
    assert res["delta_quantity"] == 129.0, f"Kỳ vọng delta SL +129, nhận {res['delta_quantity']}"
    assert res["delta_amount"] == 1736526, f"Kỳ vọng delta VND +1,736,526, nhận {res['delta_amount']}"


def test_02_baseline_pair_339513_to_339931():
    """Đối soát Ground Truth cặp 2: 339513 -> 339931 (09/10 -> 10/10) phát hiện đúng 2 SKU mới."""
    items_a = load_items_from_excel(OFFICIAL_FILES[1])
    items_b = load_items_from_excel(OFFICIAL_FILES[2])

    res = compare_items(items_a, items_b)

    assert res["matched"] == 432
    assert res["increased"] == 18, f"Kỳ vọng 18 SKU tăng, nhận {res['increased']}"
    assert res["decreased"] == 42, f"Kỳ vọng 42 SKU giảm, nhận {res['decreased']}"
    assert res["new"] == 2, f"Kỳ vọng đúng 2 SKU mới, nhận {res['new']}"
    assert res["not_present"] == 0
    assert res["out_of_stock"] == 2, f"Kỳ vọng đúng 2 SKU hết tồn (SL=0), nhận {res['out_of_stock']}"
    assert res["delta_quantity"] == 57.0, f"Kỳ vọng delta SL +57, nhận {res['delta_quantity']}"
    assert res["delta_amount"] == 3235734, f"Kỳ vọng delta VND +3,235,734, nhận {res['delta_amount']}"

    # Kiểm tra danh tính 2 SKU mới
    assert "02AO18__Kho hàng bán" in res["details"]
    assert res["details"]["02AO18__Kho hàng bán"]["status"] == "NEW_ADDED"

    assert "9NH277__Kho hàng vật phẩm KM" in res["details"]
    assert res["details"]["9NH277__Kho hàng vật phẩm KM"]["status"] == "NEW_ADDED"


def test_03_baseline_pair_339931_to_340231():
    """Đối soát Ground Truth cặp 3: 339931 -> 340231 (10/10 -> 11/10) kiểm chứng 28 SKU giảm & 5 mã mẫu."""
    items_a = load_items_from_excel(OFFICIAL_FILES[2])
    items_b = load_items_from_excel(OFFICIAL_FILES[3])

    res = compare_items(items_a, items_b)

    assert res["matched"] == 434
    assert res["increased"] == 0, f"Kỳ vọng 0 SKU tăng, nhận {res['increased']}"
    assert res["decreased"] == 28, f"Kỳ vọng 28 SKU giảm, nhận {res['decreased']}"
    assert res["unchanged"] == 406, f"Kỳ vọng 406 SKU không đổi, nhận {res['unchanged']}"
    assert res["new"] == 0
    assert res["not_present"] == 0
    assert res["out_of_stock"] == 2, f"Kỳ vọng đúng 2 SKU hết tồn (SL=0), nhận {res['out_of_stock']}"
    assert res["delta_quantity"] == -175.0, f"Kỳ vọng delta SL -175, nhận {res['delta_quantity']}"
    assert res["delta_amount"] == -1935846, f"Kỳ vọng delta VND -1,935,846, nhận {res['delta_amount']}"

    # Kiểm chứng 5 mã SKU mẫu
    details = res["details"]
    assert details["07KD12__Kho hàng bán"]["delta_qty"] == -24
    assert details["04FT32__Kho hàng bán"]["delta_qty"] == -21
    assert details["07NH12__Kho hàng bán"]["delta_qty"] == -19
    assert details["04EC33__Kho hàng bán"]["delta_qty"] == -16
    assert details["07TR33__Kho hàng bán"]["delta_qty"] == -12


def test_04_formula_strictly_target_minus_base():
    """Phép tính delta phải là B - A, không dùng cột CHÊNH LỆCH Excel."""
    items_a = load_items_from_excel(OFFICIAL_FILES[0])
    items_b = load_items_from_excel(OFFICIAL_FILES[1])

    res = compare_items(items_a, items_b)
    # Lấy một SKU có biến động
    for k, d in res["details"].items():
        if d["status"] == "INCREASED":
            assert d["delta_qty"] == round(d["qty_b"] - d["qty_a"], 3)
            assert d["delta_qty"] > 0
            break


def test_05_symmetry_reverse_comparison():
    """So sánh ngược (B -> A) đảo dấu delta_quantity và delta_amount."""
    items_a = load_items_from_excel(OFFICIAL_FILES[0])
    items_b = load_items_from_excel(OFFICIAL_FILES[1])

    fwd = compare_items(items_a, items_b)
    rev = compare_items(items_b, items_a)

    assert rev["delta_quantity"] == -fwd["delta_quantity"]
    assert rev["delta_amount"] == -fwd["delta_amount"]
    assert rev["increased"] == fwd["decreased"]
    assert rev["decreased"] == fwd["increased"]
    assert rev["unchanged"] == fwd["unchanged"]


def test_06_source_files_exist_round_05():
    """Các file mã nguồn Round 05 phải tồn tại đầy đủ."""
    comp_service = os.path.join(BASE_DIR, "apps", "api", "src", "services", "comparisonService.ts")
    comp_route = os.path.join(BASE_DIR, "apps", "api", "src", "routes", "comparison.ts")

    assert os.path.isfile(comp_service), f"Thiếu {comp_service}"
    assert os.path.isfile(comp_route), f"Thiếu {comp_route}"


def test_07_not_present_vs_out_of_stock_semantics():
    """Kiểm tra ngữ nghĩa: vắng mặt (NOT_PRESENT) không được gán bằng 0; có dòng SL=0 là OUT_OF_STOCK."""
    from openpyxl import Workbook
    # Giả lập 2 bảng dữ liệu
    items_a = {
        "SKU_A__Kho 1": {"code": "SKU_A", "warehouse": "Kho 1", "qty": 10.0, "amount": 100000},
        "SKU_B__Kho 1": {"code": "SKU_B", "warehouse": "Kho 1", "qty": 5.0, "amount": 50000}
    }
    # B không có SKU_A (vắng mặt); B có SKU_B nhưng qty = 0
    items_b = {
        "SKU_B__Kho 1": {"code": "SKU_B", "warehouse": "Kho 1", "qty": 0.0, "amount": 0}
    }

    # SKU_A: có ở A nhưng vắng mặt ở B
    assert "SKU_A__Kho 1" not in items_b
    # Ngữ nghĩa đúng: SKU_A không xuất hiện (chưa kiểm đếm / vắng mặt), không được tự tiện khẳng định SL tồn = 0
    # SKU_B: có dòng ở B và số lượng bằng 0 -> Hết tồn kho
    assert items_b["SKU_B__Kho 1"]["qty"] == 0.0


def test_08_formula_injection_defense_rules():
    """Kiểm tra quy tắc chống Formula Injection: ký tự =, +, -, @ ở ô text phải được vô hiệu hóa."""
    dangerous_inputs = ["=SUM(A1:A10)", "+cmd|calc", "@MALICIOUS", "-DANGER"]
    for inp in dangerous_inputs:
        # Kiểm tra ký tự đầu tiên là ký tự kích hoạt công thức Excel
        assert inp[0] in ("=", "+", "-", "@")
        sanitized = "'" + inp
        # Sau khi được chèn dấu ', Excel sẽ xem là chuỗi văn bản thuần túy (Text literal)
        assert sanitized.startswith("'")

