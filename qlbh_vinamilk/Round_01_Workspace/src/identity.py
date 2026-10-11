"""
Module: src/identity.py
Mục đích: Định danh Snapshot (Snapshot Identity), trích xuất metadata từ filename & content,
tính content checksum, và thực thi chính sách deduplication/conflict.
"""

import re
import hashlib
import json
from typing import Dict, Any, Optional, Tuple, List

FILENAME_REGEX = re.compile(
    r"^KiemKe_(?P<doc_prefix>[A-Z]+)\.(?P<store_code>[A-Z0-9]+)\.(?P<year_prefix>\d{2})\.(?P<ticket_num>\d+)(?:_(?P<date_str>\d{8}))?\.xlsx$"
)

class SnapshotIdentity:
    def __init__(self, filename: str, file_sha256: str = "", parsed_items: Optional[list] = None):
        self.filename = filename
        self.file_sha256 = file_sha256
        self.parsed_items = parsed_items or []
        self._parse_filename()

    def _parse_filename(self):
        match = FILENAME_REGEX.match(self.filename)
        if match:
            gd = match.groupdict()
            self.doc_prefix = gd["doc_prefix"]
            self.store_code = gd["store_code"]
            self.year_prefix = gd["year_prefix"]
            self.ticket_number = gd["ticket_num"]
            self.full_code = f"{self.doc_prefix}.{self.store_code}.{self.year_prefix}.{self.ticket_number}"
            
            raw_date = gd.get("date_str")
            if raw_date and len(raw_date) == 8:
                self.inventory_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            else:
                self.inventory_date = None
        else:
            # Fallback nếu tên file không theo quy chuẩn
            self.doc_prefix = "UNKNOWN"
            self.store_code = "UNKNOWN"
            self.year_prefix = "UNKNOWN"
            self.ticket_number = "UNKNOWN"
            self.full_code = self.filename
            self.inventory_date = None

    def calculate_content_hash(self) -> str:
        """
        Tính hash nội dung dựa trên danh sách sản phẩm chuẩn hóa đã sắp xếp.
        Giúp phát hiện trùng lặp nội dung ngay cả khi file bị re-save làm đổi binary hash.
        """
        if not self.parsed_items:
            return ""

        # Chuẩn hóa dữ liệu cốt lõi để băm
        normalized = []
        for it in sorted(self.parsed_items, key=lambda x: (x["product_code"], x["warehouse"])):
            normalized.append({
                "sku": it["product_code"],
                "wh": it["warehouse"],
                "qty": it["quantity"],
                "price": it["unit_price"],
                "amt": it["total_amount"]
            })
        data_str = json.dumps(normalized, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

    def to_metadata_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "full_code": self.full_code,
            "ticket_number": self.ticket_number,
            "store_code": self.store_code,
            "inventory_date": self.inventory_date,
            "file_sha256": self.file_sha256,
            "content_hash": self.calculate_content_hash(),
            # Ca kiểm kê mặc định là Chưa xác định khi chưa qua xác nhận audit
            "shift": "Chưa xác định"
        }

    @staticmethod
    def evaluate_ingestion_policy(
        incoming_meta: Dict[str, Any],
        existing_records: Dict[str, Dict[str, Any]]
    ) -> Tuple[str, str]:
        """
        Xác định chính sách tiếp nhận snapshot đối với cơ sở dữ liệu:
        Trả về (Action, Reason)
        Action có thể là: 'NEW', 'DUPLICATE', 'CONFLICT', 'ALREADY_IMPORTED', 'SOFT_DELETED'
        """
        key = incoming_meta["full_code"]
        existing = existing_records.get(key)

        if not existing:
            return "NEW", "Chứng từ kiểm kê mới chưa từng tồn tại"

        if existing.get("is_deleted", False):
            return "SOFT_DELETED", "Chứng từ này đã bị Admin xóa mềm. Không tự động phục hồi khi sync/import lại."

        if existing.get("file_sha256") == incoming_meta.get("file_sha256"):
            return "ALREADY_IMPORTED", "File nhị phân chính xác đã được import trước đó"

        if existing.get("content_hash") == incoming_meta.get("content_hash"):
            return "DUPLICATE", "Chứng từ trùng mã và nội dung dữ liệu kiểm kê hoàn toàn giống nhau (Bỏ qua/Cảnh báo)"

        # Trùng mã nhưng khác content hash -> Xung đột nghiêm trọng
        return "CONFLICT", (
            f"Chứng từ {key} đã tồn tại với nội dung khác (hash cũ: {existing.get('content_hash')[:8]}, "
            f"hash mới: {incoming_meta.get('content_hash')[:8]}). Cấm tự động ghi đè."
        )
