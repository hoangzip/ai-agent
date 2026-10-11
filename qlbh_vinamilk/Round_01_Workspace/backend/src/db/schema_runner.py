"""
Module: backend/src/db/schema_runner.py
Mục đích: Bộ thực thi migration và kiểm tra tính toàn vẹn của D1 SQLite schema trên môi trường dev/local.
Mô phỏng 100% môi trường Cloudflare D1 thông qua SQLite với Foreign Keys enabled.
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional

class D1DatabaseManager:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        # Kích hoạt ràng buộc khóa ngoại (Foreign Keys) bắt buộc trong D1
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def apply_migration_file(self, migration_sql_path: str):
        """Thực thi file SQL migration."""
        if not os.path.exists(migration_sql_path):
            raise FileNotFoundError(f"Không tìm thấy file migration: {migration_sql_path}")

        with open(migration_sql_path, "r", encoding="utf-8") as f:
            sql_content = f.read()

        # Thực thi theo script
        self.conn.executescript(sql_content)
        self.conn.commit()

    def get_table_names(self) -> List[str]:
        """Lấy danh sách các bảng người dùng trong database."""
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        return [row[0] for row in cur.fetchall()]

    def get_index_names(self) -> List[str]:
        """Lấy danh sách các index trong database."""
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';")
        return [row[0] for row in cur.fetchall()]

    def close(self):
        self.conn.close()
