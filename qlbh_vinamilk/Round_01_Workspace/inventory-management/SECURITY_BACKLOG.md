# KẾ HOẠCH BẢO MẬT HẬU MVP (SECURITY BACKLOG)

**Dự án:** Quản lý & Đối soát Tồn kho (Vinamilk)  
**Tài liệu:** SECURITY_BACKLOG.md  
**Giai đoạn:** Round 03/10 – MVP Acceptance Scope  
**Ngày lập:** 11/10/2026  

---

> [!WARNING]
> **CẢNH BÁO BẢO MẬT TRIỂN KHAI:**  
> Cấu hình xác thực trong giai đoạn MVP hiện tại **CHƯA HARDENING ĐẦY ĐỦ CHO MÔI TRƯỜNG PUBLIC INTERNET**.  
> Tuyệt đối **không mở public authentication** trên internet khi chưa hoàn tất các hạng mục nâng cao bên dưới. Hệ thống MVP chỉ được phép vận hành trong mạng nội bộ (Intranet), môi trường Staging/UAT cô lập, hoặc đứng sau lớp bảo vệ truy cập Cloudflare Access / Zero Trust VPN.

---

## 1. CÁC HẠNG MỤC BẢO MẬT TẠM HOÃN TRONG GIAI ĐOẠN MVP

Theo chỉ đạo phạm vi tinh giản (Simplified Acceptance Scope), các tính năng bảo mật nâng cao sau đây được hoãn lại để ưu tiên tập trung hoàn thành các nghiệp vụ cốt lõi quản lý tồn kho (Round 04–08):

| STT | Hạng mục bảo mật hoãn | Mô tả kỹ thuật chi tiết | Kế hoạch triển khai |
| :---: | :---|---|:---:|
| **SEC-01** | **Rate Limiting Phân tán (Distributed Rate Limiting)** | Nâng cấp từ bộ nhớ in-memory/isolate hiện tại lên Cloudflare KV / Durable Objects / Upstash Redis để duy trì giới hạn brute-force nhất quán trên toàn bộ mạng lưới Edge toàn cầu của Cloudflare. | Giai đoạn Hardening (Trước Go-Live) |
| **SEC-02** | **Chính sách Mật khẩu Doanh nghiệp Nâng cao** | Tích hợp thuật toán đánh giá độ mạnh mật khẩu (zxcvbn entropy scoring), bắt buộc định kỳ đổi mật khẩu sau 90 ngày, kiểm tra mật khẩu bị rò rỉ qua dịch vụ HaveIBeenPwned API (k-Anonymity). | Giai đoạn Production Ready |
| **SEC-03** | **Xác thực Đa yếu tố (MFA / 2FA / WebAuthn)** | Hỗ trợ TOTP (Google Authenticator / Microsoft Authenticator) hoặc FIDO2 / Passkeys cho tài khoản Quản trị viên (ADMIN) trước khi truy cập dữ liệu đối soát tài chính nhạy cảm. | Round 09 / Security Hardening |
| **SEC-04** | **Bảo vệ CSRF Nâng cao Phân tán** | Bổ sung cơ chế Double Submit Cookie với CSRF Token đồng bộ mã hóa qua cryptographic token per-session, kết hợp với cấu hình cookie `SameSite=Strict`. | Giai đoạn Hardening |
| **SEC-05** | **Khóa tài khoản Tự động & Mở khóa qua Email** | Cơ chế tự động khóa tài khoản người dùng sau N lần đăng nhập sai trên toàn hệ thống kèm luồng gửi email xác thực mở khóa có thời hạn. | Giai đoạn Vận hành Doanh nghiệp |
| **SEC-06** | **Tách biệt Hoàn toàn Cookie Auth & Machine Bearer Flow** | Tách hẳn 2 luồng endpoint riêng biệt giữa Web Session (Cookie HttpOnly thuần túy, không trả raw token) và Machine-to-Machine API Tokens (quản lý qua API Key hash riêng biệt). | Round 07 (Google Drive Sync / API Integration) |
| **SEC-07** | **Cảnh báo Bất thường Đăng nhập (Anomaly Detection)** | Phát hiện đăng nhập từ IP/Địa lý bất thường, nhiều ca làm việc đồng thời trên cùng một tài khoản, gửi thông báo Telegram/Email cho Admin. | Giai đoạn Vận hành |

---

## 2. NỀN TẢNG BẢO MẬT ĐÃ HOÀN THÀNH & ĐANG HOẠT ĐỘNG TRONG MVP

Dù hoãn các tính năng nâng cao, hệ thống MVP vẫn giữ nguyên các cơ chế an toàn cốt lõi:
1. **PBKDF2-HMAC-SHA256**: 100.000 vòng lặp, salt 16-byte ngẫu nhiên bảo mật, constant-time comparison.
2. **Khóa chặt Bootstrap Admin (P0 Fix)**: Bắt buộc cấu hình `BOOTSTRAP_TOKEN` trên server mới cho phép tạo Admin; từ chối 403 `BOOTSTRAP_DISABLED` nếu thiếu token.
3. **Session Hashing**: SQLite D1 chỉ lưu `token_hash` (SHA-256), không lưu token bí mật bản rõ.
4. **Phân quyền Server-side (RBAC)**: Phân tách vai trò ADMIN vs USER, chặn 403 `FORBIDDEN_ADMIN_ONLY` tại tầng API.
5. **Thu hồi phiên tức thì (Instant Revocation)**: Đăng xuất, khóa tài khoản hoặc reset mật khẩu lập tức thu hồi mọi phiên.
6. **Bảo vệ Deadlock**: Ngăn chặn tuyệt đối việc tự khóa hoặc hạ quyền Admin duy nhất (`CANNOT_LOCK_LAST_ADMIN`, `CANNOT_DEMOTE_LAST_ADMIN`).
7. **Nhật ký kiểm toán (Audit Logs)**: Ghi nhận sự kiện xác thực và vòng đời người dùng vào bảng `audit_logs`.
