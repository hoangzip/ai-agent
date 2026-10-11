-- ==============================================================================
-- MIGRATION: 0002_sync_concurrency_lock.sql
-- MODULE: Động cơ Đồng bộ Dữ liệu Google Drive (Round 07 Fix 02)
-- MỤC ĐÍCH: Bổ sung bảng sync_locks hỗ trợ atomic concurrency lease lock cho Cloudflare D1
-- ==============================================================================
-- LƯU Ý AN TOÀN PRODUCTION:
-- 1. File migration này CHỈ được chuẩn bị và kiểm thử trên môi trường local / test database.
-- 2. TUYỆT ĐỐI CHƯA THỰC THI TRÊN PRODUCTION CLOUDFLARE D1 KHI CHƯA CÓ PHÊ DUYỆT VĂN BẢN CỦA QUẢN TRỊ VIÊN.
-- 3. Kế hoạch Phê duyệt:
--    - Bước 1: Nghiệm thu local test và xác nhận không có race condition.
--    - Bước 2: Người dùng chấp thuận và chạy lệnh wrangler d1 migrations apply.
-- 4. Kế hoạch Rollback:
--    DROP TABLE IF EXISTS sync_locks;
-- ==============================================================================

-- 1. Bảng lưu trữ Khóa Đồng bộ Nguyên tử (Atomic Concurrency Lease Lock)
CREATE TABLE IF NOT EXISTS sync_locks (
  source_id INTEGER PRIMARY KEY,
  lock_token TEXT NOT NULL,
  run_id INTEGER,
  locked_at TEXT NOT NULL,
  lease_expires_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES sync_sources(id) ON DELETE CASCADE
);

-- 2. Bổ sung cột phân loại kết quả chi tiết cho sync_runs (SUCCESS, PARTIAL, FAILED, CONFLICT)
-- Cột này không phá vỡ CHECK constraint hiện có trên cột status
-- ROLLBACK: Cột cho phép NULL/DEFAULT nên an toàn 100% khi rollback hoặc duy trì tương thích ngược
ALTER TABLE sync_runs ADD COLUMN outcome TEXT DEFAULT 'SUCCESS';
