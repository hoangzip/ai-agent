# BẮT ĐẦU ROUND 01 — INVENTORY MANAGEMENT (V2)

## Quan trọng

Đây là **bộ hồ sơ khởi động**, không phải kết quả đã thực thi Round 01.
Bốn file Excel nguồn là dữ liệu nội bộ: chỉ sử dụng trong workspace private; không tự commit/push lên GitHub/public repository.

## Bước 1 — Giải nén trong workspace Antigravity/VS Code

**macOS/Linux** (mở terminal tại folder có ZIP):

```bash
mkdir -p Round_01_Workspace
unzip -o Inventory_Management_Round_01_Kickoff_Pack_V2.zip -d Round_01_Workspace
```

**Windows PowerShell**:

```powershell
Expand-Archive -Path '.\Inventory_Management_Round_01_Kickoff_Pack_V2.zip' -DestinationPath '.\Round_01_Workspace' -Force
```

Bước tiếp: mở folder `Round_01_Workspace` trong IDE. Đảm bảo trong đó có 3 tài liệu `.md` và folder `Data Source/Kiem Ke` chứa đủ **4** file `.xlsx`.

**Chỉ thấy biểu tượng ZIP và thông báo "binary / unsupported encoding" là bình thường. Không gửi riêng ZIP để Agent coi là tài liệu Markdown.**

## Bước 2 — Mở Agent và gửi prompt này

```
Bạn là Orchestrator của dự án Inventory Management. Hãy bắt đầu Round 01/10.

1. Đọc README_START_HERE.md, MASTER_PROMPT_Inventory_Management_V2.md, ROUND_01_PROMPT_Excel_Data_Contract_V2.md, KICKOFF_CHECKLIST_V2.md.
2. Xác minh có đủ 4 file Excel trong 'Data Source/Kiem Ke', liệt kê tên, dung lượng, SHA256 trước khi phân tích.
3. Phân vai Data Engineer → QC Reviewer → QA Tester. Nếu môi trường có sub-agent, ủy quyền từng vai trò với đầu ra có kiểm chứng. Nếu không có, thực hiện theo các lượt role-based riêng biệt và nói đúng giới hạn.
4. Thực hiện toàn bộ Round 01 từ dữ liệu Excel thật: phân tích 15 cột; Data Contract; Snapshot Identity; test parser và comparison cho 4 snapshot / 3 cặp kiểm kê, bao gồm so sánh 2 file cùng ngày 09/10.
5. Đọc các skill đã quy định; nếu skill unavailable, ghi rõ và làm checklist tương đương.
6. Dùng workspace thực, không tự thực hiện Git ops, không chỉnh sửa source Excel, Google Drive, DB production hoặc secrets.
7. Chỉ PASS nếu QA/QC và automated tests có logs thật; không chế tạo kết quả.
8. Tạo chính xác một ZIP kết quả Round 01 và file SHA256 nằm ngoài ZIP. Gồm báo cáo ngắn tiếng Việt PASS/PARTIAL/BLOCKED/FAIL, issues và NEXT_ROUND_PROMPT.md.
9. DỪNG sau khi báo cáo Round 01 để tôi review/chấp thuận, không tự chuyển Round 02.

Bắt đầu ngay bằng việc xác minh các file và lập kế hoạch ngắn, sau đó thực thi.
```

## Bước 3 — Khi Round 01 kết thúc

Nhận từ Agent:

- `Round_01_Excel_Data_Contract.zip`
- `Round_01_Excel_Data_Contract.zip.sha256`
- Báo cáo ngắn trạng thái, test PASS/FAIL, vấn đề và bước tiếp.

Đối chiếu SHA256 trước khi nghiệm thu. Trạng thái PASS là quyết định dựa trên evidence, không tự động theo lời Agent.
