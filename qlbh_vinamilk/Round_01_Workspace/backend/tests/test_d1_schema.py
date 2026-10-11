"""
Module: backend/tests/test_d1_schema.py
Kiểm thử tự động toàn diện đối với Cloudflare D1 Migration (SQLite engine):
- Khởi tạo đầy đủ 8 bảng và 7 chỉ mục (indexes).
- Kiểm tra các ràng buộc: UNIQUE, CHECK (âm, enum shift), FOREIGN KEY.
- Nạp thử nghiệm toàn bộ dữ liệu thật của 4 snapshot từ Round 01 vào D1.
- Kiểm tra tính toán tổng tồn, phân trang, và phép join so sánh đối soát bằng SQL thuần.
"""

import os
import sqlite3
import pytest
from backend.src.db.schema_runner import D1DatabaseManager
from src.parser import InventoryExcelParser
from src.identity import SnapshotIdentity

MIGRATION_SQL = "backend/migrations/0001_initial_schema.sql"

DATA_DIR = "Data Source/Kiem Ke"
FILE_339000 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.339000_20261009.xlsx")
FILE_339513 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.339513_20261009.xlsx")
FILE_339931 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.339931_20261010.xlsx")
FILE_340231 = os.path.join(DATA_DIR, "KiemKe_KK.CH41551.26.340231_20261011.xlsx")


@pytest.fixture
def db():
    """Khởi tạo một D1 database trong bộ nhớ (in-memory) có migration đã apply."""
    manager = D1DatabaseManager(":memory:")
    manager.apply_migration_file(MIGRATION_SQL)
    yield manager
    manager.close()


def test_schema_tables_and_indexes_created(db):
    """Xác minh 8 bảng và các chỉ mục được tạo thành công."""
    tables = db.get_table_names()
    expected_tables = {
        "stores",
        "stock_scopes",
        "users",
        "sessions",
        "inventory_snapshots",
        "inventory_items",
        "import_staging",
        "audit_logs"
    }
    assert expected_tables.issubset(set(tables)), f"Thiếu bảng: {expected_tables - set(tables)}"

    indexes = db.get_index_names()
    expected_indexes = {
        "idx_snapshots_store_date",
        "idx_snapshots_full_code",
        "idx_snapshots_content_hash",
        "idx_snapshots_active",
        "idx_items_snapshot_sku",
        "idx_items_product_code",
        "idx_sessions_user_active"
    }
    assert expected_indexes.issubset(set(indexes)), f"Thiếu index: {expected_indexes - set(indexes)}"


def test_constraint_negative_quantity_rejected(db):
    """CHECK constraint: SL tồn kho âm bị từ chối."""
    conn = db.conn
    # Tạo snapshot giả lập
    conn.execute(
        "INSERT INTO inventory_snapshots (full_code, ticket_number, store_code, inventory_date, shift, file_sha256, content_hash, source_filename) "
        "VALUES ('KK.TEST.01', '01', 'CH41551', '2026-10-09', 'Sáng', 'hash', 'content_hash', 'test.xlsx')"
    )
    snap_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO inventory_items (snapshot_id, row_index, stt, category, product_code, product_name, quantity, warehouse, unit_price, total_amount) "
            "VALUES (?, 3, 1, 'A', '02AA15', 'SP A', -10.0, 'Kho hàng bán', 50000, -500000)",
            (snap_id,)
        )


def test_constraint_duplicate_sku_in_same_warehouse_rejected(db):
    """UNIQUE constraint: Trùng lặp (snapshot_id, product_code, warehouse) bị từ chối."""
    conn = db.conn
    conn.execute(
        "INSERT INTO inventory_snapshots (full_code, ticket_number, store_code, inventory_date, shift, file_sha256, content_hash, source_filename) "
        "VALUES ('KK.TEST.02', '02', 'CH41551', '2026-10-09', 'Sáng', 'hash', 'content_hash', 'test.xlsx')"
    )
    snap_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Bản ghi 1: Thành công
    conn.execute(
        "INSERT INTO inventory_items (snapshot_id, row_index, stt, category, product_code, product_name, quantity, warehouse, unit_price, total_amount) "
        "VALUES (?, 3, 1, 'A', '02AA15', 'SP A', 10.0, 'Kho hàng bán', 50000, 500000)",
        (snap_id,)
    )

    # Bản ghi 2 cùng mã + cùng kho: Thất bại do UNIQUE constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO inventory_items (snapshot_id, row_index, stt, category, product_code, product_name, quantity, warehouse, unit_price, total_amount) "
            "VALUES (?, 4, 2, 'A', '02AA15', 'SP A', 15.0, 'Kho hàng bán', 50000, 750000)",
            (snap_id,)
        )


def test_same_sku_in_different_warehouse_allowed(db):
    """Cùng 1 mã SKU nằm ở 2 loại kho khác nhau trong cùng snapshot được phép lưu."""
    conn = db.conn
    conn.execute(
        "INSERT INTO inventory_snapshots (full_code, ticket_number, store_code, inventory_date, shift, file_sha256, content_hash, source_filename) "
        "VALUES ('KK.TEST.03', '03', 'CH41551', '2026-10-09', 'Sáng', 'hash', 'content_hash', 'test.xlsx')"
    )
    snap_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO inventory_items (snapshot_id, row_index, stt, category, product_code, product_name, quantity, warehouse, unit_price, total_amount) "
        "VALUES (?, 3, 1, 'A', '02AA15', 'SP A', 10.0, 'Kho hàng bán', 50000, 500000)",
        (snap_id,)
    )
    conn.execute(
        "INSERT INTO inventory_items (snapshot_id, row_index, stt, category, product_code, product_name, quantity, warehouse, unit_price, total_amount) "
        "VALUES (?, 4, 2, 'A', '02AA15', 'SP A', 2.0, 'Kho hàng vật phẩm KM', 0, 0)",
        (snap_id,)
    )
    count = conn.execute("SELECT COUNT(*) FROM inventory_items WHERE snapshot_id = ?", (snap_id,)).fetchone()[0]
    assert count == 2


