# GEMINI.md - Kế hoạch Phát triển Website Học Từ Vựng Tiếng Anh ZipH English AI

Dự án xây dựng Landing Page giới thiệu dịch vụ học từ vựng tiếng Anh ứng dụng AI (**ZipH English AI**). Thiết kế được định hình theo phong cách tối giản hiện đại, trẻ trung và chuyên nghiệp, lấy cảm hứng từ phong cách Neo-brutalism/Playful Modernist của trang web tham khảo (màu nền ấm, nét viền mảng màu đậm, các hình khối capsule/pill xếp chồng sáng tạo và typography có tính tương phản cao).

---

## 1. Tổng quan Dự án (Project Overview)
- **Tên dự án**: ZipH English AI Landing Page
- **Mục tiêu**: Xây dựng trang giới thiệu dịch vụ học từ vựng tiếng Anh thông minh với AI. Website gây ấn tượng mạnh thông qua phong cách thiết kế độc đáo, thân thiện, kết hợp các khối tương tác sinh động và hiệu ứng chuyển động mượt mà.
- **Thị trường mục tiêu**: Học sinh, sinh viên, và người đi làm muốn cải thiện từ vựng tiếng Anh thông qua phương pháp học công nghệ mới.

---

## 2. Ngôn ngữ Thiết kế & Hệ thống Style (Design System)
Dựa trên hình ảnh tham khảo từ `nudot`:
*   **Tone màu chủ đạo (Color Palette)**:
    *   **Background chính**: Màu kem/off-white ấm (`#FAF9F5` hoặc `#F4F1EA`) tạo cảm giác dễ chịu, gần gũi như trang giấy học tập.
    *   **Màu chữ chính**: Đen than (`#0A0A0A` hoặc `#1A1A1A`) đảm bảo độ tương phản tối đa.
    *   **Màu bổ trợ (Accent Colors)**: Sử dụng các khối màu trơn nổi bật không đổ bóng phức tạp:
        *   Xanh dương (Motivation/Adventures): `#4F67E8`
        *   Cam đỏ (Talk/Support): `#E85D44`
        *   Xanh lục (Communicate/Teal): `#3A9E75`
        *   Vàng (Exams/Speaking): `#F5C84C`
        *   Hồng tím (Studies/Effectively): `#E8A2C9`
        *   Xanh Navy đậm (Easy): `#03071E`
*   **Borders & Shadows (Đường nét & Đổ bóng)**:
    *   Đường viền: Viền đen mảnh (`border: 1.5px solid #000000`) bao quanh các nút và các khối capsule.
    *   Đổ bóng (Box Shadow): Sử dụng đổ bóng phẳng cứng cáp đặc trưng của Neo-brutalism (`box-shadow: 4px 4px 0px #000000`) thay vì shadow mờ nhạt.
*   **Typography (Phông chữ)**:
    *   **Font chữ**: Phông chữ hình học không chân hiện đại như `Outfit`, `Plus Jakarta Sans` hoặc `Cabinet Grotesk`.
    *   **Tiêu đề chính (Hero Headline)**: Cực đậm (font-weight 800), kích thước lớn (~4.5rem), khoảng cách chữ khít (`letter-spacing: -0.02em`), phối hợp chèn các ký tự icon trang trí sáng tạo (ví dụ: hình ngôi sao lấp lánh `✦` hoặc ký tự cách điệu ở giữa từ khóa).
*   **Chi tiết trang trí**:
    *   Sử dụng nét vẽ nguệch ngoạc (doodles), các đường mũi tên chỉ dẫn vẽ tay mộc mạc làm nổi bật hành động CTA.
    *   Các thẻ từ vựng dạng khối capsule bo tròn hoàn toàn (`border-radius: 9999px`) xếp chồng lên nhau tự nhiên ở đáy trang.

---

## 3. Cấu trúc Trang Web & Dự án (Site & Project Structure)

