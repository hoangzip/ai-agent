import React, { useState } from "react";
import { KeyRound, AlertTriangle, CheckCircle2, Lock } from "lucide-react";
import { useAuth } from "../context/AuthContext";

interface ChangePasswordModalProps {
  isOpen: boolean;
  onSuccess?: () => void;
}

export const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({ isOpen, onSuccess }) => {
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!currentPassword || !newPassword || !confirmPassword) {
      setError("Vui lòng điền đầy đủ tất cả các trường.");
      return;
    }

    if (newPassword.length < 8) {
      setError("Mật khẩu mới phải có tối thiểu 8 ký tự.");
      return;
    }

    const commonBlacklist = ["123456", "12345678", "123456789", "password", "password123", "admin123", "qwerty", "admin", "vinamilk"];
    if (commonBlacklist.includes(newPassword.toLowerCase())) {
      setError("Mật khẩu mới nằm trong danh sách mật khẩu yếu, không an toàn. Vui lòng chọn mật khẩu phức tạp hơn.");
      return;
    }

    if (newPassword === currentPassword) {
      setError("Mật khẩu mới phải khác với mật khẩu hiện tại.");
      return;
    }


    if (newPassword !== confirmPassword) {
      setError("Xác nhận mật khẩu mới không khớp.");
      return;
    }

    setIsLoading(true);
    try {
      const res = await changePassword(currentPassword, newPassword);
      if (res.success) {
        setSuccess("Đổi mật khẩu thành công! Bạn có thể sử dụng hệ thống bình thường.");
        setTimeout(() => {
          if (onSuccess) onSuccess();
        }, 1200);
      } else {
        setError(res.error || "Không thể đổi mật khẩu.");
      }
    } catch (err: any) {
      setError(err?.message || "Lỗi kết nối");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-y-0 inset-x-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header Banner */}
        <div className="bg-amber-500 p-6 text-white text-center relative">
          <div className="w-12 h-12 bg-white/20 rounded-2xl flex items-center justify-center mx-auto mb-2.5 backdrop-blur-xs">
            <KeyRound className="w-6 h-6 text-white" />
          </div>
          <h3 className="text-base font-bold">Bắt buộc Đổi Mật khẩu Lần đầu</h3>
          <p className="text-xs text-amber-100 mt-1">
            Tài khoản đang sử dụng mật khẩu tạm thời. Vui lòng thiết lập mật khẩu mới để tiếp tục.
          </p>
        </div>

        <div className="p-6">
          {error && (
            <div className="mb-4 bg-rose-50 border border-rose-200 rounded-xl p-3 flex items-start space-x-2.5 text-rose-800 text-xs font-medium">
              <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="mb-4 bg-emerald-50 border border-emerald-200 rounded-xl p-3 flex items-start space-x-2.5 text-emerald-800 text-xs font-medium">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <span>{success}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mật khẩu hiện tại (Mật khẩu tạm)
              </label>
              <div className="relative">
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="Nhập mật khẩu hiện tại"
                  required
                  autoFocus
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mật khẩu mới (Tối thiểu 8 ký tự, gồm chữ và số)
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Nhập mật khẩu mới an toàn"
                required
                className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>


            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Xác nhận mật khẩu mới
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Nhập lại mật khẩu mới"
                required
                className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || Boolean(success)}
              className="w-full mt-2 py-2.5 px-4 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-300 text-white text-sm font-semibold rounded-xl shadow-md shadow-amber-600/20 transition flex items-center justify-center space-x-2"
            >
              <Lock className="w-4 h-4" />
              <span>{isLoading ? "Đang cập nhật..." : "Cập nhật mật khẩu & Mở khóa"}</span>
            </button>
          </form>

          <p className="text-[11px] text-slate-400 text-center mt-4">
            Mật khẩu mới sẽ được mã hóa an toàn bằng thuật toán PBKDF2 chống brute-force.
          </p>
        </div>
      </div>
    </div>
  );
};
