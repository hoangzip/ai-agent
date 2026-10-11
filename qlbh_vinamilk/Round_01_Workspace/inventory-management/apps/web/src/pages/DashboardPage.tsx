/**
 * Trang Tổng quan Tồn kho (Dashboard Page) - Round 06
 * File: apps/web/src/pages/DashboardPage.tsx
 *
 * Lịch sử phát triển & Kiến trúc:
 * - Round 02 Foundation: Từng dùng nhãn DỮ LIỆU MẪU và thông báo CHƯA KẾT NỐI DATABASE THỰC TẾ chờ Round 04 nạp Excel.
 * - Round 06 Dashboard & UI: Chính thức kết nối dữ liệu thời gian thực từ Cloudflare D1 Database qua API /v1/dashboard/stats.
 *
 * Tính năng:
 * 1. Kết nối số liệu thời gian thực từ Cloudflare D1 Database qua API /v1/dashboard/stats.
 * 2. Thẻ chỉ số KPI động:
 *    - Tổng tồn kho kỳ mới nhất (kèm xu hướng biến động số lượng delta so với kỳ trước).
 *    - Tổng giá trị tồn kho VND (kèm xu hướng biến động giá trị VND).
 *    - Số lượng mặt hàng SKU theo dõi.
 *    - Thống kê chứng từ: Hoàn tất, Chờ duyệt Staging, Xung đột, Lỗi.
 * 3. Bảng hoạt động kiểm kê gần nhất kết nối dữ liệu thực tế.
 * 4. Phím tắt thao tác nhanh: Đối soát tức thì 2 kỳ mới nhất, Nhập file mới, Xem danh sách.
 */

import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Package,
  DollarSign,
  Files,
  TrendingDown,
  TrendingUp,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
  UploadCloud,
  Layers,
  FileSpreadsheet,
  Store,
  Info
} from "lucide-react";
import { api } from "../api/client";
import { KpiCard } from "../components/KpiCard";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";

