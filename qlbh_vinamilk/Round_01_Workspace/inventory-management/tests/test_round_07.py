"""
Module: inventory-management/tests/test_round_07.py
Kiểm thử tự động đối với Round 07: Google Drive Auto-Sync Engine:
1. Kiến trúc Dual-Driver (LiveGoogleDriveDriver + SimulationGoogleDriveDriver):
   - Không giả mạo kết nối live khi thiếu credentials (tuân thủ mục 10 Master Prompt).
   - Hỗ trợ folder ID chuẩn 1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk.
2. Dịch vụ điều phối Đồng bộ (syncService.ts):
   - Đảm bảo nguồn sync_sources.
   - Idempotency & chống nạp trùng lặp.
   - Ghi nhận lịch sử chi tiết vào sync_runs.
3. API Endpoints (routes/sync.ts):
   - GET /api/v1/sync/status
   - GET /api/v1/sync/runs
   - POST /api/v1/sync/trigger
4. Giao diện Người dùng (SyncPage.tsx):
   - Hiển thị thông tin Thư mục Drive và Driver Mode (Mô phỏng vs Trực tiếp).
   - Nút kích hoạt đồng bộ thủ công ("Đồng bộ ngay").
   - 4 Thẻ chỉ số KPI (Tổng đợt chạy, Thành công, File đã nạp, File bỏ qua).
   - Bảng lịch sử các đợt đồng bộ với trạng thái trực quan.
5. Tích hợp Điều hướng & Client API (AppShell.tsx, api/client.ts).
"""

import os
import re
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(BASE_DIR, "apps", "api", "src")
WEB_DIR = os.path.join(BASE_DIR, "apps", "web", "src")
SCHEMA_FILE = os.path.join(BASE_DIR, "database", "migrations", "0001_initial_schema.sql")

GDRIVE_FOLDER_ID = "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk"


