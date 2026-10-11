import React from "react";
import {
  LayoutDashboard,
  ClipboardList,
  FileSpreadsheet,
  GitCompare,
  History,
  RefreshCw,
  Users,
  Trash2,
  Settings,
  Package
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

export type NavItemKey =
  | "dashboard"
  | "snapshots"
  | "import"
  | "compare"
  | "history"
  | "sync"
  | "users"
  | "trash"
  | "settings";

interface SidebarProps {
  currentTab: NavItemKey;
  onTabChange: (tab: NavItemKey) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onTabChange }) => {
  const { currentUser } = useAuth();
  const isAdmin = currentUser?.role === "ADMIN";

  const allNavItems = [
    { key: "dashboard" as NavItemKey, label: "Tổng quan", icon: LayoutDashboard },
    { key: "snapshots" as NavItemKey, label: "Danh sách kiểm kê", icon: ClipboardList },
    { key: "import" as NavItemKey, label: "Nhập file Excel", icon: FileSpreadsheet },
    { key: "compare" as NavItemKey, label: "So sánh tồn kho", icon: GitCompare },
    { key: "history" as NavItemKey, label: "Lịch sử sản phẩm", icon: History },
    { key: "sync" as NavItemKey, label: "Đồng bộ Google Drive", icon: RefreshCw },
    { key: "users" as NavItemKey, label: "Quản lý người dùng", icon: Users, badge: "Admin", adminOnly: true },
    { key: "trash" as NavItemKey, label: "Thùng rác", icon: Trash2, badge: "Admin", adminOnly: true },
    { key: "settings" as NavItemKey, label: "Cài đặt", icon: Settings },
  ];

  // RBAC Guard: Người dùng thường (USER) không hiển thị Quản lý người dùng và Thùng rác
  const navItems = allNavItems.filter((item) => !item.adminOnly || isAdmin);

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col h-screen shrink-0 select-none">
      {/* Brand Header */}
      <div className="p-5 border-b border-slate-100 flex items-center space-x-3">
        <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center text-white shadow-md shadow-primary/20">
          <Package className="w-6 h-6" />
        </div>
        <div>
          <h1 className="font-bold text-base text-slate-900 tracking-tight leading-none">Vinamilk</h1>
          <p className="text-xs text-slate-500 font-medium mt-1">Đối Soát Tồn Kho</p>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.key;
          return (
            <button
              key={item.key}
              onClick={() => onTabChange(item.key)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                isActive
                  ? "bg-primary text-white shadow-sm shadow-primary/25"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-100/80"
              }`}
            >
              <div className="flex items-center space-x-3">
                <Icon className={`w-4 h-4 ${isActive ? "text-white" : "text-slate-500"}`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span
                  className={`text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded ${
                    isActive ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* User profile footer */}
      <div className="p-3 border-t border-slate-100 bg-slate-50/50">
        <div className="flex items-center space-x-3 px-2 py-2">
          <div className="w-8 h-8 rounded-full bg-primary/10 text-primary font-bold text-xs flex items-center justify-center border border-primary/20">
            {isAdmin ? "AD" : "NV"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-slate-900 truncate">
              {currentUser?.full_name || (isAdmin ? "Quản trị viên" : "Nhân viên kiểm kê")}
            </p>
            <p className="text-[11px] text-slate-500 truncate">
              {isAdmin ? "Quản trị viên" : "Nhân viên"} • @{currentUser?.username || "user"}
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
};
