/**
 * Page: So sánh Đối soát Tồn kho (Stock Reconciliation & Comparison)
 * File: apps/web/src/pages/ComparePage.tsx (Round 05)
 *
 * Tiêu chuẩn & Quy tắc:
 * 1. Phép tính biến động: B.quantity - A.quantity (QUY TẮC BẮT BUỘC)
 * 2. So sánh 2 snapshot bất kỳ (cùng ngày hoặc khác ngày)
 * 3. Phân loại: Tăng tồn, Giảm tồn, Mới xuất hiện, Hết tồn, Không đổi
 * 4. Xem lịch sử diễn biến SKU qua các kỳ kiểm kê
 * 5. Xuất báo cáo CSV đối soát
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { EmptyState } from "../components/EmptyState";
import {
  ArrowUpDown,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  Sparkles,
  AlertTriangle,
  Download,
  Search,
  Filter,
  History,
  TrendingUp,
  TrendingDown,
  Layers,
  DollarSign,
  Package,
  Calendar,
  Clock,
  X
} from "lucide-react";
import { SnapshotCombobox } from "../components/SnapshotCombobox";
import { ComparisonItem, ComparisonStatus, ProductHistoryPoint, ProductHistoryResponse } from "@inventory/shared";

export const ComparePage: React.FC = () => {
  const [baseId, setBaseId] = useState<number | null>(null);
  const [targetId, setTargetId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [warehouseFilter, setWarehouseFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [page, setPage] = useState<number>(1);
  const [selectedSkuForHistory, setSelectedSkuForHistory] = useState<string | null>(null);

  // 1. Tự động nhận diện Snapshot A và B từ URL query param, sessionStorage hoặc nạp 2 snapshot COMPLETED mới nhất
  React.useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const qBaseId = urlParams.get("base_id") ? Number(urlParams.get("base_id")) : null;
    const qTargetId = urlParams.get("target_id") ? Number(urlParams.get("target_id")) : null;

    if (qBaseId && qTargetId) {
      setBaseId(qBaseId);
      setTargetId(qTargetId);
      return;
    }

    try {
      const stored = sessionStorage.getItem("vinamilk_compare_selection");
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.baseId && parsed.targetId) {
          setBaseId(parsed.baseId);
          setTargetId(parsed.targetId);
          sessionStorage.removeItem("vinamilk_compare_selection");
          return;
        }
      }
    } catch (e) {
      // ignore
    }

    // Nếu chưa có, tự động nạp 2 snapshot COMPLETED mới nhất
    api.getSnapshots({ page: 1, limit: 2, status: "COMPLETED" }).then((res) => {
      if (res.success && res.data?.items && res.data.items.length > 0) {
        const items = res.data.items;
        if (items.length >= 2) {
          setBaseId((prev) => (prev === null ? items[1].id : prev));
          setTargetId((prev) => (prev === null ? items[0].id : prev));
        } else if (items.length === 1) {
          setBaseId((prev) => (prev === null ? items[0].id : prev));
          setTargetId((prev) => (prev === null ? items[0].id : prev));
        }
      }
    });
  }, []);

  // 2. Tải kết quả so sánh giữa Snapshot A và Snapshot B
  const {
    data: comparisonData,
    isLoading: isLoadingComparison,
    error: comparisonError,
    refetch: refetchComparison
  } = useQuery({
    queryKey: ["comparison", baseId, targetId, statusFilter, warehouseFilter, searchQuery, page],
    queryFn: () => {
      if (!baseId || !targetId) return null;
      return api.compareSnapshots({
        base_id: baseId,
        target_id: targetId,
        status: statusFilter,
        warehouse: warehouseFilter,
        search: searchQuery,
        page,
        limit: 50
      });
    },
    enabled: Boolean(baseId && targetId)
  });

  // 3. Tải lịch sử SKU khi mở modal
  const { data: historyData, isLoading: isLoadingHistory } = useQuery({
    queryKey: ["sku-history", selectedSkuForHistory],
    queryFn: () => {
      if (!selectedSkuForHistory) return null;
      return api.getProductHistory(selectedSkuForHistory);
    },
    enabled: Boolean(selectedSkuForHistory)
  });

  // Đổi chiều so sánh A <-> B
  const handleSwap = () => {
    const temp = baseId;
    setBaseId(targetId);
    setTargetId(temp);
    setPage(1);
  };

  const formatVnd = (val: number) => {
    return new Intl.NumberFormat("vi-VN").format(val) + " đ";
  };

  const formatNumber = (val: number) => {
    return new Intl.NumberFormat("vi-VN").format(val);
  };

  const getStatusBadge = (status: ComparisonStatus, label: string) => {
    switch (status) {
      case "INCREASED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <ArrowUpRight className="w-3.5 h-3.5" />
            {label}
          </span>
        );
      case "DECREASED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <ArrowDownRight className="w-3.5 h-3.5" />
            {label}
          </span>
        );
      case "NEW_ADDED":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
            <Sparkles className="w-3.5 h-3.5" />
            {label}
          </span>
        );
      case "OUT_OF_STOCK":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle className="w-3.5 h-3.5" />
            {label}
          </span>
        );
      case "NOT_PRESENT":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300">
            <X className="w-3.5 h-3.5" />
            {label}
          </span>
        );
      case "NO_CHANGE":
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-50 text-slate-600 border border-slate-200">
            <CheckCircle2 className="w-3.5 h-3.5" />
            {label}
          </span>
        );
    }
  };

  const summary = comparisonData?.data?.summary;
  const items: ComparisonItem[] = comparisonData?.data?.items || [];
  const pagination = comparisonData?.data?.pagination;

  return (
    <div className="space-y-6">
      {/* 1. THANH CHỌN HAI SNAPSHOT ĐỐI SOÁT (SEARCHABLE ASYNC COMBOBOX - ROUND 06) */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-4">
          {/* Bộ chọn Kỳ gốc (A) */}
          <div className="flex-1 w-full">
            <SnapshotCombobox
              label="Kỳ gốc (A)"
              badgeText="Kỳ gốc"
              badgeColor="blue"
              selectedId={baseId}
              disabledId={targetId}
              onSelect={(id) => {
                setBaseId(id);
                setPage(1);
              }}
              placeholder="Tìm và chọn kỳ gốc (A)..."
            />
          </div>

          {/* Nút Hoán đổi chiều so sánh */}
          <div className="flex flex-col items-center justify-center pt-5">
            <button
              onClick={handleSwap}
              title="Đổi chiều đối soát (A ↔ B)"
              className="p-3 rounded-full border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 shadow-xs transition hover:scale-105 active:scale-95 group"
            >
              <ArrowUpDown className="w-5 h-5 text-blue-600 group-hover:rotate-180 transition-transform duration-300" />
            </button>
            <span className="text-[10px] text-slate-400 mt-1 font-medium">Đổi chiều</span>
          </div>

          {/* Bộ chọn Kỳ đối soát (B) */}
          <div className="flex-1 w-full">
            <SnapshotCombobox
              label="Kỳ đối soát (B)"
              badgeText="Kỳ đối soát"
              badgeColor="emerald"
              selectedId={targetId}
              disabledId={baseId}
              onSelect={(id) => {
                setTargetId(id);
                setPage(1);
              }}
              placeholder="Tìm và chọn kỳ đối soát (B)..."
            />
          </div>

          {/* Nút Xuất Báo cáo CSV */}
          {baseId && targetId && (
            <div className="pt-5 w-full lg:w-auto">
              <a
                href={api.getExportComparisonUrl(baseId, targetId, {
                  status: statusFilter,
                  warehouse: warehouseFilter,
                  search: searchQuery
                })}
                download
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-sm shadow-sm transition"
              >
                <Download className="w-4 h-4" />
                <span>Xuất file CSV</span>
              </a>
            </div>
          )}
        </div>
      </div>

      {/* CẢNH BÁO PHẠM VI NẾU HAI SNAPSHOT THUỘC HAI CỬA HÀNG KHÁC NHAU */}
      {summary?.scope_warning && (
        <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-xl flex items-start gap-3 shadow-sm">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-bold text-amber-900">Cảnh báo phạm vi đối soát</h4>
            <p className="text-xs text-amber-800 mt-0.5 leading-relaxed">
              {summary.scope_warning}
            </p>
          </div>
        </div>
      )}

      {/* 2. KHỐI THẺ KPI TỔNG QUAN BIẾN ĐỘNG */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-9 gap-3">
          {/* Biến động SL Net */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm col-span-2 lg:col-span-2">
            <div className="flex items-center justify-between text-slate-500 mb-1">
              <span className="text-xs font-semibold uppercase tracking-wider">Tổng chênh lệch tồn kho (B − A)</span>
              {summary.delta_quantity >= 0 ? (
                <TrendingUp className="w-4 h-4 text-emerald-500" />
              ) : (
                <TrendingDown className="w-4 h-4 text-rose-500" />
              )}
            </div>
            <div
              className={`text-2xl font-bold ${
                summary.delta_quantity > 0
                  ? "text-emerald-600"
                  : summary.delta_quantity < 0
                  ? "text-rose-600"
                  : "text-slate-800"
              }`}
            >
              {summary.delta_quantity > 0 ? `+${formatNumber(summary.delta_quantity)}` : formatNumber(summary.delta_quantity)}
            </div>
            <div className="text-xs text-slate-400 mt-1 flex justify-between">
              <span>A: {formatNumber(summary.base_total_quantity)}</span>
              <span>B: {formatNumber(summary.target_total_quantity)}</span>
            </div>
          </div>

          {/* Biến động Giá trị Net */}
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm col-span-2 lg:col-span-2">
            <div className="flex items-center justify-between text-slate-500 mb-1">
              <span className="text-xs font-semibold uppercase tracking-wider">Tổng chênh lệch thành tiền (VND)</span>
              <DollarSign className="w-4 h-4 text-slate-400" />
            </div>
            <div
              className={`text-xl font-bold ${
                summary.delta_amount > 0
                  ? "text-emerald-600"
                  : summary.delta_amount < 0
                  ? "text-rose-600"
                  : "text-slate-800"
              }`}
            >
              {summary.delta_amount > 0 ? `+${formatVnd(summary.delta_amount)}` : formatVnd(summary.delta_amount)}
            </div>
            <div className="text-xs text-slate-400 mt-1 truncate">
              <span>Độ lệch giá trị sau VAT</span>
            </div>
          </div>

          {/* Số SKU Tăng */}
          <div
            onClick={() => {
              setStatusFilter("INCREASED");
              setPage(1);
            }}
            className={`cursor-pointer p-3 rounded-xl border transition ${
              statusFilter === "INCREASED"
                ? "bg-emerald-50 border-emerald-400 shadow-sm"
                : "bg-white border-slate-200 hover:border-emerald-300"
            }`}
          >
            <div className="text-xs font-semibold text-emerald-700 flex items-center justify-between">
              <span>Tăng tồn</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </div>
            <div className="text-lg font-bold text-emerald-700 mt-1">{summary.increased_count}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">mặt hàng</div>
          </div>

          {/* Số SKU Giảm */}
          <div
            onClick={() => {
              setStatusFilter("DECREASED");
              setPage(1);
            }}
            className={`cursor-pointer p-3 rounded-xl border transition ${
              statusFilter === "DECREASED"
                ? "bg-rose-50 border-rose-400 shadow-sm"
                : "bg-white border-slate-200 hover:border-rose-300"
            }`}
          >
            <div className="text-xs font-semibold text-rose-700 flex items-center justify-between">
              <span>Giảm tồn</span>
              <ArrowDownRight className="w-3.5 h-3.5" />
            </div>
            <div className="text-lg font-bold text-rose-700 mt-1">{summary.decreased_count}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">mặt hàng</div>
          </div>

          {/* Số SKU Mới */}
          <div
            onClick={() => {
              setStatusFilter("NEW_ADDED");
              setPage(1);
            }}
            className={`cursor-pointer p-3 rounded-xl border transition ${
              statusFilter === "NEW_ADDED"
                ? "bg-purple-50 border-purple-400 shadow-sm"
                : "bg-white border-slate-200 hover:border-purple-300"
            }`}
          >
            <div className="text-xs font-semibold text-purple-700 flex items-center justify-between">
              <span>Mới ở B</span>
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <div className="text-lg font-bold text-purple-700 mt-1">{summary.new_count}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">mặt hàng</div>
          </div>

          {/* Số SKU Không xuất hiện ở B */}
          <div
            onClick={() => {
              setStatusFilter("NOT_PRESENT");
              setPage(1);
            }}
            className={`cursor-pointer p-3 rounded-xl border transition ${
              statusFilter === "NOT_PRESENT"
                ? "bg-slate-100 border-slate-400 shadow-sm"
                : "bg-white border-slate-200 hover:border-slate-300"
            }`}
          >
            <div className="text-xs font-semibold text-slate-700 flex items-center justify-between">
              <span>Vắng mặt</span>
              <X className="w-3.5 h-3.5 text-slate-400" />
            </div>
            <div className="text-lg font-bold text-slate-700 mt-1">{summary.not_present_count || 0}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">không có ở B</div>
          </div>

          {/* Số SKU Hết tồn (SL = 0) */}
          <div
            onClick={() => {
              setStatusFilter("OUT_OF_STOCK");
              setPage(1);
            }}
            className={`cursor-pointer p-3 rounded-xl border transition ${
              statusFilter === "OUT_OF_STOCK"
                ? "bg-amber-50 border-amber-400 shadow-sm"
                : "bg-white border-slate-200 hover:border-amber-300"
            }`}
          >
            <div className="text-xs font-semibold text-amber-700 flex items-center justify-between">
              <span>Hết tồn</span>
              <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            </div>
            <div className="text-lg font-bold text-amber-700 mt-1">{summary.out_of_stock_count}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">SL = 0 ở B</div>
          </div>
        </div>
      )}

      {/* 3. THANH CÔNG CỤ TÌM KIẾM & BỘ LỌC */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          {/* Lọc Trạng thái */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="bg-transparent font-medium text-slate-700 focus:outline-none"
            >
              <option value="ALL">Tất cả trạng thái ({summary?.total_sku_union || 0})</option>
              <option value="INCREASED">Tăng tồn ({summary?.increased_count || 0})</option>
              <option value="DECREASED">Giảm tồn ({summary?.decreased_count || 0})</option>
              <option value="NEW_ADDED">Mới xuất hiện ở kỳ B ({summary?.new_count || 0})</option>
              <option value="NOT_PRESENT">Không xuất hiện ở kỳ B ({summary?.not_present_count || 0})</option>
              <option value="OUT_OF_STOCK">Hết tồn (SL = 0) ({summary?.out_of_stock_count || 0})</option>
              <option value="NO_CHANGE">Không đổi ({summary?.unchanged_count || 0})</option>
            </select>
          </div>

          {/* Lọc Loại kho */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs">
            <Layers className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={warehouseFilter}
              onChange={(e) => {
                setWarehouseFilter(e.target.value);
                setPage(1);
              }}
              className="bg-transparent font-medium text-slate-700 focus:outline-none"
            >
              <option value="">Tất cả loại kho</option>
              <option value="Kho hàng bán">Kho hàng bán</option>
              <option value="Kho hàng vật phẩm KM">Kho hàng vật phẩm KM</option>
            </select>
          </div>

          {(statusFilter !== "ALL" || warehouseFilter || searchQuery) && (
            <button
              onClick={() => {
                setStatusFilter("ALL");
                setWarehouseFilter("");
                setSearchQuery("");
                setPage(1);
              }}
              className="text-xs text-rose-600 hover:text-rose-700 font-medium px-2 py-1"
            >
              Xóa bộ lọc
            </button>
          )}
        </div>

        {/* Ô Tìm kiếm SKU hoặc Tên */}
        <div className="relative w-full md:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Tìm mã SKU (vd: 02AA15) hoặc tên SP..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="w-full text-xs pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition"
          />
        </div>
      </div>

      {/* 4. BẢNG DỮ LIỆU ĐỐI SOÁT CHI TIẾT */}
      {isLoadingComparison ? (
        <div className="bg-white rounded-xl border border-slate-200 p-12">
          <LoadingState message="Đang phân tích và đối soát số liệu giữa 2 snapshot..." />
        </div>
      ) : comparisonError ? (
        <ErrorState
          title="Không thể thực hiện đối soát"
          message={(comparisonError as any)?.message || "Vui lòng kiểm tra lại 2 snapshot đã chọn."}
          onRetry={refetchComparison}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="Không tìm thấy mặt hàng phù hợp"
          description="Không có sản phẩm nào khớp với điều kiện lọc hiện tại."
        />
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-3 w-12 text-center">STT</th>
                  <th className="py-3 px-3">Mã SKU</th>
                  <th className="py-3 px-3">Tên sản phẩm</th>
                  <th className="py-3 px-3">Ngành hàng</th>
                  <th className="py-3 px-3">Loại kho</th>
                  <th className="py-3 px-3 text-right">Tồn A ({summary?.base_snapshot.ticket_number})</th>
                  <th className="py-3 px-3 text-right">Tồn B ({summary?.target_snapshot.ticket_number})</th>
                  <th className="py-3 px-3 text-right">Biến động SL (B - A)</th>
                  <th className="py-3 px-3 text-right">% Biến động</th>
                  <th className="py-3 px-3 text-right">Biến động Tiền</th>
                  <th className="py-3 px-3 text-center">Trạng thái</th>
                  <th className="py-3 px-3 text-center">Lịch sử</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((it, idx) => {
                  const rowStt = ((pagination?.page || 1) - 1) * (pagination?.limit || 50) + idx + 1;
                  return (
                    <tr key={`${it.product_code}-${it.warehouse}`} className="hover:bg-slate-50/80 transition">
                      <td className="py-2.5 px-3 text-center text-slate-400 font-mono">{rowStt}</td>
                      <td className="py-2.5 px-3 font-mono font-semibold text-slate-900">
                        <span className="bg-slate-100 text-slate-800 px-1.5 py-0.5 rounded text-[11px]">
                          {it.product_code}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 font-medium text-slate-800 max-w-xs truncate" title={it.product_name}>
                        {it.product_name}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">{it.category}</td>
                      <td className="py-2.5 px-3 text-slate-500">
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-full ${
                            it.warehouse === "Kho hàng bán"
                              ? "bg-blue-50 text-blue-700"
                              : "bg-amber-50 text-amber-700"
                          }`}
                        >
                          {it.warehouse}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-slate-600 font-mono">
                        {it.base_quantity !== null ? formatNumber(it.base_quantity) : <span className="text-slate-300">-</span>}
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-slate-900 font-mono">
                        {it.target_quantity !== null ? formatNumber(it.target_quantity) : <span className="text-slate-300">-</span>}
                      </td>
                      <td
                        className={`py-2.5 px-3 text-right font-bold font-mono ${
                          it.delta_quantity !== null && it.delta_quantity > 0
                            ? "text-emerald-600"
                            : it.delta_quantity !== null && it.delta_quantity < 0
                            ? "text-rose-600"
                            : "text-slate-400"
                        }`}
                      >
                        {it.delta_quantity !== null ? (
                          it.delta_quantity > 0 ? `+${formatNumber(it.delta_quantity)}` : formatNumber(it.delta_quantity)
                        ) : (
                          <span className="text-slate-300">-</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-slate-500">
                        {it.percentage_change !== null ? (
                          <span
                            className={
                              it.percentage_change > 0
                                ? "text-emerald-600 font-semibold"
                                : it.percentage_change < 0
                                ? "text-rose-600 font-semibold"
                                : "text-slate-400"
                            }
                          >
                            {it.percentage_change > 0 ? `+${it.percentage_change}%` : `${it.percentage_change}%`}
                          </span>
                        ) : (
                          <span className="text-slate-300">-</span>
                        )}
                      </td>
                      <td
                        className={`py-2.5 px-3 text-right font-medium ${
                          it.delta_amount !== null && it.delta_amount > 0
                            ? "text-emerald-600"
                            : it.delta_amount !== null && it.delta_amount < 0
                            ? "text-rose-600"
                            : "text-slate-400"
                        }`}
                      >
                        {it.delta_amount !== null ? (
                          it.delta_amount > 0 ? `+${formatVnd(it.delta_amount)}` : formatVnd(it.delta_amount)
                        ) : (
                          <span className="text-slate-300">-</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {getStatusBadge(it.status, it.status_label_vi)}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <button
                          onClick={() => setSelectedSkuForHistory(it.product_code)}
                          title="Xem lịch sử biến động qua các đợt kiểm kê"
                          className="p-1 text-slate-400 hover:text-primary hover:bg-slate-100 rounded transition"
                        >
                          <History className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Phân trang */}
          {pagination && pagination.total_pages > 1 && (
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
              <div>
                Hiển thị trang <strong>{pagination.page}</strong> / <strong>{pagination.total_pages}</strong> (Tổng cộng{" "}
                {pagination.total} mặt hàng)
              </div>
              <div className="flex items-center gap-1">
                <button
                  disabled={pagination.page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1.5 border border-slate-200 rounded bg-white font-medium hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-white transition"
                >
                  Trang trước
                </button>
                <button
                  disabled={pagination.page >= pagination.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-3 py-1.5 border border-slate-200 rounded bg-white font-medium hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-white transition"
                >
                  Trang sau
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 5. MODAL XEM LỊCH SỬ BIẾN ĐỘNG THEO SKU */}
      {selectedSkuForHistory && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Header Modal */}
            <div className="p-5 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-primary/10 text-primary rounded-xl">
                  <History className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    Lịch sử Biến động Sản phẩm: {selectedSkuForHistory}
                  </h3>
                  <p className="text-xs text-slate-500">
                    {historyData?.data?.product_name} ({historyData?.data?.category})
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedSkuForHistory(null)}
                className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Nội dung Timeline Modal */}
            <div className="p-6 overflow-y-auto space-y-4">
              {isLoadingHistory ? (
                <LoadingState message="Đang tải chuỗi lịch sử SKU..." />
              ) : !historyData?.data?.history || historyData.data.history.length === 0 ? (
                <EmptyState title="Không có dữ liệu lịch sử" description="Chưa có dữ liệu kiểm kê cho sản phẩm này." />
              ) : (
                <div className="relative border-l-2 border-slate-200 ml-4 space-y-6 py-2">
                  {historyData.data.history.map((pt: ProductHistoryPoint, i: number) => (
                    <div key={`${pt.snapshot_id}-${pt.warehouse}-${i}`} className="relative pl-6">
                      {/* Điểm mốc trên trục thời gian */}
                      <span className="absolute -left-[9px] top-1 w-4 h-4 rounded-full border-2 border-white bg-primary shadow-sm"></span>

                      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 hover:border-primary/40 transition">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-900 text-sm">{pt.ticket_number}</span>
                            <span className="text-xs bg-slate-200 text-slate-700 px-2 py-0.5 rounded-full">
                              {pt.shift}
                            </span>
                            <span className="text-xs text-slate-500 font-mono">{pt.warehouse}</span>
                          </div>
                          <div className="flex items-center gap-1.5 text-xs text-slate-400">
                            <Calendar className="w-3.5 h-3.5" />
                            <span>{pt.inventory_date}</span>
                            {pt.inventory_time && (
                              <>
                                <Clock className="w-3.5 h-3.5 ml-1" />
                                <span>{pt.inventory_time}</span>
                              </>
                            )}
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-200/60 text-xs">
                          <div>
                            <span className="text-slate-400 block">Số lượng tồn:</span>
                            <span className="font-bold text-slate-800 text-sm font-mono">
                              {formatNumber(pt.quantity)}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400 block">Biến động so với kỳ trước:</span>
                            {pt.delta_quantity !== null ? (
                              <span
                                className={`font-bold font-mono text-sm ${
                                  pt.delta_quantity > 0
                                    ? "text-emerald-600"
                                    : pt.delta_quantity < 0
                                    ? "text-rose-600"
                                    : "text-slate-500"
                                }`}
                              >
                                {pt.delta_quantity > 0 ? `+${formatNumber(pt.delta_quantity)}` : formatNumber(pt.delta_quantity)}
                              </span>
                            ) : (
                              <span className="text-slate-400 text-xs">Mốc bắt đầu</span>
                            )}
                          </div>
                          <div>
                            <span className="text-slate-400 block">Thành tiền VND:</span>
                            <span className="font-medium text-slate-700">{formatVnd(pt.total_amount)}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer Modal */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setSelectedSkuForHistory(null)}
                className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 font-semibold rounded-lg text-xs transition"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
