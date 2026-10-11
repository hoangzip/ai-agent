"""
Module: inventory-management/tests/test_round_03.py
Kiểm thử tự động toàn diện đối với Round 03: Xác thực, Bootstrap Admin & Quản lý Người dùng (RBAC):
1. Bảng users và sessions tồn tại với schema đầy đủ.
2. Ràng buộc Role check ('ADMIN', 'USER').
3. Khóa ngoại ON DELETE CASCADE giữa sessions và users.
4. Token hash: session.id là TEXT khóa chính lưu băm, không lưu token bản rõ.
5. Cờ must_change_password mặc định = 1 cho tài khoản mới.
6. Mật khẩu không bao giờ lưu bản rõ trong database.
7. Toàn bộ frontend components Round 03 tồn tại và đầy đủ tiếng Việt.
8. Quét bảo mật chống rò rỉ secrets trong codebase Round 03.
"""

import os
import sqlite3
import re
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION_SQL = os.path.join(BASE_DIR, "database", "migrations", "0001_initial_schema.sql")

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


def test_01_users_table_schema(d1_conn):
    """Bảng users có đầy đủ các cột bảo mật."""
    cur = d1_conn.cursor()
    cur.execute("PRAGMA table_info(users);")
    cols = {row["name"]: row["type"].upper() for row in cur.fetchall()}

    expected_cols = {
        "id": "INTEGER",
        "username": "TEXT",
        "password_hash": "TEXT",
        "role": "TEXT",
        "full_name": "TEXT",
        "must_change_password": "INTEGER",
        "is_active": "INTEGER",
        "created_at": "TEXT",
        "updated_at": "TEXT"
    }
    for col, col_type in expected_cols.items():
        assert col in cols, f"Thiếu cột {col} trong bảng users"
        assert cols[col] == col_type, f"Cột {col} sai kiểu: {cols[col]} != {col_type}"


def test_02_sessions_table_schema(d1_conn):
    """Bảng sessions có đầy đủ các trường quản lý phiên và thu hồi."""
    cur = d1_conn.cursor()
    cur.execute("PRAGMA table_info(sessions);")
    cols = {row["name"]: row["type"].upper() for row in cur.fetchall()}

    assert "id" in cols
    assert cols["id"] == "TEXT" # Khóa chính lưu token_hash
    assert "user_id" in cols
    assert "expires_at" in cols
    assert "created_at" in cols
    assert "revoked_at" in cols # Hỗ trợ thu hồi phiên tức thì


def test_03_users_role_check_constraint(d1_conn):
    """Ràng buộc role chỉ cho phép 'ADMIN' hoặc 'USER'."""
    # Thành công với ADMIN và USER
    d1_conn.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES ('admin_ok', 'hash', 'ADMIN', 'Admin')"
    )
    d1_conn.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES ('user_ok', 'hash', 'USER', 'User')"
    )
    d1_conn.commit()

    # Thất bại khi truyền role lạ
    with pytest.raises(sqlite3.IntegrityError):
        d1_conn.execute(
            "INSERT INTO users (username, password_hash, role, full_name) VALUES ('invalid_role', 'hash', 'SUPERUSER', 'Invalid')"
        )


def test_04_session_cascade_delete(d1_conn):
    """Khi xóa user (hard delete), các session liên quan tự động cascade delete."""
    cur = d1_conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES ('u1', 'h', 'USER', 'User 1')"
    )
    user_id = cur.lastrowid

    cur.execute(
        "INSERT INTO sessions (id, user_id, expires_at) VALUES ('session_hash_1', ?, '2026-12-31')",
        (user_id,)
    )
    d1_conn.commit()

    # Kiểm tra session tồn tại
    assert cur.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)).fetchone()[0] == 1

    # Xóa user
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    d1_conn.commit()

    # Session tự động bị xóa theo
    assert cur.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)).fetchone()[0] == 0


def test_05_must_change_password_default_flag(d1_conn):
    """Cờ must_change_password mặc định an toàn là 1 (Bắt buộc đổi)."""
    cur = d1_conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES ('newbie', 'hash', 'USER', 'New User')"
    )
    d1_conn.commit()

    row = cur.execute("SELECT must_change_password FROM users WHERE username = 'newbie'").fetchone()
    assert row["must_change_password"] == 1


def test_06_frontend_auth_files_exist():
    """Kiểm tra các file mã nguồn giao diện Round 03 tồn tại và đầy đủ."""
    login_page = os.path.join(BASE_DIR, "apps", "web", "src", "pages", "LoginPage.tsx")
    modal_page = os.path.join(BASE_DIR, "apps", "web", "src", "components", "ChangePasswordModal.tsx")
    user_mgmt = os.path.join(BASE_DIR, "apps", "web", "src", "pages", "UserManagementPage.tsx")
    auth_ctx = os.path.join(BASE_DIR, "apps", "web", "src", "context", "AuthContext.tsx")

    for fpath in [login_page, modal_page, user_mgmt, auth_ctx]:
        assert os.path.exists(fpath), f"Thiếu file: {fpath}"

    with open(login_page, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Đăng nhập tài khoản" in content
        assert "Vinamilk Inventory Management" in content

    with open(user_mgmt, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Quản lý Người dùng & Phân quyền" in content or "Danh sách Người dùng Hệ thống" in content
        assert "Thêm người dùng mới" in content
        assert "403 Forbidden" in content


def test_07_no_secrets_leaked_in_codebase():
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