def test_01_google_drive_service_dual_driver():
    """Kiểm tra googleDriveService.ts cài đặt đầy đủ kiến trúc Dual-Driver."""
    svc_path = os.path.join(API_DIR, "services", "googleDriveService.ts")
    assert os.path.isfile(svc_path), f"Thiếu file {svc_path}"

    with open(svc_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "interface GoogleDriveDriver" in content
    assert "class LiveGoogleDriveDriver implements GoogleDriveDriver" in content
    assert "class SimulationGoogleDriveDriver implements GoogleDriveDriver" in content
    assert 'getMode(): "LIVE"' in content
    assert 'getMode(): "SIMULATION"' in content
    assert "getGoogleDriveDriver" in content
    assert "setGoogleDriveDriver" in content

    # Tuân thủ Master Prompt: Không fake live connection
    assert "Chưa cấu hình Google Service Account credentials" in content


def test_02_sync_service_idempotency_and_runs():
    """Kiểm tra syncService.ts quản lý nguồn, kiểm tra trùng lặp và ghi nhận sync_runs."""
    sync_svc_path = os.path.join(API_DIR, "services", "syncService.ts")
    assert os.path.isfile(sync_svc_path), f"Thiếu file {sync_svc_path}"

    with open(sync_svc_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert GDRIVE_FOLDER_ID in content
    assert "ensureDefaultSyncSource" in content
    assert "getSyncStatus" in content
    assert "getSyncRuns" in content
    assert "triggerSync" in content

    # Kiểm tra cơ chế Idempotency
    assert "source_file_id" in content
    assert "files_skipped" in content
    assert "files_imported" in content
    assert "sync_runs" in content
    assert "sync_sources" in content


def test_03_sync_routes_and_api_index():
    """Kiểm tra các endpoint đồng bộ trong routes/sync.ts và định tuyến index.ts."""
    routes_path = os.path.join(API_DIR, "routes", "sync.ts")
    index_path = os.path.join(API_DIR, "index.ts")
    assert os.path.isfile(routes_path)
    assert os.path.isfile(index_path)

    with open(routes_path, "r", encoding="utf-8") as f:
        route_content = f.read()

    assert "handleGetSyncStatus" in route_content
    assert "handleGetSyncRuns" in route_content
    assert "handleTriggerSync" in route_content

    with open(index_path, "r", encoding="utf-8") as f:
        index_content = f.read()

    assert "/api/v1/sync/status" in index_content
    assert "/api/v1/sync/runs" in index_content
    assert "/api/v1/sync/trigger" in index_content


def test_04_web_sync_page_component():
    """Kiểm tra giao diện SyncPage.tsx đáp ứng đầy đủ yêu cầu Round 07."""
    sync_page_path = os.path.join(WEB_DIR, "pages", "SyncPage.tsx")
    assert os.path.isfile(sync_page_path), f"Thiếu component {sync_page_path}"

    with open(sync_page_path, "r", encoding="utf-8") as f:
        page_content = f.read()

    # Kiểm tra hiển thị Folder ID
    assert GDRIVE_FOLDER_ID in page_content

    # Kiểm tra hiển thị Driver Mode rõ ràng
    assert "SIMULATION" in page_content
    assert "Mô phỏng" in page_content

    # Kiểm tra nút đồng bộ thủ công
    assert "Đồng bộ ngay" in page_content or "triggerSync" in page_content

    # Kiểm tra các thẻ KPI
    assert re.search(r"tổng đợt đồng bộ", page_content, re.IGNORECASE) is not None
    assert "File Đã Nạp Mới" in page_content or "File đã nạp" in page_content
    assert "File Bỏ qua (Trùng lặp)" in page_content or "Bỏ qua" in page_content
    assert "Tỷ lệ Thành công" in page_content

    # Kiểm tra bảng lịch sử
    assert "Nhật ký Lịch sử Đồng bộ" in page_content or "Lịch sử Đồng bộ" in page_content


def test_05_web_api_client_and_app_navigation():
    """Kiểm tra API Client và Menu điều hướng tích hợp trang Sync."""
    client_path = os.path.join(WEB_DIR, "api", "client.ts")
    appshell_path = os.path.join(WEB_DIR, "components", "AppShell.tsx")
    assert os.path.isfile(client_path)
    assert os.path.isfile(appshell_path)

    with open(client_path, "r", encoding="utf-8") as f:
        client_content = f.read()

    assert "getSyncStatus" in client_content
    assert "getSyncRuns" in client_content
    assert "triggerSync" in client_content

    with open(appshell_path, "r", encoding="utf-8") as f:
        appshell_content = f.read()

    assert "SyncPage" in appshell_content
    assert "Đồng bộ Drive" in appshell_content or "sync" in appshell_content


def test_06_database_schema_compatibility():
    """Kiểm tra cơ sở dữ liệu đã có sẵn bảng sync_sources, sync_runs mà không cần thay đổi schema."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema = f.read()

    assert "CREATE TABLE IF NOT EXISTS sync_sources" in schema
    assert "CREATE TABLE IF NOT EXISTS sync_runs" in schema
    assert "source_type TEXT NOT NULL DEFAULT 'MANUAL_UPLOAD'" in schema
    assert "source_file_id TEXT" in schema
    assert "source_revision TEXT" in schema


def test_07_fix01_scheduler_and_crons():
    """P1-01: Kiểm tra cấu hình Scheduler thực tế (Cloudflare Cron, Apps Script, Worker scheduled handler)."""
    wrangler_path = os.path.join(BASE_DIR, "apps", "api", "wrangler.toml")
    index_path = os.path.join(API_DIR, "index.ts")
    gas_path = os.path.join(BASE_DIR, "google-apps-script", "Code.gs")

    assert os.path.isfile(wrangler_path)
    assert os.path.isfile(index_path)
    assert os.path.isfile(gas_path)

    with open(wrangler_path, "r", encoding="utf-8") as f:
        wrangler = f.read()
    assert "crons" in wrangler
    assert '0 * * * *' in wrangler

    with open(index_path, "r", encoding="utf-8") as f:
        idx = f.read()
    assert "scheduled(" in idx
    assert "handleScheduledSync" in idx

    with open(gas_path, "r", encoding="utf-8") as f:
        gas = f.read()
    assert "setupHourlyTrigger" in gas
    assert "runScheduledSync" in gas


def test_08_fix01_revision_conflict_and_concurrency_lock():
    """P1-02 & P2-03: Kiểm tra cơ chế chống chạy chồng nguyên tử (Atomic Lock) và phát hiện CONFLICT khi file bị sửa trên Drive."""
    sync_svc_path = os.path.join(API_DIR, "services", "syncService.ts")
    with open(sync_svc_path, "r", encoding="utf-8") as f:
        content = f.read()

    # P1-02 & P2-03: Concurrency lock nguyên tử (Fix 02 atomic lease)
    assert "SYNC_ALREADY_RUNNING" in content
    assert "acquireSyncLock" in content or "sync_locks" in content

    # P1-02: Revision conflict
    assert "filesConflict" in content
    assert "isSameRevision" in content
    assert "Phát hiện xung đột phiên bản" in content


def test_09_fix01_pagination_and_native_sheets():
    """P2-01 & P2-04: Kiểm tra hỗ trợ phân trang nextPageToken và export Google Sheets native."""
    gdrive_svc_path = os.path.join(API_DIR, "services", "googleDriveService.ts")
    with open(gdrive_svc_path, "r", encoding="utf-8") as f:
        content = f.read()

    # P2-01: Phân trang
    assert "nextPageToken" in content
    assert "maxPages" in content

    # P2-04: Google Sheets native
    assert "application/vnd.google-apps.spreadsheet" in content
    assert "export?mimeType=" in content
    assert "isSheetNative" in content


def test_10_fix01_verify_connection_blocked_for_live():
    """P1-03 & P2-08: Kiểm tra phương thức verifyConnection và trạng thái BLOCKED_FOR_LIVE."""
    gdrive_svc_path = os.path.join(API_DIR, "services", "googleDriveService.ts")
    sync_svc_path = os.path.join(API_DIR, "services", "syncService.ts")

    with open(gdrive_svc_path, "r", encoding="utf-8") as f:
        gd_content = f.read()
    with open(sync_svc_path, "r", encoding="utf-8") as f:
        sync_content = f.read()

    assert "verifyConnection" in gd_content
    assert "BLOCKED_FOR_LIVE" in sync_content
    assert "LIVE_ACTIVE" in sync_content


def test_11_fix02_fail_closed_webhook_security():
    """P1-01: Kiểm tra fail-closed webhook, loại bỏ BOOTSTRAP_TOKEN fallback và đọc secret từ Script Properties."""
    sync_route_path = os.path.join(API_DIR, "routes", "sync.ts")
    gas_path = os.path.join(BASE_DIR, "google-apps-script", "Code.gs")

    with open(sync_route_path, "r", encoding="utf-8") as f:
        route_code = f.read()
    with open(gas_path, "r", encoding="utf-8") as f:
        gas_code = f.read()

    # Fail closed: Bắt buộc SYNC_WEBHOOK_SECRET, tuyệt đối không fallback sang BOOTSTRAP_TOKEN hoặc hardcode
    assert "UNCONFIGURED_WEBHOOK_SECRET" in route_code
    assert "UNAUTHORIZED_CRON" in route_code
    assert "INVALID_WEBHOOK_SECRET" in route_code
    assert "FORBIDDEN_ORIGIN" in route_code
    assert "env.BOOTSTRAP_TOKEN" not in route_code
    assert "BOOTSTRAP_TOKEN ||" not in route_code
    assert "vinamilk-cron-secret" not in route_code

    # Google Apps Script: Đọc từ Script Properties
    assert "PropertiesService.getScriptProperties()" in gas_code
    assert "vinamilk-cron-secret" not in gas_code


def test_12_fix02_atomic_lock_migration():
    """P1-02: Kiểm tra file migration local/test 0002_sync_concurrency_lock.sql chuẩn bị bảng sync_locks."""
    mig_path = os.path.join(BASE_DIR, "database", "migrations", "0002_sync_concurrency_lock.sql")
    assert os.path.exists(mig_path), "File migration 0002 phải tồn tại"
    with open(mig_path, "r", encoding="utf-8") as f:
        mig_sql = f.read()

    assert "CREATE TABLE IF NOT EXISTS sync_locks" in mig_sql
    assert "PRIMARY KEY" in mig_sql
    assert "expires_at" in mig_sql
    assert "outcome" in mig_sql



def test_13_fix02_live_auth_service_account_jwt():
    """P1-03: Kiểm tra cơ chế ký Service Account JWT RS256 và refresh token tự động."""
    gd_svc_path = os.path.join(API_DIR, "services", "googleDriveService.ts")
    with open(gd_svc_path, "r", encoding="utf-8") as f:
        gd_code = f.read()

    assert "createServiceAccountSignedJwt" in gd_code
    assert "fetchServiceAccountAccessToken" in gd_code
    assert "RS256" in gd_code
    assert "oauth2.googleapis.com/token" in gd_code
    assert "BLOCKED_FOR_LIVE" in gd_code


def test_14_fix02_pagination_limit_and_partial_outcome():
    """P2-01 & P2-02: Kiểm tra giới hạn phân trang an toàn và lưu trữ trạng thái outcome PARTIAL."""
    gd_svc_path = os.path.join(API_DIR, "services", "googleDriveService.ts")
    sync_svc_path = os.path.join(API_DIR, "services", "syncService.ts")

    with open(gd_svc_path, "r", encoding="utf-8") as f:
        gd_code = f.read()
    with open(sync_svc_path, "r", encoding="utf-8") as f:
        sync_code = f.read()

    # P2-02: Pagination limit an toàn
    assert "Vượt quá giới hạn phân trang an toàn" in gd_code

    # P2-01: Partial outcome
    assert "PARTIAL" in sync_code
    assert "outcome" in sync_code


