"""
collector/analysis/cic_extractor.py — High-precision CIC Credit Report & Score Extractor.

Extracts:
- Điểm tín dụng (Credit score: 300 - 850)
- Hạng (Credit tier: 1 - 10)
- Ngày chấm điểm / Ngày chấm (Scoring date: DD/MM/YYYY)
- Nợ xấu / Dư nợ (if available)

Uses fast native macOS Vision OCR binary (collector/bin/vision_ocr) or pytesseract fallback.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import logging
from pathlib import Path
import re
import shutil
import subprocess
from typing import Optional
import unicodedata

logger = logging.getLogger(__name__)

# Path to compiled vision_ocr binary
BIN_PATH = Path(__file__).resolve().parent.parent / "bin" / "vision_ocr"


def _strip_accents(s: str) -> str:
    """Normalize string and strip Vietnamese diacritics for resilient keyword matching."""
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def score_to_cic_tier(score: int) -> int:
    """
    Map CIC credit score to official CIC tier (Hạng 1 to 10).
    Based on official National Credit Information Center (CIC) scale:
      - Hạng 1:  645 - 850 (Rất tốt)
      - Hạng 2:  623 - 644 (Tốt)
      - Hạng 3:  609 - 622 (Khá)
      - Hạng 4:  588 - 608 (Trung bình khá)
      - Hạng 5:  567 - 587 (Trung bình)
      - Hạng 6:  545 - 566 (Dưới trung bình)
      - Hạng 7:  480 - 544 (Rủi ro trung bình cao)
      - Hạng 8:  455 - 479 (Rủi ro cao)
      - Hạng 9:  435 - 454 (Rủi ro rất cao)
      - Hạng 10: 300 - 434 (Nợ xấu / Cảnh báo)
    """
    if score >= 645:
        return 1
    elif score >= 623:
        return 2
    elif score >= 609:
        return 3
    elif score >= 588:
        return 4
    elif score >= 567:
        return 5
    elif score >= 545:
        return 6
    elif score >= 480:
        return 7
    elif score >= 455:
        return 8
    elif score >= 435:
        return 9
    return 10


@dataclass
class CICReportInfo:
    is_cic: bool = False
    # Credit Score & Tier
    score: Optional[int] = None
    tier: Optional[int] = None
    scoring_date: Optional[str] = None  # Format: DD/MM/YYYY
    # Customer Personal Identification (Thông tin định danh khách hàng)
    customer_name: Optional[str] = None      # Tên khách hàng / Họ và tên
    date_of_birth: Optional[str] = None      # Ngày tháng năm sinh (DD/MM/YYYY)
    cic_code: Optional[str] = None           # Mã số CIC
    address: Optional[str] = None            # Địa chỉ thường trú / Nơi cư trú
    phone_number: Optional[str] = None       # Số điện thoại
    id_card_number: Optional[str] = None     # Số CCCD / CMND
    # Debt & Provider Info
    total_debt: Optional[str] = None
    has_bad_debt: Optional[bool] = None
    provider: Optional[str] = None
    raw_text: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class CICExtractor:
    """Extracts structured credit score data from image files."""

    @staticmethod
    async def extract_from_image(image_path: str | Path) -> CICReportInfo:
        """Run OCR on image and parse structured CIC credit score info."""
        path = Path(image_path)
        if not path.exists():
            return CICReportInfo()

        raw_text = await CICExtractor._run_ocr(path)
        if not raw_text:
            return CICReportInfo()

        return CICExtractor.parse_text(raw_text)

    @staticmethod
    async def _run_ocr(image_path: Path) -> str:
        """Run OCR asynchronously using native macOS Vision OCR binary."""
        if BIN_PATH.exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(BIN_PATH),
                    str(image_path.resolve()),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and stdout:
                    return stdout.decode("utf-8", errors="replace")
            except Exception as e:
                logger.debug("vision_ocr execution failed: %s", e)

        # Fallback if vision_ocr fails or binary missing
        try:
            import pytesseract
            from PIL import Image
            return await asyncio.to_thread(pytesseract.image_to_string, Image.open(image_path), lang="vie+eng")
        except Exception:
            pass

        return ""

    @staticmethod
    def parse_text(text: str) -> CICReportInfo:
        """Parse structured fields (Score, Tier, Scoring Date, Debt) from OCR text."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        full_text = "\n".join(lines)
        norm_text = _strip_accents(full_text).lower()
        norm_lines = [_strip_accents(line).lower() for line in lines]

        # 0. Check if this is a credit report, score, loan statement, or debt/identity document
        cic_indicators = [
            "cic",
            "diem tin dung",
            "diem ten dung",
            "thong tin diem",
            "creditinfo",
            "cham diem",
            "cham doom",
            "ket thuc bao cao",
            "thong tin lich su no",
            "bao dam tien vay",
            "to chuc tin dung",
            "tctd",
            "mcredit",
            "fe credit",
            "fecredit",
            "hd saison",
            "hdsaison",
            "home credit",
            "homecredit",
            "shinhan",
            "tin dung",
            "hop dong",
            "giai quyet no",
            "nhac no",
            "thu hoi no",
            "khoan vay",
            "qua han",
            "du no",
            "vay tien",
            "vay von",
            "cccd",
            "cmnd",
        ]
        if not any(k in norm_text for k in cic_indicators):
            return CICReportInfo(raw_text=full_text)

        info = CICReportInfo(is_cic=True, raw_text=full_text)

        # Provider (MoMo, CIC, CreditInfo, Mcredit, etc.)
        if "momo" in norm_text:
            info.provider = "MoMo / CIC"
        elif "creditinfo" in norm_text or "cicb" in norm_text:
            info.provider = "CreditInfo / CIC"
        elif "mcredit" in norm_text:
            info.provider = "Mcredit"
        elif "fe credit" in norm_text or "fecredit" in norm_text:
            info.provider = "FE Credit"
        elif "hd saison" in norm_text or "hdsaison" in norm_text:
            info.provider = "HD Saison"
        elif "home credit" in norm_text or "homecredit" in norm_text:
            info.provider = "Home Credit"
        elif "shinhan" in norm_text:
            info.provider = "Shinhan Finance"
        elif "mirae asset" in norm_text:
            info.provider = "Mirae Asset"
        elif "easy credit" in norm_text:
            info.provider = "Easy Credit"
        elif "tpbank" in norm_text or "tien phong" in norm_text:
            info.provider = "TPBank"
        elif "vpbank" in norm_text:
            info.provider = "VPBank"
        elif "mb" in norm_text or "shinsei" in norm_text:
            info.provider = "MB Shinsei"
        else:
            info.provider = "CIC"

        # 1. Ngày chấm điểm (Scoring date)
        # Matches strictly "Ngày chấm điểm: 21/09/2026", "Ngày chấm: 02/07/2026", "Ngày chẩm điểm: 21/09/2026"
        m_date = re.search(
            r"(?:ngay\s*(?:cham\s*diem|cham\s*doom|cham))\s*[:\s]*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            norm_text,
        )
        if m_date:
            info.scoring_date = m_date.group(1).replace("-", "/")
        else:
            # Look in the "THÔNG TIN ĐIỂM TÍN DỤNG" section
            for i, l in enumerate(norm_lines):
                if "thong tin diem" in l:
                    for sub_line in lines[i:i + 8]:
                        m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", sub_line)
                        if m:
                            info.scoring_date = m.group(1).replace("-", "/")
                            break
                    break

        # Fallback to general report/inquiry date only if scoring date is missing
        if not info.scoring_date:
            m_report_date = re.search(
                r"(?:ngay\s*(?:hoi\s*tin|tra\s*loi|bao\s*cao[^:\n]*))\s*[:\s]*\n?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
                norm_text,
            )
            if m_report_date:
                info.scoring_date = m_report_date.group(1).replace("-", "/")

        # 2. Điểm tín dụng (Credit Score: 300 - 850)
        # Pattern A: "Điểm tín dụng: 602" or "Điểm: 543"
        m_score = re.search(r"(?:diem\s*(?:tin|ten)?\s*(?:dung)?\s*[:\s]*\n?)\s*(\d{3})", norm_text)
        if m_score and 300 <= int(m_score.group(1)) <= 850:
            info.score = int(m_score.group(1))

        # Pattern B: Score under section "THÔNG TIN ĐIỂM TÍN DỤNG"
        if not info.score:
            for i, l in enumerate(norm_lines):
                if "thong tin diem" in l:
                    for sub_line in lines[i:i + 8]:
                        m = re.search(r"\b(\d{3})\b", sub_line)
                        if m and 300 <= int(m.group(1)) <= 850:
                            info.score = int(m.group(1))
                            break
                    break

        # Pattern C: Standalone 3-digit score in screenshot
        if not info.score:
            for i, line in enumerate(lines):
                m = re.match(r"^(\d{3})$", line)
                if m and 300 <= int(m.group(1)) <= 850:
                    surr = " ".join(lines[max(0, i - 3):min(len(lines), i + 4)]).lower()
                    if any(w in surr for w in ("hang", "cic", "momo", "tin dung", "cham")):
                        info.score = int(m.group(1))
                        break

        # 3. Hạng (Credit Tier: 1 - 10)
        # MoMo style: "Hạng 7 ©"
        if "momo" in norm_text:
            m_tier = re.search(r"hang\s*(\d{1,2})", norm_text)
            if m_tier and 1 <= int(m_tier.group(1)) <= 10:
                info.tier = int(m_tier.group(1))

        # Direct explicit tier in official reports: "Hạng: 4" (avoid header row like 09)
        if not info.tier:
            m_tier = re.search(r"\bhang\s*[:\s]+0?([1-9]|10)\b(?![\s\w-]*403)", norm_text)
            if m_tier:
                info.tier = int(m_tier.group(1))

        # Tier derivation from score using official CIC scale
        if not info.tier and info.score:
            info.tier = score_to_cic_tier(info.score)

        # 4. Bad debt info (Nợ xấu)
        # Check explicit negative signals first
        if re.search(r"(?:khong\s*co\s*no\s*xau|no\s*xau\s*[:\s]*0\b|no\s*xau\s*0\b)", norm_text):
            info.has_bad_debt = False
        elif re.search(r"(?:ban\s*)?co\s*khoan\s*no\s*xau", norm_text):
            info.has_bad_debt = True
        elif re.search(r"no\s*xau\s*[:\s]*[1-9]\d*", norm_text):
            info.has_bad_debt = True
        elif any(w in norm_text for w in ("no qua han", "qua han nghiem trong", "dut no", "du no xau", "thu hoi no", "don to cao")):
            info.has_bad_debt = True

        # 5. Total debt (Tổng dư nợ / Khoản nợ / Khoản vay) - Requires explicit currency unit or formatted amount
        m_debt = re.search(
            r"(?:tổng\s*(?:cộng\s*)?(?:dư\s*)?nợ|dư\s*nợ\s*(?:khoản\s*vay|hiện\s*thời)?|tong\s*du\s*no|khoản\s*(?:nợ|vay)\s*(?:của\s*bạn)?|hạn\s*mức\s*(?:khoản\s*vay)?)\s*[:\s\n]*((?:[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+(?:[.,][0-9]+)?)\s*(?:triệu\s*vnđ|triệu|tr|tỷ|vnđ|trieu|vnd|đồng|đ))\b",
            full_text,
            re.IGNORECASE,
        )
        if m_debt:
            cand_debt = m_debt.group(1).strip()
            if not re.match(r"^\d[.,]?$", cand_debt):
                info.total_debt = cand_debt
        else:
            # Fallback for multiline layout (e.g. MoMo screenshot with label and value separated)
            for i, l in enumerate(norm_lines):
                if any(k in l for k in ("tong du no", "du no khoan vay", "tong no", "khoan vay cua ban", "khoan vay")):
                    for sub in lines[i + 1:i + 6]:
                        m_sub = re.search(r"((?:[0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+(?:[.,][0-9]+)?)\s*(?:triệu\s*vnđ|triệu|tr|tỷ|vnđ|đồng|vnd|đ))\b", sub, re.IGNORECASE)
                        if m_sub:
                            info.total_debt = m_sub.group(1).strip()
                            break
                    if info.total_debt:
                        break

        # 6. Customer Identification (Thông tin định danh cá nhân)
        CICExtractor._extract_personal_info(lines, norm_lines, full_text, norm_text, info)

        # Final check: if no actual structured CIC/debt/identity information was extracted, mark is_cic=False
        has_any_data = any([
            info.score is not None,
            info.tier is not None,
            info.scoring_date is not None,
            info.customer_name is not None,
            info.id_card_number is not None,
            info.cic_code is not None,
            info.total_debt is not None,
            info.has_bad_debt is True,
        ])
        if not has_any_data:
            info.is_cic = False

        return info

    @staticmethod
    def _extract_personal_info(
        lines: list[str],
        norm_lines: list[str],
        full_text: str,
        norm_text: str,
        info: CICReportInfo,
    ) -> None:
        """Extract customer identity information (Tên, Ngày sinh, Mã số CIC, Địa chỉ, SĐT, Số CCCD/CMND)."""
        # Try global regex first for customer name
        m_name = re.search(
            r"(?:tên\s*(?:khách\s*hàng|kh)|họ\s*và\s*tên)\s*[:\s]+([^\n|\t]+)",
            full_text,
            re.IGNORECASE,
        )
        if m_name:
            cand = " ".join(m_name.group(1).strip().split())
            if len(cand) >= 2 and not any(k in cand.lower() for k in ("ngày", "mã số", "địa chỉ")):
                info.customer_name = cand

        if not info.customer_name:
            cand_matches = re.findall(
                r"(?:ông\/bà|ong\/ba|nếu|neu|khách\s*hàng|kh|anh|chị)\s+([^\n,\t]+?)(?=[,\s]+(?:cccd|cmnd|sinh|sn|\d|\n|$))",
                full_text,
                re.IGNORECASE,
            )
            for m in cand_matches:
                cand = " ".join(m.strip().split())
                if cand.isupper() and len(cand.split()) >= 2 and not any(k in cand.lower() for k in ("đang", "sinh sống", "vui lòng", "liên hệ")):
                    info.customer_name = cand
                    break

        # Try global regex for DOB
        m_dob = re.search(
            r"(?:ngày\s*(?:tháng\s*năm\s*)?sinh|năm\s*sinh)\s*[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if m_dob:
            info.date_of_birth = m_dob.group(1).replace("-", "/")

        # Try global regex for CIC Code
        m_cic = re.search(r"(?:mã\s*(?:số)?\s*cic)\s*[:\s]+([0-9A-Z]{6,15})", full_text, re.IGNORECASE)
        if m_cic:
            info.cic_code = m_cic.group(1).strip()

        # Try global regex for CCCD / CMND
        m_cccd = re.search(r"(?:cccd|cmnd|căn\s*cước|số\s*đdcn)\s*[:\s]*([^\n|]+)", full_text, re.IGNORECASE)
        if m_cccd:
            found_ids = re.findall(r"\b\d{9}\b|\b\d{12}\b", m_cccd.group(1))
            if found_ids:
                info.id_card_number = " / ".join(dict.fromkeys(found_ids))

        # Try global regex for Phone
        m_phone = re.search(
            r"(?:điện\s*thoại|sđt|sdt|đt|dt|di\s*động|lh|liên\s*hệ|zalo|hotline|tel|call)\s*[:\s.-]+([0-9\s.+-]{9,15})",
            full_text,
            re.IGNORECASE,
        )
        if m_phone:
            cleaned_phone = re.sub(r"[^\d+]", "", m_phone.group(1))
            if 9 <= len(cleaned_phone) <= 12:
                info.phone_number = cleaned_phone

        # Fallback to standalone VN phone number pattern (03x, 05x, 07x, 08x, 09x)
        if not info.phone_number:
            m_vn_phone = re.search(
                r"\b(0(?:3[2-9]|5[6-9]|7[06-9]|8[1-9]|9[0-9])[.\s-]?\d{3}[.\s-]?\d{4})\b",
                full_text,
            )
            if m_vn_phone:
                cand_phone = re.sub(r"[^\d]", "", m_vn_phone.group(1))
                if len(cand_phone) == 10:
                    info.phone_number = cand_phone

        # Debt amount in notices
        if not info.total_debt:
            m_amount = re.search(
                r"(?:sô\s*tiên|số\s*tiền|dư\s*nợ|khoản\s*nợ)\s*(?:tạm\s*tính\s*)?(?:là)?\s*[:\s]*([0-9.,]+\s*(?:vnđ|vnd|đ|đồng|triệu|tr))\b",
                full_text,
                re.IGNORECASE,
            )
            if m_amount:
                cand = m_amount.group(1).strip()
                if not re.match(r"^\d[.,]?$", cand):
                    info.total_debt = cand

        # Clean & validate total_debt
        if info.total_debt:
            clean_d = info.total_debt.strip(" ,.-:;")
            if len(clean_d) < 3 or re.match(r"^\d+[.,]?$", clean_d):
                info.total_debt = None
            else:
                info.total_debt = clean_d

        # Overdue / collection notice indicator
        if info.has_bad_debt is None:
            if any(w in norm_text for w in ("no qua han", "qua han nghiem trong", "dut no", "thu hoi no", "don to cao", "khoi kien")):
                info.has_bad_debt = True

        # Line-by-line fallback for structured table blocks without colons
        for i, (l, nl) in enumerate(zip(lines, norm_lines)):
            # 1. Customer Name fallback
            if not info.customer_name and re.search(r"^(?:1\.\s*)?(?:ten\s*khach\s*hang|ho\s*va\s*ten|ten\s*kh)\b", nl):
                inline = re.split(r"[:\t|]", l, maxsplit=1)
                if len(inline) > 1 and inline[1].strip():
                    info.customer_name = inline[1].strip()
                elif i + 1 < len(lines):
                    next_l = lines[i + 1].strip()
                    if not any(k in _strip_accents(next_l).lower() for k in ("ngay", "ma so", "dia chi", "dien thoai", "cccd", "cmnd")):
                        info.customer_name = next_l

            # 2. DOB fallback
            if not info.date_of_birth and re.search(r"^(?:ngay\s*(?:thang\s*nam\s*)?sinh|nam\s*sinh)\b", nl):
                m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", l)
                if m:
                    info.date_of_birth = m.group(1).replace("-", "/")
                elif i + 1 < len(lines):
                    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})", lines[i + 1])
                    if m:
                        info.date_of_birth = m.group(1).replace("-", "/")

            # 3. CIC code fallback
            if not info.cic_code and re.search(r"^ma\s*(?:so)?\s*cic\b", nl):
                inline = re.split(r"[:\t|]", l, maxsplit=1)
                if len(inline) > 1 and re.search(r"\b([0-9A-Z]{6,15})\b", inline[1]):
                    info.cic_code = re.search(r"\b([0-9A-Z]{6,15})\b", inline[1]).group(1)
                elif i + 1 < len(lines):
                    m = re.search(r"\b([0-9A-Z]{6,15})\b", lines[i + 1])
                    if m:
                        info.cic_code = m.group(1)

            # 4. Address
            if not info.address and re.search(r"^(?:dia\s*chi(?:\s*thuong\s*tru)?|noi\s*cu\s*tru)\b", nl):
                inline = re.split(r"[:\t|]", l, maxsplit=1)
                if len(inline) > 1 and len(inline[1].strip()) > 5:
                    addr = inline[1].strip()
                    addr = re.split(r"(?:dien\s*thoai|sdt|cccd|cmnd)", addr, flags=re.IGNORECASE)[0]
                    info.address = " ".join(addr.split())
                elif i + 1 < len(lines):
                    addr_parts = []
                    for sub in lines[i + 1:i + 4]:
                        sub_nl = _strip_accents(sub).lower()
                        if any(k in sub_nl for k in ("dien thoai", "sdt", "cccd", "cmnd", "thong tin", "ii.")):
                            break
                        addr_parts.append(sub)
                    if addr_parts:
                        info.address = " ".join(" ".join(addr_parts).split())

            # 5. Phone fallback
            if not info.phone_number and re.search(r"^(?:dien\s*thoai|sdt|di\s*dong)\b", nl):
                m = re.search(r"([0-9\s.+-]{9,15})", l)
                if m and len(re.sub(r"[^\d]", "", m.group(1))) >= 9:
                    info.phone_number = re.sub(r"[^\d+]", "", m.group(1))
                elif i + 1 < len(lines):
                    m = re.search(r"([0-9\s.+-]{9,15})", lines[i + 1])
                    if m and len(re.sub(r"[^\d]", "", m.group(1))) >= 9:
                        info.phone_number = re.sub(r"[^\d+]", "", m.group(1))

            # 6. Số CCCD/CMND
            if not info.id_card_number and re.search(r"^(?:so\s*)?(?:cccd|cmnd|can\s*cuoc|dinh\s*danh)\b", nl):
                id_block = " ".join(lines[i:i + 4])
                id_block = re.split(r"(?:2\.\s*thông|thông\s*tin|ii\.)", id_block, flags=re.IGNORECASE)[0]
                found = re.findall(r"\b\d{9}\b|\b\d{12}\b", id_block)
                if found:
                    info.id_card_number = " / ".join(dict.fromkeys(found))

        # Filter out CIC headquarters address and hotline if mistakenly captured
        if info.phone_number and (info.phone_number.startswith("1800") or info.phone_number.startswith("1900") or info.phone_number in ("1800585891", "1800585892", "02433527881")):
            info.phone_number = None

        # Clean & validate address
        if info.address:
            clean_addr = info.address.strip(" ,.-:;")
            norm_addr = _strip_accents(clean_addr).lower()
            if len(clean_addr) < 8 or any(norm_addr.startswith(x) for x in ("dien thoai", "sdt", "dt", "cccd", "cmnd", "so dien thoai")) or any(k in norm_addr for k in ("45 ly thuong kiet", "ly thuong kiet")):
                info.address = None
            elif not any(k in norm_addr for k in ("xa", "phuong", "quan", "huyen", "tinh", "tp", "thanh pho", "duong", "to ", "thon", "ap ", "so ", "khu ")):
                info.address = None
            else:
                info.address = clean_addr

        # Validate customer name
        if info.customer_name:
            cand_norm = _strip_accents(info.customer_name).upper()
            invalid_terms = (
                "VAY CA NHAN", "DANH GIA DIEM", "THONG TIN", "CHI TIET", "BAO CAO",
                "DIEM TIN DUNG", "KHACH HANG", "CA NHAN", "KHO DU LIEU", "NGAN HANG",
                "LUU Y", "TONG NO", "DU NO", "LICH SU NO", "TO CHUC", "CHI NHANH",
                "DIEM HANG", "BAO HIEM", "HANG", "NGAY CHAM", "CONG TY"
            )
            if any(term in cand_norm for term in invalid_terms) or len(info.customer_name) < 3 or len(info.customer_name) > 40:
                info.customer_name = None
