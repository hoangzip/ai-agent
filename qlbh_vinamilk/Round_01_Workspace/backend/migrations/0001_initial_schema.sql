-- ====================================================================
-- MIGRATION: 0001_initial_schema.sql
-- DỰ ÁN: Quản lý & Đối soát Tồn kho (Vinamilk)
-- NỀN TẢNG: Cloudflare D1 (SQLite Database)
-- PHIÊN BẢN CONTRACT: Round 01 Data Contract & Snapshot Identity
-- ====================================================================

-- Bảng 1: Cửa hàng (Stores)
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_code TEXT UNIQUE NOT NULL,            -- e.g. 'CH41551'
    store_name TEXT NOT NULL,
    address TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Bảng 2: Phạm vi kho (Stock Scopes)
CREATE TABLE IF NOT EXISTS stock_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_code TEXT UNIQUE NOT NULL,            -- e.g. 'MAIN_STORE', 'EXP_PROMO'
    scope_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Bảng 3: Người dùng & Phân quyền (Users & RBAC)
-- Tuân thủ: Mật khẩu băm (bcrypt/argon2), không lưu mật khẩu bản rõ.
-- Tài khoản mặc định ban đầu admin/123456 phải được kích hoạt an toàn qua script dev bootstrap.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN', 'USER')),
    full_name TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 1, -- Bắt buộc đổi pass lần đầu
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Bảng 4: Phiên làm việc (Sessions)
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,                        -- Token UUID ngẫu nhiên bảo mật
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    revoked_at TEXT                             -- Dùng khi logout hoặc Admin khóa tài khoản
);

-- Bảng 5: Metadata Snapshot Kiểm kê (Inventory Snapshots)
-- Tuân thủ: Định danh đa cấp (full_code, ticket_number, store_code, inventory_date, shift)
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_code TEXT UNIQUE NOT NULL,            -- e.g. 'KK.CH41551.26.339000'
    ticket_number TEXT NOT NULL,               -- e.g. '339000'
    store_id INTEGER REFERENCES stores(id),
    store_code TEXT NOT NULL,                  -- e.g. 'CH41551'
    inventory_date TEXT NOT NULL,              -- 'YYYY-MM-DD'
    shift TEXT NOT NULL DEFAULT 'Chưa xác định' CHECK(shift IN ('Sáng', 'Chiều', 'Tối', 'Khác', 'Chưa xác định')),
    file_sha256 TEXT NOT NULL,                 -- Checksum băm file nhị phân
    content_hash TEXT NOT NULL,                -- Checksum băm dữ liệu sản phẩm đã chuẩn hóa
    source_filename TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'MANUAL_UPLOAD' CHECK(source_type IN ('MANUAL_UPLOAD', 'GDRIVE_SYNC')),
    status TEXT NOT NULL DEFAULT 'COMPLETED' CHECK(status IN ('STAGING', 'COMPLETED', 'FAILED', 'CONFLICT')),
    total_sku_count INTEGER NOT NULL DEFAULT 0,
    total_quantity REAL NOT NULL DEFAULT 0,    -- Tổng SL tồn (khớp với dòng 2 Excel)
    total_amount_vnd REAL NOT NULL DEFAULT 0,  -- Tổng thành tiền VND (khớp dòng 2 Excel)
    is_deleted INTEGER NOT NULL DEFAULT 0,     -- Xóa mềm: 0=active, 1=deleted
    deleted_at TEXT,
    deleted_by INTEGER REFERENCES users(id),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Bảng 6: Chi tiết Sản phẩm Kiểm kê (Inventory Items)
