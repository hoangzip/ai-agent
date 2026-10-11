# HỆ THỐNG QUẢN LÝ & ĐỐI SOÁT TỒN KHO VINAMILK

Dự án ứng dụng web chuyên dụng cho bài toán **Quản lý & Đối soát Tồn kho hàng hóa** (Vinamilk).  
Ứng dụng phục vụ đối soát số dư tồn kho sổ sách, phát hiện biến động tăng/giảm, mã mới nhập kho, tỷ lệ biến động và quản lý đa snapshot trong ngày.

---

## 1. CẤU TRÚC DỰ ÁN (MONOREPO)

```text
inventory-management/
├── apps/
│   ├── web/                    # Frontend React 18 + Vite + TypeScript + Tailwind CSS (shadcn tokens)
│   └── api/                    # Backend Cloudflare Workers (TypeScript, REST API, Zod)
├── packages/
│   └── shared/                 # Định nghĩa dùng chung: Types, Zod Schemas, Data Contract 15 cột
├── database/
│   └── migrations/             # Migrations Cloudflare D1 (SQLite) chuẩn hóa 10 bảng
├── tests/                      # Bộ kiểm thử tự động toàn diện
├── docs/                       # Tài liệu kiến trúc và đặc tả API
└── reports/                    # Báo cáo kiểm định QC/QA và Manifest bàn giao
```

---

## 2. YÊU CẦU MÔI TRƯỜNG & KHỞI CHẠY

### 2.1. Yêu cầu môi trường
- **Node.js:** v20.x trở lên (khuyến nghị LTS).
- **npm:** v10.x trở lên.
- **Python:** v3.11.x (phục vụ test harness và so sánh đối soát).

### 2.2. Khởi chạy cục bộ (Local Development)
```bash
# 1. Cài đặt dependencies cho toàn bộ monorepo
npm install

# 2. Build toàn bộ packages (shared, api, web)
npm run build

# 3. Kiểm tra kiểu dữ liệu (TypeScript typecheck)
npm run typecheck

# 4. Chạy kiểm thử tự động
python3 -m pytest tests/
node --test apps/api/tests/api.test.js

# 5. Khởi chạy Frontend Web App (cổng 3000)
cd apps/web && npm run dev
```

---

## 3. CƠ SỞ DỮ LIỆU CLOUDFLARE D1 (10 BẢNG)

Database được thiết kế tối ưu trên SQLite / Cloudflare D1:
1. `stores`: Danh mục cửa hàng / chi nhánh phân phối.
2. `stock_scopes`: Phạm vi kho (Kho bán lẻ, kho hàng khuyến mãi...).
3. `users`: Tài khoản và phân quyền (ADMIN / USER), hỗ trợ đổi mật khẩu bắt buộc lần đầu.
4. `sessions`: Quản lý phiên làm việc, hỗ trợ thu hồi token tức thì khi khóa tài khoản.
5. `product_catalog`: Danh mục sản phẩm chuẩn hóa (mã text bảo toàn số 0 đầu).
6. `inventory_files`: Chứng từ snapshot kiểm kê (định danh bằng `full_code`, hỗ trợ nhiều snapshot/ngày).
7. `inventory_items`: Chi tiết 15 cột sản phẩm, khóa tự nhiên `(file_id, product_code, warehouse)`.
8. `sync_sources`: Cấu hình đồng bộ Google Drive (Folder ID: `1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk`).
9. `sync_runs`: Nhật ký các đợt đồng bộ tự động / thủ công.
10. `audit_logs`: Nhật ký kiểm toán mọi hành vi sửa đổi dữ liệu và xóa mềm.

---

## 4. BẢO MẬT & NGUYÊN TẮC AN TOÀN

- **Mật khẩu:** Băm an toàn bằng thuật toán hiện đại, tuyệt đối không lưu mật khẩu dạng bản rõ. Mật khẩu mặc định `123456` chỉ dùng cho dev bootstrap và bắt buộc đổi ngay ở lần đăng nhập đầu tiên.
- **Database Safety:** Không tự ý chạy các câu lệnh DDL/DML trên database production. Mọi script nạp dữ liệu mẫu đều được comment để chờ duyệt.
- **Zero Secret Exposure:** Không hardcode API key, OAuth client secret, private key trong source code.
