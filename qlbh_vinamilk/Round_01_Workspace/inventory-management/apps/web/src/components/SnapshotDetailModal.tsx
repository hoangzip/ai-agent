/**
 * Component Modal: Chi tiết Chứng từ Kiểm kê (15 Cột Tiêu chuẩn)
 * Module: apps/web/src/components/SnapshotDetailModal.tsx
 *
 * Tính năng:
 * 1. Hiển thị thông tin tổng quan snapshot (Mã, Số phiếu, Ngày, Cửa hàng, Hashes, Trạng thái).
 * 2. Bảng 15 cột tiêu chuẩn bảo toàn chính xác số 0 đầu mã SKU.
 * 3. Tìm kiếm tức thì theo mã sản phẩm hoặc tên sản phẩm trong chứng từ.
 * 4. Nút duyệt (Commit) nếu đang ở trạng thái STAGING.
 */

import React, { useState, useEffect } from "react";
import {
  X,
  Search,
  CheckCircle2,
  Clock,
  AlertTriangle,
  FileSpreadsheet,
  Check,
  RefreshCw,
  Copy
} from "lucide-react";
import { api } from "../api/client";

interface Props {
  snapshotId: number;
  onClose: () => void;
  onCommitSuccess?: (updatedSnapshot: any) => void;
}

