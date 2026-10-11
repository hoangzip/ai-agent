/**
 * Trang Quản lý & Đồng bộ Đám mây Google Drive (Sync Page - Round 07)
 * File: apps/web/src/pages/SyncPage.tsx
 *
 * Tính năng:
 * 1. Hiển thị cấu hình và trạng thái kết nối Google Drive (Folder ID: 1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk).
 * 2. Nút thao tác nhanh "Đồng bộ ngay" (Manual Trigger) kèm hiệu ứng loading, phản hồi tiến trình.
 * 3. 4 thẻ KPI thống kê các đợt đồng bộ (Tổng đợt, File đã nạp, File bỏ qua/trùng, Tỷ lệ thành công).
 * 4. Bảng nhật ký các đợt đồng bộ (sync_runs) hiển thị chi tiết số file phát hiện, đã nạp, bỏ qua, lỗi.
 * 5. Ngôn ngữ 100% tiếng Việt, định dạng ngày giờ chuẩn dd/MM/yyyy HH:mm:ss.
 */

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Cloud,
  RefreshCw,
  FolderSync,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  ArrowRight,
  ShieldCheck,
  FileSpreadsheet,
  Copy,
  ExternalLink,
  Info
} from "lucide-react";
import { api } from "../api/client";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";

export const SyncPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState<boolean>(false);
  const [syncFeedback, setSyncFeedback] = useState<{
    type: "success" | "error" | "info";
    message: string;
    summary?: any;
  } | null>(null);

  // 1. Lấy trạng thái nguồn đồng bộ
  const {
    data: statusData,
    isLoading: isStatusLoading,
    error: statusError,
    refetch: refetchStatus
  } = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => api.getSyncStatus(),
    refetchInterval: 30000 // Tự động làm mới mỗi 30s
  });

  // 2. Lấy danh sách lịch sử các đợt đồng bộ
  const {
    data: runsData,
    isLoading: isRunsLoading,
    error: runsError,
    refetch: refetchRuns
  } = useQuery({
    queryKey: ["sync-runs"],
    queryFn: () => api.getSyncRuns({ page: 1, limit: 20 })
  });

  // 3. Mutation kích hoạt đồng bộ thủ công
  const syncMutation = useMutation({
    mutationFn: () => api.triggerSync(),
    onSuccess: (res: any) => {
      queryClient.invalidateQueries({ queryKey: ["sync-status"] });
      queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });

      if (res.success && res.data) {
        const sum = res.data.summary;
        setSyncFeedback({
          type: res.data.status === "COMPLETED" ? "success" : "error",
          message: `Đồng bộ hoàn tất: Phát hiện ${sum.files_detected} file, nạp mới ${sum.files_imported} snapshot, bỏ qua ${sum.files_skipped} file trùng lặp.`,
          summary: sum
        });
      } else {
        setSyncFeedback({
          type: "error",
          message: res.error?.message || "Đồng bộ không thành công."
        });
      }
    },
    onError: (err: any) => {
      setSyncFeedback({
        type: "error",
        message: "Lỗi kết nối máy chủ đồng bộ: " + (err.message || String(err))
      });
    }
  });

  const handleCopyFolderId = (folderId: string) => {
    if (navigator?.clipboard) {
      navigator.clipboard.writeText(folderId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formatDateTime = (dateStr?: string | null) => {
    if (!dateStr) return "Chưa thực hiện";
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      const day = String(d.getDate()).padStart(2, "0");
      const month = String(d.getMonth() + 1).padStart(2, "0");
      const year = d.getFullYear();
      const hours = String(d.getHours()).padStart(2, "0");
      const mins = String(d.getMinutes()).padStart(2, "0");
      const secs = String(d.getSeconds()).padStart(2, "0");
      return `${day}/${month}/${year} ${hours}:${mins}:${secs}`;
    } catch {
      return dateStr;
    }
  };

  if (isStatusLoading || isRunsLoading) {
    return <LoadingState message="Đang tải thông tin cấu hình và lịch sử đồng bộ Google Drive..." />;
  }

  if (statusError || !statusData?.success) {
    return (
      <ErrorState
        title="Không thể tải trạng thái đồng bộ"
        message={statusData?.error?.message || "Đã xảy ra lỗi kết nối cơ sở dữ liệu."}
        onRetry={() => {
          refetchStatus();
          refetchRuns();
        }}
      />
    );
  }

  const status = statusData.data;
  const source = status?.source || {
    folder_id: "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk",
    folder_name: "Kiem ke hang hoa Vinamilk",
    sync_interval_minutes: 60,
    is_active: true
  };
  const metrics = status?.metrics || {
    total_runs: 0,
    successful_runs: 0,
    failed_runs: 0,
    total_files_imported: 0,
    total_files_skipped: 0
  };
  const runs = runsData?.data?.items || [];
  const successRate = metrics.total_runs > 0 
    ? Math.round((metrics.successful_runs / metrics.total_runs) * 100) 
    : 100;

  return (
    <div className="space-y-6">
      {/* 1. Header Tác vụ & Trạng thái Kết nối Đám mây */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-2xs flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-bold text-slate-900">Đồng bộ Đám mây Google Drive</h2>
            {status.connection_status === "LIVE_ACTIVE" ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                LIVE ({status?.driver_mode || "LIVE"})
              </span>
            ) : status.connection_status === "BLOCKED_FOR_LIVE" ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-300">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                BLOCKED_FOR_LIVE (Thiếu Service Account)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                Chế độ Mô phỏng ({status?.driver_mode || "SIMULATION"})
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 max-w-2xl">
            Tự động quét thư mục Google Drive định kỳ mỗi {source.sync_interval_minutes} phút (Cloudflare Cron / Google Apps Script Trigger), bóc tách cấu trúc Excel 15 cột và nạp chứng từ kiểm kê vào Staging.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          <button
            onClick={() => {
              refetchStatus();
              refetchRuns();
            }}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition"
            title="Làm mới trạng thái"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Làm mới</span>
          </button>

          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 rounded-lg shadow-2xs transition cursor-pointer"
          >
            <FolderSync className={`w-4 h-4 ${syncMutation.isPending ? "animate-spin" : ""}`} />
            <span>{syncMutation.isPending ? "Đang đồng bộ..." : "Đồng bộ ngay"}</span>
          </button>
        </div>
      </div>

      {/* Cảnh báo trạng thái kết nối Google Drive LIVE nếu bị chặn (BLOCKED_FOR_LIVE) */}
      {status.connection_status === "BLOCKED_FOR_LIVE" && (
        <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 text-amber-900 text-xs flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-bold">Chế độ kết nối Google Drive LIVE đang tạm dừng (BLOCKED_FOR_LIVE)</p>
            <p className="text-amber-800">
              Hệ thống chưa được cấp thông tin xác thực Google Service Account (hoặc OAuth credentials) để truy cập thư mục Google Drive trực tuyến. Để đảm bảo tính liên tục của quy trình kiểm thử và demo, hệ thống đang vận hành an toàn qua <strong>Bộ điều khiển Mô phỏng (Simulation Driver)</strong> bằng 4 tệp kiểm kê thực tế.
            </p>
          </div>
        </div>
      )}

      {/* Thông báo kết quả sau khi bấm đồng bộ */}
      {syncFeedback && (
        <div
          className={`p-4 rounded-xl border flex items-start justify-between gap-3 text-xs ${
            syncFeedback.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : syncFeedback.type === "error"
              ? "bg-rose-50 border-rose-200 text-rose-800"
              : "bg-blue-50 border-blue-200 text-blue-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {syncFeedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            )}
            <span>{syncFeedback.message}</span>
          </div>
          <button
            onClick={() => setSyncFeedback(null)}
            className="font-semibold hover:opacity-75 cursor-pointer ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* 2. Thẻ Cấu hình Thư mục Nguồn */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-2xs">
        <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Cloud className="w-4 h-4 text-blue-600" />
          <span>Thông tin Nguồn Thư mục Google Drive</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-100">
            <span className="text-slate-500 block mb-1">Mã Thư mục (Folder ID):</span>
            <div className="flex items-center justify-between gap-2">
              <code className="font-mono font-bold text-slate-900 select-all truncate">
                {source.folder_id}
              </code>
              <button
                onClick={() => handleCopyFolderId(source.folder_id)}
                className="text-slate-500 hover:text-blue-600 p-1 rounded transition"
                title="Sao chép Folder ID"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
            {copied && <span className="text-[10px] text-emerald-600 font-semibold block mt-0.5">Đã sao chép!</span>}
          </div>

          <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-100">
            <span className="text-slate-500 block mb-1">Tên Thư mục & Chu kỳ:</span>
            <p className="font-bold text-slate-900 truncate">{source.folder_name}</p>
            <p className="text-[11px] text-slate-500 mt-0.5">Tự động quét: Mỗi {source.sync_interval_minutes} phút</p>
          </div>

          <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-100">
            <span className="text-slate-500 block mb-1">Lần đồng bộ gần nhất:</span>
            <p className="font-bold text-slate-900">{formatDateTime(source.last_sync_at)}</p>
            <p className="text-[11px] text-emerald-600 font-medium mt-0.5">
              {source.last_sync_at ? "Cơ sở dữ liệu sẵn sàng" : "Chờ kích hoạt đợt đầu"}
            </p>
          </div>
        </div>
      </div>

      {/* 3. Lưới 4 Thẻ KPI Chỉ số Đồng bộ */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-500 font-medium">Tổng Đợt Đồng bộ</span>
            <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
              <RefreshCw className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900">{metrics.total_runs}</div>
          <p className="text-[11px] text-slate-500 mt-1">Đợt chạy ghi nhận trong hệ thống</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-500 font-medium">File Đã Nạp Mới</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-700">{metrics.total_files_imported}</div>
          <p className="text-[11px] text-slate-500 mt-1">Chứng từ hoàn tất lưu trữ</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-500 font-medium">File Bỏ qua (Trùng lặp)</span>
            <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-700">{metrics.total_files_skipped}</div>
          <p className="text-[11px] text-slate-500 mt-1">Bảo toàn Idempotency chống trùng</p>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-slate-500 font-medium">Tỷ lệ Thành công</span>
            <div className="w-8 h-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-purple-700">{successRate}%</div>
          <p className="text-[11px] text-slate-500 mt-1">{metrics.successful_runs} đợt thành công / {metrics.total_runs} đợt</p>
        </div>
      </div>

      {/* 4. Bảng Nhật ký Lịch sử Đồng bộ (sync_runs) */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-2xs">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-900 text-sm">Nhật ký Lịch sử Đồng bộ</h3>
            <p className="text-xs text-slate-500 mt-0.5">Theo dõi chi tiết kết quả từng phiên quét dữ liệu Google Drive</p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50/80 text-slate-600 border-b border-slate-100 uppercase tracking-wider font-semibold">
              <tr>
                <th className="py-3 px-4">Mã đợt</th>
                <th className="py-3 px-4">Thời điểm thực hiện</th>
                <th className="py-3 px-4 text-center">Hình thức</th>
                <th className="py-3 px-4 text-center">File phát hiện</th>
                <th className="py-3 px-4 text-center">Đã nạp mới</th>
                <th className="py-3 px-4 text-center">Bỏ qua (Trùng)</th>
                <th className="py-3 px-4 text-center">Trạng thái</th>
                <th className="py-3 px-4">Ghi chú</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    Chưa có nhật ký đợt đồng bộ nào. Nhấn nút "Đồng bộ ngay" ở trên để bắt đầu đợt đầu tiên.
                  </td>
                </tr>
              ) : (
                runs.map((run: any) => (
                  <tr key={run.id} className="hover:bg-slate-50/60 transition">
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">
                      #{run.id}
                    </td>
                    <td className="py-3 px-4 text-slate-700 whitespace-nowrap">
                      {formatDateTime(run.started_at)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                        {run.triggered_by === "MANUAL" ? "Thủ công" : "Tự động"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center font-bold text-slate-900">
                      {run.files_detected || 0}
                    </td>
                    <td className="py-3 px-4 text-center font-bold text-emerald-700">
                      +{run.files_imported || 0}
                    </td>
                    <td className="py-3 px-4 text-center text-slate-500 font-medium">
                      {run.files_skipped || 0}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {run.status === "COMPLETED" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3" />
                          Hoàn tất
                        </span>
                      ) : run.status === "RUNNING" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                          <Clock className="w-3 h-3 animate-spin" />
                          Đang chạy
                        </span>
                      ) : (run.outcome === "PARTIAL" || run.files_imported > 0 || run.files_skipped > 0 || (run.error_message && run.error_message.includes("PARTIAL"))) ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200" title={run.error_message || "Đồng bộ một phần có file lỗi"}>
                          <AlertTriangle className="w-3 h-3 text-amber-600" />
                          Một phần (PARTIAL)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                          <AlertTriangle className="w-3 h-3" />
                          Thất bại
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-500 text-[11px] max-w-xs truncate" title={run.error_message || ""}>
                      {run.error_message || (run.files_imported > 0 ? "Nạp dữ liệu thành công" : "Dữ liệu đã cập nhật đầy đủ")}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
