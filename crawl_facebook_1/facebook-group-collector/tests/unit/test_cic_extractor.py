"""
tests/unit/test_cic_extractor.py — Unit tests for CIC credit report extraction.
Verifies parsing of score, tier, and scoring date (Ngày chấm điểm) across formats.
"""
import pytest
from pathlib import Path

from collector.analysis.cic_extractor import (
    CICExtractor,
    CICReportInfo,
    score_to_cic_tier,
)


def test_score_to_cic_tier_mapping():
    assert score_to_cic_tier(750) == 1
    assert score_to_cic_tier(645) == 1
    assert score_to_cic_tier(630) == 2
    assert score_to_cic_tier(615) == 3
    assert score_to_cic_tier(602) == 4
    assert score_to_cic_tier(575) == 5
    assert score_to_cic_tier(550) == 6
    assert score_to_cic_tier(543) == 7
    assert score_to_cic_tier(460) == 8
    assert score_to_cic_tier(440) == 9
    assert score_to_cic_tier(350) == 10


def test_parse_momo_cic_report():
    raw_ocr = """
    18:15
    Kiểm tra Điểm tín dụng CIC
    543
    Hạng 7 ©
    Ngày chấm: 02/07/2026
    Đã tới kỳ chấm điểm mới. Cập nhật ngay!
    Điểm cao hơn 16% khách hàng cá nhân khác
    Được chấm bởi CIC và hiển thị trên MoMo
    Theo dữ liệu tính đến ngày chấm 02/07/2026, bạn không có nợ xấu hoặc nợ cần chú ý.
    Tổng dư nợ: 18 Triệu VNĐ
    """
    res = CICExtractor.parse_text(raw_ocr)

    assert res.is_cic is True
    assert res.score == 543
    assert res.tier == 7
    assert res.scoring_date == "02/07/2026"
    assert res.provider == "MoMo / CIC"
    assert res.has_bad_debt is False
    assert "18 Triệu VNĐ" in (res.total_debt or "")


def test_parse_official_cic_report():
    raw_ocr = """
    2.3. Thông tin về đảm bảo tiền vay
    STT 1 Giá trị Không có
    II. THÔNG TIN ĐIỂM TÍN DỤNG
    Điểm tín dụng:
    602
    Hạng: 4
    Ngày chấm điểm:
    21/09/2026
    Xếp hạng của khách hàng
    ĐÁNH GIÁ ĐIỂM TÍN DỤNG
    KẾT THÚC BÁO CÁO
    """
    res = CICExtractor.parse_text(raw_ocr)

    assert res.is_cic is True
    assert res.score == 602
    assert res.tier == 4
    assert res.scoring_date == "21/09/2026"
    assert res.provider == "CIC"


def test_parse_cic_with_ocr_typos():
    """Test OCR variations like 'chẩm điểm', 'Điêm tin dung' without accents."""
    raw_ocr = """
    II. THÔNG TIN ĐIÊM TÍN DỤNG
    Điêm tin dung
    569
    Histor
    Ngày chẩm điểm: 21/09/2026
    CHI TIẾT ĐIỂM VÀ HẠNG
    KẾT THÚC BÁO CÁO
    """
    res = CICExtractor.parse_text(raw_ocr)

    assert res.is_cic is True
    assert res.score == 569
    assert res.tier == 5  # Derived via standard CIC table for 569 (567-587)
    assert res.scoring_date == "21/09/2026"


def test_parse_non_cic_content():
    raw_ocr = """
    Lâm Chạy Hs Shinhan Bank 2
    Lâm Chạy Hs Shinhan Bank chưa có hoạt động nào. Hãy trò chuyện để hiểu nhau hơn.
    Nhắn tin
    """
    res = CICExtractor.parse_text(raw_ocr)
    assert res.is_cic is False
    assert res.score is None
    assert res.tier is None
    assert res.scoring_date is None


def test_parse_cic_personal_identity_info():
    raw_ocr = """
    TRUNG TÂM THÔNG TIN TÍN DỤNG QUỐC GIA VIỆT NAM
    THÔNG TIN TÍN DỤNG KHÁCH HÀNG VAY CÁ NHÂN
    Số: 2026/K11.1
    I. THÔNG TIN TÍN DỤNG CỦA KHÁCH HÀNG TẠI KHO DỮ LIỆU CIC
    1. Thông tin định danh
    Tên khách hàng: NGUYỄN ĐÌNH LONG
    Ngày tháng năm sinh: 24/07/1993
    Mã số CIC: 0198021822
    Địa chỉ: THÔN PHÙ LONG 3, XÃ LONG XUYÊN, HUYỆN PHÚC THỌ, THÀNH PHỐ HÀ NỘI
    Điện thoại: 0983621343
    Số CCCD/CMND: 001093010399 / 017182034

    II. THÔNG TIN ĐIỂM TÍN DỤNG
    Điểm tín dụng: 551
    Hạng: 6
    Ngày chấm điểm: 27/08/2026
    """
    res = CICExtractor.parse_text(raw_ocr)

    assert res.is_cic is True
    assert res.customer_name == "NGUYỄN ĐÌNH LONG"
    assert res.date_of_birth == "24/07/1993"
    assert res.cic_code == "0198021822"
    assert "THÔN PHÙ LONG 3" in (res.address or "")
    assert res.phone_number == "0983621343"
    assert "001093010399" in (res.id_card_number or "")
    assert "017182034" in (res.id_card_number or "")
    assert res.score == 551
    assert res.tier == 6
    assert res.scoring_date == "27/08/2026"


@pytest.mark.asyncio
async def test_extract_from_crawled_images_if_present():
    """Verify live extraction from actual group image if exists."""
    sample_img = Path("data/groups/978769317924542/images/posts/8840730d-bf4e-4279-9414-fb8cbd3f47e5_0.jpg")
    if not sample_img.exists():
        pytest.skip("Crawled image not available")

    info = await CICExtractor.extract_from_image(sample_img)
    assert info.is_cic is True
    assert info.score == 543
    assert info.tier == 7
    assert info.scoring_date == "02/07/2026"
