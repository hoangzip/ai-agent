import React from "react";
import { EmptyState } from "../components/EmptyState";
import { Cloud, GitCompare, History, UploadCloud, Users, Trash, Settings } from "lucide-react";

export const SnapshotsPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Danh sách Chứng từ Kiểm kê</h3>
    <p className="text-xs text-slate-500 mb-6">
      Tìm kiếm, lọc theo ngày/ca và quản lý các đợt kiểm kê đã nạp vào hệ thống.
    </p>
    <EmptyState
      title="Bộ lọc nâng cao"
      description="Chức năng lọc và phân trang bảng dữ liệu hoàn chỉnh sẽ được kích hoạt ở Round 04 (Excel Import & Management)."
    />
  </div>
);

export const ImportPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Nhập File Kiểm kê Excel (.xlsx)</h3>
    <p className="text-xs text-slate-500 mb-6">
      Kéo thả hoặc chọn file Excel kiểm kê để xem trước và nạp vào staging.
    </p>
    <div className="border-2 border-dashed border-slate-200 rounded-xl p-12 text-center hover:border-primary/50 transition">
      <UploadCloud className="w-10 h-10 text-primary mx-auto mb-3" />
      <h4 className="text-sm font-semibold text-slate-800">Kéo thả file .xlsx vào đây</h4>
      <p className="text-xs text-slate-500 mt-1">Chức năng upload và staging sẽ được tích hợp tại Round 04</p>
    </div>
  </div>
);

export const ComparePage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">So sánh Đối soát Tồn kho</h3>
    <p className="text-xs text-slate-500 mb-6">
      Chọn Snapshot A và Snapshot B bất kỳ để phân tích biến động tăng/giảm, sản phẩm mới và tỷ lệ phần trăm.
    </p>
    <EmptyState
      title="Công cụ đối soát Snapshot"
      description="Giao diện bộ chọn 2 snapshot và bảng phân loại sản phẩm sẽ được hoàn thiện ở Round 05."
    />
  </div>
);

export const HistoryPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Lịch sử Biến động Sản phẩm (SKU)</h3>
    <p className="text-xs text-slate-500 mb-6">
      Tra cứu đường biến động tồn kho và giá bán của từng SKU qua các đợt kiểm kê.
    </p>
    <EmptyState
      title="Tra cứu mã sản phẩm"
      description="Biểu đồ xu hướng và bảng lịch sử SKU sẽ được hoàn thiện tại Round 05."
    />
  </div>
);

export const SyncPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Đồng bộ Google Drive</h3>
    <p className="text-xs text-slate-500 mb-4">
      Folder ID được cấu hình: <code className="bg-slate-100 px-2 py-1 rounded text-primary font-mono text-xs">1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk</code>
    </p>
    <EmptyState
      title="Google Drive Connector"
      description="Tiến trình đồng bộ tự động 60 phút và nút 'Đồng bộ ngay' sẽ được kết nối ở Round 07."
    />
  </div>
);

export const UsersPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Quản lý Người dùng & Phân quyền</h3>
    <p className="text-xs text-slate-500 mb-6">
      Chỉ dành riêng cho tài khoản Quản trị viên (ADMIN). Quản lý danh sách người dùng, cấp lại mật khẩu tạm và khóa tài khoản.
    </p>
    <EmptyState
      title="Phân quyền RBAC"
      description="Giao diện quản lý người dùng và đổi mật khẩu bắt buộc lần đầu sẽ được bàn giao ở Round 03."
    />
  </div>
);

export const TrashPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Thùng rác & Khôi phục Snapshot</h3>
    <p className="text-xs text-slate-500 mb-6">
      Danh sách các chứng từ kiểm kê đã bị xóa mềm (Soft Deleted). Cho phép Quản trị viên khôi phục lại khi cần.
    </p>
    <EmptyState
      title="Chức năng sẽ triển khai trong Round 08"
      description="Chức năng Quản lý Thùng rác & Phục hồi dữ liệu xóa mềm đang được bảo lưu và sẽ triển khai đầy đủ trong Round 08 (Quản trị & Phục hồi)."
    />
  </div>
);

export const SettingsPage: React.FC = () => (
  <div className="bg-white rounded-xl border border-slate-200 p-6">
    <h3 className="text-base font-bold text-slate-900 mb-2">Cài đặt Hệ thống</h3>
    <p className="text-xs text-slate-500 mb-6">
      Cấu hình thời gian hiển thị (mặc định Asia/Ho_Chi_Minh), các tham số dung sai kiểm kê và thông tin phiên bản.
    </p>
    <div className="space-y-4 max-w-lg text-xs">
      <div className="flex justify-between items-center py-2 border-b border-slate-100">
        <span className="font-medium text-slate-700">Múi giờ hiển thị</span>
        <span className="font-mono text-slate-900">Asia/Ho_Chi_Minh (GMT+7)</span>
      </div>
      <div className="flex justify-between items-center py-2 border-b border-slate-100">
        <span className="font-medium text-slate-700">Định dạng ngày giờ</span>
        <span className="font-mono text-slate-900">dd/MM/yyyy HH:mm:ss</span>
      </div>
      <div className="flex justify-between items-center py-2 border-b border-slate-100">
        <span className="font-medium text-slate-700">Phiên bản nền tảng</span>
        <span className="font-mono text-primary font-semibold">0.2.0 (Round 02 Foundation)</span>
      </div>
    </div>
  </div>
);
