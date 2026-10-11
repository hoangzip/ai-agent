/**
 * Trang Quản lý Chứng từ Kiểm kê (Snapshots Page) - Round 04
 * Module: apps/web/src/pages/SnapshotsPage.tsx
 *
 * Tính năng:
 * 1. Bảng danh sách toàn diện các chứng từ kiểm kê đã nạp vào D1.
 * 2. Bộ lọc trạng thái (STAGING, COMPLETED, CONFLICT, FAILED) và theo ngày/cửa hàng.
 * 3. Hỗ trợ đa snapshot trong ngày (phân biệt bằng full_code & ticket_number).
 * 4. Nút xem chi tiết 15 cột, duyệt Staging -> Completed, và xóa mềm (dành cho Admin).
 */

import React, { useState, useEffect } from "react";
import {
  FileSpreadsheet,
  Filter,
  Search,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Eye,
  Check,
  Trash2,
  RefreshCw,
  Calendar,
  Store,
  Layers
} from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { SnapshotDetailModal } from "../components/SnapshotDetailModal";

export const SnapshotsPage: React.FC = () => {
  const { currentUser } = useAuth();
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [storeFilter, setStoreFilter] = useState<string>("");
  const [dateFilter, setDateFilter] = useState<string>("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [viewingSnapshotId, setViewingSnapshotId] = useState<number | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  useEffect(() => {
    loadSnapshots();
  }, [statusFilter, storeFilter, dateFilter, page]);

  const loadSnapshots = async () => {
    setLoading(true);
    try {
      const res = await api.getSnapshots({
        page,
        limit: 20,
        status: statusFilter || undefined,
        store_code: storeFilter || undefined,
        inventory_date: dateFilter || undefined
      });

      if (res.success && res.data) {
        setSnapshots(res.data.items || []);
        if (res.data.pagination) {
          setTotalPages(res.data.pagination.total_pages || 1);
          setTotalCount(res.data.pagination.total || 0);
        }
      } else {
        alert(res.error?.message || "Không thể tải danh sách chứng từ.");
      }
    } catch (err: any) {
      alert("Lỗi kết nối khi tải danh sách: " + (err.message || String(err)));
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async (id: number) => {
    setActionLoadingId(id);
    try {
      const res = await api.commitSnapshot(id);
      if (res.success) {
        setSnapshots((prev) =>
          prev.map((s) => (s.id === id ? { ...s, status: "COMPLETED" } : s))
        );
      } else {
        alert(res.error?.message || "Không thể duyệt chứng từ.");
      }
    } catch (err: any) {
      alert("Lỗi kết nối khi duyệt: " + (err.message || String(err)));
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDelete = async (id: number, fullCode: string) => {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa chứng từ kiểm kê '${fullCode}' không?`)) {
      return;
    }

    setActionLoadingId(id);
    try {
      const res = await api.deleteSnapshot(id);
      if (res.success) {
        setSnapshots((prev) => prev.filter((s) => s.id !== id));
        setTotalCount((prev) => Math.max(0, prev - 1));
      } else {
        alert(res.error?.message || "Không thể xóa chứng từ.");
      }
    } catch (err: any) {
      alert("Lỗi kết nối khi xóa: " + (err.message || String(err)));
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Tiêu đề trang */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">
            Quản lý Chứng từ Kiểm kê (Snapshots)
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Theo dõi danh sách các đợt kiểm kê, trạng thái Chờ duyệt / Hoàn tất, và kiểm tra chi tiết dữ liệu.
          </p>
        </div>
        <button
          onClick={loadSnapshots}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 text-slate-700 hover:bg-slate-50 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Làm mới</span>
        </button>
      </div>

      {/* Thanh bộ lọc */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-slate-400" />
          <span className="font-semibold text-slate-700">Bộ lọc:</span>
        </div>

        {/* Lọc Trạng thái */}
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-primary focus:border-primary outline-none"
        >
          <option value="">Tất cả trạng thái</option>
          <option value="STAGING">Chờ duyệt</option>
          <option value="COMPLETED">Đã hoàn tất</option>
          <option value="CONFLICT">Xung đột</option>
          <option value="FAILED">Lỗi kiểm tra</option>
        </select>

        {/* Lọc Mã cửa hàng */}
        <div className="relative">
          <input
            type="text"
            placeholder="Mã CH (vd: CH41551)..."
            value={storeFilter}
            onChange={(e) => {
              setStoreFilter(e.target.value);
              setPage(1);
            }}
            className="pl-3 pr-3 py-1.5 rounded-lg border border-slate-200 text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none w-36"
          />
        </div>

        {/* Lọc Ngày kiểm kê */}
        <div className="relative">
          <input
            type="date"
            value={dateFilter}
            onChange={(e) => {
              setDateFilter(e.target.value);
              setPage(1);
            }}
            className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none"
          />
        </div>

        {(statusFilter || storeFilter || dateFilter) && (
          <button
            onClick={() => {
              setStatusFilter("");
              setStoreFilter("");
              setDateFilter("");
              setPage(1);
            }}
            className="text-xs text-rose-600 hover:underline"
          >
            Xóa bộ lọc
          </button>
        )}

        <div className="ml-auto text-slate-500">
          Tìm thấy <span className="font-semibold text-slate-800">{totalCount}</span> chứng từ
        </div>
      </div>

      {/* Bảng danh sách Snapshot */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-16 text-center text-slate-500 flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-primary" />
            <p className="text-sm">Đang tải danh sách chứng từ kiểm kê...</p>
          </div>
        ) : snapshots.length === 0 ? (
          <div className="p-16 text-center text-slate-500">
            <FileSpreadsheet className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h4 className="text-sm font-semibold text-slate-700">Chưa có chứng từ kiểm kê nào</h4>
            <p className="text-xs text-slate-400 mt-1">
              Hãy chuyển sang tab "Nhập File Excel" để tải lên các tệp kiểm kê đầu tiên.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs whitespace-nowrap">
              <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Mã Snapshot (Full Code)</th>
                  <th className="px-4 py-3">Số phiếu</th>
                  <th className="px-4 py-3">Cửa hàng</th>
                  <th className="px-4 py-3">Ngày kiểm kê</th>
                  <th className="px-4 py-3 text-right">Tổng SKU</th>
                  <th className="px-4 py-3 text-right">Tổng SL tồn</th>
                  <th className="px-4 py-3 text-right">Tổng giá trị (VND)</th>
                  <th className="px-4 py-3 text-center">Trạng thái</th>
                  <th className="px-4 py-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {snapshots.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-4 py-3 font-mono font-bold text-slate-900">
                      {item.full_code}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-700">
                      {item.ticket_number}
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-700">
                      {item.store_code}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {item.inventory_date}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-medium text-slate-800">
                      {item.total_sku_count}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-700">
                      {Number(item.total_quantity).toLocaleString("vi-VN")}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-semibold text-emerald-700">
                      {Number(item.total_amount_vnd).toLocaleString("vi-VN")}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                          item.status === "COMPLETED"
                            ? "bg-emerald-100 text-emerald-800"
                            : item.status === "STAGING"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {item.status === "COMPLETED" && <CheckCircle2 className="w-3 h-3" />}
                        {item.status === "STAGING" && <Clock className="w-3 h-3" />}
                        {item.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {item.status === "STAGING" && (
                          <button
                            onClick={() => handleCommit(item.id)}
                            disabled={actionLoadingId === item.id}
                            className="p-1.5 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 rounded-lg transition"
                            title="Duyệt snapshot sang COMPLETED"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                        )}
                        {item.status === "COMPLETED" && (
                          <button
                            onClick={() => {
                              window.dispatchEvent(
                                new CustomEvent("navigate-tab", {
                                  detail: { tab: "compare", baseId: item.id }
                                })
                              );
                            }}
                            className="p-1.5 text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition"
                            title="So sánh đối soát snapshot này"
                          >
                            <Layers className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={() => setViewingSnapshotId(item.id)}
                          className="p-1.5 text-slate-500 hover:text-blue-600 hover:bg-slate-100 rounded-lg transition"
                          title="Xem chi tiết 15 cột"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        {currentUser?.role === "ADMIN" && (
                          <button
                            onClick={() => handleDelete(item.id, item.full_code)}
                            disabled={actionLoadingId === item.id}
                            className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                            title="Xóa mềm snapshot"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Phân trang */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <div>
              Trang {page} / {totalPages}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1 rounded border border-slate-200 disabled:opacity-50 hover:bg-slate-50"
              >
                Trước
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1 rounded border border-slate-200 disabled:opacity-50 hover:bg-slate-50"
              >
                Sau
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal xem chi tiết */}
      {viewingSnapshotId !== null && (
        <SnapshotDetailModal
          snapshotId={viewingSnapshotId}
          onClose={() => setViewingSnapshotId(null)}
          onCommitSuccess={(updated) => {
            setSnapshots((prev) =>
              prev.map((s) => (s.id === updated.id ? { ...s, status: "COMPLETED" } : s))
            );
          }}
        />
      )}
    </div>
  );
};