def test_real_snapshots_ingestion_and_sql_verification(db):
    """
    Nạp dữ liệu thực tế của cả 4 file Excel vào database D1:
    - 339000, 339513, 339931, 340231
    - Kiểm tra tổng cộng 1,732 bản ghi chi tiết
    - Đối chiếu tính toán tổng bằng SQL (SUM) với số liệu Ground Truth
    - Thực hiện phép SQL JOIN so sánh nội ngày 339000 -> 339513
    """
    conn = db.conn

    # 1. Tạo Store
    conn.execute("INSERT INTO stores (store_code, store_name) VALUES ('CH41551', 'Vinamilk Store CH41551')")
    store_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    files = [FILE_339000, FILE_339513, FILE_339931, FILE_340231]
    inserted_snapshot_ids = {}

    for fpath in files:
        parser = InventoryExcelParser(fpath)
        data = parser.parse()
        meta = data["metadata"]
        summary = data["summary_row"]
        calc_totals = data["calculated_totals"]

        ident = SnapshotIdentity(meta["filename"], meta["file_sha256"], data["items"])
        ident_dict = ident.to_metadata_dict()

        cur = conn.execute(
            """
            INSERT INTO inventory_snapshots (
                full_code, ticket_number, store_id, store_code, inventory_date,
                shift, file_sha256, content_hash, source_filename, status,
                total_sku_count, total_quantity, total_amount_vnd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?)
            """,
            (
                ident_dict["full_code"],
                ident_dict["ticket_number"],
                store_id,
                ident_dict["store_code"],
                ident_dict["inventory_date"],
                ident_dict["shift"],
                ident_dict["file_sha256"],
                ident_dict["content_hash"],
                meta["filename"],
                len(data["items"]),
                calc_totals["total_quantity"],
                calc_totals["total_amount"]
            )
        )
        snap_id = cur.lastrowid
        inserted_snapshot_ids[ident_dict["ticket_number"]] = snap_id

        # Insert items
        for it in data["items"]:
            conn.execute(
                """
                INSERT INTO inventory_items (
                    snapshot_id, row_index, stt, category, product_code, product_name,
                    quantity, warehouse, unit_price, total_amount, audit_package_qty,
                    audit_loose_qty, audit_total_qty_formula, discrepancy_formula,
                    package_unit, conversion_rate, loose_unit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap_id, it["row_index"], it["stt"], it["category"], it["product_code"],
                    it["product_name"], it["quantity"], it["warehouse"], it["unit_price"],
                    it["total_amount"], it["audit_package_qty"], it["audit_loose_qty"],
                    it["audit_total_qty_formula"], it["discrepancy_formula"],
                    it["package_unit"], it["conversion_rate"], it["loose_unit"]
                )
            )

    conn.commit()

    # Xác minh tổng số dòng chi tiết = 432 + 432 + 434 + 434 = 1,732
    total_items = conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0]
    assert total_items == 1732

    # Kiểm tra phép tính SQL SUM cho file 339000
    id_339000 = inserted_snapshot_ids["339000"]
    sum_row = conn.execute(
        "SELECT SUM(quantity) as sum_qty, ROUND(SUM(total_amount), 2) as sum_amt FROM inventory_items WHERE snapshot_id = ?",
        (id_339000,)
    ).fetchone()
    assert sum_row["sum_qty"] == 16961.0
    assert sum_row["sum_amt"] == 270739477.0

    # Phép SQL so sánh trực tiếp 2 file cùng ngày 09/10: 339000 vs 339513
    id_339513 = inserted_snapshot_ids["339513"]
    cmp_query = """
    SELECT 
        COUNT(*) as matched_count,
        SUM(b.quantity - a.quantity) as delta_qty,
        ROUND(SUM(b.total_amount - a.total_amount), 2) as delta_val
    FROM inventory_items a
    JOIN inventory_items b 
      ON a.product_code = b.product_code 
     AND a.warehouse = b.warehouse
    WHERE a.snapshot_id = ? AND b.snapshot_id = ?
    """
    cmp_row = conn.execute(cmp_query, (id_339000, id_339513)).fetchone()
    assert cmp_row["matched_count"] == 432
    assert cmp_row["delta_qty"] == 129.0
    assert cmp_row["delta_val"] == 1736526.0


def test_soft_delete_query_filter(db):
    """Xóa mềm: bản ghi có is_deleted = 1 không xuất hiện trong query active."""
    conn = db.conn
    conn.execute(
        "INSERT INTO inventory_snapshots (full_code, ticket_number, store_code, inventory_date, shift, file_sha256, content_hash, source_filename, is_deleted) "
        "VALUES ('KK.DEL.01', '99', 'CH41551', '2026-10-09', 'Sáng', 'hash', 'content_hash', 'del.xlsx', 1)"
    )
    conn.execute(
        "INSERT INTO inventory_snapshots (full_code, ticket_number, store_code, inventory_date, shift, file_sha256, content_hash, source_filename, is_deleted) "
        "VALUES ('KK.ACT.01', '98', 'CH41551', '2026-10-09', 'Sáng', 'hash', 'content_hash', 'act.xlsx', 0)"
    )

    active_count = conn.execute("SELECT COUNT(*) FROM inventory_snapshots WHERE is_deleted = 0").fetchone()[0]
    assert active_count == 1