### 3.1. Cấu trúc Giao diện Site (Site Structure)
```
/                   # Trang chủ (Landing Page)
├── Header          # Logo (ZipH English AI) + Menu (Courses, About, Pricing, FAQ) separated by "/"
├── Hero            # Dòng tiêu đề lớn "Learn English without borders" + Doodles vẽ tay + Nút CTA
├── VisualShowcase  # Khối capsule màu sắc tương tác xếp chồng (khi hover sẽ hiển thị nghĩa từ vựng hoặc phát âm)
├── AIFeatures      # Bento Grid giới thiệu tính năng AI (AI Flashcard, AI Pronounce Coach, AI Context Generator)
├── HowItWorks      # 3 bước học thông minh vẽ theo sơ đồ mũi tên viết tay
├── Testimonials    # Nhận xét từ học viên thiết kế dạng thẻ bài phát biểu nhiều màu
├── Pricing         # Bảng giá các gói học Premium của ZipH English AI
└── Footer          # Footer tối giản với layout đối xứng
```

### 3.2. Cấu trúc Thư mục Dự án (Project Structure)
```
src/
├── app/
│   ├── layout.tsx     # Cấu hình font chữ, thẻ metadata SEO
│   ├── page.tsx       # Giao diện chính của Landing Page
│   └── globals.css    # Cấu hình Tailwind CSS, biến màu kem nền và viền đen
├── components/
│   ├── ui/            # Các component cơ bản (Button.tsx, CapsuleBadge.tsx, Card.tsx)
│   ├── sections/      # Các phần lớn (Hero.tsx, FeatureGrid.tsx, StackShowcase.tsx, Footer.tsx)
│   └── layout/        # Navbar.tsx và Container.tsx
├── lib/
│   └── utils.ts       # Hàm helper "cn" kết hợp class
└── assets/            # Chứa các hình vẽ minh họa, icon vẽ tay (SVG)
```

### 3.3. Quy ước Lập trình (Coding Conventions)
*   **Naming**: Component sử dụng PascalCase (`CapsuleCard.tsx`), các hàm helper dùng camelCase.
*   **Tailwind CSS**: Tận dụng triệt để các utility class của Tailwind. Dùng `border-black border-[1.5px]` và shadow cứng `shadow-[4px_4px_0px_#000000]` để đồng bộ style Neo-brutalism.
*   **Animation Guidelines**:
    *   Hiệu ứng Hover: Các khối capsule khi hover sẽ hơi xoay nhẹ (`rotate-1` hoặc `rotate-[-1]`) và trượt nhẹ lên trên (`-translate-y-1`).
    *   Hiệu ứng Xuất hiện: Khi cuộn trang (scroll reveal), các khối capsule sẽ rơi xuống xếp chồng lên nhau bằng Framer Motion tạo cảm giác chân thực.

### 3.4. Các lệnh phát triển (Commands)
*   `npm run dev`: Chạy dự án ở local.
*   `npm run build`: Tạo bản build tối ưu cho production.
*   `npm run lint`: Kiểm tra chất lượng và chuẩn code.

---

## 4. Kế hoạch Triển khai Kỹ thuật (Technical Implementation Plan)
*   **Công nghệ**:
    *   **Framework**: Next.js App Router + TypeScript.
    *   **Styling**: Tailwind CSS + Custom CSS cho các nét vẽ doodle.
    *   **Animations**: Framer Motion để tạo hiệu ứng xếp chồng capsule động và xoay lắc tự nhiên khi hover.
*   **SEO & Hiệu năng**:
    *   Tối ưu hóa Lighthouse đạt 98+ nhờ dung lượng ảnh SVG/WebP nhẹ.
    *   Sử dụng dynamic metadata để tối ưu hóa SEO Google.
    *   Font chữ tự lưu trữ cục bộ qua `next/font` nhằm triệt tiêu độ trễ hiển thị văn bản (CLS).

---

## 5. Các bước tiếp theo (Next Steps)
1.  **Khởi động dự án**: Cấu hình Next.js trong thư mục `web_study_english`.
2.  **Cài đặt CSS & Theme**: Thiết lập màu nền kem và các màu accent trong Tailwind config.
3.  **Xây dựng Hero & Navbar**: Triển khai thiết kế tối giản với phân cách thanh gạch `/`.
4.  **Xây dựng khối tương tác Capsule Stack**: Viết mã React cho hiệu ứng hover lật thẻ từ vựng hoặc phát âm.
5.  **Hoàn thiện Bento Grid & Doodles**: Dựng các tính năng AI và gắn SVG vẽ nguệch ngoạc.
6.  **Tối ưu hóa Responsive & SEO**: Đảm bảo hiển thị hoàn hảo trên các thiết bị di động.
