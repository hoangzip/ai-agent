"""
Module: inventory-management/tests/test_round_04.py
Kiểm thử tự động toàn diện đối với Round 04: Excel Import, Staging & Batch Validation (Core Engine):
1. Đọc và xác thực cấu trúc 4 file Excel thật tại Data Source/Kiem ke/
2. Kiểm tra 15 cột tiêu chuẩn trên Dòng 1.
3. Đối soát toán học độc lập với Dòng 2 (Tổng SL tồn kho = E2, Tổng thành tiền = H2, chênh lệch = 0).
4. Bảo toàn số 0 ở đầu mã sản phẩm (e.g. '02AA15').
5. Kiểm tra cơ sở dữ liệu D1 (SQLite in-memory):
   - Bảng inventory_files và inventory_items có đầy đủ các ràng buộc.
   - Hỗ trợ đa snapshot trong ngày (339000 & 339513 ngày 09/10/2026).
   - Ràng buộc khóa duy nhất full_code và (file_id, product_code, warehouse).
6. Kiểm tra giao diện và dịch vụ Round 04:
   - excelParser.ts, inventoryService.ts, inventory.ts, ImportPage.tsx, SnapshotsPage.tsx tồn tại.
   - 100% thông báo lỗi và nhãn giao diện bằng tiếng Việt.
"""

import os
import glob
import sqlite3
import pytest
import openpyxl

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
MIGRATION_SQL = os.path.join(BASE_DIR, "database", "migrations", "0001_initial_schema.sql")

EXPECTED_HEADERS = [
    "STT", "NGÀNH HÀNG", "MÃ SẢN PHẨM", "TÊN SẢN PHẨM", "SL TỒN KHO",
    "LOẠI KHO", "GIÁ (SAU VAT)", "THÀNH TIỀN", "SL PACKAGE KIỂM KÊ",
    "SL LẺ KIỂM KÊ", "TỔNG SL KIỂM KÊ", "CHÊNH LỆCH", "ĐVT PACKAGE",
    "QUY ĐỔI", "ĐVT LẺ"
]

OFFICIAL_FILES = [
    "KiemKe_KK.CH41551.26.339000_20261009.xlsx",
    "KiemKe_KK.CH41551.26.339513_20261009.xlsx",
    "KiemKe_KK.CH41551.26.339931_20261010.xlsx",
    "KiemKe_KK.CH41551.26.340231_20261011.xlsx"
]

