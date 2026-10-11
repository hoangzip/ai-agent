/**
 * Trang Nhập File Kiểm kê Excel (.xlsx) - Round 04 (Revision 2 - Fix 01 Data Integrity)
 * Module: apps/web/src/pages/ImportPage.tsx
 *
 * Tính năng:
 * 1. Kéo thả (Drag & Drop) hoặc chọn đa tệp Excel (.xlsx).
 * 2. Cung cấp chọn Ca kiểm kê (Sáng/Chiều/Tối/Khác) và Giờ kiểm kê (R04-P2-01).
 * 3. Hỗ trợ Xem trước (Preview) kiểm tra cấu trúc 15 cột và dòng 2 trước khi nạp (R04-P2-03).
 * 4. Chống nạp snapshot lỗi, xác thực toàn vẹn DB trước khi cho phép COMPLETED (R04-P1-01).
 * 5. Duyệt Staging -> Completed an toàn (R04-P1-02).
 */

import React, { useState, useRef } from "react";
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Eye,
  Check,
  RefreshCw,
  Clock,
  Layers,
  Search
} from "lucide-react";
import { api } from "../api/client";
import { SnapshotDetailModal } from "../components/SnapshotDetailModal";

interface UploadFileItem {
  file: File;
  status: "pending" | "uploading" | "success" | "error";
  progress?: number;
  result?: any;
  error?: string;
  previewData?: any;
}

