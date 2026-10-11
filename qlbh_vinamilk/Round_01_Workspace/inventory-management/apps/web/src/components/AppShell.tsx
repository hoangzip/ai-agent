import React, { useState, useEffect } from "react";
import { Sidebar, NavItemKey } from "./Sidebar";
import { Header } from "./Header";
import { DashboardPage } from "../pages/DashboardPage";
import { UserManagementPage } from "../pages/UserManagementPage";
import { LoginPage } from "../pages/LoginPage";
import { ChangePasswordModal } from "./ChangePasswordModal";
import { useAuth } from "../context/AuthContext";
import { SnapshotsPage } from "../pages/SnapshotsPage";
import { ImportPage } from "../pages/ImportPage";
import { ComparePage } from "../pages/ComparePage";
import { HistoryPage } from "../pages/HistoryPage";
import { SyncPage } from "../pages/SyncPage";
import {
  TrashPage,
  SettingsPage
} from "../pages/OtherPages";
import { AlertTriangle } from "lucide-react";

export const AppShell: React.FC = () => {
  const { currentUser, isLoading } = useAuth();
  const [currentTab, setCurrentTab] = useState<NavItemKey>(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab") as NavItemKey;
      const hash = window.location.hash.replace("#", "") as NavItemKey;
      if (tabParam) return tabParam;
      if (hash) return hash;
    } catch {
      // fallback
    }
    return "dashboard";
  });
  const [storeScope, setStoreScope] = useState<string>("Tự động (Theo đợt mới nhất)");
  const isAdmin = currentUser?.role === "ADMIN";

  // Lắng nghe sự kiện đồng bộ phạm vi cửa hàng cho Header (P2 Header Context)
  useEffect(() => {
    const handleStoreScopeChanged = (e: any) => {
      if (e.detail?.storeScope !== undefined) {
        setStoreScope(e.detail.storeScope);
      }
    };
    window.addEventListener("store-scope-changed", handleStoreScopeChanged);
    return () => window.removeEventListener("store-scope-changed", handleStoreScopeChanged);
  }, []);

  // Lắng nghe sự kiện điều hướng giữa các tab (Round 06)
  useEffect(() => {
    const handleNavigateTab = (e: any) => {
      if (e.detail?.tab) {
        // RBAC: Chặn điều hướng đến trang quản trị nếu không phải ADMIN
        if ((e.detail.tab === "users" || e.detail.tab === "trash") && !isAdmin) {
          setCurrentTab("dashboard");
          return;
        }
        setCurrentTab(e.detail.tab);
        if (e.detail.baseId && e.detail.targetId) {
          sessionStorage.setItem(
            "vinamilk_compare_selection",
            JSON.stringify({ baseId: e.detail.baseId, targetId: e.detail.targetId })
          );
        }
      }
    };
    window.addEventListener("navigate-tab", handleNavigateTab);
    return () => window.removeEventListener("navigate-tab", handleNavigateTab);
  }, [isAdmin]);

  // RBAC Guard chủ động: Tự động chuyển hướng về Tổng quan nếu USER cố vào trang Quản trị
  useEffect(() => {
    if (!isAdmin && (currentTab === "users" || currentTab === "trash")) {
      setCurrentTab("dashboard");
    }
  }, [isAdmin, currentTab]);

  const tabTitles: Record<NavItemKey, { title: string; subtitle: string }> = {
    dashboard: {
      title: "Tổng quan Tồn kho",
      subtitle: "Bảng điều khiển theo dõi số liệu và biến động kiểm kê"
    },
    snapshots: {
      title: "Danh sách Chứng từ Kiểm kê",
      subtitle: "Tra cứu các đợt kiểm đếm theo ngày, ca và cửa hàng"
    },
    import: {
      title: "Nhập File Excel Kiểm kê",
      subtitle: "Nạp và chuẩn hóa dữ liệu từ file Excel .xlsx 15 cột"
    },
    compare: {
      title: "So sánh Đối soát Tồn kho",
      subtitle: "Phân tích chênh lệch số lượng và thành tiền giữa hai snapshot"
    },
    history: {
      title: "Lịch sử Biến động Sản phẩm",
      subtitle: "Theo dõi chuỗi thời gian tồn kho của từng SKU"
    },
    sync: {
      title: "Đồng bộ Đám mây",
      subtitle: "Cấu hình tự động quét folder và đối soát dữ liệu đám mây"
    },
    users: {
      title: "Quản lý Người dùng & Phân quyền",
      subtitle: "Quản lý tài khoản, trạng thái khóa và phân quyền RBAC (Chỉ Quản trị viên)"
    },
    trash: {
      title: "Thùng rác & Phục hồi",
      subtitle: "Quản lý các snapshot đã xóa mềm (Chỉ Quản trị viên)"
    },
    settings: {
      title: "Cài đặt Hệ thống",
      subtitle: "Tham số kiểm kê, múi giờ và cấu hình vận hành"
    }
  };

  // Loading spinner khi kiểm tra phiên ban đầu
  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4">
        <div className="w-10 h-10 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mb-3"></div>
        <p className="text-xs text-slate-500 font-medium">Đang kiểm tra phiên làm việc...</p>
      </div>
    );
  }

  // Nếu chưa đăng nhập, hiển thị trang Đăng nhập
  if (!currentUser) {
    return <LoginPage />;
  }

  const currentInfo = tabTitles[currentTab];

  const renderAccessDenied = () => (
    <div className="bg-white rounded-xl border border-rose-200 p-8 text-center max-w-md mx-auto mt-12 shadow-sm">
      <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto mb-3">
        <AlertTriangle className="w-6 h-6" />
      </div>
      <h3 className="text-base font-bold text-slate-900 mb-1">Không có quyền truy cập</h3>
      <p className="text-xs text-slate-500 mb-4">
        Chức năng này chỉ dành riêng cho tài khoản Quản trị viên (ADMIN). Bạn đang đăng nhập với quyền Nhân viên.
      </p>
      <button
        onClick={() => setCurrentTab("dashboard")}
        className="px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition"
      >
        Quay lại Tổng quan
      </button>
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Modal Bắt buộc đổi mật khẩu lần đầu */}
      <ChangePasswordModal isOpen={currentUser.must_change_password} />

      {/* Sidebar navigation */}
      <Sidebar currentTab={currentTab} onTabChange={setCurrentTab} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header title={currentInfo.title} subtitle={currentInfo.subtitle} storeScope={storeScope} />

        <main className="flex-1 overflow-y-auto p-6">
          {currentTab === "dashboard" && <DashboardPage />}
          {currentTab === "snapshots" && <SnapshotsPage />}
          {currentTab === "import" && <ImportPage />}
          {currentTab === "compare" && <ComparePage />}
          {currentTab === "history" && <HistoryPage />}
          {currentTab === "sync" && <SyncPage />}
          {currentTab === "users" && (isAdmin ? <UserManagementPage /> : renderAccessDenied())}
          {currentTab === "trash" && (isAdmin ? <TrashPage /> : renderAccessDenied())}
          {currentTab === "settings" && <SettingsPage />}
        </main>
      </div>
    </div>
  );
};
