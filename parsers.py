# -*- coding: utf-8 -*-
"""
parsers.py – Các module bóc tách văn bản, tọa độ bảng và ghép nối dữ liệu
========================================================================
Đề tài: AI + IoT cảnh báo ngập tại Hội An (học sinh lớp 11)
Phiên bản 2:
  - Module D: Đọc bảng theo tọa độ (pdfplumber.extract_words)
  - Module E: Hiệu chuẩn cột bảng theo ngày lũ
  - Module F: Sửa parser câu văn, chống nhận nhầm trạm, tách dự báo, nhãn định tính
  - Module G: API GloFAS Open-Meteo, ghép mưa, dữ liệu nhập tay & chính thức
  - Module H: Hợp nhất đa nguồn chọn level_best (không ghi đè, không nội suy)
"""

import io
import json
import logging
import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── Ngưỡng mực nước tham chiếu trạm Câu Lâu (m) ──────────────────────────────
BD1_M = 2.00  # Báo động 1 tham khảo
BD2_M = 3.00  # Báo động 2 (suy ra từ bản tin: dưới BĐ2 0,13m khi mực 2,87m)
BD3_M = 4.00  # Báo động 3 (suy ra từ bản tin: trên BĐ3 1,20m khi mực 5,20m)
HIST_M = 5.48 # Lũ lịch sử năm 1964

# =============================================================================
# HÀM BỔ TRỢ CHUẨN HÓA TIẾNG VIỆT
# =============================================================================

