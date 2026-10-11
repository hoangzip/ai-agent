import React, { useState, useEffect } from "react";
import {
  Users,
  UserPlus,
  ShieldAlert,
  ShieldCheck,
  Lock,
  Unlock,
  KeyRound,
  AlertTriangle,
  CheckCircle2,
  X,
  UserCheck,
  RefreshCw,
  Copy,
  Check
} from "lucide-react";
import { User, Role } from "@inventory/shared";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";

export const UserManagementPage: React.FC = () => {
  const { currentUser } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Helper sinh mật khẩu ngẫu nhiên
  const generateRandomPassword = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*";
    let pass = "";
    for (let i = 0; i < 12; i++) {
      pass += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return pass;
  };

  // Modal tạo người dùng mới
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createUsername, setCreateUsername] = useState("");
  const [createFullName, setCreateFullName] = useState("");
  const [createRole, setCreateRole] = useState<Role>("USER");
  const [createPassword, setCreatePassword] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);

  // Modal thông báo mật khẩu tạm thời sau khi tạo / reset
  const [tempPasswordModal, setTempPasswordModal] = useState<{
    isOpen: boolean;
    title: string;
    username: string;
    tempPassword: string;
    copied: boolean;
  }>({
    isOpen: false,
    title: "",
    username: "",
    tempPassword: "",
    copied: false
  });

  // Load danh sách người dùng
  const loadUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getUsers();
      if (res.success && Array.isArray(res.data)) {
        setUsers(res.data);
      } else {
        setError(res.error?.message || "Không thể tải danh sách người dùng");
      }
    } catch (err: any) {
      setError(err?.message || "Lỗi kết nối");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (currentUser?.role === "ADMIN") {
      loadUsers();
    }
  }, [currentUser]);

  // Kiểm tra quyền RBAC phía client
  if (currentUser?.role !== "ADMIN") {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center max-w-lg mx-auto mt-12 shadow-sm">
        <div className="w-14 h-14 bg-rose-100 rounded-2xl flex items-center justify-center mx-auto mb-4 text-rose-600">
          <ShieldAlert className="w-8 h-8" />
        </div>
        <h3 className="text-base font-bold text-slate-900">Quyền truy cập bị từ chối (403 Forbidden)</h3>
        <p className="text-xs text-slate-600 mt-2 leading-relaxed">
          Màn hình Quản lý Người dùng & Phân quyền (RBAC) chỉ dành riêng cho tài khoản có vai trò <strong>Quản trị viên (ADMIN)</strong>.
          Tài khoản hiện tại của bạn là <strong>{currentUser?.role || "USER"}</strong>.
        </p>
      </div>
    );
  }

  // Khóa / Mở khóa tài khoản
  const handleToggleStatus = async (user: User) => {
    const actionText = user.is_active ? "khóa" : "mở khóa";
    if (!confirm(`Bạn có chắc chắn muốn ${actionText} tài khoản '${user.username}' không?`)) {
      return;
    }

    try {
      const res = await api.updateUserStatus(user.id, !user.is_active);
      if (res.success) {
        setSuccess(`Đã ${actionText} tài khoản '${user.username}' thành công.`);
        loadUsers();
      } else {
        setError(res.error?.message || `Không thể ${actionText} tài khoản.`);
      }
    } catch (err: any) {
      setError(err?.message || "Lỗi thao tác");
    }
  };

  // Đặt lại mật khẩu tạm
  const handleResetPassword = async (user: User) => {
    if (!confirm(`Xác nhận đặt lại mật khẩu cho '${user.username}'? Toàn bộ phiên làm việc của người dùng này sẽ bị thu hồi và một mật khẩu tạm mới sẽ được tạo.`)) {
      return;
    }

    try {
      const res = await api.resetUserPassword(user.id);
      if (res.success) {
        const tempPass = res.data?.temporary_password || "";
        setTempPasswordModal({
          isOpen: true,
          title: "Đã đặt lại mật khẩu thành công",
          username: user.username,
          tempPassword: tempPass,
          copied: false
        });
        loadUsers();
      } else {
        setError(res.error?.message || "Không thể đặt lại mật khẩu.");
      }
    } catch (err: any) {
      setError(err?.message || "Lỗi thao tác");
    }
  };

  // Mở modal tạo người dùng mới
  const handleOpenCreateModal = () => {
    setCreateUsername("");
    setCreateFullName("");
    setCreateRole("USER");
    setCreatePassword(generateRandomPassword());
    setIsCreateOpen(true);
  };

  // Tạo người dùng mới
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateSubmitting(true);
    setError(null);

    try {
      const res = await api.createUser({
        username: createUsername.trim(),
        full_name: createFullName.trim(),
        role: createRole,
        password: createPassword
      });

      if (res.success) {
        const tempPass = res.data?.temporary_password || createPassword;
        setIsCreateOpen(false);
        setTempPasswordModal({
          isOpen: true,
          title: "Đã tạo tài khoản người dùng mới thành công",
          username: createUsername.trim(),
          tempPassword: tempPass,
          copied: false
        });
        loadUsers();
      } else {
        setError(res.error?.message || "Tạo người dùng thất bại.");
      }
    } catch (err: any) {
      setError(err?.message || "Lỗi kết nối");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleCopyPassword = () => {
    navigator.clipboard.writeText(tempPasswordModal.tempPassword);
    setTempPasswordModal((prev) => ({ ...prev, copied: true }));
    setTimeout(() => {
      setTempPasswordModal((prev) => ({ ...prev, copied: false }));
    }, 2000);
  };

  return (
    <div className="space-y-6">
      {/* Action Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900">Danh sách Người dùng Hệ thống</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Quản trị tài khoản, phân quyền RBAC và kiểm soát truy cập đối soát tồn kho
          </p>
        </div>
        <button
          onClick={handleOpenCreateModal}
          className="px-4 py-2 bg-purple-700 hover:bg-purple-800 text-white text-xs font-semibold rounded-xl shadow-sm transition flex items-center space-x-1.5"
        >
          <UserPlus className="w-4 h-4" />
          <span>Thêm người dùng mới</span>
        </button>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-3.5 flex items-start space-x-2.5 text-rose-800 text-xs font-medium">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">{error}</div>
          <button onClick={() => setError(null)} className="text-rose-500 hover:text-rose-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {success && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3.5 flex items-start space-x-2.5 text-emerald-800 text-xs font-medium">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          <div className="flex-1">{success}</div>
          <button onClick={() => setSuccess(null)} className="text-emerald-500 hover:text-emerald-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Users Table Card */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Tài khoản (Username)</th>
                <th className="py-3 px-4">Họ và tên</th>
                <th className="py-3 px-4">Vai trò (Role)</th>
                <th className="py-3 px-4">Trạng thái</th>
                <th className="py-3 px-4">Đổi MK lần đầu</th>
                <th className="py-3 px-4 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    Đang tải danh sách người dùng...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    Chưa có người dùng nào
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50/60 transition">
                    <td className="py-3 px-4 font-mono text-slate-500">#{u.id}</td>
                    <td className="py-3 px-4 font-semibold text-slate-900 font-mono">
                      {u.username}
                      {u.id === currentUser?.id && (
                        <span className="ml-2 text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded-full font-sans font-bold">
                          Bạn
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-800 font-medium">{u.full_name}</td>
                    <td className="py-3 px-4">
                      {u.role === "ADMIN" ? (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">
                          <ShieldCheck className="w-3 h-3 text-amber-600" />
                          <span>ADMIN</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700">
                          <UserCheck className="w-3 h-3 text-slate-500" />
                          <span>USER</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {u.is_active ? (
                        <span className="inline-flex items-center space-x-1 text-emerald-700 font-semibold text-[11px]">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                          <span>Hoạt động</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center space-x-1 text-rose-700 font-semibold text-[11px]">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                          <span>Đã khóa</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {u.must_change_password ? (
                        <span className="px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200/60 rounded-md text-[10px] font-medium">
                          Bắt buộc
                        </span>
                      ) : (
                        <span className="text-slate-400 text-[11px]">Đã đổi</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right space-x-1">
                      {/* Nút Khóa / Mở khóa */}
                      <button
                        onClick={() => handleToggleStatus(u)}
                        title={u.is_active ? "Khóa tài khoản" : "Mở khóa tài khoản"}
                        className={`p-1.5 rounded-lg border transition ${
                          u.is_active
                            ? "text-rose-600 hover:bg-rose-50 border-rose-200"
                            : "text-emerald-600 hover:bg-emerald-50 border-emerald-200"
                        }`}
                      >
                        {u.is_active ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                      </button>

                      {/* Nút Đặt lại mật khẩu */}
                      <button
                        onClick={() => handleResetPassword(u)}
                        title="Đặt lại mật khẩu tạm thời"
                        className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition"
                      >
                        <KeyRound className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Thêm người dùng mới */}
      {isCreateOpen && (
        <div className="fixed inset-y-0 inset-x-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <h4 className="font-bold text-slate-900 text-sm">Thêm người dùng mới</h4>
              <button onClick={() => setIsCreateOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Tên đăng nhập</label>
                <input
                  type="text"
                  value={createUsername}
                  onChange={(e) => setCreateUsername(e.target.value)}
                  placeholder="e.g. nv_kiemke"
                  required
                  autoFocus
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-600"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Họ và tên</label>
                <input
                  type="text"
                  value={createFullName}
                  onChange={(e) => setCreateFullName(e.target.value)}
                  placeholder="e.g. Nguyễn Văn A"
                  required
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-600"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Vai trò (Role)</label>
                <select
                  value={createRole}
                  onChange={(e) => setCreateRole(e.target.value as Role)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-600"
                >
                  <option value="USER">Nhân viên (USER)</option>
                  <option value="ADMIN">Quản trị viên (ADMIN)</option>
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-semibold text-slate-700">
                    Mật khẩu khởi tạo tạm thời (Tối thiểu 8 ký tự)
                  </label>
                  <button
                    type="button"
                    onClick={() => setCreatePassword(generateRandomPassword())}
                    className="text-[11px] text-purple-700 hover:text-purple-900 font-semibold flex items-center space-x-1"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Sinh ngẫu nhiên</span>
                  </button>
                </div>
                <input
                  type="text"
                  value={createPassword}
                  onChange={(e) => setCreatePassword(e.target.value)}
                  required
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-600"
                />
                <p className="text-[11px] text-amber-700 mt-1">
                  * Người dùng sẽ bắt buộc phải đổi mật khẩu ở lần đăng nhập đầu tiên.
                </p>
              </div>

              <div className="pt-2 flex items-center justify-end space-x-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 border border-slate-300 rounded-xl text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="px-4 py-2 bg-purple-700 hover:bg-purple-800 disabled:bg-purple-400 text-white rounded-xl text-xs font-semibold shadow-sm"
                >
                  {createSubmitting ? "Đang tạo..." : "Xác nhận tạo"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Hiển thị Mật khẩu Tạm thời sau khi Tạo / Reset */}
      {tempPasswordModal.isOpen && (
        <div className="fixed inset-y-0 inset-x-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
            <div className="bg-purple-700 p-6 text-white text-center">
              <div className="w-12 h-12 bg-white/20 rounded-2xl flex items-center justify-center mx-auto mb-2">
                <KeyRound className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-base font-bold">{tempPasswordModal.title}</h3>
              <p className="text-xs text-purple-200 mt-1">
                Tài khoản: <strong className="font-mono text-white">{tempPasswordModal.username}</strong>
              </p>
            </div>

            <div className="p-6">
              <p className="text-xs text-slate-600 mb-3">
                Vui lòng sao chép mật khẩu tạm thời bên dưới và bàn giao an toàn cho người dùng:
              </p>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-between mb-4">
                <span className="font-mono text-base font-bold text-slate-900 tracking-wider">
                  {tempPasswordModal.tempPassword}
                </span>
                <button
                  onClick={handleCopyPassword}
                  className="px-3 py-1.5 bg-white border border-slate-300 hover:bg-slate-50 rounded-lg text-xs font-medium text-slate-700 flex items-center space-x-1.5 transition shadow-xs"
                >
                  {tempPasswordModal.copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-600" />
                      <span className="text-emerald-700 font-semibold">Đã sao chép</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-slate-500" />
                      <span>Sao chép</span>
                    </>
                  )}
                </button>
              </div>

              <div className="bg-amber-50 border border-amber-200/80 rounded-xl p-3 text-[11px] text-amber-800 leading-relaxed mb-6">
                <strong>Lưu ý bảo mật:</strong> Mật khẩu này chỉ hiển thị một lần duy nhất tại đây. Người dùng sẽ bắt buộc phải đổi sang mật khẩu mới ngay khi đăng nhập.
              </div>

              <button
                onClick={() => setTempPasswordModal((prev) => ({ ...prev, isOpen: false }))}
                className="w-full py-2.5 px-4 bg-purple-700 hover:bg-purple-800 text-white text-xs font-semibold rounded-xl shadow-md transition"
              >
                Đã hoàn tất sao chép & Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