-- Tuân thủ Data Contract 15 cột, khóa tự nhiên (snapshot_id, product_code, warehouse)
CREATE TABLE IF NOT EXISTS inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL REFERENCES inventory_snapshots(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,                -- Dòng trong Excel (3..N)
    stt INTEGER NOT NULL,                      -- Cột 1: STT
    category TEXT NOT NULL,                    -- Cột 2: NGÀNH HÀNG
    product_code TEXT NOT NULL,                -- Cột 3: MÃ SẢN PHẨM (Text, giữ số 0 đầu)
    product_name TEXT NOT NULL,                -- Cột 4: TÊN SẢN PHẨM
    quantity REAL NOT NULL CHECK(quantity >= 0),-- Cột 5: SL TỒN KHO (>= 0)
    warehouse TEXT NOT NULL,                   -- Cột 6: LOẠI KHO ('Kho hàng bán' / 'Kho hàng vật phẩm KM')
    unit_price REAL NOT NULL CHECK(unit_price >= 0), -- Cột 7: GIÁ (SAU VAT)
    total_amount REAL NOT NULL CHECK(total_amount >= 0), -- Cột 8: THÀNH TIỀN
    audit_package_qty REAL DEFAULT 0,          -- Cột 9: SL PACKAGE KIỂM KÊ
    audit_loose_qty REAL DEFAULT 0,            -- Cột 10: SL LẺ KIỂM KÊ
    audit_total_qty_formula TEXT,              -- Cột 11: TỔNG SL KIỂM KÊ (=I*N+J)
    discrepancy_formula TEXT,                  -- Cột 12: CHÊNH LỆCH (=K-E)
    package_unit TEXT,                         -- Cột 13: ĐVT PACKAGE
    conversion_rate REAL DEFAULT 1.0 CHECK(conversion_rate > 0), -- Cột 14: QUY ĐỔI (> 0)
    loose_unit TEXT,                           -- Cột 15: ĐVT LẺ
    
    -- Khóa ràng buộc tính duy nhất cho mỗi SKU trong 1 loại kho của snapshot
    UNIQUE(snapshot_id, product_code, warehouse)
);

-- Bảng 7: Hàng đợi Staging / Batch Ingestion (Import Staging)
CREATE TABLE IF NOT EXISTS import_staging (
    id TEXT PRIMARY KEY,                       -- UUID của job nạp
    filename TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'PROCESSING', 'VALIDATED', 'FAILED', 'COMMITTED')),
    total_rows INTEGER DEFAULT 0,
    valid_rows INTEGER DEFAULT 0,
    error_log TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Bảng 8: Nhật ký kiểm toán thao tác (Audit Logs)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,                      -- e.g. 'IMPORT_EXCEL', 'SOFT_DELETE_SNAPSHOT', 'RESTORE_SNAPSHOT'
    target_type TEXT NOT NULL,                 -- e.g. 'SNAPSHOT', 'USER'
    target_id TEXT,
    details TEXT,                              -- Dữ liệu JSON mô tả chi tiết biến động
    ip_address TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- ====================================================================
-- CHỈ MỤC HIỆU NĂNG (INDEXES)
-- Thiết kế tối ưu cho Cloudflare D1 free tier, ngăn ngừa quét bảng toàn bộ
-- ====================================================================

-- Tìm kiếm snapshot theo cửa hàng và ngày
CREATE INDEX IF NOT EXISTS idx_snapshots_store_date 
ON inventory_snapshots(store_code, inventory_date);

-- Tìm kiếm nhanh theo mã kiểm kê
CREATE INDEX IF NOT EXISTS idx_snapshots_full_code 
ON inventory_snapshots(full_code);

-- Tìm kiếm theo băm nội dung để chống trùng lặp (Dedup)
CREATE INDEX IF NOT EXISTS idx_snapshots_content_hash 
ON inventory_snapshots(content_hash);

-- Lọc snapshot chưa xóa (dùng cho danh sách active và dashboard)
CREATE INDEX IF NOT EXISTS idx_snapshots_active 
ON inventory_snapshots(is_deleted, inventory_date DESC);

-- Khóa so sánh nhanh items theo snapshot và SKU
CREATE INDEX IF NOT EXISTS idx_items_snapshot_sku 
ON inventory_items(snapshot_id, product_code, warehouse);

-- Tìm kiếm lịch sử của một mã sản phẩm qua các snapshot
CREATE INDEX IF NOT EXISTS idx_items_product_code 
ON inventory_items(product_code);

-- Tra cứu phiên đăng nhập còn hiệu lực
CREATE INDEX IF NOT EXISTS idx_sessions_user_active 
ON sessions(user_id, expires_at);

-- ====================================================================
-- GHI CHÚ BẢO MẬT & DỮ LIỆU SEED KIỂM THỬ:
-- Toàn bộ lệnh INSERT dưới đây mặc định được COMMENT để đảm bảo không làm
-- biến đổi dữ liệu ngoài kiểm soát.
-- Để nạp dữ liệu mẫu ban đầu trong môi trường dev test, mở comment khối dưới:
-- ====================================================================

-- INSERT INTO stores (store_code, store_name, address) 
-- VALUES ('CH41551', 'Vinamilk Store CH41551', 'Chi nhánh phân phối mẫu');

-- INSERT INTO stock_scopes (scope_code, scope_name) 
-- VALUES ('MAIN_STORE', 'Kho cửa hàng chính');
