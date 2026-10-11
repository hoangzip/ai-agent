"""
Module: src/parser.py
Mục đích: Parse, kiểm tra hợp lệ (validate), và chuẩn hóa dữ liệu từ file Excel kiểm kê tồn kho (.xlsx).
Tuân thủ Data Contract 15 cột, bảo toàn chuỗi mã sản phẩm (giữ số 0 đầu chuỗi), kiểm tra summary row.
"""

import os
import hashlib
from typing import Dict, List, Any, Tuple, Optional
import openpyxl

EXPECTED_HEADERS = [
    "STT",
    "NGÀNH HÀNG",
    "MÃ SẢN PHẨM",
    "TÊN SẢN PHẨM",
    "SL TỒN KHO",
    "LOẠI KHO",
    "GIÁ (SAU VAT)",
    "THÀNH TIỀN",
    "SL PACKAGE KIỂM KÊ",
    "SL LẺ KIỂM KÊ",
    "TỔNG SL KIỂM KÊ",
    "CHÊNH LỆCH",
    "ĐVT PACKAGE",
    "QUY ĐỔI",
    "ĐVT LẺ"
]

class ExcelParseError(Exception):
    """Lỗi cấu trúc hoặc định dạng trong file Excel."""
    pass

class ExcelValidationError(Exception):
    """Lỗi tính hợp lệ của dữ liệu nghiệp vụ."""
    pass


