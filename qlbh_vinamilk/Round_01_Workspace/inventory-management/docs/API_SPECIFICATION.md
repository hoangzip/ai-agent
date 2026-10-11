# ĐẶC TẢ GIAO DIỆN LẬP TRÌNH ỨNG DỤNG (API SPECIFICATION)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Phiên bản API:** v1  
**Giai đoạn:** Round 02/10 – Project Foundation, Database & API  

---

## 1. QUY ƯỚC CHUNG

- **Base URL:** `/api` hoặc `/api/v1`
- **Định dạng dữ liệu:** `application/json; charset=utf-8`
- **Múi giờ:** UTC trong dữ liệu lưu trữ, phản hồi ISO 8601 (`YYYY-MM-DDTHH:mm:ss.sssZ`).
- **Headers bắt buộc:**
  - `Content-Type: application/json`
  - `X-Request-ID`: Chuỗi UUID định danh yêu cầu (nếu client không truyền, Worker tự sinh).

### Cấu trúc phản hồi chuẩn (Response Envelopes):

**Phản hồi thành công (HTTP 200/201):**
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2026-10-11T09:50:00.000Z",
    "requestId": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Phản hồi lỗi (HTTP 4xx/5xx):**
```json
{
  "success": false,
  "error": {
    "code": "BAD_REQUEST | NOT_FOUND | NOT_IMPLEMENTED | INTERNAL_SERVER_ERROR",
    "message": "Mô tả lỗi chi tiết bằng tiếng Việt",
    "details": null
  },
  "meta": {
    "requestId": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-10-11T09:50:00.000Z"
  }
}
```

---

## 2. CÁC ENDPOINT ĐÃ KÍCH HOẠT (ROUND 02)

### 2.1. Kiểm tra trạng thái máy chủ (Health Check)
- **Method:** `GET`
- **URL:** `/api/health`
- **Mục đích:** Kiểm tra trạng thái sống của Cloudflare Worker.
- **Phản hồi mẫu (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "ok",
    "service": "inventory-management-api",
    "timestamp": "2026-10-11T09:50:12.345Z"
  },
  "meta": {
    "requestId": "uuid-..."
  }
}
```

### 2.2. Thông tin hệ thống & Roadmap Module (System Info)
- **Method:** `GET`
- **URL:** `/api/v1/system/info`
- **Phản hồi mẫu (200 OK):**
```json
{
  "success": true,
  "data": {
    "service": "inventory-management-backend",
    "version": "0.2.0",
    "round": "02/10 – Project Foundation, Database & API",
    "environment": "development",
    "timezone": "Asia/Ho_Chi_Minh",
    "timestamp": "2026-10-11T09:50:12.345Z",
    "database": {
      "provider": "Cloudflare D1 (SQLite Engine)",
      "status": "connected"
    },
    "modules": {
      "auth": "ROUND_03_PLANNED",
      "users": "ROUND_03_PLANNED",
      "inventory_import": "ROUND_04_PLANNED",
      "comparison_engine": "ROUND_05_PLANNED",
      "product_history": "ROUND_05_PLANNED",
      "ui_dashboard": "ROUND_06_PLANNED",
      "gdrive_sync": "ROUND_07_PLANNED",
      "soft_delete": "ROUND_08_PLANNED"
    }
  }
}
```

---

## 3. CÁC MODULE LÊN LỊCH & QUY ƯỚC 501 NOT IMPLEMENTED

Hệ thống tuân thủ nguyên tắc không tạo API giả lập kết quả nạp/kiểm kê. Mọi yêu cầu tới các module chưa kích hoạt đều trả về mã HTTP `501 Not Implemented` trung thực:

| Tiền tố URL | Tên chức năng | Trạng thái hiện tại | Round lên lịch |
|---|---|---|:---:|
| `/api/v1/auth/*` | Xác thực đăng nhập & Đổi mật khẩu | HTTP 200/401/403 | **Active (Round 03)** |
| `/api/v1/users/*` | Quản lý người dùng & Phân quyền RBAC | HTTP 200/401/403 | **Active (Round 03)** |
| `/api/v1/inventory/*` | Nạp file Excel & Quản lý Staging | HTTP 201/200/409 | **Active (Round 04)** |
| `/api/v1/compare/*` | Động cơ đối soát Snapshot A $\leftrightarrow$ B | HTTP 501 | Round 05 |
| `/api/v1/history/*` | Lịch sử biến động theo SKU | HTTP 501 | Round 05 |
| `/api/v1/sync/*` | Đồng bộ tự động Google Drive | HTTP 501 | Round 07 |
| `/api/v1/export/*` | Xuất báo cáo XLSX / CSV | HTTP 501 | Round 08 |

**Ví dụ phản hồi 501:**
```json
{
  "success": false,
  "error": {
    "code": "NOT_IMPLEMENTED",
    "message": "Chức năng 'Authentication' chưa được kích hoạt. Module này được lên lịch triển khai tại Round 03.",
    "details": {
      "module": "Authentication",
      "scheduled_round": "Round 03"
    }
  },
  "meta": {
    "requestId": "req-123456",
    "timestamp": "2026-10-11T09:50:12.345Z"
  }
}
```

---

## 4. CHÍNH SÁCH BẢO MẬT CORS VÀ XỬ LÝ LỖI (FIX 02 CONTRACT)

### 4.1. Chính sách CORS: Exact Origin Allowlist
- **Không sử dụng Wildcard:** Tuyệt đối không chấp nhận `*` hoặc regex `*.pages.dev`/`*.workers.dev`.
- **So khớp chính xác (Exact Match):** Chỉ các Origin được cấu hình trong `ALLOWED_ORIGINS` (và localhost khi dev/test) mới được phản hồi `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials: true`.
- **Phản hồi khi Origin không hợp lệ:**
  - Yêu cầu Preflight `OPTIONS`: Trả về HTTP `403 Forbidden CORS Origin`, không có header ACAO.
  - Yêu cầu `GET/POST`: Phản hồi bình thường nhưng không kèm header ACAO và không kèm credentials.
- **Cache Header:** Luôn đính kèm `Vary: Origin` để tránh CDN cache sai lệch giữa các origin.

### 4.2. Xử lý Lỗi Fail-Closed (Production-Safe)
- **Mặc định An toàn:** Khi thiếu biến `ENVIRONMENT` hoặc giá trị không xác định, API tự động hoạt động ở chế độ production-safe.
- **Che giấu lỗi 500:** Toàn bộ thông tin nhạy cảm (stack trace, thông tin cơ sở dữ liệu) bị gán `details: null` và thay bằng thông báo lỗi máy chủ chuẩn.
- **Môi trường dev/test:** Chỉ hiển thị `details` khi `ENVIRONMENT === "development"` hoặc `"test"`.

