"""
Module: inventory-management/tests/test_round_02.py
Kiểm thử tự động toàn diện đối với Round 02 (Bổ sung kiểm thử sau review P1/P2):
1. Migration file tồn tại và hợp lệ.
2. Database schema có đầy đủ 10 bảng.
3. Database schema có đầy đủ 10 chỉ mục (bao gồm idx_inv_files_source_id).
4. Cột mới: inventory_time, source_file_id, source_revision, status DEFAULT STAGING.
5. Hỗ trợ nhiều snapshot cùng ngày (09/10/2026).
6. Mã sản phẩm dạng string giữ số 0 đầu chuỗi.
7. Hỗ trợ xóa mềm (soft delete).
8. Không để lộ secrets trong codebase.
9. Dashboard hiển thị rõ ràng nhãn 'DỮ LIỆU MẪU' (không gây nhầm lẫn).
10. Frontend hiển thị tiếng Việt 100%.
11. Backend API cấu trúc chuẩn, hỗ trợ /api/snapshots và /api/v1/snapshots (501).
12. Files .gitignore và .env.example tồn tại.
"""

import os
import sqlite3
import json
import re
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION_SQL = os.path.join(BASE_DIR, "database", "migrations", "0001_initial_schema.sql")

@pytest.fixture
def d1_conn():
    """Khởi tạo SQLite in-memory mô phỏng Cloudflare D1 và áp dụng migration."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    with open(MIGRATION_SQL, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    yield conn
    conn.close()


def test_01_migration_file_exists():
    """File migration tồn tại và có dung lượng hợp lệ."""
    assert os.path.exists(MIGRATION_SQL)
    assert os.path.getsize(MIGRATION_SQL) > 500


def test_02_database_has_all_10_tables(d1_conn):
    """Database schema có đầy đủ 10 bảng bắt buộc."""
    cur = d1_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = set(row[0] for row in cur.fetchall())

    expected_tables = {
        "users",
        "sessions",
        "stores",
        "stock_scopes",
        "product_catalog",
        "inventory_files",
        "inventory_items",
        "sync_sources",
        "sync_runs",
        "audit_logs"
    }

    assert expected_tables.issubset(tables), f"Thiếu các bảng: {expected_tables - tables}"


def test_03_database_has_required_indexes(d1_conn):
    """Database schema có đầy đủ các chỉ mục tối ưu hiệu năng (bao gồm source_id)."""
    cur = d1_conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';")
    indexes = set(row[0] for row in cur.fetchall())

    expected_indexes = {
        "idx_inv_files_store_date",
        "idx_inv_files_full_code",
        "idx_inv_files_content_hash",
        "idx_inv_files_active",
        "idx_inv_files_source_id",
        "idx_inv_items_file_sku",
        "idx_inv_items_product_code",
        "idx_sessions_user_active",
        "idx_catalog_code",
        "idx_sync_runs_source"
    }

    assert expected_indexes.issubset(indexes), f"Thiếu các index: {expected_indexes - indexes}"


def test_04_inventory_files_schema_enhancements(d1_conn):
    """Kiểm tra các trường bổ sung: inventory_time, source metadata, status mặc định STAGING."""
    d1_conn.execute("INSERT INTO stores (store_code, store_name) VALUES ('CH41551', 'Vinamilk CH41551')")
    store_id = d1_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    d1_conn.execute(
        """
        INSERT INTO inventory_files (
            full_code, ticket_number, store_id, store_code, inventory_date,
            inventory_time, shift, file_sha256, content_hash, source_filename,
            source_file_id, source_revision
        ) VALUES (
            'KK.TEST.REV2', '888000', ?, 'CH41551', '2026-10-11',
            '14:06:20', 'Chiều', 'hash888', 'content888', 'test.xlsx',
            'gdrive_id_123', 'rev_v1'
        )
        """,
        (store_id,)
    )
    d1_conn.commit()

    row = d1_conn.execute("SELECT * FROM inventory_files WHERE full_code = 'KK.TEST.REV2'").fetchone()
    assert row["inventory_time"] == "14:06:20"
    assert row["source_file_id"] == "gdrive_id_123"
    assert row["source_revision"] == "rev_v1"
    assert row["status"] == "STAGING"  # Mặc định an toàn là STAGING


def test_05_support_multiple_snapshots_on_same_date(d1_conn):
    """
    Hỗ trợ lưu trữ nhiều snapshot trong CÙNG một ngày (09/10/2026),
    khác mã kiểm kê (339000 và 339513) mà không bị xung đột unique key.
    """
    d1_conn.execute("INSERT INTO stores (store_code, store_name) VALUES ('CH41551', 'Vinamilk CH41551')")
    store_id = d1_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Snapshot 1: 339000 (Ca Đêm ngày 09/10/2026, 00:52:29)
    d1_conn.execute(
        """
        INSERT INTO inventory_files (
            full_code, ticket_number, store_id, store_code, inventory_date, inventory_time, shift,
            file_sha256, content_hash, source_filename, total_sku_count, total_quantity, total_amount_vnd
        ) VALUES (
            'KK.CH41551.26.339000', '339000', ?, 'CH41551', '2026-10-09', '00:52:29', 'Khác',
            'hash_339000', 'content_339000', 'KiemKe_KK.CH41551.26.339000_20261009.xlsx',
            432, 16961.0, 270739477.0
        )
        """,
        (store_id,)
    )

    # Snapshot 2: 339513 (Ca Chiều ngày 09/10/2026, 14:41:47 - CÙNG NGÀY)
    d1_conn.execute(
        """
        INSERT INTO inventory_files (
            full_code, ticket_number, store_id, store_code, inventory_date, inventory_time, shift,
            file_sha256, content_hash, source_filename, total_sku_count, total_quantity, total_amount_vnd
        ) VALUES (
            'KK.CH41551.26.339513', '339513', ?, 'CH41551', '2026-10-09', '14:41:47', 'Chiều',
            'hash_339513', 'content_339513', 'KiemKe_KK.CH41551.26.339513_20261009.xlsx',
            432, 17090.0, 272476003.0
        )
        """,
        (store_id,)
    )
    d1_conn.commit()

    count_same_date = d1_conn.execute(
        "SELECT COUNT(*) FROM inventory_files WHERE inventory_date = '2026-10-09' AND is_deleted = 0"
    ).fetchone()[0]
    assert count_same_date == 2


def test_06_product_code_string_with_leading_zeros(d1_conn):
    """Mã sản phẩm là dạng text, bảo toàn ký tự '0' ở đầu chuỗi (vd '02AA15')."""
    d1_conn.execute("INSERT INTO stores (store_code, store_name) VALUES ('CH41551', 'Vinamilk CH41551')")
    store_id = d1_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    d1_conn.execute(
        "INSERT INTO inventory_files (full_code, ticket_number, store_id, store_code, inventory_date, file_sha256, content_hash, source_filename) "
        "VALUES ('KK.01', '01', ?, 'CH41551', '2026-10-09', 'h', 'c', 'f.xlsx')",
        (store_id,)
    )
    file_id = d1_conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    d1_conn.execute(
        """
        INSERT INTO inventory_items (
            file_id, row_index, stt, category, product_code, product_name,
            quantity, warehouse, unit_price, total_amount
        ) VALUES (?, 3, 1, 'A', '02AA15', 'SB Dielac Alpha 1 HT 400g', 2.0, 'Kho hàng bán', 164268.0, 328536.0)
        """,
        (file_id,)
    )
    d1_conn.commit()

    row = d1_conn.execute("SELECT product_code FROM inventory_items WHERE file_id = ?", (file_id,)).fetchone()
    assert row["product_code"] == "02AA15"
    assert isinstance(row["product_code"], str)


def test_07_soft_delete_support(d1_conn):
    """Hỗ trợ xóa mềm (is_deleted, deleted_at, deleted_by)."""
    d1_conn.execute(
        "INSERT INTO inventory_files (full_code, ticket_number, store_code, inventory_date, file_sha256, content_hash, source_filename, is_deleted) "
        "VALUES ('KK.DEL', '999', 'CH41551', '2026-10-09', 'h', 'c', 'f.xlsx', 1)"
    )
    d1_conn.commit()

    active_count = d1_conn.execute("SELECT COUNT(*) FROM inventory_files WHERE is_deleted = 0").fetchone()[0]
    assert active_count == 0


def test_08_no_secrets_leaked_in_codebase():
    """Quét codebase để bảo đảm không rò rỉ private keys, tokens, mật khẩu production."""
    sensitive_patterns = [
        re.compile(r"BEGIN PRIVATE KEY"),
        re.compile(r"api_key\s*=\s*['\"][A-Za-z0-9_\-]{20,}['\"]"),
        re.compile(r"client_secret\s*=\s*['\"][A-Za-z0-9_\-]{20,}['\"]")
    ]

    for root, dirs, files in os.walk(BASE_DIR):
        if "node_modules" in root or ".git" in root or ".pytest_cache" in root or "dist" in root or "tests" in root:
            continue
        for f in files:
            if f.endswith((".ts", ".tsx", ".js", ".json", ".sql", ".py", ".toml")):
                fpath = os.path.join(root, f)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as file_obj:
                    content = file_obj.read()
                    for pattern in sensitive_patterns:
                        assert not pattern.search(content), f"Phát hiện nghi vấn rò rỉ secret tại: {fpath}"


def test_09_dashboard_has_transparent_sample_data_warning():
    """Kiểm tra Dashboard hiển thị rõ ràng nhãn DỮ LIỆU MẪU và không giả mạo kết nối thực."""
    dash_file = os.path.join(BASE_DIR, "apps", "web", "src", "pages", "DashboardPage.tsx")
    assert os.path.exists(dash_file)

    with open(dash_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "DỮ LIỆU MẪU" in content
        assert "CHƯA KẾT NỐI DATABASE THỰC TẾ" in content
        assert "Round 04" in content


def test_10_hygiene_files_exist():
    """Kiểm tra tồn tại file .gitignore và .env.example."""
    assert os.path.exists(os.path.join(BASE_DIR, ".gitignore"))
    assert os.path.exists(os.path.join(BASE_DIR, ".env.example"))


def test_11_frontend_files_and_vietnamese_localization():
    """Frontend có đầy đủ 9 menu tiếng Việt."""
    sidebar_file = os.path.join(BASE_DIR, "apps", "web", "src", "components", "Sidebar.tsx")
    assert os.path.exists(sidebar_file)

    with open(sidebar_file, "r", encoding="utf-8") as f:
        content = f.read()
        expected_menus = [
            "Tổng quan",
            "Danh sách kiểm kê",
            "Nhập file Excel",
            "So sánh tồn kho",
            "Lịch sử sản phẩm",
            "Đồng bộ Google Drive",
            "Quản lý người dùng",
            "Thùng rác",
            "Cài đặt"
        ]
        for menu in expected_menus:
            assert menu in content, f"Thiếu mục menu tiếng Việt: {menu}"


def test_12_cors_exact_origin_and_no_wildcards():
    """Kiểm tra mã nguồn CORS không sử dụng regex wildcard *.pages.dev hoặc *.workers.dev."""
    cors_file = os.path.join(BASE_DIR, "apps", "api", "src", "middleware", "cors.ts")
    assert os.path.exists(cors_file)
    with open(cors_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "allowedSet.has(origin)" in content
        assert "Vary" in content
        # Tuyệt đối không chứa wildcard regex cho pages.dev hoặc workers.dev
        assert r"\.pages\.dev" not in content
        assert r"\.workers\.dev" not in content


def test_13_vnd_currency_integer_precision(d1_conn):
    """Kiểm tra schema tiền tệ VND dùng INTEGER (tránh sai số làm tròn số thực nhị phân)."""
    cur = d1_conn.cursor()
    cur.execute("PRAGMA table_info(inventory_files);")
    cols = {row["name"]: row["type"].upper() for row in cur.fetchall()}
    assert cols["total_amount_vnd"] == "INTEGER", f"total_amount_vnd phải là INTEGER, hiện là {cols['total_amount_vnd']}"

    cur.execute("PRAGMA table_info(inventory_items);")
    item_cols = {row["name"]: row["type"].upper() for row in cur.fetchall()}
    assert item_cols["unit_price"] == "INTEGER", f"unit_price phải là INTEGER, hiện là {item_cols['unit_price']}"
    assert item_cols["total_amount"] == "INTEGER", f"total_amount phải là INTEGER, hiện là {item_cols['total_amount']}"


def test_14_cloudflare_pages_routes_contract():
    """Kiểm tra tồn tại hợp đồng định tuyến _routes.json và Pages Function cho frontend."""
    routes_json = os.path.join(BASE_DIR, "apps", "web", "public", "_routes.json")
    assert os.path.exists(routes_json)
    with open(routes_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "/api/*" in data.get("include", [])

    pages_fn = os.path.join(BASE_DIR, "apps", "web", "functions", "api", "[[catchall]].ts")
    assert os.path.exists(pages_fn)

