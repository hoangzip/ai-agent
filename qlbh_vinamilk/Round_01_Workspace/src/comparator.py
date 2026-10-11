"""
Module: src/comparator.py
Mục đích: Đối soát (so sánh) giữa 2 snapshot kiểm kê tồn kho bất kỳ (cùng ngày/khác ngày/cùng ca/khác ca).
Khóa tự nhiên: (mã sản phẩm, loại kho).
Phân loại chính xác: Matched (Tăng, Giảm, Không đổi), Mới xuất hiện (New), Không xuất hiện (Missing).
Xử lý chia cho 0 an toàn.
"""

from typing import Dict, List, Any, Optional, Tuple

class InventoryComparator:
    def __init__(self, snapshot_a: Dict[str, Any], snapshot_b: Dict[str, Any]):
        """
        snapshot_a và snapshot_b là output từ InventoryExcelParser.parse()
        """
        self.meta_a = snapshot_a["metadata"]
        self.meta_b = snapshot_b["metadata"]
        self.items_a = {
            (item["product_code"], item["warehouse"]): item
            for item in snapshot_a["items"]
        }
        self.items_b = {
            (item["product_code"], item["warehouse"]): item
            for item in snapshot_b["items"]
        }

    def compare(self) -> Dict[str, Any]:
        keys_a = set(self.items_a.keys())
        keys_b = set(self.items_b.keys())

        matched_keys = keys_a.intersection(keys_b)
        new_keys = keys_b - keys_a
        missing_keys = keys_a - keys_b

        increased = []
        decreased = []
        unchanged = []
        price_changed_qty_same = []

        total_delta_qty = 0.0
        total_delta_val = 0.0

        item_details = []

        # 1. Xử lý các sản phẩm xuất hiện ở cả 2 snapshot (Matched)
        for key in sorted(matched_keys):
            a = self.items_a[key]
            b = self.items_b[key]

            qty_a = a["quantity"]
            qty_b = b["quantity"]
            diff_qty = qty_b - qty_a

            val_a = a["total_amount"]
            val_b = b["total_amount"]
            diff_val = val_b - val_a

            total_delta_qty += diff_qty
            total_delta_val += diff_val

            # Tính % an toàn tránh chia cho 0
            if qty_a != 0:
                pct_qty_change = (diff_qty / qty_a) * 100.0
            else:
                pct_qty_change = None  # Phép chia cho 0 được xử lý an toàn

            if val_a != 0:
                pct_val_change = (diff_val / val_a) * 100.0
            else:
                pct_val_change = None

            status = "UNCHANGED"
            if diff_qty > 0:
                status = "INCREASED"
                increased.append(key)
            elif diff_qty < 0:
                status = "DECREASED"
                decreased.append(key)
            else:
                unchanged.append(key)

            # Trường hợp đổi đơn giá nhưng lượng không đổi
            if diff_qty == 0 and a["unit_price"] != b["unit_price"]:
                price_changed_qty_same.append({
                    "key": key,
                    "old_price": a["unit_price"],
                    "new_price": b["unit_price"],
                    "diff_val": diff_val
                })

            item_details.append({
                "product_code": key[0],
                "warehouse": key[1],
                "product_name": b["product_name"],
                "status": status,
                "qty_a": qty_a,
                "qty_b": qty_b,
                "diff_qty": diff_qty,
                "pct_qty_change": pct_qty_change,
                "price_a": a["unit_price"],
                "price_b": b["unit_price"],
                "val_a": val_a,
                "val_b": val_b,
                "diff_val": diff_val,
                "pct_val_change": pct_val_change
            })

        # 2. Xử lý các sản phẩm mới xuất hiện ở Snapshot B (New)
        new_items_list = []
        for key in sorted(new_keys):
            b = self.items_b[key]
            total_delta_qty += b["quantity"]
            total_delta_val += b["total_amount"]
            item_info = {
                "product_code": key[0],
                "warehouse": key[1],
                "product_name": b["product_name"],
                "status": "NEW",
                "qty_a": None,
                "qty_b": b["quantity"],
                "diff_qty": b["quantity"],
                "pct_qty_change": None,  # Mới xuất hiện, không có cơ sở chia cho A
                "price_a": None,
                "price_b": b["unit_price"],
                "val_a": None,
                "val_b": b["total_amount"],
                "diff_val": b["total_amount"],
                "pct_val_change": None
            }
            new_items_list.append(item_info)
            item_details.append(item_info)

        # 3. Xử lý các sản phẩm không xuất hiện ở Snapshot B (Missing)
        # Lưu ý: Không tự suy luận tồn B = 0
        missing_items_list = []
        for key in sorted(missing_keys):
            a = self.items_a[key]
            total_delta_qty -= a["quantity"]
            total_delta_val -= a["total_amount"]
            item_info = {
                "product_code": key[0],
                "warehouse": key[1],
                "product_name": a["product_name"],
                "status": "NOT_APPEARED",
                "qty_a": a["quantity"],
                "qty_b": None,
                "diff_qty": -a["quantity"],
                "pct_qty_change": -100.0 if a["quantity"] != 0 else None,
                "price_a": a["unit_price"],
                "price_b": None,
                "val_a": a["total_amount"],
                "val_b": None,
                "diff_val": -a["total_amount"],
                "pct_val_change": -100.0 if a["total_amount"] != 0 else None
            }
            missing_items_list.append(item_info)
            item_details.append(item_info)

        return {
            "summary": {
                "snapshot_a": self.meta_a["filename"],
                "snapshot_b": self.meta_b["filename"],
                "matched_count": len(matched_keys),
                "increased_count": len(increased),
                "decreased_count": len(decreased),
                "unchanged_count": len(unchanged),
                "new_count": len(new_keys),
                "not_appeared_count": len(missing_keys),
                "total_delta_quantity": total_delta_qty,
                "total_delta_value": total_delta_val,
                "price_changed_qty_same_count": len(price_changed_qty_same)
            },
            "new_keys": [list(k) for k in sorted(new_keys)],
            "missing_keys": [list(k) for k in sorted(missing_keys)],
            "price_changed_qty_same": price_changed_qty_same,
            "details": item_details
        }
