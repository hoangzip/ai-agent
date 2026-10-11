"""
Module: inventory-management/tests/test_round_06.py
Kiểm thử tự động đối với Round 06: Dashboard & UI + Carryover P2 (Snapshot Selector Combobox):
1. Kiểm tra sự tồn tại và tính hợp lệ của Component SnapshotCombobox.tsx
2. Kiểm chứng SnapshotCombobox:
   - Không tải tràn ngập DOM (server-side pagination, giới hạn 20 snapshot mỗi trang)
   - Lọc chỉ chọn snapshot COMPLETED và chưa xóa mềm (is_deleted = 0)
   - Tìm kiếm bất đồng bộ (full_code, ticket_number, store_code, shift, date)
   - Bảo toàn snapshot được chọn sẵn (pre-selected preservation)
3. Kiểm tra DashboardPage.tsx:
   - Đã loại bỏ hoàn toàn banner cảnh báo dữ liệu mẫu (mockup preview)
   - Kết nối số liệu thật từ API /v1/dashboard/stats
4. Kiểm tra ngôn ngữ tiếng Việt 100% trong toàn bộ UI Round 06
"""

import os
import re
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "apps", "web", "src")


def test_01_snapshot_combobox_component_exists():
    """Kiểm tra component SnapshotCombobox.tsx tồn tại và export đúng."""
    combobox_path = os.path.join(WEB_DIR, "components", "SnapshotCombobox.tsx")
    assert os.path.isfile(combobox_path), f"Thiếu component {combobox_path}"

    with open(combobox_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "export const SnapshotCombobox" in content
    # Kiểm tra server-side pagination & limit 20
    assert "limit: 20" in content or "limit:20" in content
    # Kiểm tra chỉ lọc snapshot COMPLETED
    assert 'status: "COMPLETED"' in content
    # Kiểm tra cơ chế tải thêm (handleLoadMore)
    assert "handleLoadMore" in content
    # Kiểm tra bảo toàn snapshot đã chọn sẵn (fetch riêng nếu ngoài trang 1)
    assert "api.getSnapshot(selectedId" in content


def test_02_compare_page_uses_snapshot_combobox():
    """Kiểm tra ComparePage.tsx đã thay thế hoàn toàn select cũ bằng SnapshotCombobox."""
    compare_page_path = os.path.join(WEB_DIR, "pages", "ComparePage.tsx")
    assert os.path.isfile(compare_page_path)

    with open(compare_page_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Không còn dùng getSnapshots({ limit: 100 }) cố định
    assert "limit: 100" not in content
    # Phải import và sử dụng SnapshotCombobox
    assert "SnapshotCombobox" in content
    assert "<SnapshotCombobox" in content
    # Có nút đổi chiều A/B
    assert "handleSwap" in content


def test_03_dashboard_page_connected_to_live_api():
    """Kiểm tra DashboardPage.tsx đã kết nối API thật và loại bỏ mockup preview."""
    dashboard_path = os.path.join(WEB_DIR, "pages", "DashboardPage.tsx")
    assert os.path.isfile(dashboard_path)

    with open(dashboard_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Phải gọi API dashboard stats (hỗ trợ tham số cửa hàng)
    assert "api.getDashboardStats" in content
    # Không còn cảnh báo banner mockup preview
    assert "DỮ LIỆU MẪU (PREVIEW GIAO DIỆN)" not in content
    # Có liên kết đối soát nhanh
    assert "Đối soát" in content or "Đối Soát" in content


def test_04_vietnamese_labels_and_messages_round_06():
    """Toàn bộ nhãn, thông báo và tooltip phải bằng tiếng Việt."""
    combobox_path = os.path.join(WEB_DIR, "components", "SnapshotCombobox.tsx")
    with open(combobox_path, "r", encoding="utf-8") as f:
        combobox_content = f.read()

    assert "Tìm và chọn chứng từ kiểm kê" in combobox_content
    assert "Ca Sáng" in combobox_content
    assert "Ca Chiều" in combobox_content
    assert "Ca Tối" in combobox_content
    assert "Tải thêm chứng từ" in combobox_content
    assert "Bỏ chọn" in combobox_content


def test_05_backend_dashboard_and_search_endpoints():
    """Kiểm tra backend inventory service hỗ trợ search và dashboard stats."""
    inv_service = os.path.join(BASE_DIR, "apps", "api", "src", "services", "inventoryService.ts")
    with open(inv_service, "r", encoding="utf-8") as f:
        service_content = f.read()

    assert "getDashboardStats" in service_content
    assert "filter.search" in service_content
    assert "full_code LIKE" in service_content


def test_06_dashboard_scope_isolation_backend():
    """Kiểm tra getDashboardStats trong backend cách ly nghiêm ngặt cùng cửa hàng (P1 Isolation)."""
    inv_service = os.path.join(BASE_DIR, "apps", "api", "src", "services", "inventoryService.ts")
    with open(inv_service, "r", encoding="utf-8") as f:
        service_content = f.read()

    # Kiểm tra kiểm tra cùng cửa hàng
    assert "isSameStore" in service_content
    assert "latest.store_code === previous.store_code" in service_content
    # Sắp xếp đầy đủ theo ngày và giờ
    assert "ORDER BY inventory_date DESC, COALESCE(inventory_time, '') DESC, id DESC" in service_content
    # Hỗ trợ lọc theo store_code
    assert "storeCode" in service_content


def test_07_rbac_sidebar_and_appshell_guards():
    """Kiểm tra phân quyền UI: Sidebar và AppShell guard trang Admin (users, trash)."""
    sidebar_path = os.path.join(WEB_DIR, "components", "Sidebar.tsx")
    with open(sidebar_path, "r", encoding="utf-8") as f:
        sidebar_content = f.read()

    # Sidebar phải kiểm tra quyền ADMIN
    assert "isAdmin" in sidebar_content
    assert "adminOnly" in sidebar_content

    appshell_path = os.path.join(WEB_DIR, "components", "AppShell.tsx")
    with open(appshell_path, "r", encoding="utf-8") as f:
        appshell_content = f.read()

    # AppShell phải chặn điều hướng và hiển thị access denied cho non-admin
    assert "isAdmin" in appshell_content
    assert "renderAccessDenied" in appshell_content or "Không có quyền truy cập" in appshell_content


def test_08_trash_page_placeholder_round_08():
    """Kiểm tra trang Thùng rác ghi rõ lộ trình Round 08, không tự ý tuyên bố trống dữ liệu."""
    other_pages_path = os.path.join(WEB_DIR, "pages", "OtherPages.tsx")
    with open(other_pages_path, "r", encoding="utf-8") as f:
        other_content = f.read()

    assert "Chức năng sẽ triển khai trong Round 08" in other_content
    assert "Thùng rác trống" not in other_content


def test_09_vietnamese_business_labels_in_compare_page():
    """Kiểm tra đổi toàn bộ nhãn kỹ thuật Snapshot A/B, Net Biến động sang tiếng Việt chuẩn."""
    compare_path = os.path.join(WEB_DIR, "pages", "ComparePage.tsx")
    with open(compare_path, "r", encoding="utf-8") as f:
        compare_content = f.read()

    assert "Kỳ gốc (A)" in compare_content
    assert "Kỳ đối soát (B)" in compare_content
    assert "Tổng chênh lệch tồn kho (B − A)" in compare_content
    assert "Tổng chênh lệch thành tiền (VND)" in compare_content
    assert "Net Biến động" not in compare_content


def test_10_stock_scope_isolation_fix02():
    """Kiểm tra P1 Fix 02: Stock Scope Isolation (cùng store, cùng scope_id, chặn scope -1, có scope_message)."""
    inv_service = os.path.join(BASE_DIR, "apps", "api", "src", "services", "inventoryService.ts")
    with open(inv_service, "r", encoding="utf-8") as f:
        service_content = f.read()

    # Kiểm tra kiểm tra phạm vi kho scope_id
    assert "scope_id" in service_content
    assert "isSameScope" in service_content
    assert "isValidComparison" in service_content
    assert "scope_message" in service_content
    assert "scopeStatus" in service_content
    # Chặn scope không xác định (-1 hoặc 99)
    assert "scope_id === -1" in service_content
    assert "isUnknownScope" in service_content


def test_11_header_context_and_cleanup_fix02():
    """Kiểm tra P2 Fix 02: Header động theo ngữ cảnh, gỡ mã CH41551 cứng và gỡ nhãn debug Round 03 Auth & RBAC."""
    header_path = os.path.join(WEB_DIR, "components", "Header.tsx")
    with open(header_path, "r", encoding="utf-8") as f:
        header_content = f.read()

    # Không còn nhãn kỹ thuật Round 03 Auth & RBAC
    assert "Round 03 Auth & RBAC" not in header_content
    # Không còn viết cứng CH41551
    assert "Chi nhánh: <strong className=\"text-slate-900\">CH41551</strong>" not in header_content
    # Nhận prop storeScope
    assert "storeScope" in header_content

