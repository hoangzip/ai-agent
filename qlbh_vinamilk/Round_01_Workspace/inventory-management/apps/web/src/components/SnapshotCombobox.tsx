/**
 * Component: Searchable Async Combobox cho Snapshot (Round 06 Carryover P2)
 * File: apps/web/src/components/SnapshotCombobox.tsx
 *
 * Tính năng:
 * 1. Tìm kiếm bất đồng bộ (Async Debounced Search) theo:
 *    - Mã chứng từ (full_code)
 *    - Số phiếu (ticket_number)
 *    - Mã cửa hàng (store_code)
 *    - Ngày kiểm kê (inventory_date)
 *    - Ca kiểm kê (shift)
 * 2. Phân trang Server-side / Tải thêm: Giới hạn 20 snapshot mỗi trang, không tải tràn DOM.
 * 3. Chỉ lọc các snapshot COMPLETED và chưa xóa mềm (is_deleted = 0).
 * 4. Bảo toàn Snapshot được chọn sẵn (Pre-selected preservation):
 *    - Tự động nạp độc lập chi tiết snapshot nếu chưa có trong trang 1.
 *    - Xử lý ngoại lệ nếu snapshot bị xóa hoặc không hợp lệ kèm thông báo tiếng Việt.
 * 5. Hiển thị thông tin chứng từ chi tiết: Mã, Ca, Ngày, Giờ, Cửa hàng, Số lượng SKU, Tổng tồn kho, Tổng tiền.
 */

import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  Search,
  ChevronDown,
  Check,
  Calendar,
  Clock,
  Store,
  Package,
  Layers,
  AlertTriangle,
  X,
  Loader2,
  RefreshCw
} from "lucide-react";
import { api } from "../api/client";

export interface SnapshotOption {
  id: number;
  full_code: string;
  ticket_number: string;
  store_code: string;
  inventory_date: string;
  inventory_time?: string | null;
  shift: string;
  status: string;
  total_sku_count: number;
  total_quantity: number;
  total_amount_vnd: number;
  is_deleted?: number;
}

interface SnapshotComboboxProps {
  label: string;
  badgeText?: string;
  badgeColor?: "blue" | "emerald" | "amber" | "purple";
  selectedId: number | null;
  onSelect: (id: number | null, snapshot?: SnapshotOption | null) => void;
  disabledId?: number | null; // ID snapshot đối phương (để cảnh báo hoặc hiển thị ký hiệu)
  placeholder?: string;
  className?: string;
}

