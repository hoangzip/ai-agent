/**
 * Page: Lịch sử Biến động Sản phẩm (SKU History Timeline)
 * File: apps/web/src/pages/HistoryPage.tsx (Round 05)
 *
 * Cho phép tra cứu diễn biến tồn kho, đơn giá và thành tiền của từng SKU
 * xuyên suốt các mốc kiểm kê (snapshots) theo thứ tự thời gian.
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { EmptyState } from "../components/EmptyState";
import {
  Search,
  History,
  TrendingUp,
  TrendingDown,
  Minus,
  Calendar,
  Clock,
  Package,
  Layers,
  ArrowRight,
  Sparkles,
  FileText
} from "lucide-react";
import { ProductHistoryPoint } from "@inventory/shared";

const SUGGESTED_SKUS = [
  { code: "07KD12", name: "Sữa tươi TH 180ml / SP biến động ngày 11/10" },
  { code: "04FT32", name: "Sữa chua uống / SP giảm tồn ca 2" },
  { code: "02AO18", name: "Sản phẩm mới xuất hiện từ ngày 10/10" },
  { code: "9NH277", name: "Mặt hàng khuyến mãi mới" },
  { code: "07NH12", name: "Sữa tươi tiệt trùng" }
];

export const HistoryPage: React.FC = () => {
  const [searchInput, setSearchInput] = useState<string>("07KD12");
  const [activeSku, setActiveSku] = useState<string>("07KD12");

  const { data: historyData, isLoading, isError, error } = useQuery({
    queryKey: ["product-history", activeSku],
    queryFn: () => api.getProductHistory(activeSku),
    enabled: !!activeSku.trim()
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      setActiveSku(searchInput.trim());
    }
  };

  const history = historyData?.data;
  const points: ProductHistoryPoint[] = history?.history || [];

  return (
    <div className="space-y-6">
      {/* 1. Header & Search Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="max-w-3xl">
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <History className="w-5 h-5 text-primary" />
            Tra cứu Lịch sử Biến động Tồn kho theo Mã SKU
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Theo dõi chuỗi thời gian kiểm kê, thay đổi số lượng, biến động thành tiền và tình trạng tồn kho của từng sản phẩm.
          </p>

          <form onSubmit={handleSearch} className="mt-4 flex gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Nhập mã sản phẩm SKU (ví dụ: 07KD12, 02AO18, 04FT32)..."
                className="w-full pl-9 pr-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary font-mono"
              />
            </div>
            <button
              type="submit"
              className="px-5 py-2.5 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary/90 transition shadow-sm flex items-center gap-2"
            >
              <Search className="w-4 h-4" />
              Tra cứu
            </button>
          </form>

          {/* Quick suggestions */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400">Gợi ý SKU tiêu biểu:</span>
            {SUGGESTED_SKUS.map((item) => (
              <button
                key={item.code}
                onClick={() => {
                  setSearchInput(item.code);
                  setActiveSku(item.code);
                }}
                className={`text-xs px-2.5 py-1 rounded-full border transition font-mono ${
                  activeSku === item.code
                    ? "bg-primary/10 border-primary text-primary font-bold"
                    : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100"
                }`}
                title={item.name}
              >
                {item.code}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 2. Loading / Error / Content */}
      {isLoading ? (
        <LoadingState message={`Đang tải dữ liệu lịch sử của SKU ${activeSku}...`} />
      ) : isError ? (
        <ErrorState
          message={`Lỗi tra cứu lịch sử SKU: ${(error as any)?.message || "Không thể tải dữ liệu"}`}
        />
      ) : !history || points.length === 0 ? (
        <EmptyState
          title={`Không tìm thấy dữ liệu cho mã SKU: ${activeSku}`}
          description="Sản phẩm này chưa từng xuất hiện trong các snapshot kiểm kê đã nạp vào hệ thống."
        />
      ) : (
        <div className="space-y-6">
          {/* Summary Box */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 bg-slate-900 text-white rounded text-xs font-mono font-bold tracking-wider">
                    {history.product_code}
                  </span>
                  <h3 className="text-base font-bold text-slate-900">{history.product_name}</h3>
                </div>
                <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                  <span>Ngành hàng: <strong className="text-slate-800">{history.category || "—"}</strong></span>
                  <span>Tổng số mốc kiểm kê: <strong className="text-slate-800">{points.length} đợt</strong></span>
                  <span>
                    Mốc gần nhất:{" "}
                    <strong className="text-slate-800">
                      {points[points.length - 1]?.inventory_date} (SL: {points[points.length - 1]?.quantity})
                    </strong>
                  </span>
                </div>
              </div>

              {/* Latest Status Pill */}
              <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-lg p-3">
                <div className="text-right">
                  <div className="text-[11px] text-slate-400 uppercase font-semibold">Tồn kho hiện tại</div>
                  <div className="text-xl font-bold text-slate-900 font-mono">
                    {points[points.length - 1]?.quantity.toLocaleString("vi-VN")}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Timeline Table */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <Calendar className="w-4 h-4 text-primary" />
                Chuỗi diễn biến theo từng mốc kiểm kê
              </h4>
              <span className="text-xs text-slate-500">
                Thứ tự từ kỳ cũ đến kỳ mới nhất
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                    <th className="py-3 px-4">#</th>
                    <th className="py-3 px-4">Ngày kiểm kê</th>
                    <th className="py-3 px-4">Cửa hàng / Chứng từ</th>
                    <th className="py-3 px-4">Kho</th>
                    <th className="py-3 px-4 text-right">Số lượng</th>
                    <th className="py-3 px-4 text-right">Đơn giá (VNĐ)</th>
                    <th className="py-3 px-4 text-right">Thành tiền (VNĐ)</th>
                    <th className="py-3 px-4 text-right">Biến động SL (Δ)</th>
                    <th className="py-3 px-4 text-center">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-xs">
                  {points.map((pt, idx) => {
                    const deltaQty = pt.delta_quantity;
                    const deltaAmount = pt.delta_amount;

                    let statusBadge = (
                      <span className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-600 font-medium">
                        Kỳ gốc
                      </span>
                    );

                    if (deltaQty !== null) {
                      if (deltaQty > 0) {
                        statusBadge = (
                          <span className="px-2 py-0.5 rounded text-[11px] bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200 flex items-center gap-1 justify-center">
                            <TrendingUp className="w-3 h-3" /> Tăng (+{deltaQty})
                          </span>
                        );
                      } else if (deltaQty < 0) {
                        statusBadge = (
                          <span className="px-2 py-0.5 rounded text-[11px] bg-rose-50 text-rose-700 font-semibold border border-rose-200 flex items-center gap-1 justify-center">
                            <TrendingDown className="w-3 h-3" /> Giảm ({deltaQty})
                          </span>
                        );
                      } else {
                        statusBadge = (
                          <span className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-600 font-medium flex items-center gap-1 justify-center">
                            <Minus className="w-3 h-3" /> Không đổi
                          </span>
                        );
                      }
                    }

                    return (
                      <tr key={`${pt.snapshot_id}-${pt.warehouse}-${idx}`} className="hover:bg-slate-50/70 transition">
                        <td className="py-3 px-4 text-slate-400 font-mono">{idx + 1}</td>
                        <td className="py-3 px-4 font-semibold text-slate-800">
                          <div className="flex items-center gap-1.5">
                            <Calendar className="w-3.5 h-3.5 text-slate-400" />
                            {pt.inventory_date}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-slate-600">
                          <div className="font-mono text-xs">{pt.ticket_number}</div>
                          {pt.store_code && (
                            <span className="text-[10px] text-slate-400">CH: {pt.store_code}</span>
                          )}
                          {pt.shift && (
                            <span className="ml-1 text-[10px] text-slate-400">({pt.shift})</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-slate-600">
                          <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px]">
                            {pt.warehouse || "Kho chuẩn"}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-slate-900 text-sm">
                          {pt.quantity.toLocaleString("vi-VN")}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-slate-600">
                          {pt.unit_price.toLocaleString("vi-VN")}
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-slate-800">
                          {pt.total_amount.toLocaleString("vi-VN")}
                        </td>
                        <td className="py-3 px-4 text-right font-mono">
                          {deltaQty === null ? (
                            <span className="text-slate-400">-</span>
                          ) : deltaQty > 0 ? (
                            <span className="text-emerald-600 font-bold">+{deltaQty}</span>
                          ) : deltaQty < 0 ? (
                            <span className="text-rose-600 font-bold">{deltaQty}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-center">
                          {statusBadge}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