export const DashboardPage: React.FC = () => {
  const [selectedStore, setSelectedStore] = useState<string>(
    () => (typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("store") || "" : "")
  );

  const { data: statsData, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["dashboard-stats", selectedStore],
    queryFn: () => api.getDashboardStats(selectedStore || undefined)
  });

  // Đồng bộ phạm vi cửa hàng lên Header tuân thủ nghiêm ngặt Rules of Hooks (P2 Header Context)
  const latestStoreCode = statsData?.data?.summary?.latest_snapshot?.store_code;
  useEffect(() => {
    let scopeLabel = "Tự động (Theo đợt mới nhất)";
    if (selectedStore) {
      scopeLabel = selectedStore;
    } else if (latestStoreCode) {
      scopeLabel = `Tự động (Đợt mới nhất: ${latestStoreCode})`;
    }
    window.dispatchEvent(
      new CustomEvent("store-scope-changed", {
        detail: { storeScope: scopeLabel }
      })
    );
  }, [selectedStore, latestStoreCode]);

  const formatVnd = (val: number) => {
    return new Intl.NumberFormat("vi-VN").format(val) + " đ";
  };

  const formatNumber = (val: number) => {
    return new Intl.NumberFormat("vi-VN").format(val);
  };

  const handleNavigate = (tab: string, baseId?: number, targetId?: number) => {
    window.dispatchEvent(
      new CustomEvent("navigate-tab", {
        detail: { tab, baseId, targetId }
      })
    );
  };

  if (isLoading) {
    return <LoadingState message="Đang nạp số liệu bảng điều khiển tổng quan..." />;
  }

  if (error || !statsData?.success) {
    return (
      <ErrorState
        title="Không thể tải số liệu Tổng quan"
        message={statsData?.error?.message || "Đã xảy ra lỗi kết nối cơ sở dữ liệu."}
        onRetry={() => refetch()}
      />
    );
  }

  const summary = statsData.data?.summary || {
    total_snapshots: 0,
    completed_snapshots: 0,
    staging_snapshots: 0,
    failed_snapshots: 0,
    conflict_snapshots: 0,
    available_stores: [],
    selected_store: null,
    scope_store_code: null,
    latest_snapshot: null,
    previous_snapshot: null,
    trend: { has_comparison: false, delta_quantity: 0, delta_amount_vnd: 0, store_code: null }
  };

  const availableStores: string[] = summary.available_stores || [];
  const recentSnapshots = statsData.data?.recent_snapshots || [];
  const latest = summary.latest_snapshot;
  const previous = summary.previous_snapshot;
  const trend = summary.trend;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3" />
            Hoàn tất
          </span>
        );
      case "STAGING":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3 h-3" />
            Chờ duyệt
          </span>
        );
      case "CONFLICT":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <AlertTriangle className="w-3 h-3" />
            Xung đột
          </span>
        );
      case "FAILED":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle className="w-3 h-3" />
            Lỗi nạp
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Header tác vụ & Bộ lọc phạm vi cửa hàng */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
        <div>
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
            <span>Dữ liệu Kiểm kê Trực tuyến</span>
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Kết nối trực tiếp cơ sở dữ liệu Cloudflare D1 • Bảo toàn phạm vi đối soát cùng cửa hàng
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Bộ chọn Cửa hàng / Phạm vi đối soát (P1 Requirement) */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs">
            <Store className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={selectedStore}
              onChange={(e) => setSelectedStore(e.target.value)}
              className="bg-transparent font-medium text-slate-700 focus:outline-none cursor-pointer"
              aria-label="Chọn phạm vi cửa hàng"
            >
              <option value="">Tất cả cửa hàng (Tự động theo đợt mới nhất)</option>
              {availableStores.map((code: string) => (
                <option key={code} value={code}>
                  Cửa hàng {code}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition"
            title="Làm mới số liệu"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin text-blue-600" : ""}`} />
            <span>Làm mới</span>
          </button>
          <button
            onClick={() => handleNavigate("import")}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-2xs transition"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>Nạp Excel mới</span>
          </button>
        </div>
      </div>

      {/* 2. Lưới thẻ KPI thực tế (KPI Cards Grid) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Tổng tồn kho kỳ mới nhất */}
        <KpiCard
          title={`Tồn kho kỳ mới (${latest ? `#${latest.ticket_number}` : "Chưa có"})`}
          value={latest ? formatNumber(latest.total_quantity) : "0"}
          subtitle={
            latest
              ? `Kỳ ${latest.inventory_date} (${latest.shift}) • ${latest.store_code}`
              : "Chưa có chứng từ hoàn tất"
          }
          icon={Package}
          trend={
            trend.has_comparison
              ? {
                  value: `${trend.delta_quantity >= 0 ? "+" : ""}${formatNumber(trend.delta_quantity)} SP`,
                  isPositive: trend.delta_quantity >= 0
                }
              : undefined
          }
          iconBgColor="bg-blue-50 text-blue-600"
        />

        {/* KPI 2: Tổng giá trị tồn kho (VND) */}
        <KpiCard
          title="Tổng giá trị tồn (VND)"
          value={latest ? formatVnd(latest.total_amount_vnd) : "0 đ"}
          subtitle="Theo đơn giá sau VAT chuẩn hóa"
          icon={DollarSign}
          trend={
            trend.has_comparison
              ? {
                  value: `${trend.delta_amount_vnd >= 0 ? "+" : ""}${formatVnd(trend.delta_amount_vnd)}`,
                  isPositive: trend.delta_amount_vnd >= 0
                }
              : undefined
          }
          iconBgColor="bg-emerald-50 text-emerald-600"
        />

        {/* KPI 3: Số mặt hàng theo dõi */}
        <KpiCard
          title="Số mặt hàng theo dõi"
          value={latest ? `${formatNumber(latest.total_sku_count)} mặt hàng` : "0 mặt hàng"}
          subtitle={latest ? `Cửa hàng ${latest.store_code}` : "Đang chờ nạp"}
          icon={Files}
          iconBgColor="bg-purple-50 text-purple-600"
        />

        {/* KPI 4: Thống kê Chứng từ kiểm kê */}
        <KpiCard
          title="Chứng từ đã lưu trữ"
          value={`${summary.completed_snapshots} / ${summary.total_snapshots}`}
          subtitle={`${summary.staging_snapshots} chờ duyệt • ${summary.failed_snapshots} lỗi`}
          icon={Layers}
          iconBgColor="bg-amber-50 text-amber-600"
        />
      </div>

      {/* 3. Banner Thao tác nhanh & Đối soát CÙNG CỬA HÀNG VÀ CÙNG PHẠM VI (P1 Scope Isolation) */}
      {trend.has_comparison && latest && previous && latest.store_code === previous.store_code ? (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-xl p-5 text-white shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-white/20 rounded-full text-[11px] font-semibold text-blue-100">
              <RefreshCw className="w-3 h-3" />
              <span>
                Đối soát Nhanh Tức thì • Cùng Cửa hàng {latest.store_code}
                {latest.scope_id != null ? ` (Kho #${latest.scope_id})` : " (Toàn cửa hàng)"}
              </span>
            </div>
            <h3 className="text-base font-bold text-white">
              Phát hiện 2 kỳ kiểm kê liên tiếp ({previous.ticket_number} → {latest.ticket_number})
            </h3>
            <p className="text-xs text-blue-100 max-w-2xl">
              Biến động giữa kỳ {previous.inventory_date} ({previous.shift}) và kỳ {latest.inventory_date} ({latest.shift}):{" "}
              <strong>{trend.delta_quantity >= 0 ? `+${formatNumber(trend.delta_quantity)}` : formatNumber(trend.delta_quantity)} SP</strong>{" "}
              ({trend.delta_amount_vnd >= 0 ? `+${formatVnd(trend.delta_amount_vnd)}` : formatVnd(trend.delta_amount_vnd)}).
            </p>
          </div>

          <button
            onClick={() => handleNavigate("compare", previous.id, latest.id)}
            className="shrink-0 px-4 py-2.5 bg-white text-blue-700 hover:bg-blue-50 font-bold text-xs rounded-lg shadow-sm transition flex items-center gap-2 cursor-pointer"
          >
            <span>Mở Đối Soát Chi Tiết</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      ) : latest ? (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-slate-600 text-xs">
          <div className="flex items-center gap-2.5">
            <Info className="w-4 h-4 text-slate-500 shrink-0" />
            <span>
              {trend.scope_message ||
                (selectedStore
                  ? `Cửa hàng ${selectedStore} hiện có 1 kỳ kiểm kê hoàn tất (#${latest.ticket_number}). Cần thêm kỳ kiểm kê tiếp theo cùng phạm vi kho để tính toán biến động tồn.`
                  : `Kỳ kiểm kê mới nhất thuộc Cửa hàng ${latest.store_code} (#${latest.ticket_number}). Hệ thống chỉ tính biến động giữa các kỳ cùng cửa hàng và cùng phạm vi kho.`)}
            </span>
          </div>
          <button
            onClick={() => handleNavigate("import")}
            className="text-xs font-semibold text-blue-600 hover:text-blue-700 shrink-0 inline-flex items-center gap-1"
          >
            <span>Nạp thêm file Excel</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : null}

      {/* 4. Bảng Chứng từ Kiểm kê Gần nhất */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-2xs">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-900 text-sm">Các Đợt Kiểm kê Mới Nhất</h3>
            <p className="text-xs text-slate-500 mt-0.5">Dữ liệu ghi nhận từ hệ thống Staging và Cloudflare D1</p>
          </div>
          <button
            onClick={() => handleNavigate("snapshots")}
            className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1 transition"
          >
            <span>Xem toàn bộ ({summary.total_snapshots})</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50/80 text-slate-600 border-b border-slate-100 uppercase tracking-wider font-semibold">
              <tr>
                <th className="py-3 px-4">Mã chứng từ</th>
                <th className="py-3 px-4">Ngày & Ca</th>
                <th className="py-3 px-4 text-center">Cửa hàng</th>
                <th className="py-3 px-4 text-right">Số SKU</th>
                <th className="py-3 px-4 text-right">Tổng tồn kho</th>
                <th className="py-3 px-4 text-right">Tổng thành tiền (VND)</th>
                <th className="py-3 px-4 text-center">Trạng thái</th>
                <th className="py-3 px-4 text-center">Hành động</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {recentSnapshots.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">
                    Chưa có chứng từ kiểm kê nào trong hệ thống.
                  </td>
                </tr>
              ) : (
                recentSnapshots.map((s: any) => (
                  <tr key={s.id} className="hover:bg-slate-50/70 transition">
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">
                      {s.full_code}
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-semibold text-slate-900">{s.inventory_date}</span>
                      {s.inventory_time && <span className="ml-1 text-slate-400">({s.inventory_time})</span>}
                      <span className="ml-1.5 px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                        Ca {s.shift}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[11px] font-semibold">
                        {s.store_code}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-medium">{formatNumber(s.total_sku_count)}</td>
                    <td className="py-3 px-4 text-right font-bold text-slate-900">
                      {formatNumber(s.total_quantity)}
                    </td>
                    <td className="py-3 px-4 text-right font-semibold text-emerald-700">
                      {formatVnd(s.total_amount_vnd)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {getStatusBadge(s.status)}
                    </td>
                    <td className="py-3 px-4 text-center">
                      {s.status === "COMPLETED" ? (
                        <button
                          onClick={() => handleNavigate("compare", s.id)}
                          className="px-2.5 py-1 text-[11px] font-semibold text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded border border-blue-200 transition"
                          title="Đối soát chứng từ này với snapshot khác"
                        >
                          Đối soát
                        </button>
                      ) : (
                        <span className="text-[11px] text-slate-400">—</span>
                      )}
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
