/**
 * File: apps/web/src/api/client.ts
 * API Client kết nối Backend Cloudflare Workers
 */

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  meta?: Record<string, any>;
}

const RAW_BASE = import.meta.env?.VITE_API_BASE_URL as string | undefined;
export const API_BASE_URL = (RAW_BASE && RAW_BASE.trim() !== "" ? RAW_BASE.trim() : "/api").replace(/\/$/, "");

export async function fetchApi<T = any>(endpoint: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const url = `${API_BASE_URL}${cleanEndpoint}`;
  const headers = new Headers(options.headers || {});
  
  // Hỗ trợ cả Cookie HttpOnly và Bearer Token từ localStorage / URL token
  const token = typeof window !== "undefined" 
    ? (localStorage.getItem("vinamilk_auth_token") || new URLSearchParams(window.location.search).get("token")) 
    : null;
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Nếu body là FormData, không đặt Content-Type để trình duyệt tự thêm boundary
  if (options.body instanceof FormData) {
    headers.delete("Content-Type");
  } else if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const res = await fetch(url, {
      credentials: "include",
      ...options,
      headers
    });
    const json = await res.json();
    return json;
  } catch (err: any) {
    return {
      success: false,
      error: {
        code: "NETWORK_ERROR",
        message: "Không thể kết nối đến máy chủ API: " + (err?.message || String(err))
      }
    };
  }
}

export const api = {
  getHealth: () => fetchApi("/health"),
  getSystemInfo: () => fetchApi("/v1/system/info"),

  // Auth APIs (Round 03)
  login: (credentials: { username: string; password: string }) =>
    fetchApi("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(credentials)
    }),
  logout: () =>
    fetchApi("/v1/auth/logout", {
      method: "POST"
    }),
  changePassword: (data: { current_password: string; new_password: string }) =>
    fetchApi("/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify(data)
    }),
  getMe: () => fetchApi("/v1/auth/me"),

  // User Management APIs (Round 03 - Admin Only)
  getUsers: () => fetchApi("/v1/users"),
  createUser: (userData: { username: string; password?: string; role?: string; full_name: string }) =>
    fetchApi("/v1/users", {
      method: "POST",
      body: JSON.stringify(userData)
    }),
  updateUser: (userId: number, data: { full_name?: string; role?: string }) =>
    fetchApi(`/v1/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(data)
    }),
  updateUserStatus: (userId: number, is_active: boolean) =>
    fetchApi(`/v1/users/${userId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active })
    }),
  resetUserPassword: (userId: number, temp_password?: string) =>
    fetchApi(`/v1/users/${userId}/reset-password`, {
      method: "POST",
      body: JSON.stringify(temp_password ? { temp_password } : {})
    }),

  // Inventory & Snapshot APIs (Round 04)
  previewInventory: (formData: FormData) =>
    fetchApi("/v1/inventory/preview", {
      method: "POST",
      body: formData
    }),
  uploadInventory: (formData: FormData) =>
    fetchApi("/v1/inventory/upload", {
      method: "POST",
      body: formData
    }),
  uploadInventoryJson: (payload: { files?: any[]; filename?: string; content_base64?: string; auto_commit?: boolean }) =>
    fetchApi("/v1/inventory/upload", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getSnapshots: (params: {
    page?: number;
    limit?: number;
    status?: string;
    store_code?: string;
    inventory_date?: string;
    start_date?: string;
    end_date?: string;
    search?: string;
    shift?: string;
  } = {}) => {
    const query = new URLSearchParams();
    if (params.page) query.set("page", params.page.toString());
    if (params.limit) query.set("limit", params.limit.toString());
    if (params.status) query.set("status", params.status);
    if (params.store_code) query.set("store_code", params.store_code);
    if (params.inventory_date) query.set("inventory_date", params.inventory_date);
    if (params.start_date) query.set("start_date", params.start_date);
    if (params.end_date) query.set("end_date", params.end_date);
    if (params.search) query.set("search", params.search);
    if (params.shift) query.set("shift", params.shift);
    return fetchApi(`/v1/inventory/snapshots?${query.toString()}`);
  },
  getDashboardStats: (storeCode?: string) => {
    const query = storeCode ? `?store_code=${encodeURIComponent(storeCode)}` : "";
    return fetchApi(`/v1/dashboard/stats${query}`);
  },
  getSnapshot: (id: number, includeItems: boolean = true) =>
    fetchApi(`/v1/inventory/snapshots/${id}?include_items=${includeItems}`),
  commitSnapshot: (id: number) =>
    fetchApi(`/v1/inventory/snapshots/${id}/commit`, {
      method: "POST"
    }),
  deleteSnapshot: (id: number) =>
    fetchApi(`/v1/inventory/snapshots/${id}`, {
      method: "DELETE"
    }),

  // Comparison & History APIs (Round 05)
  compareSnapshots: (params: {
    base_id: number;
    target_id: number;
    status?: string;
    category?: string;
    warehouse?: string;
    search?: string;
    page?: number;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    query.set("base_id", params.base_id.toString());
    query.set("target_id", params.target_id.toString());
    if (params.status && params.status !== "ALL") query.set("status", params.status);
    if (params.category) query.set("category", params.category);
    if (params.warehouse) query.set("warehouse", params.warehouse);
    if (params.search) query.set("search", params.search);
    if (params.page) query.set("page", params.page.toString());
    if (params.limit) query.set("limit", params.limit.toString());
    return fetchApi(`/v1/comparison?${query.toString()}`);
  },
  getProductHistory: (productCode: string, warehouse?: string) => {
    const query = warehouse ? `?warehouse=${encodeURIComponent(warehouse)}` : "";
    return fetchApi(`/v1/comparison/history/${encodeURIComponent(productCode)}${query}`);
  },
  getExportComparisonUrl: (baseId: number, targetId: number, options?: { status?: string; warehouse?: string; search?: string }) => {
    const query = new URLSearchParams();
    query.set("base_id", baseId.toString());
    query.set("target_id", targetId.toString());
    if (options?.status && options.status !== "ALL") query.set("status", options.status);
    if (options?.warehouse) query.set("warehouse", options.warehouse);
    if (options?.search) query.set("search", options.search);
    return `${API_BASE_URL}/v1/comparison/export?${query.toString()}`;
  },

  // Google Drive Sync APIs (Round 07)
  getSyncStatus: () => fetchApi("/v1/sync/status"),
  getSyncRuns: (params: { page?: number; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.page) query.set("page", params.page.toString());
    if (params.limit) query.set("limit", params.limit.toString());
    return fetchApi(`/v1/sync/runs?${query.toString()}`);
  },
  triggerSync: () =>
    fetchApi("/v1/sync/trigger", {
      method: "POST"
    })
};