export const SnapshotDetailModal: React.FC<Props> = ({
  snapshotId,
  onClose,
  onCommitSuccess
}) => {
  const [loading, setLoading] = useState(true);
  const [snapshot, setSnapshot] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [committing, setCommitting] = useState(false);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [snapshotId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await api.getSnapshot(snapshotId, true);
      if (res.success && res.data) {
        setSnapshot(res.data.snapshot);
        setItems(res.data.items || []);
      } else {
        alert(res.error?.message || "Không thể tải chi tiết chứng từ.");
      }
    } catch (err: any) {
      alert("Lỗi kết nối khi tải chứng từ: " + (err.message || String(err)));
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!snapshot) return;
    setCommitting(true);
    try {
      const res = await api.commitSnapshot(snapshot.id);
      if (res.success && res.data) {
        setSnapshot(res.data.snapshot);
        if (onCommitSuccess) {
          onCommitSuccess(res.data.snapshot);
        }
      } else {
        alert(res.error?.message || "Không thể duyệt chứng từ.");
      }
    } catch (err: any) {
      alert("Lỗi kết nối khi duyệt: " + (err.message || String(err)));
    } finally {
      setCommitting(false);
    }
  };

  const copyToClipboard = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(type);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const filteredItems = items.filter((item) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      (item.product_code && item.product_code.toLowerCase().includes(term)) ||
      (item.product_name && item.product_name.toLowerCase().includes(term)) ||
      (item.category && item.category.toLowerCase().includes(term))
    );
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header Modal */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-900">
                  {snapshot ? snapshot.full_code : "Đang tải chứng từ..."}
                </h3>
                {snapshot && (
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      snapshot.status === "COMPLETED"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {snapshot.status}
                  </span>
                )}
              </div>
              {snapshot && (
                <p className="text-xs text-slate-500 mt-0.5">
                  Ngày kiểm kê: <span className="font-semibold text-slate-700">{snapshot.inventory_date}</span> |
                  Cửa hàng: <span className="font-semibold text-slate-700">{snapshot.store_code}</span> |
                  Phiếu: <span className="font-semibold text-slate-700">{snapshot.ticket_number}</span> |
                  Nguồn: <span className="font-mono text-slate-600">{snapshot.source_filename}</span>
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {snapshot && snapshot.status === "STAGING" && (
              <button
                onClick={handleCommit}
                disabled={committing}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-sm disabled:opacity-50"
              >
                {committing ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                <span>Duyệt Snapshot</span>
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="p-16 text-center text-slate-500 flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-primary" />
            <p className="text-sm">Đang tải dữ liệu 15 cột chi tiết...</p>
          </div>
        ) : !snapshot ? (
          <div className="p-12 text-center text-slate-500">
            Không tìm thấy dữ liệu chứng từ kiểm kê.
          </div>
        ) : (
          <>
            {/* Thanh thông tin KPI tóm tắt và Hash */}
            <div className="px-6 py-3 bg-slate-50 border-b border-slate-100 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-slate-500">Tổng mặt hàng (SKU):</span>
                <p className="font-bold text-slate-800 text-sm">{snapshot.total_sku_count} mặt hàng</p>
              </div>
              <div>
                <span className="text-slate-500">Tổng SL tồn kho:</span>
                <p className="font-bold text-slate-800 text-sm">
                  {Number(snapshot.total_quantity).toLocaleString("vi-VN")}
                </p>
              </div>
              <div>
                <span className="text-slate-500">Tổng giá trị tồn kho:</span>
                <p className="font-bold text-emerald-700 text-sm">
                  {Number(snapshot.total_amount_vnd).toLocaleString("vi-VN")} VND
                </p>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-slate-500">Mã băm kiểm toán:</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => copyToClipboard(snapshot.file_sha256, "sha256")}
                    className="font-mono text-[10px] bg-slate-200 px-1.5 py-0.5 rounded text-slate-700 hover:bg-slate-300 transition flex items-center gap-1"
                    title={`Binary SHA256: ${snapshot.file_sha256}`}
                  >
                    <span>SHA: {snapshot.file_sha256?.substring(0, 8)}...</span>
                    <Copy className="w-2.5 h-2.5" />
                  </button>
                  <button
                    onClick={() => copyToClipboard(snapshot.content_hash, "content")}
                    className="font-mono text-[10px] bg-slate-200 px-1.5 py-0.5 rounded text-slate-700 hover:bg-slate-300 transition flex items-center gap-1"
                    title={`Content Hash: ${snapshot.content_hash}`}
                  >
                    <span>DATA: {snapshot.content_hash?.substring(0, 8)}...</span>
                    <Copy className="w-2.5 h-2.5" />
                  </button>
                  {copiedHash && (
                    <span className="text-[10px] text-emerald-600 font-semibold">Đã copy!</span>
                  )}
                </div>
              </div>
            </div>

            {/* Thanh tìm kiếm */}
            <div className="px-6 py-3 border-b border-slate-100 flex items-center justify-between gap-4">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Tìm theo mã SKU (vd: 02AA15), tên sản phẩm, ngành hàng..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 text-xs focus:ring-1 focus:ring-primary focus:border-primary outline-none"
                />
              </div>
              <div className="text-xs text-slate-500">
                Hiển thị <span className="font-semibold text-slate-800">{filteredItems.length}</span> / {items.length} mặt hàng
              </div>
            </div>

            {/* Bảng 15 cột dữ liệu cuộn ngang & dọc */}
            <div className="flex-1 overflow-auto">
              <table className="w-full text-left text-xs whitespace-nowrap">
                <thead className="bg-slate-100/90 text-slate-600 font-semibold sticky top-0 z-10 shadow-sm">
                  <tr>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-center">STT</th>
                    <th className="px-3 py-2.5 border-b border-slate-200">Ngành hàng</th>
                    <th className="px-3 py-2.5 border-b border-slate-200">Mã sản phẩm</th>
                    <th className="px-3 py-2.5 border-b border-slate-200">Tên sản phẩm</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-right">SL Tồn kho</th>
                    <th className="px-3 py-2.5 border-b border-slate-200">Loại kho</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-right">Giá (sau VAT)</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-right">Thành tiền</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-right">SL Package</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-right">SL Lẻ</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-center">Tổng SL Kiểm kê</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-center">Chênh lệch</th>
                    <th className="px-3 py-2.5 border-b border-slate-200">ĐVT Package</th>
                    <th className="px-3 py-2.5 border-b border-slate-200 text-right">Quy đổi</th>
                    <th className="px-3 py-2.5 border-b border-slate-200">ĐVT Lẻ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredItems.map((item, idx) => (
                    <tr key={item.id || idx} className="hover:bg-slate-50/80 transition">
                      <td className="px-3 py-2 text-center text-slate-400 font-mono text-[11px]">
                        {item.stt || idx + 1}
                      </td>
                      <td className="px-3 py-2 font-medium text-slate-700">{item.category}</td>
                      <td className="px-3 py-2 font-mono font-bold text-slate-900 bg-slate-50/50">
                        {item.product_code}
                      </td>
                      <td className="px-3 py-2 font-medium text-slate-800 max-w-[280px] truncate" title={item.product_name}>
                        {item.product_name}
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-semibold text-slate-900">
                        {Number(item.quantity).toLocaleString("vi-VN")}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
                          item.warehouse.includes("KM")
                            ? "bg-purple-50 text-purple-700 border border-purple-100"
                            : "bg-blue-50 text-blue-700 border border-blue-100"
                        }`}>
                          {item.warehouse}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-slate-600">
                        {Number(item.unit_price).toLocaleString("vi-VN")}
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-semibold text-emerald-700">
                        {Number(item.total_amount).toLocaleString("vi-VN")}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-slate-600">
                        {Number(item.audit_package_qty || 0).toLocaleString("vi-VN")}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-slate-600">
                        {Number(item.audit_loose_qty || 0).toLocaleString("vi-VN")}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-slate-500 text-[11px]">
                        {item.audit_total_qty_formula || "0"}
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-slate-500 text-[11px]">
                        {item.discrepancy_formula || "0"}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{item.package_unit}</td>
                      <td className="px-3 py-2 text-right font-mono text-slate-600">
                        {item.conversion_rate}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{item.loose_unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Footer Modal */}
            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
              <span>
                Chứng từ ID: <span className="font-mono text-slate-700">{snapshot.id}</span>
              </span>
              <button
                onClick={onClose}
                className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-lg font-medium transition"
              >
                Đóng
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
