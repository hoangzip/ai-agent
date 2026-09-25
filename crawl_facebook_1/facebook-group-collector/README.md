# Facebook Group CIC & Lead Collector

Hệ thống crawl bài viết, hình ảnh thư viện (/media), bóc tách báo cáo điểm tín dụng CIC và thu thập khách hàng tiềm năng (Leads) từ cả bài đăng và bình luận trong Facebook Groups.

---

## 1. Cấu Trúc Đóng Gói (Multi-Group)
Mỗi group được tự động phân vùng độc lập (namespaced) theo mã group (`group_slug` hoặc `group_id`) trong thư mục `data/groups/<group_slug>/`:
```
data/groups/<group_slug>/
├── cic_customers.json            # Danh sách lead CIC đã verify (sđt, cccd, điểm, nhóm nợ...)
├── media_gallery_order.json      # Toàn bộ danh sách ảnh trong gallery theo thứ tự từ trái qua phải
├── media_gallery_state.json      # Trạng thái xử lý từng ảnh (skipped, crawled, error)
├── checked_comment_posts.json    # Danh sách các post ID đã quét xong phần bình luận
├── images/
│   ├── posts/                    # Ảnh đính kèm bài viết chính
│   └── comments/                 # Ảnh báo cáo CIC đính kèm trong comment
└── posts/                        # Chi tiết từng bài viết chuẩn hóa theo schema JSON
```

---

## 2. Hướng Dẫn Sử Dụng CLI

### A. Cào bài mới hàng ngày / tương lai (Chế độ Tăng dần - Incremental)
Khi bạn chạy vào ngày hôm sau hoặc bất kỳ lúc nào trong tương lai, sử dụng cờ `--update-new`:
```bash
python run_collector.py --group 978769317924542 --update-new --check-comments
```
**Quy tắc hoạt động của `--update-new`:**
1. Trình duyệt truy cập `https://web.facebook.com/groups/<group_slug>/media`.
2. Kiểm tra các ảnh mới nhất từ đầu trang.
3. Khi gặp **5 ảnh liên tiếp đã từng cào trước đó**, hệ thống tự động nhận diện đã chạm tới mốc lịch sử cũ và **dừng cuộn ngay lập tức** (chỉ mất ~5-10 giây).
4. Nếu có ảnh mới, hệ thống tự động chèn vào đầu danh sách `media_gallery_order.json` và chỉ crawl, OCR, bóc tách CIC cho riêng các ảnh mới này.
5. Nếu không có bài mới nào, hệ thống thông báo dữ liệu đã cập nhật và kết thúc an toàn.

### B. Chạy cho một Facebook Group khác
Để chạy cho bất kỳ group nào khác, bạn chỉ cần thay đổi tham số `--group`:
```bash
# Cào khởi tạo ban đầu cho group mới:
python run_collector.py --group <group_slug_hoac_id> --check-comments

# Hoặc giới hạn số lượng bài để test trước:
python run_collector.py --group <group_slug_hoac_id> --limit 10 --check-comments
```

### C. Quét sâu bình luận để tìm thêm CIC
Nếu muốn quét riêng phần bình luận của một bài viết cụ thể:
```bash
python scripts/crawl_comments_cic.py --group 978769317924542 --post-url "https://web.facebook.com/groups/978769317924542/posts/1113475811120558/"
```
Hoặc quét bình luận cho toàn bộ các bài đã lưu:
```bash
python scripts/crawl_comments_cic.py --group 978769317924542 --all-posts
```

---

## 3. Các Quy Tắc Xử Lý Dữ Liệu
1. **Tránh trùng lặp (Deduplication):**
   - Không crawl lại ảnh đã có kết quả CIC hoàn chỉnh (`has_complete_cic`).
   - Khách hàng CIC được gộp và cập nhật (upsert) theo `cic_code`, `id_card_number` hoặc `post_id`.
2. **Bình luận (Comments):**
   - Đính kèm chính xác tác giả của comment (Commenter), không gán nhầm sang tác giả bài viết.
   - Luôn tải ảnh gốc độ phân giải cao qua Photo Theater trước khi OCR.
   - Nhận diện số điện thoại cả từ văn bản bình luận và ảnh báo cáo.
3. **Tài khoản ẩn danh (Anonymous):**
   - Tự động nhận diện tài khoản ẩn danh ("Người tham gia ẩn danh" / "Thành viên ẩn danh" / Report nickname) và gán `author_is_anonymous: true`.
