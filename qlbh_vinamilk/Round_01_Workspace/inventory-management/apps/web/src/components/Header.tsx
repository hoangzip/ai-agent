import React from "react";
import { Store, Layers, User, LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";

interface HeaderProps {
  title: string;
  subtitle?: string;
  storeScope?: string;
}

export const Header: React.FC<HeaderProps> = ({ title, subtitle, storeScope }) => {
  const { currentUser, logout } = useAuth();
  const displayScope = storeScope || "Tự động (Theo đợt mới nhất)";
  const isSpecificStore = displayScope !== "Tự động (Theo đợt mới nhất)" && !displayScope.startsWith("Tự động");

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between shrink-0">
      <div>
        <h2 className="text-lg font-bold text-slate-900 tracking-tight">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
      </div>

      <div className="flex items-center space-x-3.5">
        {/* Dynamic Store / Scope Indicator */}
        <div className="flex items-center space-x-2 px-3 py-1.5 bg-slate-100 rounded-lg text-xs font-medium text-slate-700">
          <Store className="w-3.5 h-3.5 text-slate-500" />
          <span>
            {isSpecificStore ? (
              <>
                Chi nhánh: <strong className="text-slate-900">{displayScope}</strong>
              </>
            ) : (
              <>
                Phạm vi: <strong className="text-slate-900">{displayScope}</strong>
              </>
            )}
          </span>
        </div>

        {/* User Profile Badge */}
        {currentUser && (
          <div className="flex items-center space-x-2 pl-2 border-l border-slate-200">
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-xs">
                {currentUser.username.substring(0, 2).toUpperCase()}
              </div>
              <div className="hidden sm:block text-left">
                <p className="text-xs font-bold text-slate-900 leading-tight">{currentUser.full_name}</p>
                <span
                  className={`inline-block px-1.5 py-0.2 rounded text-[10px] font-semibold ${
                    currentUser.role === "ADMIN" ? "bg-purple-100 text-purple-800" : "bg-blue-100 text-blue-800"
                  }`}
                >
                  {currentUser.role === "ADMIN" ? "Quản trị viên" : "Nhân viên"}
                </span>
              </div>
            </div>

            {/* Logout button */}
            <button
              onClick={() => logout()}
              title="Đăng xuất khỏi hệ thống"
              className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors ml-1"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
};