export const ImportPage: React.FC = () => {
  const [fileQueue, setFileQueue] = useState<UploadFileItem[]>([]);
  const [autoCommit, setAutoCommit] = useState(false);
  const [shift, setShift] = useState<"Sáng" | "Chiều" | "Tối" | "Khác" | "Chưa xác định">("Chưa xác định");
  const [inventoryTime, setInventoryTime] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [viewingSnapshotId, setViewingSnapshotId] = useState<number | null>(null);
  const [previewingItem, setPreviewingItem] = useState<any | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFilesSelected = (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newItems: UploadFileItem[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (file.name.endsWith(".xlsx") || file.name.endsWith(".xls")) {
        newItems.push({
          file,
          status: "pending"
        });
      }
    }

    if (newItems.length === 0) {
      alert("Vui lòng chỉ chọn các tệp Excel định dạng .xlsx hoặc .xls");
      return;
    }

    setFileQueue((prev) => [...prev, ...newItems]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFilesSelected(e.dataTransfer.files);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handlePreviewFile = async (item: UploadFileItem, index: number) => {
    try {
      const formData = new FormData();
      formData.append("file", item.file);
      if (shift !== "Chưa xác định") formData.append("shift", shift);
      if (inventoryTime) formData.append("inventory_time", inventoryTime);

      const res = await api.previewInventory(formData);
      if (res.success && res.data) {
        setPreviewingItem(res.data);
        setFileQueue((prev) =>
          prev.map((f, idx) => (idx === index ? { ...f, previewData: res.data } : f))
        );
      } else {
        alert(res.error?.message || "Không thể phân tích xem trước file.");
      }
    } catch (err: any) {
      alert("Lỗi xem trước file: " + (err.message || String(err)));
    }
  };

  const handleUploadAll = async () => {
    const pendingItems = fileQueue.filter((item) => item.status === "pending" || item.status === "error");
    if (pendingItems.length === 0) return;

    setIsProcessing(true);

    for (let i = 0; i < fileQueue.length; i++) {
      const item = fileQueue[i];
      if (item.status !== "pending" && item.status !== "error") continue;

      setFileQueue((prev) =>
        prev.map((f, idx) => (idx === i ? { ...f, status: "uploading" } : f))
      );

      try {
        const formData = new FormData();
        formData.append("file", item.file);
        if (autoCommit) {
          formData.append("auto_commit", "true");
        }
        if (shift !== "Chưa xác định") {
          formData.append("shift", shift);
        }
        if (inventoryTime.trim()) {
          formData.append("inventory_time", inventoryTime.trim());
        }

        const res = await api.uploadInventory(formData);

        if (res.success && res.data) {
          const snapshot = res.data.snapshot || (res.data.results && res.data.results[0]?.snapshot);
          setFileQueue((prev) =>
            prev.map((f, idx) =>
              idx === i
                ? {
                    ...f,
                    status: "success",
                    result: snapshot
                  }
                : f
            )
          );
        } else {
          setFileQueue((prev) =>
            prev.map((f, idx) =>
              idx === i
                ? {
                    ...f,
                    status: "error",
                    error: res.error?.message || "Lỗi nạp file Excel vào hệ thống."
                  }
                : f
            )
          );
        }
      } catch (err: any) {
        setFileQueue((prev) =>
          prev.map((f, idx) =>
            idx === i
              ? {
                  ...f,
                  status: "error",
                  error: err?.message || "Lỗi mạng hoặc máy chủ không phản hồi."
                }
              : f
          )
        );
      }
    }

    setIsProcessing(false);
  };

  const handleCommitSingle = async (snapshotId: number, index: number) => {
    try {
      const res = await api.commitSnapshot(snapshotId);
      if (res.success) {
        setFileQueue((prev) =>
          prev.map((item, idx) => {
            if (idx === index && item.result) {
              return {
                ...item,
                result: { ...item.result, status: "COMPLETED" }
              };
            }
            return item;
          })
        );
      } else {
        alert(res.error?.message || "Không thể duyệt snapshot.");
      }
    } catch (err: any) {
      alert("Lỗi kết nối khi duyệt snapshot: " + (err.message || String(err)));
    }
  };

  const clearQueue = () => {
    setFileQueue([]);
  };

  return (
    <div className="space-y-6">
      {/* Tiêu đề trang */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">
            Nhập File Kiểm kê Excel (.xlsx)
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Động cơ tải lên, xác thực 15 cột tiêu chuẩn, đối soát toán học Dòng 2 và quy trình Staging an toàn.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 hover:bg-slate-100 transition">
            <input
              type="checkbox"
              checked={autoCommit}
              onChange={(e) => setAutoCommit(e.target.checked)}
              className="rounded text-primary focus:ring-primary h-4 w-4"
            />
            <span>Tự động chuyển COMPLETED khi hợp lệ 100%</span>
          </label>
          {fileQueue.length > 0 && (
            <button
              onClick={clearQueue}
              className="text-xs text-slate-500 hover:text-rose-600 transition px-2 py-1"
            >
              Xóa danh sách
            </button>
          )}
        </div>
      </div>

      {/* Thanh cấu hình Metadata kiểm kê (Ca / Giờ) */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-wrap items-center gap-4 text-xs">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-slate-400" />
          <span className="font-semibold text-slate-700">Thông tin ca/giờ:</span>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-slate-500">Ca kiểm kê:</label>
          <select
            value={shift}
            onChange={(e) => setShift(e.target.value as any)}
            className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-primary outline-none"
          >
            <option value="Chưa xác định">Chưa xác định</option>
            <option value="Sáng">Ca Sáng</option>
            <option value="Chiều">Ca Chiều</option>
            <option value="Tối">Ca Tối</option>
            <option value="Khác">Khác</option>
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-slate-500">Giờ kiểm kê:</label>
          <input
            type="time"
            value={inventoryTime}
            onChange={(e) => setInventoryTime(e.target.value)}
            className="px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-slate-700 focus:ring-1 focus:ring-primary outline-none"
          />
        </div>
      </div>

      {/* Khu vực Drag & Drop */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
          isDragging
            ? "border-primary bg-primary/5 scale-[1.005]"
            : "border-slate-200 bg-white hover:border-primary/50 hover:bg-slate-50/50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls"
          multiple
          className="hidden"
          onChange={(e) => handleFilesSelected(e.target.files)}
        />
        <div className="w-14 h-14 bg-primary/10 text-primary rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-sm">
          <UploadCloud className="w-7 h-7" />
        </div>
        <h3 className="text-base font-semibold text-slate-800">
          Kéo thả file kiểm kê Excel (.xlsx) vào đây
        </h3>
        <p className="text-xs text-slate-500 mt-1.5 max-w-md mx-auto">
          Hoặc nhấp vào vùng này để duyệt chọn từ máy tính. Hỗ trợ chọn đồng thời nhiều file cùng lúc (tối đa 10 file, 10MB/file).
        </p>
        <div className="flex flex-wrap items-center justify-center gap-4 mt-4 text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> 15 Cột chuẩn hóa
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Đối soát Dòng 2 tự động
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Giữ số 0 đầu mã SKU
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Xác thực toàn vẹn DB
          </span>
        </div>
      </div>

      {/* Danh sách hàng đợi & Kết quả xử lý */}
      {fileQueue.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-bold text-slate-800">
                Hàng đợi tệp tin ({fileQueue.length} tệp)
              </h3>
            </div>
            <button
              onClick={handleUploadAll}
              disabled={isProcessing || !fileQueue.some((f) => f.status === "pending" || f.status === "error")}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white transition shadow-sm ${
                isProcessing || !fileQueue.some((f) => f.status === "pending" || f.status === "error")
                  ? "bg-slate-300 cursor-not-allowed"
                  : "bg-primary hover:bg-primary-hover shadow-primary/20"
              }`}
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Đang xử lý nạp dữ liệu...</span>
                </>
              ) : (
                <>
                  <UploadCloud className="w-3.5 h-3.5" />
                  <span>Xử lý & Nạp tất cả</span>
                </>
              )}
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {fileQueue.map((item, idx) => (
              <div key={idx} className="p-4 hover:bg-slate-50/50 transition">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="p-2.5 rounded-xl bg-slate-100 text-slate-600 mt-0.5">
                      <FileSpreadsheet className="w-5 h-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-800">
                          {item.file.name}
                        </span>
                        <span className="text-[11px] text-slate-400 font-mono">
                          ({(item.file.size / 1024).toFixed(1)} KB)
                        </span>
                      </div>

                      {/* Trạng thái xử lý */}
                      <div className="mt-1 flex items-center gap-2 text-xs">
                        {item.status === "pending" && (
                          <span className="text-slate-500 flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                            Chờ xử lý
                          </span>
                        )}
                        {item.status === "uploading" && (
                          <span className="text-primary font-medium flex items-center gap-1">
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            Đang phân tích & lưu vào D1...
                          </span>
                        )}
                        {item.status === "success" && (
                          <span className="text-emerald-600 font-semibold flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Nạp thành công
                          </span>
                        )}
                        {item.status === "error" && (
                          <span className="text-rose-600 font-medium flex items-center gap-1">
                            <XCircle className="w-3.5 h-3.5" />
                            Thất bại
                          </span>
                        )}
                      </div>

                      {/* Hiển thị chi tiết lỗi nếu có */}
                      {item.error && (
                        <div className="mt-2 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2.5 flex items-start gap-2">
                          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-500 mt-0.5" />
                          <span>{item.error}</span>
                        </div>
                      )}

                      {/* Hiển thị tóm tắt snapshot khi nạp thành công */}
                      {item.result && (
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-600 bg-emerald-50/50 border border-emerald-100 rounded-lg px-3 py-2">
                          <span className="font-mono font-medium text-slate-800">
                            Mã: {item.result.full_code}
                          </span>
                          <span className="text-slate-300">|</span>
                          <span>Ngày: {item.result.inventory_date}</span>
                          <span className="text-slate-300">|</span>
                          <span>Ca: {item.result.shift || "Chưa rõ"}</span>
                          <span className="text-slate-300">|</span>
                          <span>SKU: {item.result.total_sku_count}</span>
                          <span className="text-slate-300">|</span>
                          <span>
                            Tổng SL: {Number(item.result.total_quantity).toLocaleString("vi-VN")}
                          </span>
                          <span className="text-slate-300">|</span>
                          <span className="font-semibold text-emerald-700">
                            {Number(item.result.total_amount_vnd).toLocaleString("vi-VN")} VND
                          </span>
                          <span className="text-slate-300">|</span>
                          <span
                            className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                              item.result.status === "COMPLETED"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-amber-100 text-amber-800"
                            }`}
                          >
                            {item.result.status}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Hành động */}
                  <div className="flex items-center gap-2 self-end md:self-center">
                    {item.status === "pending" && (
                      <button
                        onClick={() => handlePreviewFile(item, idx)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-700 hover:bg-slate-50 transition"
                        title="Xem trước cấu trúc và đối soát trước khi ghi DB"
                      >
                        <Search className="w-3.5 h-3.5 text-slate-500" />
                        <span>Xem trước</span>
                      </button>
                    )}
                    {item.result && item.result.status === "STAGING" && (
                      <button
                        onClick={() => handleCommitSingle(item.result.id, idx)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-sm"
                        title="Duyệt snapshot chuyển sang COMPLETED"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Duyệt snapshot</span>
                      </button>
                    )}
                    {item.result && (
                      <button
                        onClick={() => setViewingSnapshotId(item.result.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-700 hover:bg-slate-50 transition"
                      >
                        <Eye className="w-3.5 h-3.5 text-slate-500" />
                        <span>Xem chi tiết 15 cột</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal xem trước (Preview Modal) */}
      {previewingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-primary" />
                <h3 className="text-base font-bold text-slate-900">
                  Xem trước Tệp: {previewingItem.filename}
                </h3>
              </div>
              <button
                onClick={() => setPreviewingItem(null)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold"
              >
                ✕ Đóng
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4 text-xs">
              {/* Trạng thái xác thực */}
              <div className={`p-4 rounded-xl border ${previewingItem.isValid ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-rose-50 border-rose-200 text-rose-800"}`}>
                <div className="flex items-center gap-2 font-bold text-sm">
                  {previewingItem.isValid ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      <span>Xác thực thành công – Dữ liệu hợp lệ 100%</span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="w-4 h-4 text-rose-600" />
                      <span>Phát hiện lỗi trong cấu trúc hoặc dữ liệu file</span>
                    </>
                  )}
                </div>
                {previewingItem.errors && previewingItem.errors.length > 0 && (
                  <ul className="mt-2 list-disc list-inside space-y-1">
                    {previewingItem.errors.map((e: string, i: number) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Tóm tắt số liệu */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-xl">
                <div>
                  <span className="text-slate-500">Mã chứng từ:</span>
                  <p className="font-bold text-slate-800">{previewingItem.metadata?.full_code}</p>
                </div>
                <div>
                  <span className="text-slate-500">Ngày kiểm kê:</span>
                  <p className="font-bold text-slate-800">{previewingItem.metadata?.inventory_date}</p>
                </div>
                <div>
                  <span className="text-slate-500">Tổng mặt hàng:</span>
                  <p className="font-bold text-slate-800">{previewingItem.total_sku_count} SKU</p>
                </div>
                <div>
                  <span className="text-slate-500">Tổng giá trị:</span>
                  <p className="font-bold text-emerald-700">
                    {Number(previewingItem.summary?.calculated_total_amount || 0).toLocaleString("vi-VN")} VND
                  </p>
                </div>
              </div>

              {/* Bảng xem trước mẫu */}
              <div>
                <h4 className="font-bold text-slate-800 mb-2">Xem trước các mặt hàng mẫu (tối đa 50 dòng):</h4>
                <div className="border border-slate-200 rounded-lg overflow-x-auto">
                  <table className="w-full text-left whitespace-nowrap text-[11px]">
                    <thead className="bg-slate-100 text-slate-600 font-semibold">
                      <tr>
                        <th className="px-2.5 py-1.5">STT</th>
                        <th className="px-2.5 py-1.5">Mã SKU</th>
                        <th className="px-2.5 py-1.5">Tên sản phẩm</th>
                        <th className="px-2.5 py-1.5 text-right">SL Tồn</th>
                        <th className="px-2.5 py-1.5">Kho</th>
                        <th className="px-2.5 py-1.5 text-right">Giá</th>
                        <th className="px-2.5 py-1.5 text-right">Thành tiền</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(previewingItem.preview_items || []).map((it: any, i: number) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="px-2.5 py-1">{it.stt}</td>
                          <td className="px-2.5 py-1 font-mono font-bold">{it.product_code}</td>
                          <td className="px-2.5 py-1 truncate max-w-[200px]">{it.product_name}</td>
                          <td className="px-2.5 py-1 text-right font-mono">{it.quantity}</td>
                          <td className="px-2.5 py-1">{it.warehouse}</td>
                          <td className="px-2.5 py-1 text-right font-mono">{Number(it.unit_price).toLocaleString("vi-VN")}</td>
                          <td className="px-2.5 py-1 text-right font-mono font-semibold text-emerald-700">{Number(it.total_amount).toLocaleString("vi-VN")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex justify-end">
              <button
                onClick={() => setPreviewingItem(null)}
                className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-lg font-medium transition text-xs"
              >
                Đóng xem trước
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal xem chi tiết Snapshot */}
      {viewingSnapshotId !== null && (
        <SnapshotDetailModal
          snapshotId={viewingSnapshotId}
          onClose={() => setViewingSnapshotId(null)}
          onCommitSuccess={(updated) => {
            setFileQueue((prev) =>
              prev.map((item) => {
                if (item.result?.id === updated.id) {
                  return { ...item, result: updated };
                }
                return item;
              })
            );
          }}
        />
      )}
    </div>
  );
};
