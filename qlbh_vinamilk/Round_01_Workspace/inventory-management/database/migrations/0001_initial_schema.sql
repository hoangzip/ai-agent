-- ====================================================================
-- MIGRATION: 0001_initial_schema.sql
-- DỰ ÁN: Inventory Management – Stock Reconciliation Web App (Vinamilk)
-- GIAI ĐOẠN: Round 02/10 – Project Foundation, Database & API (Revision 2 - Fix Review)
-- CƠ SỞ DỮ LIỆU: Cloudflare D1 (SQLite Engine)
-- ====================================================================

-- 1. Bảng Cửa hàng (stores)
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_code TEXT UNIQUE NOT NULL,             -- e.g. 'CH41551'
    store_name TEXT NOT NULL,
    address TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 2. Bảng Phạm vi kho (stock_scopes)
CREATE TABLE IF NOT EXISTS stock_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_code TEXT UNIQUE NOT NULL,             -- e.g. 'MAIN_STORE', 'PROMO'
    scope_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 3. Bảng Người dùng (users)
-- Mật khẩu lưu dưới dạng hash an toàn (argon2id/bcrypt), không lưu bản rõ.
-- Mật khẩu tạm thời '123456' phải đổi ngay lần đầu đăng nhập (must_change_password = 1).
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'USER')),
    full_name TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 4. Bảng Phiên làm việc (sessions)
-- Lưu ý bảo mật: id lưu trữ token_hash (SHA-256 / HMAC băm của session token),
-- KHÔNG lưu token bí mật bản rõ trong cơ sở dữ liệu.
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                         -- token_hash chuỗi băm 64 ký tự hex
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    revoked_at TEXT
);

-- 5. Bảng Danh mục sản phẩm (product_catalog)
-- Mã sản phẩm bảo toàn dạng chuỗi text (giữ số 0 đầu chuỗi).
CREATE TABLE IF NOT EXISTS product_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code TEXT UNIQUE NOT NULL,           -- e.g. '02AA15', '02AO18'
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    package_unit TEXT,
    conversion_rate REAL DEFAULT 1.0,
    loose_unit TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 6. Bảng Chứng từ kiểm kê / Snapshot (inventory_files)
-- Hỗ trợ nhiều snapshot trong cùng một ngày (vd: 339000 và 339513 cùng ngày 09/10/2026).
-- Định danh bằng full_code duy nhất, không dùng ngày làm unique key.
-- Trạng thái mặc định an toàn: STAGING (chỉ chuyển COMPLETED sau khi validate thành công ở Round 04).
CREATE TABLE IF NOT EXISTS inventory_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_code TEXT UNIQUE NOT NULL,             -- e.g. 'KK.CH41551.26.339000'
    ticket_number TEXT NOT NULL,                -- e.g. '339000'
    store_id INTEGER REFERENCES stores(id),
    store_code TEXT NOT NULL,                   -- e.g. 'CH41551'
    scope_id INTEGER REFERENCES stock_scopes(id),
    inventory_date TEXT NOT NULL,               -- 'YYYY-MM-DD'
    inventory_time TEXT,                        -- 'HH:mm:ss' (thời điểm xuất cụ thể trong ca)
    shift TEXT NOT NULL DEFAULT 'Chưa xác định' CHECK(shift IN ('Sáng', 'Chiều', 'Tối', 'Khác', 'Chưa xác định')),
    file_sha256 TEXT NOT NULL,                  -- Băm nhị phân file gốc
    content_hash TEXT NOT NULL,                 -- Băm dữ liệu sản phẩm chuẩn hóa (chống duplicate khi re-save)
    source_filename TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'MANUAL_UPLOAD' CHECK(source_type IN ('MANUAL_UPLOAD', 'GDRIVE_SYNC')),
    source_file_id TEXT,                        -- ID file trên Google Drive (phục vụ idempotency Round 07)
    source_revision TEXT,                       -- Revision ID của Google Drive
    status TEXT NOT NULL DEFAULT 'STAGING' CHECK(status IN ('STAGING', 'COMPLETED', 'FAILED', 'CONFLICT')),
    total_sku_count INTEGER NOT NULL DEFAULT 0,
    total_quantity REAL NOT NULL DEFAULT 0,     -- Tổng SL tồn (khớp với số liệu Summary Dòng 2)
    total_amount_vnd INTEGER NOT NULL DEFAULT 0, -- Tổng giá trị VND (INTEGER, đơn vị Đồng nguyên bản, tránh sai số số thực nhị phân)
    is_deleted INTEGER NOT NULL DEFAULT 0,      -- Hỗ trợ xóa mềm (Soft delete)
    deleted_at TEXT,
    deleted_by INTEGER REFERENCES users(id),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 7. Bảng Chi tiết sản phẩm trong chứng từ (inventory_items)
