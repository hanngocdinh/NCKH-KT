# -*- coding: utf-8 -*-
"""
tests/test_parsers.py – Bộ kiểm thử tự động cho parsers.py (Phiên bản 2)
======================================================================
"""

import sys
from datetime import date
from pathlib import Path
import pandas as pd
import pytest

# Thêm đường dẫn gốc vào sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import (
    parse_prose,
    determine_quality_flag,
    calculate_calibration_stats,
    compute_level_best,
    vn_float,
    normalize_vn,
    _RE_CAULAU_NAME,
)


def test_v1_full_sentence():
    """Test 1 (kế thừa v1): câu văn đầy đủ, trên BĐ3."""
    t = date(2025, 10, 29)
    text = "Mực nước trên sông Thu Bồn tại trạm Câu Lâu (lúc 7h ngày 29/10/2025) là 5,20m, trên BĐ3 1,20m."
    r = parse_prose(text, t)
    assert r["level_m_text"] is not None
    assert abs(r["level_m_text"] - 5.20) < 0.01
    assert r["alarm_ref"] == "BĐ3"
    assert abs(r["alarm_diff_m"] - 1.20) < 0.01
    assert r["level_hour"] == "7:00"
    assert r["alarm_class"] == "above_BĐ3"


def test_v1_short_sentence():
    """Test 2 (kế thừa v1): câu văn ngắn, dưới BĐ2."""
    t = date(2025, 10, 29)
    text = "Sông Thu Bồn tại Câu Lâu 2,87m, dưới BĐ2 0,13m."
    r = parse_prose(text, t)
    assert r["level_m_text"] is not None
    assert abs(r["level_m_text"] - 2.87) < 0.01
    assert r["alarm_ref"] == "BĐ2"
    assert abs(r["alarm_diff_m"] - (-0.13)) < 0.01
    assert r["alarm_class"] == "below_BĐ2"


def test_v1_slow_change():
    """Test 3 (kế thừa v1): ngày không có lũ ('biến đổi chậm')."""
    t = date(2025, 10, 29)
    text = "Mực nước trên sông Thu Bồn tại trạm Câu Lâu biến đổi chậm, dao động theo triều."
    r = parse_prose(text, t)
    assert r["level_m_text"] is None
    assert r["alarm_class"] == "no_alert_text"
    assert "biến đổi chậm" in r["trend_text"]
    assert "dao động theo triều" in r["trend_text"]


def test_v1_no_caulau():
    """Test 4 (kế thừa v1): không có Câu Lâu trong văn bản."""
    t = date(2025, 10, 29)
    text = "Mực nước sông Hương tại Kim Long lên mức 3,50m."
    r = parse_prose(text, t)
    assert r["level_m_text"] is None
    assert r["alarm_class"] == "no_section"


def test_v1_broken_line():
    """Test 5 (kế thừa v1): câu bị ngắt dòng giữa chừng."""
    t = date(2025, 10, 29)
    text = "... trên sông Thu Bồn tại trạm\nCâu Lâu là 4,15m,\ntrên BĐ3 0,15m..."
    r = parse_prose(text, t)
    assert r["level_m_text"] is not None
    assert abs(r["level_m_text"] - 4.15) < 0.01
    assert r["alarm_ref"] == "BĐ3"


# ── TEST MỚI CHO V2 ──────────────────────────────────────────────────────────

def test_v2_ai_nghia_preceding():
    """V2: Câu có trạm Ái Nghĩa đứng trước Câu Lâu -> phải lấy đúng số của Câu Lâu."""
    t = date(2025, 10, 29)
    text = (
        "Lũ trên sông Vu Gia-Thu Bồn dao động ở mức cao. Mực nước lúc 08 giờ ngày "
        "29/10/2025, trên sông Vu Gia tại trạm Ái Nghĩa là 9,92m, trên BĐ3 0,92m; trên sông "
        "Thu Bồn tại trạm Câu Lâu (lúc 7h ngày 29/10/2025) là 5,20m, trên BĐ3 1,20m."
    )
    r = parse_prose(text, t)
    assert r["level_m_text"] == 5.20, f"Mong đợi 5.20 nhưng nhận được {r['level_m_text']}"
    assert r["level_m_text"] != 9.92, "Lỗi: Đã nhận nhầm mực nước của trạm Ái Nghĩa!"
    assert r["alarm_ref"] == "BĐ3"
    assert r["alarm_diff_m"] == 1.20
    assert r["level_hour"] == "7:00"


def test_v2_forecast_separation():
    """V2: Câu dự báo không được đưa vào level_m_text mà lưu vào forecast_text."""
    t = date(2025, 10, 29)
    text = "Trong 6 giờ tới, lũ trên sông Thu Bồn tại Câu Lâu tiếp tục lên và ở trên mức BĐ3 từ 1,6-1,7m."
    r = parse_prose(text, t)
    assert r["level_m_text"] is None, f"Dự báo không được vào level_m_text, nhưng bị: {r['level_m_text']}"
    assert "1,6-1,7m" in r["forecast_text"] or "BĐ3" in r["forecast_text"]


def test_v2_known_day_30_10():
    """V2: Mẫu câu ngày 30/10/2025 lúc 2 giờ."""
    t = date(2025, 10, 30)
    text = "Mực nước lúc 2 giờ ngày 30/10/2025 trên sông Thu Bồn tại Câu Lâu là 5,62m, trên BĐ3 1,62m."
    r = parse_prose(text, t)
    assert r["level_m_text"] == 5.62
    assert r["alarm_ref"] == "BĐ3"
    assert abs(r["alarm_diff_m"] - 1.62) < 0.01
    assert r["level_hour"] == "2:00"
    assert r["alarm_class"] == "above_BĐ3"


