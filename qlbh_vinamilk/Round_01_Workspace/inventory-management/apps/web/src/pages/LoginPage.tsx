import React, { useState } from "react";
import { Package, Lock, User as UserIcon, Eye, EyeOff, AlertCircle, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !password) {
      setError("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.");
      return;
    }

    setIsLoading(true);
    try {
      const res = await login(username.trim(), password);
      if (!res.success) {
        setError(res.error || "Tên đăng nhập hoặc mật khẩu không chính xác.");
      }
    } catch (err: any) {
      setError(err?.message || "Lỗi kết nối máy chủ");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-200/80 overflow-hidden">
        {/* Brand Banner */}
        <div className="bg-gradient-to-r from-purple-700 to-indigo-800 p-8 text-white text-center relative overflow-hidden">
          <div className="absolute top-0 right-0 transform translate-x-4 -translate-y-4 opacity-10">
            <Package className="w-32 h-32" />
          </div>
          <div className="w-14 h-14 bg-white/10 backdrop-blur-md rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-inner">
            <Package className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Vinamilk Inventory Management</h1>
          <p className="text-xs text-purple-200 mt-1">Hệ thống Quản lý & Đối soát Tồn kho Cửa hàng</p>
        </div>

        {/* Login Form */}
        <div className="p-8">
          <div className="mb-6">
            <h2 className="text-lg font-bold text-slate-900">Đăng nhập tài khoản</h2>
            <p className="text-xs text-slate-500 mt-0.5">Vui lòng nhập thông tin xác thực để truy cập hệ thống</p>
          </div>

          {error && (
            <div className="mb-5 bg-rose-50 border border-rose-200 rounded-xl p-3 flex items-start space-x-2.5 text-rose-800 text-xs">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <div className="flex-1 font-medium">{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Tên đăng nhập
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <UserIcon className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  required
                  autoFocus
                  className="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-300 rounded-xl text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Mật khẩu
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••"
                  required
                  className="w-full pl-9 pr-10 py-2.5 bg-slate-50 border border-slate-300 rounded-xl text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full mt-2 py-2.5 px-4 bg-purple-700 hover:bg-purple-800 disabled:bg-purple-400 text-white text-sm font-semibold rounded-xl shadow-md shadow-purple-700/20 transition flex items-center justify-center space-x-2"
            >
              {isLoading ? (
                <span>Đang xác thực...</span>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  <span>Đăng nhập an toàn</span>
                </>
              )}
            </button>
          </form>

          {/* Security Notice */}
          <div className="mt-6 pt-5 border-t border-slate-100 text-center">
            <div className="bg-slate-50 rounded-xl p-3 text-[11px] text-slate-600 border border-slate-200/60 leading-relaxed text-left flex items-start space-x-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-slate-800 block mb-0.5">Hệ thống Doanh nghiệp Bảo mật:</span>
                <span>Chỉ người dùng được cấp thẩm quyền mới được phép đăng nhập. Mọi hoạt động xác thực đều được ghi nhận vào nhật ký kiểm toán.</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