-- Khóa tự nhiên: (file_id, product_code, warehouse).
-- total_amount: lưu giá trị tính toán làm tròn 2 chữ số thập phân (= ROUND(quantity * unit_price, 2)).
CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES inventory_files(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,                 -- Dòng thực tế trong file Excel (3..N)
    stt INTEGER NOT NULL,                       -- Cột 1: STT
    category TEXT NOT NULL,                     -- Cột 2: NGÀNH HÀNG
    product_code TEXT NOT NULL,                 -- Cột 3: MÃ SẢN PHẨM (Text, giữ số 0 đầu)
    product_name TEXT NOT NULL,                 -- Cột 4: TÊN SẢN PHẨM
    quantity REAL NOT NULL CHECK(quantity >= 0),-- Cột 5: SL TỒN KHO (số dư sổ sách dùng so sánh, >= 0)
    warehouse TEXT NOT NULL,                    -- Cột 6: LOẠI KHO ('Kho hàng bán', 'Kho hàng vật phẩm KM')
    unit_price INTEGER NOT NULL CHECK(unit_price >= 0), -- Cột 7: GIÁ (SAU VAT) (VND nguyên, INTEGER)
    total_amount INTEGER NOT NULL CHECK(total_amount >= 0), -- Cột 8: THÀNH TIỀN (VND nguyên, INTEGER)
    audit_package_qty REAL DEFAULT 0,           -- Cột 9: SL PACKAGE KIỂM KÊ
    audit_loose_qty REAL DEFAULT 0,             -- Cột 10: SL LẺ KIỂM KÊ
    audit_total_qty_formula TEXT,               -- Cột 11: TỔNG SL KIỂM KÊ (=I*N+J)
    discrepancy_formula TEXT,                   -- Cột 12: CHÊNH LỆCH (=K-E)
    package_unit TEXT,                          -- Cột 13: ĐVT PACKAGE
    conversion_rate REAL DEFAULT 1.0 CHECK(conversion_rate > 0), -- Cột 14: QUY ĐỔI (> 0)
    loose_unit TEXT,                            -- Cột 15: ĐVT LẺ
    
    -- Khóa duy nhất đảm bảo mỗi SKU trong 1 loại kho của snapshot chỉ xuất hiện đúng 1 lần
    UNIQUE(file_id, product_code, warehouse)
);

-- 8. Bảng Cấu hình nguồn đồng bộ (sync_sources)
-- Chuẩn bị cho Google Drive Sync (Round 07). Folder ID: 1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk
CREATE TABLE IF NOT EXISTS sync_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL DEFAULT 'GOOGLE_DRIVE',
    folder_id TEXT NOT NULL,
    folder_name TEXT NOT NULL DEFAULT 'Kiem ke hang hoa',
    is_active INTEGER NOT NULL DEFAULT 1,
    sync_interval_minutes INTEGER DEFAULT 60,
    last_sync_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 9. Bảng Nhật ký các đợt đồng bộ (sync_runs)
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sync_sources(id),
    triggered_by TEXT NOT NULL CHECK(triggered_by IN ('SCHEDULED', 'MANUAL')),
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    files_detected INTEGER DEFAULT 0,
    files_imported INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    files_conflict INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    finished_at TEXT
);

-- 10. Bảng Nhật ký kiểm toán thao tác người dùng (audit_logs)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,                       -- e.g. 'IMPORT_EXCEL', 'SOFT_DELETE', 'RESTORE'
    target_type TEXT NOT NULL,                  -- e.g. 'INVENTORY_FILE', 'USER'
    target_id TEXT,
    details TEXT,                               -- JSON metadata
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- ====================================================================
-- CHỈ MỤC HIỆU NĂNG (INDEXES)
-- ====================================================================
CREATE INDEX IF NOT EXISTS idx_inv_files_store_date 
ON inventory_files(store_code, inventory_date);

CREATE INDEX IF NOT EXISTS idx_inv_files_full_code 
ON inventory_files(full_code);

CREATE INDEX IF NOT EXISTS idx_inv_files_content_hash 
ON inventory_files(content_hash);

CREATE INDEX IF NOT EXISTS idx_inv_files_active 
ON inventory_files(is_deleted, inventory_date DESC);

CREATE INDEX IF NOT EXISTS idx_inv_files_source_id 
ON inventory_files(source_file_id);

CREATE INDEX IF NOT EXISTS idx_inv_items_file_sku 
ON inventory_items(file_id, product_code, warehouse);

CREATE INDEX IF NOT EXISTS idx_inv_items_product_code 
ON inventory_items(product_code);

CREATE INDEX IF NOT EXISTS idx_sessions_user_active 
ON sessions(user_id, expires_at);

CREATE INDEX IF NOT EXISTS idx_catalog_code 
ON product_catalog(product_code);

CREATE INDEX IF NOT EXISTS idx_sync_runs_source 
ON sync_runs(source_id, started_at DESC);

-- ====================================================================
-- NGUYÊN TẮC AN TOÀN DATABASE:
-- Tuyệt đối không tự ý chạy các câu lệnh biến đổi dữ liệu production.
-- Dữ liệu mẫu (seed data) bên dưới mặc định được COMMENT để bảo đảm an toàn.
-- ====================================================================

-- INSERT INTO stores (store_code, store_name, address) 
-- VALUES ('CH41551', 'Vinamilk Store CH41551', 'Chi nhánh phân phối chuẩn');

-- INSERT INTO stock_scopes (scope_code, scope_name) 
-- VALUES ('MAIN_STORE', 'Kho cửa hàng chính');

-- INSERT INTO sync_sources (provider, folder_id, folder_name) 
-- VALUES ('GOOGLE_DRIVE', '1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk', 'Kiem ke hang hoa');