def test_v2_table_tokens_with_empty_dashes():
    """V2: Hàng bảng có dấu '-' đơn lẻ -> là None, không phải 0."""
    line = "Thu Bồn Câu Lâu - - 55 -55"
    parts = line.split()
    # Tìm sau Câu Lâu: ['-', '-', '55', '-55']
    cl_idx = parts.index("Lâu")
    tokens = parts[cl_idx + 1:]
    parsed_vals = []
    for tok in tokens:
        if tok in ("-", "--", "—", "–"):
            parsed_vals.append(None)
        else:
            parsed_vals.append(vn_float(tok))

    assert parsed_vals[0] is None
    assert parsed_vals[1] is None
    assert parsed_vals[2] == 55.0
    assert parsed_vals[3] == -55.0


def test_v2_split_station_name_regex():
    """V2: Tên trạm bị cách rời chữ hoặc thừa dấu cách vẫn nhận ra."""
    samples = [
        "Thu Bồn C âu  L âu 534 515",
        "trạm Câu   Lâu 5,20m",
        "CÂU LÂU",
    ]
    for s in samples:
        norm = normalize_vn(s)
        assert _RE_CAULAU_NAME.search(norm) is not None, f"Không khớp với: {s}"


def test_v2_quality_flags():
    """V2: Kiểm tra các nhãn chất lượng mới."""
    assert determine_quality_flag({"status": "missing"}) == "missing_pdf"
    assert determine_quality_flag({"status": "ok", "level_m_text": 5.2}) == "ok_text"
    assert determine_quality_flag({"status": "ok", "level_m_text": 9.5}) == "check_range"
    assert determine_quality_flag({"status": "ok", "level_m_text": -1.0}) == "check_range"
    assert determine_quality_flag({"status": "ok", "level_m_text": None, "tbl_c1": 534.0}, calibrated_col=1) == "table_calibrated"
    assert determine_quality_flag({"status": "ok", "level_m_text": None, "tbl_c1": 534.0}, calibrated_col=None) == "table_only"
    assert determine_quality_flag({"status": "ok", "level_m_text": None, "alarm_class": "no_alert_text"}) == "no_alert_text"
    assert determine_quality_flag({"status": "ok", "level_m_text": None}) == "no_data"


def test_v2_module_e_calibration_stats():
    """V2: Module E hiệu chuẩn cột bảng bằng dữ liệu giả."""
    # Tạo 12 ngày giả định khớp 100% ở cột tbl_c1 (520cm = 5.20m)
    data = []
    for i in range(12):
        data.append({
            "date": f"2025-10-{i+1:02d}",
            "level_m_text": 5.20,
            "tbl_c1": 520.0,  # 520 cm / 100 = 5.20 m (khớp tuyệt đối)
            "tbl_c2": 450.0,  # 450 cm / 100 = 4.50 m (lệch 0.7m)
        })
    df_12 = pd.DataFrame(data)
    stats_12 = calculate_calibration_stats(df_12, max_k=2)

    c1_row = stats_12[stats_12["Cột bảng"] == "tbl_c1"].iloc[0]
    assert c1_row["Số ngày so sánh"] == 12
    assert c1_row["Khớp <= 5cm"] == 12
    assert c1_row["Tỉ lệ khớp (%)"] == 100.0
    assert c1_row["Lệch TB (m)"] == 0.0
    assert c1_row["Cảnh báo"] == ""  # Không có cảnh báo vì >= 10 ngày

    # Dưới 10 ngày -> có cảnh báo
    df_5 = df_12.iloc[:5]
    stats_5 = calculate_calibration_stats(df_5, max_k=2)
    c1_row_5 = stats_5[stats_5["Cột bảng"] == "tbl_c1"].iloc[0]
    assert c1_row_5["Số ngày so sánh"] == 5
    assert "⚠️ Chưa đủ bằng chứng" in c1_row_5["Cảnh báo"]


def test_v2_module_h_level_best():
    """V2: Module H ưu tiên nguồn: official > manual (verified=True) > text > table_calibrated."""
    df = pd.DataFrame([
        {
            "date": "2025-10-01",
            "level_official_m": 5.50,
            "level_manual_m": 5.40,
            "verified": True,
            "level_m_text": 5.30,
            "level_table_m": 5.20,
        },
        {
            "date": "2025-10-02",
            "level_official_m": None,
            "level_manual_m": 5.40,
            "verified": True,
            "level_m_text": 5.30,
            "level_table_m": 5.20,
        },
        {
            "date": "2025-10-03",
            "level_official_m": None,
            "level_manual_m": 5.40,
            "verified": False,  # Chưa xác nhận -> không được ưu tiên hơn text
            "level_m_text": 5.30,
            "level_table_m": 5.20,
        },
        {
            "date": "2025-10-04",
            "level_official_m": None,
            "level_manual_m": None,
            "verified": False,
            "level_m_text": None,
            "tbl_c1": 520.0,
        },
        {
            "date": "2025-10-05",
            "level_official_m": None,
            "level_manual_m": None,
            "verified": False,
            "level_m_text": None,
            "tbl_c1": None,
        },
    ])

    best_df = compute_level_best(df, calibrated_col=1)
    assert best_df.loc[0, "level_best"] == 5.50
    assert best_df.loc[0, "level_best_source"] == "official"

    assert best_df.loc[1, "level_best"] == 5.40
    assert best_df.loc[1, "level_best_source"] == "manual"

    assert best_df.loc[2, "level_best"] == 5.30
    assert best_df.loc[2, "level_best_source"] == "text"

    assert best_df.loc[3, "level_best"] == 5.20
    assert best_df.loc[3, "level_best_source"] == "table_calibrated"

    assert pd.isna(best_df.loc[4, "level_best"])
    assert best_df.loc[4, "level_best_source"] is None