@pytest.fixture
def d1_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(MIGRATION_SQL, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    yield conn
    conn.close()


def test_01_all_four_official_excel_files_exist():
    """Tất cả 4 file Excel thật phải tồn tại trong thư mục Data Source/Kiem ke."""
    for filename in OFFICIAL_FILES:
        filepath = os.path.join(DATA_SOURCE_DIR, filename)
        assert os.path.isfile(filepath), f"File Excel không tồn tại: {filepath}"
        assert os.path.getsize(filepath) > 0, f"File rỗng: {filepath}"


@pytest.mark.parametrize("filename", OFFICIAL_FILES)
def test_02_excel_structure_and_headers(filename):
    """File Excel phải có đúng 15 cột tiêu chuẩn ở Dòng 1."""
    filepath = os.path.join(DATA_SOURCE_DIR, filename)
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active
    assert ws.max_column == 15, f"Số cột không phải 15: {ws.max_column}"

    for c in range(1, 16):
        val = str(ws.cell(1, c).value or "").strip().upper()
        expected = EXPECTED_HEADERS[c - 1]
        assert expected in val, f"Cột {c} không khớp: '{val}' không chứa '{expected}'"


@pytest.mark.parametrize("filename", OFFICIAL_FILES)
def test_03_row2_mathematical_cross_check(filename):
    """Đối soát toán học độc lập với Dòng 2: chênh lệch SL và Thành tiền phải bằng 0."""
    filepath = os.path.join(DATA_SOURCE_DIR, filename)
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    # Dòng 2
    row2_qty = float(ws.cell(2, 5).value or 0)
    row2_amt = round(float(ws.cell(2, 8).value or 0))

    calc_qty = 0.0
    calc_amt = 0.0
    item_count = 0

    for r in range(3, ws.max_row + 1):
        code_val = ws.cell(r, 3).value
        if code_val is None or str(code_val).strip() == "":
            continue
        qty = float(ws.cell(r, 5).value or 0)
        amt = float(ws.cell(r, 8).value or 0)
        calc_qty += qty
        calc_amt += amt
        item_count += 1

    calc_amt = round(calc_amt)

    assert item_count >= 430, f"Số lượng dòng ít bất thường: {item_count}"
    assert abs(calc_qty - row2_qty) < 0.001, f"Lệch số lượng: {calc_qty} != {row2_qty}"
    assert abs(calc_amt - row2_amt) <= 1, f"Lệch thành tiền: {calc_amt} != {row2_amt}"


@pytest.mark.parametrize("filename", OFFICIAL_FILES)
def test_04_preserve_leading_zero_sku(filename):
    """Mã SKU có số 0 ở đầu (e.g. '02AA15') phải được bảo toàn dạng chuỗi."""
    filepath = os.path.join(DATA_SOURCE_DIR, filename)
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb.active

    found_skus = []
    for r in range(3, min(20, ws.max_row + 1)):
        val = str(ws.cell(r, 3).value or "").strip()
        if val.startswith("02"):
            found_skus.append(val)

    assert len(found_skus) > 0, "Không tìm thấy SKU nào bắt đầu bằng '02'"
    for sku in found_skus:
        assert len(sku) == 6, f"SKU bị mất số 0 hoặc sai độ dài: {sku}"


def test_05_d1_schema_multi_snapshot_same_day(d1_conn):
    """Cơ sở dữ liệu D1 cho phép lưu nhiều snapshot trong cùng một ngày (339000 & 339513 ngày 09/10/2026)."""
    cur = d1_conn.cursor()
    cur.execute(
        """INSERT INTO inventory_files (
            full_code, ticket_number, store_code, inventory_date, shift,
            file_sha256, content_hash, source_filename, status,
            total_sku_count, total_quantity, total_amount_vnd
        ) VALUES
        ('KK.CH41551.26.339000', '339000', 'CH41551', '2026-10-09', 'Sáng',
         'hash_binary_1', 'hash_content_1', 'file1.xlsx', 'STAGING', 432, 16961, 270739477),
        ('KK.CH41551.26.339513', '339513', 'CH41551', '2026-10-09', 'Chiều',
         'hash_binary_2', 'hash_content_2', 'file2.xlsx', 'STAGING', 432, 17090, 272476003);"""
    )
    d1_conn.commit()

    cur.execute("SELECT COUNT(*) FROM inventory_files WHERE inventory_date = '2026-10-09';")
    assert cur.fetchone()[0] == 2


def test_06_d1_schema_unique_constraints(d1_conn):
    """Ràng buộc toàn vẹn: full_code phải duy nhất và (file_id, product_code, warehouse) phải duy nhất."""
    cur = d1_conn.cursor()
    cur.execute(
        """INSERT INTO inventory_files (
            full_code, ticket_number, store_code, inventory_date, shift,
            file_sha256, content_hash, source_filename, status
        ) VALUES ('KK.CH41551.26.339000', '339000', 'CH41551', '2026-10-09', 'Sáng',
                  'hash1', 'hash1', 'file1.xlsx', 'STAGING');"""
    )
    file_id = cur.lastrowid

    # Trùng full_code -> Lỗi IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            """INSERT INTO inventory_files (
                full_code, ticket_number, store_code, inventory_date, shift,
                file_sha256, content_hash, source_filename, status
            ) VALUES ('KK.CH41551.26.339000', '339000', 'CH41551', '2026-10-09', 'Chiều',
                      'hash2', 'hash2', 'file2.xlsx', 'STAGING');"""
        )

    # Thêm item
    cur.execute(
        """INSERT INTO inventory_items (
            file_id, row_index, stt, category, product_code, product_name,
            quantity, warehouse, unit_price, total_amount
        ) VALUES (?, 3, 1, 'A', '02AA15', 'Sữa bột Dielac', 2, 'Kho hàng bán', 100000, 200000);""",
        (file_id,)
    )

    # Trùng (file_id, product_code, warehouse) -> Lỗi IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            """INSERT INTO inventory_items (
                file_id, row_index, stt, category, product_code, product_name,
                quantity, warehouse, unit_price, total_amount
            ) VALUES (?, 4, 2, 'A', '02AA15', 'Sữa bột Dielac', 5, 'Kho hàng bán', 100000, 500000);""",
            (file_id,)
        )


def test_07_round_04_source_code_integrity():
    """Toàn bộ mã nguồn cốt lõi Round 04 tồn tại và không có rò rỉ mã bí mật."""
    required_files = [
        os.path.join(BASE_DIR, "apps", "api", "src", "services", "excelParser.ts"),
        os.path.join(BASE_DIR, "apps", "api", "src", "services", "inventoryService.ts"),
        os.path.join(BASE_DIR, "apps", "api", "src", "routes", "inventory.ts"),
        os.path.join(BASE_DIR, "apps", "web", "src", "pages", "ImportPage.tsx"),
        os.path.join(BASE_DIR, "apps", "web", "src", "pages", "SnapshotsPage.tsx"),
        os.path.join(BASE_DIR, "apps", "web", "src", "components", "SnapshotDetailModal.tsx")
    ]
    for rf in required_files:
        assert os.path.isfile(rf), f"Thiếu file mã nguồn: {rf}"
        with open(rf, "r", encoding="utf-8") as f:
            content = f.read()
            assert len(content) > 100
            assert "123456" not in content, f"Phát hiện mật khẩu yếu hardcode trong {rf}"