export const SnapshotCombobox: React.FC<SnapshotComboboxProps> = ({
  label,
  badgeText,
  badgeColor = "blue",
  selectedId,
  onSelect,
  disabledId,
  placeholder = "Tìm và chọn chứng từ kiểm kê...",
  className = ""
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [items, setItems] = useState<SnapshotOption[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [selectedSnapshot, setSelectedSnapshot] = useState<SnapshotOption | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Debounce tìm kiếm 300ms
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchTerm.trim());
    }, 300);
    return () => clearTimeout(handler);
  }, [searchTerm]);

  // Click outside để đóng dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Focus ô tìm kiếm khi mở popup
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Nạp trang đầu tiên hoặc khi đổi từ khóa tìm kiếm
  useEffect(() => {
    let isCancelled = false;

    const loadData = async () => {
      setIsLoading(true);
      setFetchError(null);
      try {
        const res = await api.getSnapshots({
          page: 1,
          limit: 20,
          status: "COMPLETED",
          search: debouncedSearch || undefined
        });

        if (isCancelled) return;

        if (res.success && res.data) {
          const fetchedItems: SnapshotOption[] = (res.data.items || []).filter(
            (s: any) => s.status === "COMPLETED" && (!s.is_deleted || s.is_deleted === 0)
          );
          setItems(fetchedItems);
          setPage(1);
          setTotalPages(res.data.pagination?.total_pages || 1);
          setTotalCount(res.data.pagination?.total || 0);
        } else {
          setFetchError(res.error?.message || "Không thể tải danh sách chứng từ.");
        }
      } catch (err: any) {
        if (!isCancelled) {
          setFetchError("Lỗi kết nối khi tải danh sách: " + (err.message || String(err)));
        }
      } finally {
        if (!isCancelled) setIsLoading(false);
      }
    };

    loadData();

    return () => {
      isCancelled = true;
    };
  }, [debouncedSearch]);

  // Tải thêm trang tiếp theo (Server-side Pagination / Infinite Scroll)
  const handleLoadMore = async () => {
    if (page >= totalPages || isLoadingMore) return;
    setIsLoadingMore(true);
    const nextPage = page + 1;
    try {
      const res = await api.getSnapshots({
        page: nextPage,
        limit: 20,
        status: "COMPLETED",
        search: debouncedSearch || undefined
      });

      if (res.success && res.data) {
        const newItems: SnapshotOption[] = (res.data.items || []).filter(
          (s: any) => s.status === "COMPLETED" && (!s.is_deleted || s.is_deleted === 0)
        );
        setItems((prev) => {
          // Tránh trùng lặp ID
          const existingIds = new Set(prev.map((i) => i.id));
          const uniqueNew = newItems.filter((i) => !existingIds.has(i.id));
          return [...prev, ...uniqueNew];
        });
        setPage(nextPage);
        setTotalPages(res.data.pagination?.total_pages || totalPages);
      }
    } catch (err) {
      console.error("Lỗi tải thêm snapshots:", err);
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Bảo toàn Snapshot được chọn sẵn (Pre-selected preservation)
  // Nếu selectedId nằm ngoài trang 1, chủ động fetch chi tiết snapshot đó
  useEffect(() => {
    let isCancelled = false;

    if (!selectedId) {
      setSelectedSnapshot(null);
      return;
    }

    // 1. Kiểm tra xem snapshot đã có trong items hiện có chưa
    const existing = items.find((i) => i.id === selectedId);
    if (existing) {
      setSelectedSnapshot(existing);
      return;
    }

    // 2. Nếu chưa có, fetch riêng bằng getSnapshot(id)
    const fetchPreselected = async () => {
      try {
        const res = await api.getSnapshot(selectedId, false);
        if (isCancelled) return;

        if (res.success && res.data) {
          const snap: SnapshotOption = res.data;
          // Kiểm tra tính hợp lệ: phải là COMPLETED và chưa xóa
          if (snap.is_deleted === 1 || snap.status !== "COMPLETED") {
            setFetchError(`Chứng từ ID ${selectedId} đã bị xóa hoặc chưa hoàn tất.`);
            setSelectedSnapshot(null);
            onSelect(null, null);
          } else {
            setSelectedSnapshot(snap);
            // Bổ sung vào đầu danh sách options để người dùng thấy
            setItems((prev) => {
              if (prev.some((p) => p.id === snap.id)) return prev;
              return [snap, ...prev];
            });
          }
        } else {
          setFetchError(`Chứng từ kiểm kê ID ${selectedId} không tồn tại.`);
          setSelectedSnapshot(null);
          onSelect(null, null);
        }
      } catch (err: any) {
        if (!isCancelled) {
          setFetchError("Không thể nạp chi tiết chứng từ đã chọn: " + (err.message || String(err)));
        }
      }
    };

    fetchPreselected();

    return () => {
      isCancelled = true;
    };
  }, [selectedId, items]);

  const handleSelectItem = (item: SnapshotOption) => {
    setSelectedSnapshot(item);
    onSelect(item.id, item);
    setIsOpen(false);
    setSearchTerm("");
  };

  const handleClearSelection = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedSnapshot(null);
    onSelect(null, null);
  };

  // Định dạng hiển thị
  const formatVnd = (val: number) => new Intl.NumberFormat("vi-VN").format(val) + " đ";
  const formatNum = (val: number) => new Intl.NumberFormat("vi-VN").format(val);

  const getShiftBadge = (shift: string) => {
    switch (shift) {
      case "Sáng":
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-100 text-sky-800">Ca Sáng</span>;
      case "Chiều":
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">Ca Chiều</span>;
      case "Tối":
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-100 text-indigo-800">Ca Tối</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">{shift || "Chưa rõ"}</span>;
    }
  };

  const badgeColorClasses = {
    blue: "bg-blue-100 text-blue-800 border-blue-200",
    emerald: "bg-emerald-100 text-emerald-800 border-emerald-200",
    amber: "bg-amber-100 text-amber-800 border-amber-200",
    purple: "bg-purple-100 text-purple-800 border-purple-200"
  };

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      {/* Tiêu đề & Nhãn */}
      <div className="flex items-center justify-between mb-1.5">
        <label className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
          {label}
          {badgeText && (
            <span className={`px-2 py-0.2 rounded-full text-[10px] font-bold border ${badgeColorClasses[badgeColor]}`}>
              {badgeText}
            </span>
          )}
        </label>
        {selectedSnapshot && (
          <button
            type="button"
            onClick={handleClearSelection}
            className="text-[11px] text-slate-400 hover:text-rose-600 transition-colors flex items-center gap-0.5"
            title="Bỏ chọn chứng từ này"
          >
            <X className="w-3 h-3" />
            Bỏ chọn
          </button>
        )}
      </div>

      {/* Nút bấm hiển thị Snapshot đã chọn (Trigger Button) */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full min-h-[58px] p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between bg-white ${
          isOpen
            ? "border-blue-500 ring-2 ring-blue-500/20 shadow-sm"
            : selectedSnapshot
            ? "border-slate-300 hover:border-slate-400 shadow-2xs"
            : "border-slate-200 hover:border-slate-300 bg-slate-50/50"
        }`}
      >
        {selectedSnapshot ? (
          <div className="flex-1 min-w-0 pr-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-xs font-bold text-slate-900 tracking-tight">
                {selectedSnapshot.full_code}
              </span>
              {getShiftBadge(selectedSnapshot.shift)}
              <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded font-medium">
                CH: {selectedSnapshot.store_code}
              </span>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-slate-500 truncate">
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3 text-slate-400" />
                {selectedSnapshot.inventory_date}
                {selectedSnapshot.inventory_time ? ` (${selectedSnapshot.inventory_time})` : ""}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 text-slate-700 font-medium">
                <Package className="w-3 h-3 text-slate-400" />
                {formatNum(selectedSnapshot.total_sku_count)} SKU ({formatNum(selectedSnapshot.total_quantity)} SP)
              </span>
              <span>•</span>
              <span className="text-emerald-700 font-semibold">{formatVnd(selectedSnapshot.total_amount_vnd)}</span>
            </div>
          </div>
        ) : (
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <Layers className="w-4 h-4 text-slate-300" />
            <span>{placeholder}</span>
          </div>
        )}

        <div className="flex items-center gap-1 shrink-0 text-slate-400">
          <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isOpen ? "rotate-180 text-blue-600" : ""}`} />
        </div>
      </div>

      {/* Cảnh báo lỗi fetch snapshot nếu có */}
      {fetchError && (
        <div className="mt-1 text-[11px] text-rose-600 flex items-center gap-1">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span>{fetchError}</span>
        </div>
      )}

      {/* Dropdown Menu & Async Search Box */}
      {isOpen && (
        <div className="absolute z-50 left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden animate-in fade-in-50 duration-150">
          {/* Thanh tìm kiếm trực tiếp trong dropdown */}
          <div className="p-2 border-b border-slate-100 bg-slate-50/80">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Tìm mã chứng từ, ngày, ca, mã CH41551..."
                className="w-full pl-9 pr-8 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-hidden focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Danh sách Snapshot */}
          <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
            {isLoading ? (
              <div className="p-6 text-center text-xs text-slate-500 flex flex-col items-center justify-center gap-2">
                <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                <span>Đang tìm kiếm chứng từ kiểm kê...</span>
              </div>
            ) : items.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                <Layers className="w-8 h-8 mx-auto text-slate-300 mb-2" />
                <p className="font-medium text-slate-700">Không tìm thấy chứng từ kiểm kê nào</p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {searchTerm ? `Thử thay đổi từ khóa "${searchTerm}"` : "Chưa có snapshot nào ở trạng thái Hoàn tất"}
                </p>
              </div>
            ) : (
              items.map((item) => {
                const isSelected = selectedSnapshot?.id === item.id;
                const isPartner = disabledId === item.id;

                return (
                  <div
                    key={item.id}
                    onClick={() => handleSelectItem(item)}
                    className={`p-2.5 transition-colors cursor-pointer flex items-center justify-between ${
                      isSelected
                        ? "bg-blue-50/70 hover:bg-blue-50"
                        : isPartner
                        ? "bg-slate-50/50 hover:bg-slate-100/70"
                        : "hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex-1 min-w-0 pr-3">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`font-mono text-xs font-bold tracking-tight ${isSelected ? "text-blue-900" : "text-slate-900"}`}>
                          {item.full_code}
                        </span>
                        {getShiftBadge(item.shift)}
                        <span className="text-[10px] px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded font-medium">
                          {item.store_code}
                        </span>
                        {isPartner && (
                          <span className="text-[10px] px-1.5 py-0.2 bg-purple-100 text-purple-700 rounded font-semibold">
                            Đối tác so sánh
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-slate-500 truncate">
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-slate-400" />
                          {item.inventory_date} {item.inventory_time ? `(${item.inventory_time})` : ""}
                        </span>
                        <span>•</span>
                        <span>{formatNum(item.total_sku_count)} SKU</span>
                        <span>•</span>
                        <span>{formatNum(item.total_quantity)} SP</span>
                        <span>•</span>
                        <span className="text-emerald-700 font-medium">{formatVnd(item.total_amount_vnd)}</span>
                      </div>
                    </div>

                    <div className="shrink-0">
                      {isSelected ? (
                        <div className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center">
                          <Check className="w-3.5 h-3.5 stroke-[3]" />
                        </div>
                      ) : (
                        <div className="w-5 h-5 rounded-full border border-slate-200" />
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {/* Nút Tải thêm (Load More) nếu còn trang */}
            {page < totalPages && !isLoading && (
              <div className="p-2 bg-slate-50/80 border-t border-slate-100 text-center">
                <button
                  type="button"
                  onClick={handleLoadMore}
                  disabled={isLoadingMore}
                  className="w-full py-1.5 px-3 text-xs text-blue-600 font-semibold hover:bg-blue-50/60 rounded-lg transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Đang tải thêm...</span>
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-3.5 h-3.5" />
                      <span>Tải thêm chứng từ (Trang {page + 1}/{totalPages})</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Footer tóm tắt số lượng */}
          <div className="px-3 py-1.5 bg-slate-100/70 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span>Hiển thị {items.length} / {totalCount} chứng từ hoàn tất</span>
            <span>Chỉ chọn snapshot COMPLETED</span>
          </div>
        </div>
      )}
    </div>
  );
};