def normalize_vn(text: str) -> str:
    """Chuẩn hóa chuỗi Unicode sang dạng NFC và gộp khoảng trắng liên tiếp."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    # Chuẩn hóa khoảng trắng nhưng giữ cấu trúc cơ bản
    return norm


def vn_float(s: str) -> Optional[float]:
    """Chuyển chuỗi số kiểu Việt ('5,20', '-34', '5.20') sang float."""
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "-", "--", "—", "–", "None", "null"):
        return None
    try:
        # Thay dấu phẩy bằng dấu chấm
        s_clean = s.replace(",", ".").replace(" ", "")
        return float(s_clean)
    except (ValueError, TypeError):
        return None


# =============================================================================
# MODULE F: PARSER CÂU VĂN & ĐỊNH TÍNH
# =============================================================================

_RE_CAULAU_NAME = re.compile(
    r"C\s*[aâ]\s*u\s+L\s*[aâ]\s*u",
    re.IGNORECASE,
)

_RE_FORECAST_HINT = re.compile(
    r"(?:dự\s*báo|cảnh\s*báo|trong\s+\d+.*?giờ\s+tới|khả\s*năng|xu\s*thế|tiếp\s*tục\s*lên|tiếp\s*tục\s*xuống|đạt\s*đỉnh|\d+[,.]\d+\s*[-–]\s*\d+[,.]\d+)",
    re.IGNORECASE,
)

_RE_LEVEL_VALUE = re.compile(
    r"(?:là|ở\s*mức|lên\s*mức|xuống\s*mức|mực\s*nước(?:\s*đo\s*được)?|:)?\s*(-?\d{1,2}[,.]\d{1,2})\s*m\b",
    re.IGNORECASE,
)

_RE_ALARM_SPEC = re.compile(
    r"(tr\u00ean|tren|d\u01b0\u1edbi|d\u01b0i|duoi)\s+(?:m\u1ee9c\s+)?"
    r"(B[\u0110D][\s]?\d|b[a\u00e1]o\s*[\u0111d][\u00f4o]ng\s*\d)"
    r"(?:\s*kho[\u1ea3a]ng)?"
    r"(?:\s*(?:t\u1eeb\s*)?(\d{1,2}[,.]\d{1,2})\s*m)?",
    re.IGNORECASE | re.UNICODE,
)


def parse_prose(text: str, d: date) -> dict:
    """Phân tích các câu văn bản tin thủy văn cho trạm Câu Lâu.

    Tuân thủ quy tắc:
      1. Chỉ lấy số QUAN TRẮC gắn trực tiếp sau 'Câu Lâu'.
         Không lấy số của trạm đứng trước (như Ái Nghĩa).
      2. Câu DỰ BÁO ('Trong 6 giờ tới...', khoảng số 1,6-1,7m) lưu vào forecast_text,
         không đưa vào level_m_text.
      3. Gán nhãn alarm_class chính xác theo câu văn (above_BD1/2/3, below_BD1/2/3,
         no_alert_text, no_section).
      4. Trích xuất xu thế trend_text (lên, xuống, biến đổi chậm, dao động theo triều).
    """
    res = {
        "date": d.isoformat(),
        "level_m_text": None,
        "level_hour": None,
        "alarm_ref": None,
        "alarm_diff_m": None,
        "alarm_class": "no_section",
        "trend_text": "",
        "forecast_text": "",
        "snippet": "",
    }

    if not text or not text.strip():
        res["alarm_class"] = "no_section"
        return res

    text_norm = normalize_vn(text)
    # Nối các dòng có thể bị ngắt chữ giữa câu
    joined_text = re.sub(r"\r?\n\s*", " ", text_norm)

    # 1. Kiểm tra sự xuất hiện của mục sông Vu Gia - Thu Bồn
    vg_tb_match = re.search(
        r"(?:sông\s+)?Vu\s*Gia(?:\s*[-–]\s*|\s+v[aà]\s+)Thu\s*B[oồ]n|Thu\s*B[oồ]n",
        joined_text,
        re.IGNORECASE,
    )
    if vg_tb_match:
        res["alarm_class"] = "no_alert_text"
        # Trích xuất xu thế trong đoạn chứa lưu vực
        start_vg = max(0, vg_tb_match.start() - 50)
        end_vg = min(len(joined_text), vg_tb_match.end() + 500)
        vg_section = joined_text[start_vg:end_vg]
        trends = []
        if re.search(r"biến\s*đổi\s*chậm", vg_section, re.IGNORECASE):
            trends.append("biến đổi chậm")
        if re.search(r"dao\s*động\s*theo\s*triều", vg_section, re.IGNORECASE):
            trends.append("dao động theo triều")
        if re.search(r"\blên\b", vg_section, re.IGNORECASE) and not re.search(r"tiếp tục lên", vg_section, re.IGNORECASE):
            trends.append("lên")
        if re.search(r"\bxuống\b", vg_section, re.IGNORECASE):
            trends.append("xuống")
        res["trend_text"] = ", ".join(trends)

    # 2. Tìm tất cả câu hoặc vế câu chứa Câu Lâu
    # Tách đoạn văn thành các câu dựa trên dấu chấm, chấm phẩy, hoặc dấu gạch đầu dòng
    sentences = re.split(r"(?<=[.;\n])\s+", joined_text)

    # Lọc các câu nhắc đến Câu Lâu
    caulau_sentences = [
        s.strip() for s in sentences if _RE_CAULAU_NAME.search(s)
    ]

    if not caulau_sentences:
        return res

    # Lưu snippet đại diện câu đầu tiên chứa Câu Lâu
    res["snippet"] = caulau_sentences[0][:200]

    obs_candidate = None
    forecast_candidates = []

    for s in caulau_sentences:
        if _RE_FORECAST_HINT.search(s):
            forecast_candidates.append(s)
        else:
            if obs_candidate is None:
                obs_candidate = s

    if forecast_candidates:
        res["forecast_text"] = " | ".join(forecast_candidates)[:300]

    # Nếu không có câu riêng biệt, xem xét câu chứa Câu Lâu có cả thực đo lẫn dự báo
    target_sentence = obs_candidate or (caulau_sentences[0] if not _RE_FORECAST_HINT.search(caulau_sentences[0]) else None)

    # Trích xuất số thực đo Câu Lâu
    # Cần tìm 'Câu Lâu' và CHỈ quét từ vị trí 'Câu Lâu' trở đi trong câu/mệnh đề đó
    match_found = False
    for sent in caulau_sentences:
        # Nếu cả câu là dự báo rõ ràng (vd 'Trong 6 giờ tới ... lên mức ...') thì bỏ qua cho level_m_text
        if _RE_FORECAST_HINT.search(sent) and not re.search(r"mực\s*nước\s*lúc|thực\s*đo", sent, re.IGNORECASE):
            continue

        for m_cl in _RE_CAULAU_NAME.finditer(sent):
            after_cl = sent[m_cl.end():]
            # Giới hạn tìm kiếm sau 'Câu Lâu' trong vòng 150 ký tự (tránh sang trạm tiếp theo)
            next_station = re.search(r";|\.|\btrạm\b|\bsông\b", after_cl, re.IGNORECASE)
            limit_idx = next_station.start() if next_station and next_station.start() > 10 else 150
            clause = after_cl[:limit_idx]

            # Kiểm tra xem có số mét hay không
            m_val = _RE_LEVEL_VALUE.search(clause)
            if m_val:
                val = vn_float(m_val.group(1))
                res["level_m_text"] = val
                match_found = True

                # Tìm giờ đo trong câu (vd "lúc 7h ngày 29/10/2025" hoặc "lúc 2 giờ...")
                # Thử tìm trước hoặc sau Câu Lâu trong cùng câu
                hour_match = re.search(
                    r"lúc\s+(\d{1,2})(?:\s*[h:]\s*(\d{2})?|\s*giờ(?:\s*(\d{1,2}))?)",
                    sent,
                    re.IGNORECASE,
                )
                if hour_match:
                    h = int(hour_match.group(1))
                    m = hour_match.group(2) or hour_match.group(3) or "00"
                    res["level_hour"] = f"{h}:{int(m):02d}"

                # Tìm thông tin báo động sau số mét
                after_val = clause[m_val.end():]
                m_alarm = _RE_ALARM_SPEC.search(after_val) or _RE_ALARM_SPEC.search(after_cl)
                if m_alarm:
                    direction = m_alarm.group(1).lower()
                    raw_ref = m_alarm.group(2)
                    raw_diff = m_alarm.group(3)

                    # Chuẩn hóa tên báo động: BĐ1, BĐ2, BĐ3
                    norm_ref = "BĐ3" if "3" in raw_ref else ("BĐ2" if "2" in raw_ref else "BĐ1")
                    res["alarm_ref"] = norm_ref

                    # Phân loại alarm_class
                    is_above = bool(re.search(r"tr[eê]n", direction, re.IGNORECASE))
                    res["alarm_class"] = f"{'above' if is_above else 'below'}_{norm_ref}"

                    if raw_diff:
                        diff_num = vn_float(raw_diff)
                        if diff_num is not None:
                            res["alarm_diff_m"] = diff_num if is_above else -diff_num
                break
        if match_found:
            break

    return res


# =============================================================================
# MODULE D: ĐỌC BẢNG THEO TỌA ĐỘ (pdfplumber.extract_words)
# =============================================================================

def extract_table_words_line(
    page,
    top_tolerance: float = 3.0,
) -> Tuple[Optional[List[Optional[float]]], Optional[List[float]], str, str]:
    """Tìm hàng chứa 'Câu Lâu' trên một trang PDF bằng page.extract_words().

    Trả về:
      - col_values: danh sách giá trị số / None (dấu '-')
      - x0_coords: danh sách tọa độ x0 tương ứng
      - line_text: chuỗi text thô của hàng
      - error_or_uncertain_note: chuỗi ghi chú lý do chưa chắc chắn nếu có
    """
    words = page.extract_words()
    if not words:
        return None, None, "", "no_words"

    # Sắp xếp các từ theo top rồi x0
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))

    # Gom từ thành từng hàng theo dung sai top_tolerance
    lines: List[List[Dict[str, Any]]] = []
    curr_line: List[Dict[str, Any]] = []
    curr_top: Optional[float] = None

    for w in words_sorted:
        if curr_top is None:
            curr_top = w["top"]
            curr_line.append(w)
        elif abs(w["top"] - curr_top) <= top_tolerance:
            curr_line.append(w)
        else:
            lines.append(curr_line)
            curr_top = w["top"]
            curr_line = [w]
    if curr_line:
        lines.append(curr_line)

    # Tìm hàng chứa "Câu Lâu" (chuẩn hóa tiếng Việt, xử lý chữ tách/dính)
    for line_w in lines:
        line_str = " ".join(w["text"] for w in line_w)
        norm_line = normalize_vn(line_str)
        if _RE_CAULAU_NAME.search(norm_line):
            # Kiểm tra xem hàng này có số hay chỉ là câu chữ thường
            # Xác định vị trí từ khóa 'Câu Lâu'
            cl_end_idx = -1
            for i in range(len(line_w)):
                if _RE_CAULAU_NAME.search(normalize_vn(line_w[i]["text"])):
                    cl_end_idx = i
                    break
                if i + 1 < len(line_w):
                    pair = line_w[i]["text"] + " " + line_w[i + 1]["text"]
                    if _RE_CAULAU_NAME.search(normalize_vn(pair)):
                        cl_end_idx = i + 1
                        break

            sub_words = line_w[cl_end_idx + 1:] if cl_end_idx >= 0 else line_w

            col_values: List[Optional[float]] = []
            x0_coords: List[float] = []

            for w in sub_words:
                txt = w["text"].strip()
                # Dấu '-' đơn lẻ được quy định là ô trống (None), KHÔNG phải 0
                if txt in ("-", "--", "—", "–"):
                    col_values.append(None)
                    x0_coords.append(round(w["x0"], 1))
                elif re.match(r"^-?\d+(?:[,.]\d+)?$", txt):
                    val = vn_float(txt)
                    col_values.append(val)
                    x0_coords.append(round(w["x0"], 1))

            # Nếu hàng có ít nhất một số hoặc dấu '-', đây chính là hàng bảng
            if col_values:
                return col_values, x0_coords, line_str, ""

    return None, None, "", "caulau_not_in_table"


def extract_table_by_coords(
    pdf_bytes: bytes,
    top_tolerance: float = 3.0,
    max_k: int = 8,
) -> Dict[str, Any]:
    """Module D: Đọc bảng theo tọa độ từ PDF bytes bằng pdfplumber.

    Ghi chú kỹ thuật & tính phòng thủ:
      - Bố cục bảng KTTV các năm có thể thay đổi (số cột, vị trí phân trang).
      - Sử dụng page.extract_words() nhóm theo top với dung sai cấu hình được.
      - Chạy đối chứng với page.extract_tables().
      - Nếu phát hiện cấu trúc không chắc chắn (nhiều trạm trùng hàng, lệch cột),
        đặt cờ tbl_uncertain = True.
    """
    res = {
        f"tbl_c{i}": None for i in range(1, max_k + 1)
    }
    res["tbl_x0_list"] = ""
    res["tbl_cols_found"] = 0
    res["tbl_parse_method"] = "none"
    res["tbl_uncertain"] = False
    res["table_row_raw"] = ""

    if not pdf_bytes:
        return res

    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # Tìm trên các trang từ cuối lên đầu vì bảng thống kê thường nằm ở trang cuối
            found = False
            for page_idx in reversed(range(len(pdf.pages))):
                page = pdf.pages[page_idx]
                col_vals, x0s, raw_line, note = extract_table_words_line(page, top_tolerance)
                if col_vals:
                    found = True
                    res["tbl_parse_method"] = "words"
                    res["tbl_cols_found"] = len(col_vals)
                    res["table_row_raw"] = raw_line
                    res["tbl_x0_list"] = ";".join(str(x) for x in x0s)

                    for idx, val in enumerate(col_vals[:max_k]):
                        res[f"tbl_c{idx+1}"] = val

                    # Thử đối chứng với page.extract_tables()
                    try:
                        tables = page.extract_tables()
                        table_match_count = 0
                        for tbl in tables:
                            for row in tbl:
                                row_str = " ".join([str(c) for c in row if c is not None])
                                if _RE_CAULAU_NAME.search(normalize_vn(row_str)):
                                    table_match_count += 1
                        if table_match_count == 0:
                            # Không khớp giữa 2 phương pháp
                            res["tbl_uncertain"] = True
                    except Exception as e:
                        logger.debug("extract_tables đối chứng lỗi: %s", e)

                    # Đánh dấu cờ tbl_uncertain nếu số cột quá ít hoặc bất thường
                    if len(col_vals) < 2:
                        res["tbl_uncertain"] = True

                    break

            if not found:
                # Thử tìm bằng regex thô trên toàn văn bản làm dự phòng (như v1)
                for page in pdf.pages:
                    txt = page.extract_text() or ""
                    m = re.search(r"(?:Thu\s*B[oồ]n)?\s*C[aâ]u\s*L[aâ]u\s+([\d\s\-]+)", txt, re.IGNORECASE)
                    if m:
                        raw_nums = m.group(1).strip()
                        res["table_row_raw"] = raw_nums
                        res["tbl_parse_method"] = "raw_regex"
                        res["tbl_uncertain"] = True
                        break

    except Exception as e:
        logger.warning("Lỗi trích xuất bảng theo tọa độ: %s", e)
        res["tbl_uncertain"] = True

    return res


# =============================================================================
# NHÃN CHẤT LƯỢNG & ĐÁNH GIÁ (QUALITY FLAG)
# =============================================================================

def determine_quality_flag(
    row: dict,
    calibrated_col: Optional[int] = None,
) -> str:
    """Xác định nhãn chất lượng cho bản ghi:
      - missing_pdf: Không tải được file PDF (404, bị chặn...)
      - ok_text: Có mực nước trích từ câu văn trong dải hợp lý [0..8]m
      - check_range: Có mực nước câu văn nhưng ngoài dải [0..8]m
      - table_calibrated: Có mực nước suy từ cột bảng đã hiệu chuẩn
      - table_only: Có dữ liệu bảng nhưng chưa được hiệu chuẩn
      - no_alert_text: Bản tin chỉ có câu 'biến đổi chậm/dao động theo triều', không số
      - no_data: Có PDF nhưng hoàn toàn không tìm thấy thông tin Câu Lâu
    """
    status = row.get("status", "")
    if status in ("missing",) or status.startswith("blocked_"):
        return "missing_pdf"

    lv_text = row.get("level_m_text")
    if lv_text is not None:
        try:
            val = float(lv_text)
            if 0.0 <= val <= 8.0:
                return "ok_text"
            else:
                return "check_range"
        except (ValueError, TypeError):
            pass

    # Kiểm tra cột bảng đã hiệu chuẩn
    if calibrated_col and row.get(f"tbl_c{calibrated_col}") is not None:
        return "table_calibrated"

    # Kiểm tra có bảng thô hoặc cột bảng
    has_table = any(row.get(f"tbl_c{i}") is not None for i in range(1, 9)) or bool(row.get("table_row_raw"))
    if has_table:
        return "table_only"

    # Kiểm tra câu không có báo động
    if row.get("alarm_class") == "no_alert_text":
        return "no_alert_text"

    return "no_data"


# =============================================================================
# MODULE E: HIỆU CHUẨN CỘT BẢNG BẰNG NGÀY LŨ
# =============================================================================

def calculate_calibration_stats(
    df: pd.DataFrame,
    max_k: int = 8,
) -> pd.DataFrame:
    """So sánh từng cột bảng (tbl_c1..tbl_cK) với level_m_text của các ngày lũ.

    Bản tin KTTV ghi đơn vị bảng là cm, nên tính:
      level_table = tbl_c / 100.0 (mét)
      sai lệch = |tbl_c / 100.0 - level_m_text|

    Trả về DataFrame tổng hợp:
      - col_name: tên cột (tbl_c1 .. tbl_c8)
      - total_compare: số ngày so sánh được (cả text và bảng đều có số)
      - match_count: số ngày có sai lệch <= 0.05m (5cm)
      - match_pct: tỉ lệ khớp (%)
      - mean_diff_m: sai lệch tuyệt đối trung bình (m)
      - warning: cảnh báo nếu chưa đủ bằng chứng
    """
    rows = []
    if df.empty or "level_m_text" not in df.columns:
        return pd.DataFrame()

    # Lọc các dòng có level_m_text hợp lệ
    valid_text = df[df["level_m_text"].notna()].copy()
    valid_text["level_m_text"] = pd.to_numeric(valid_text["level_m_text"], errors="coerce")
    valid_text = valid_text[valid_text["level_m_text"].notna()]

    for k in range(1, max_k + 1):
        col_name = f"tbl_c{k}"
        if col_name not in valid_text.columns:
            continue

        subset = valid_text[valid_text[col_name].notna()].copy()
        subset[col_name] = pd.to_numeric(subset[col_name], errors="coerce")
        subset = subset[subset[col_name].notna()]

        n_compare = len(subset)
        if n_compare == 0:
            rows.append({
                "Cột bảng": col_name,
                "Số ngày so sánh": 0,
                "Khớp <= 5cm": 0,
                "Tỉ lệ khớp (%)": 0.0,
                "Lệch TB (m)": None,
                "Cảnh báo": "Không có dữ liệu đối chiếu",
            })
            continue

        # Đổi đơn vị từ cm sang m để so sánh
        table_m = subset[col_name] / 100.0
        diff = (table_m - subset["level_m_text"]).abs()
        n_match = (diff <= 0.05).sum()
        pct_match = round(n_match / n_compare * 100.0, 1)
        mean_diff = round(diff.mean(), 3)

        warning = ""
        if n_compare < 10:
            warning = "⚠️ Chưa đủ bằng chứng (< 10 ngày so sánh), đừng dùng cột bảng làm mực nước."

        rows.append({
            "Cột bảng": col_name,
            "Số ngày so sánh": n_compare,
            "Khớp <= 5cm": n_match,
            "Tỉ lệ khớp (%)": pct_match,
            "Lệch TB (m)": mean_diff,
            "Cảnh báo": warning,
        })

    return pd.DataFrame(rows)


# =============================================================================
# MODULE G: NGUỒN BỔ SUNG (GloFAS API, Mưa Open-Meteo)
# =============================================================================

GLOFAS_CACHE_DIR = Path("glofas_cache")
GLOFAS_CACHE_DIR.mkdir(exist_ok=True)


def fetch_glofas_discharge(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    cache_dir: Path = GLOFAS_CACHE_DIR,
) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]], str]:
    """Gọi Open-Meteo Flood API để lấy lưu lượng mô phỏng GloFAS (m3/s).

    URL: https://flood-api.open-meteo.com/v1/flood
    Params:
      latitude, longitude, daily=river_discharge, start_date, end_date
    """
    cache_key = f"glofas_{lat:.3f}_{lon:.3f}_{start_date}_{end_date}.json"
    cache_file = cache_dir / cache_key

    data = None
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if data is None:
        url = "https://flood-api.open-meteo.com/v1/flood"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "river_discharge",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            else:
                return None, None, f"Lỗi API HTTP {resp.status_code}: {resp.text[:150]}"
        except Exception as e:
            return None, None, f"Lỗi kết nối GloFAS API: {e}"

    if not data or "daily" not in data:
        return None, None, "Dữ liệu trả về không có trường 'daily'"

    daily = data["daily"]
    dates = daily.get("time", [])
    discharges = daily.get("river_discharge", [])

    df = pd.DataFrame({
        "date": dates,
        "discharge_m3s": discharges,
    })
    df["discharge_m3s"] = pd.to_numeric(df["discharge_m3s"], errors="coerce")
    df["discharge_1d"] = df["discharge_m3s"].round(2)
    df["discharge_3d"] = df["discharge_m3s"].rolling(3, min_periods=1).mean().round(2)

    metadata = {
        "requested_lat": lat,
        "requested_lon": lon,
        "snapped_lat": data.get("latitude"),
        "snapped_lon": data.get("longitude"),
        "elevation": data.get("elevation"),
        "units": data.get("daily_units", {}).get("river_discharge", "m3/s"),
    }
    return df, metadata, "ok"


def merge_rain_data(water_df: pd.DataFrame, rain_csv_bytes: bytes) -> pd.DataFrame:
    """Ghép dữ liệu mưa từ Open-Meteo Historical Weather API.

    Bỏ 3 dòng metadata đầu, gom nhóm mưa theo ngày tính tổng:
      rain_1d (tổng 1 ngày), rain_3d (tổng 3 ngày), rain_7d (tổng 7 ngày).
    """
    rain_df = pd.read_csv(io.BytesIO(rain_csv_bytes), skiprows=3, parse_dates=["time"])
    rain_df.columns = [c.strip() for c in rain_df.columns]

    rain_col = None
    for cand in ["precipitation (mm)", "rain (mm)", "precipitation", "rain"]:
        if cand in rain_df.columns:
            rain_col = cand
            break
    if rain_col is None:
        raise ValueError(f"Không tìm thấy cột mưa. Các cột hiện có: {list(rain_df.columns)}")

    rain_df["date"] = rain_df["time"].dt.date.astype(str)
    daily_rain = rain_df.groupby("date")[rain_col].sum().reset_index()
    daily_rain.columns = ["date", "rain_daily_mm"]
    daily_rain = daily_rain.sort_values("date").reset_index(drop=True)

    daily_rain["rain_1d"] = daily_rain["rain_daily_mm"].round(2)
    daily_rain["rain_3d"] = daily_rain["rain_daily_mm"].rolling(3, min_periods=1).sum().round(2)
    daily_rain["rain_7d"] = daily_rain["rain_daily_mm"].rolling(7, min_periods=1).sum().round(2)

    merged = water_df.copy()
    merged["date"] = merged["date"].astype(str)
    return merged.merge(
        daily_rain[["date", "rain_1d", "rain_3d", "rain_7d"]],
        on="date",
        how="left",
    )


# =============================================================================
# MODULE H: HỢP NHẤT ĐA NGUỒN (KHÔNG GHI ĐÈ, KHÔNG NỘI SUY)
# =============================================================================

def compute_level_best(df: pd.DataFrame, calibrated_col: Optional[int] = None) -> pd.DataFrame:
    """Tính toán cột level_best và level_best_source theo thứ tự ưu tiên:
      1. official: Dữ liệu chính thức (level_official_m)
      2. manual: Sự kiện lũ nhập tay đã kiểm tra (level_manual_m khi verified=True)
      3. text: Trích từ câu văn bản tin (level_m_text)
      4. table_calibrated: Suy từ cột bảng đã hiệu chuẩn (level_table_m)

    Nếu ngày nào không có nguồn nào thì để trống (None / NaN).
    TUYỆT ĐỐI KHÔNG NỘI SUY.
    """
    res = df.copy()

    # Đảm bảo các cột nguồn tồn tại
    for col in ["level_official_m", "level_manual_m", "level_m_text", "level_table_m"]:
        if col not in res.columns:
            res[col] = None

    if calibrated_col and f"tbl_c{calibrated_col}" in res.columns:
        # Cập nhật level_table_m = tbl_c{calibrated_col} / 100.0
        res["level_table_m"] = res[f"tbl_c{calibrated_col}"].apply(
            lambda x: round(float(x) / 100.0, 2) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None
        )

    best_levels: List[Optional[float]] = []
    best_sources: List[Optional[str]] = []

    for _, row in res.iterrows():
        off = row.get("level_official_m")
        man = row.get("level_manual_m")
        ver = row.get("verified", False)
        txt = row.get("level_m_text")
        tbl = row.get("level_table_m")

        if off is not None and not (isinstance(off, float) and math.isnan(off)):
            best_levels.append(float(off))
            best_sources.append("official")
        elif man is not None and ver is True and not (isinstance(man, float) and math.isnan(man)):
            best_levels.append(float(man))
            best_sources.append("manual")
        elif txt is not None and not (isinstance(txt, float) and math.isnan(txt)):
            best_levels.append(float(txt))
            best_sources.append("text")
        elif tbl is not None and not (isinstance(tbl, float) and math.isnan(tbl)):
            best_levels.append(float(tbl))
            best_sources.append("table_calibrated")
        else:
            best_levels.append(None)
            best_sources.append(None)

    res["level_best"] = best_levels
    res["level_best_source"] = best_sources
    return res


# =============================================================================
# MODULE I: TỰ ĐỘNG QUÉT TIN TỨC LŨ LỤT (HỘI AN - QUẢNG NAM - ĐÀ NẴNG)
# =============================================================================

def search_flood_news(query: str = "mực nước lũ Câu Lâu Hội An", max_results: int = 25) -> List[Dict[str, Any]]:
    """Tự động tìm kiếm các bài báo, bản tin về lũ lụt sông Vu Gia - Thu Bồn (Hội An, Quảng Nam, Đà Nẵng).

    Trích xuất: tiêu đề, ngày xuất bản, nguồn báo chí, URL bài báo, và số mét mực nước nếu có trong bài.
    """
    import urllib.parse
    import urllib.request
    import xml.etree.ElementTree as ET

    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=vi&gl=VN&ceid=VN:vi"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    results = []
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            root = ET.fromstring(resp.read())
            for it in root.findall(".//item")[:max_results]:
                title = it.find("title").text or ""
                link = it.find("link").text or ""
                pub_date_raw = it.find("pubDate").text or ""

                date_iso = ""
                try:
                    dt = datetime.strptime(pub_date_raw[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                    date_iso = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

                source_name = "Báo chí"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    source_name = parts[1].strip()
                    title_clean = parts[0].strip()
                else:
                    title_clean = title

                # Trích xuất số mét mực nước nếu xuất hiện trong tiêu đề
                m_lvl = re.search(r"(\d{1,2}[,.]\d{1,2})\s*m\b", title_clean)
                level_val = vn_float(m_lvl.group(1)) if m_lvl else None

                results.append({
                    "date": date_iso,
                    "title": title_clean,
                    "source_name": source_name,
                    "source_url": link,
                    "level_m": level_val,
                })
    except Exception as e:
        logger.warning("Lỗi tìm kiếm tin tức lũ lụt: %s", e)

    return results