def calculate_file_sha256(filepath: str) -> str:
    """Tính SHA256 của file nhị phân trên đĩa."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class InventoryExcelParser:
    def __init__(self, filepath: str, sheet_name: str = "Kiem-ke"):
        self.filepath = filepath
        self.sheet_name = sheet_name
        self.file_sha256 = calculate_file_sha256(filepath) if os.path.exists(filepath) else ""

    def parse(self) -> Dict[str, Any]:
        """
        Đọc và phân tích file Excel.
        Trả về dictionary chứa:
        - metadata: file info, sheet info, checksums
        - summary_row: tổng tồn kho và thành tiền khai báo tại dòng 2
        - items: danh sách các dòng chi tiết đã chuẩn hóa (dòng 3 trở đi)
        - calculated_totals: tổng tính toán độc lập từ detail rows
        - stock_counts: số lượng SKU theo từng loại kho
        - errors: danh sách cảnh báo hoặc lỗi không nghiêm trọng nếu có
        """
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Không tìm thấy file: {self.filepath}")

        # Tải với data_only=True để lấy giá trị số đã tính toán
        wb_data = openpyxl.load_workbook(self.filepath, data_only=True)
        # Tải với data_only=False để kiểm tra các công thức ở cột 11, 12 và dòng summary
        wb_formula = openpyxl.load_workbook(self.filepath, data_only=False)

        if self.sheet_name not in wb_data.sheetnames:
            raise ExcelParseError(
                f"Không tìm thấy sheet '{self.sheet_name}'. Các sheet hiện có: {wb_data.sheetnames}"
            )

        ws_data = wb_data[self.sheet_name]
        ws_formula = wb_formula[self.sheet_name]

        max_row = ws_data.max_row
        max_col = ws_data.max_column

        if max_row < 2:
            raise ExcelParseError("File không đủ số dòng tối thiểu (phải có ít nhất header và summary row)")

        # 1. Kiểm tra Header dòng 1
        headers = []
        for c in range(1, 16):
            val = ws_data.cell(1, c).value
            headers.append(str(val).strip() if val is not None else "")

        if headers != EXPECTED_HEADERS:
            mismatches = [
                f"Cột {i+1}: kỳ vọng '{EXPECTED_HEADERS[i]}', thực tế '{headers[i]}'"
                for i in range(15) if i < len(headers) and headers[i] != EXPECTED_HEADERS[i]
            ]
            raise ExcelParseError(f"Cấu trúc 15 cột không khớp: {'; '.join(mismatches)}")

        # 2. Đọc Summary row dòng 2
        summary_qty = ws_data.cell(2, 5).value
        summary_val = ws_data.cell(2, 8).value
        summary_audit_qty_formula = ws_formula.cell(2, 11).value
        summary_diff_formula = ws_formula.cell(2, 12).value

        summary_row = {
            "declared_quantity": float(summary_qty) if summary_qty is not None else 0.0,
            "declared_total_amount": float(summary_val) if summary_val is not None else 0.0,
            "audit_qty_formula": str(summary_audit_qty_formula),
            "discrepancy_formula": str(summary_diff_formula)
        }

        # 3. Đọc chi tiết từng dòng từ dòng 3
        items: List[Dict[str, Any]] = []
        seen_keys = set()
        wh_counts: Dict[str, int] = {}
        calc_qty = 0.0
        calc_val = 0.0

        for r in range(3, max_row + 1):
            stt_val = ws_data.cell(r, 1).value
            sku_raw = ws_data.cell(r, 3).value
            
            # Kiểm tra dòng trống hoàn toàn
            row_vals = [ws_data.cell(r, c).value for c in range(1, 16)]
            if all(v is None or str(v).strip() == "" for v in row_vals):
                continue

            if sku_raw is None or str(sku_raw).strip() == "":
                raise ExcelValidationError(f"Dòng {r}: Mã sản phẩm (cột 3) trống hoặc không hợp lệ")

            # BẢO TOÀN STRING MÃ SẢN PHẨM (giữ số 0 đầu chuỗi)
            sku = str(sku_raw).strip()

            category = str(ws_data.cell(r, 2).value or "").strip()
            product_name = str(ws_data.cell(r, 4).value or "").strip()
            
            # SL TỒN KHO
            qty_raw = ws_data.cell(r, 5).value
            try:
                quantity = float(qty_raw) if qty_raw is not None else 0.0
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Dòng {r}: SL tồn kho không phải dạng số: {qty_raw}")

            if quantity < 0:
                raise ExcelValidationError(f"Dòng {r}: SL tồn kho không được âm: {quantity}")

            warehouse = str(ws_data.cell(r, 6).value or "").strip()
            if not warehouse:
                raise ExcelValidationError(f"Dòng {r}: Loại kho trống")

            # GIÁ (SAU VAT)
            price_raw = ws_data.cell(r, 7).value
            try:
                price = float(price_raw) if price_raw is not None else 0.0
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Dòng {r}: Giá không phải dạng số: {price_raw}")

            # THÀNH TIỀN
            amt_raw = ws_data.cell(r, 8).value
            try:
                amount = float(amt_raw) if amt_raw is not None else 0.0
            except (ValueError, TypeError):
                raise ExcelValidationError(f"Dòng {r}: Thành tiền không phải dạng số: {amt_raw}")

            # Cột kiểm kê & đơn vị tính
            pkg_qty = float(ws_data.cell(r, 9).value or 0.0)
            loose_qty = float(ws_data.cell(r, 10).value or 0.0)
            audit_formula = ws_formula.cell(r, 11).value
            diff_formula = ws_formula.cell(r, 12).value
            pkg_unit = str(ws_data.cell(r, 13).value or "").strip()
            
            conv_raw = ws_data.cell(r, 14).value
            try:
                conv_rate = float(conv_raw) if conv_raw is not None else 1.0
            except (ValueError, TypeError):
                conv_rate = 1.0

            loose_unit = str(ws_data.cell(r, 15).value or "").strip()

            # Khóa tự nhiên: (mã sản phẩm, loại kho)
            natural_key = (sku, warehouse)
            if natural_key in seen_keys:
                raise ExcelValidationError(f"Dòng {r}: Trùng lặp khóa tự nhiên ({sku}, '{warehouse}')")
            seen_keys.add(natural_key)

            item = {
                "row_index": r,
                "stt": int(float(stt_val)) if stt_val is not None else r - 2,
                "category": category,
                "product_code": sku,
                "product_name": product_name,
                "quantity": quantity,
                "warehouse": warehouse,
                "unit_price": price,
                "total_amount": amount,
                "audit_package_qty": pkg_qty,
                "audit_loose_qty": loose_qty,
                "audit_total_qty_formula": str(audit_formula),
                "discrepancy_formula": str(diff_formula),
                "package_unit": pkg_unit,
                "conversion_rate": conv_rate,
                "loose_unit": loose_unit
            }
            items.append(item)

            calc_qty += quantity
            calc_val += amount
            wh_counts[warehouse] = wh_counts.get(warehouse, 0) + 1

        # 4. Đối chiếu tổng dòng chi tiết với dòng summary (Dòng 2)
        qty_matches = round(calc_qty, 4) == round(summary_row["declared_quantity"], 4)
        val_matches = round(calc_val, 2) == round(summary_row["declared_total_amount"], 2)

        if not qty_matches:
            raise ExcelValidationError(
                f"Lệch tổng số lượng tồn: Dòng 2 = {summary_row['declared_quantity']}, "
                f"Tổng chi tiết = {calc_qty}"
            )
        if not val_matches:
            raise ExcelValidationError(
                f"Lệch tổng thành tiền: Dòng 2 = {summary_row['declared_total_amount']}, "
                f"Tổng chi tiết = {calc_val}"
            )

        return {
            "metadata": {
                "filepath": self.filepath,
                "filename": os.path.basename(self.filepath),
                "file_sha256": self.file_sha256,
                "sheet_name": self.sheet_name,
                "total_rows": max_row,
                "detail_count": len(items)
            },
            "summary_row": summary_row,
            "calculated_totals": {
                "total_quantity": calc_qty,
                "total_amount": calc_val
            },
            "stock_counts": wh_counts,
            "items": items
        }
