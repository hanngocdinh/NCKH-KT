# -*- coding: utf-8 -*-
"""
app.py – Thu thập & Hợp nhất Mực nước trạm Câu Lâu (Sông Thu Bồn) – Phiên bản 2
=============================================================================
Đề tài: AI + IoT cảnh báo ngập tại Hội An (học sinh lớp 11)
Nguồn dữ liệu:
  - Bản tin Dự báo, Cảnh báo Thủy văn Thời hạn ngắn – KTTV Quốc gia (kttv.gov.vn)
  - Mô phỏng lưu lượng GloFAS qua Open-Meteo Flood API (m3/s)
  - Sự kiện lũ nhập tay có URL đối chiếu & Dữ liệu chính thức từ Đài KTTV
  - Dữ liệu lượng mưa lịch sử Open-Meteo API

CẢNH BÁO QUAN TRỌNG:
  Dữ liệu thu thập từ các nguồn công khai, chỉ phục vụ nghiên cứu học tập.
  TUYỆT ĐỐI KHÔNG BỊA SỐ, KHÔNG NỘI SUY, GIỮ NGUYÊN TÍNH TRUNG THỰC CỦA DỮ LIỆU.
"""

import io
import json
import logging
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Thiết lập encoding utf-8 cho stdout trên Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import streamlit as st

# Import các thuật toán từ module parsers
from parsers import (
    BD1_M,
    BD2_M,
    BD3_M,
    HIST_M,
    calculate_calibration_stats,
    compute_level_best,
    determine_quality_flag,
    extract_table_by_coords,
    fetch_glofas_discharge,
    merge_rain_data,
    normalize_vn,
    parse_prose,
    search_flood_news,
    vn_float,
)

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Thư mục và tệp lưu trữ
PDF_CACHE_DIR = Path("pdf_cache")
PDF_CACHE_DIR.mkdir(exist_ok=True)

GLOFAS_CACHE_DIR = Path("glofas_cache")
GLOFAS_CACHE_DIR.mkdir(exist_ok=True)

CONFIG_FILE = Path("config.json")
KNOWN_DAYS_FILE = Path("known_days.csv")
MISSING_CACHE_FILE = Path("missing_cache.csv")
EVENTS_MANUAL_FILE = Path("events_manual.csv")
OFFICIAL_DATA_FILE = Path("official_data.csv")


# =============================================================================
# CÁC HÀM QUẢN LÝ CẤU HÌNH & TỆP LƯU TRỮ
# =============================================================================

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Không đọc được config.json: %s", e)
    return {"calibrated_col": None}


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.error("Lỗi ghi config.json: %s", e)


def load_known_days() -> pd.DataFrame:
    if KNOWN_DAYS_FILE.exists():
        try:
            df = pd.read_csv(KNOWN_DAYS_FILE, dtype=str)
            return df
        except Exception:
            pass
    return pd.DataFrame([
        {"date": "2025-10-29", "level_m": "5.20", "source_url": ""},
        {"date": "2025-10-30", "level_m": "5.62", "source_url": ""},
    ])


def save_known_days(df: pd.DataFrame) -> None:
    df.to_csv(KNOWN_DAYS_FILE, index=False, encoding="utf-8-sig")


def load_missing_cache() -> pd.DataFrame:
    if MISSING_CACHE_FILE.exists():
        try:
            return pd.read_csv(MISSING_CACHE_FILE, dtype=str)
        except Exception:
            pass
    return pd.DataFrame(columns=["date", "url", "status", "checked_at"])


def append_missing_cache(date_str: str, url: str, status: str) -> None:
    df = load_missing_cache()
    new_row = pd.DataFrame([{
        "date": date_str,
        "url": url,
        "status": status,
        "checked_at": datetime.now().isoformat(),
    }])
    df = pd.concat([df, new_row], ignore_index=True).drop_duplicates(subset=["url"])
    df.to_csv(MISSING_CACHE_FILE, index=False, encoding="utf-8-sig")


def load_manual_events() -> pd.DataFrame:
    if EVENTS_MANUAL_FILE.exists():
        try:
            return pd.read_csv(EVENTS_MANUAL_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=[
        "date", "time", "level_m", "alarm_ref", "alarm_diff_m",
        "source_name", "source_url", "entered_by", "verified"
    ])


def save_manual_events(df: pd.DataFrame) -> None:
    df.to_csv(EVENTS_MANUAL_FILE, index=False, encoding="utf-8-sig")


# =============================================================================
# THU THẬP & TẢI FILE PDF (QUY TẮC AN TOÀN, LỊCH SỰ)
# =============================================================================

def candidate_urls(d: date, hour_str: str = "1030") -> List[str]:
    """Tạo danh sách URL ứng viên cho ngày d."""
    y = d.year
    m_pad = f"{d.month:02d}"
    dd_pad = f"{d.day:02d}"
    m_no = str(d.month)
    dd_no = str(d.day)
    fname = f"dbqg_tvhn_{y}{m_pad}{dd_pad}_{hour_str}.pdf"
    base = "https://kttv.gov.vn/upload/thuyvan1"

    urls = []
    seen = set()
    for m_part in ([m_pad, m_no] if m_pad != m_no else [m_pad]):
        for d_part in ([dd_pad, dd_no] if dd_pad != dd_no else [dd_pad]):
            url = f"{base}/{y}/{m_part}/{d_part}/{fname}"
            if url not in seen:
                urls.append(url)
                seen.add(url)
    return urls


def download_pdf(
    url: str,
    email: str = "student@school.edu.vn",
    timeout: int = 30,
) -> Tuple[Optional[bytes], str]:
    """Tải một file PDF từ URL với User-Agent và kiểm tra b'%PDF'."""
    headers = {
        "User-Agent": f"HoiAnFloodStudy/2.0 (student research; contact: {email})"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            content = resp.content
            if content[:4] == b"%PDF":
                return content, "ok"
            return None, "not_pdf"
        elif resp.status_code in (403, 429):
            return None, f"blocked_{resp.status_code}"
        elif resp.status_code == 404:
            return None, "404"
        return None, f"http_{resp.status_code}"
    except requests.RequestException as e:
        return None, f"error_{type(e).__name__}"


def cached_pdf_path(d: date, hour_str: str) -> Path:
    fname = f"{d.year}{d.month:02d}{d.day:02d}_{hour_str}.pdf"
    return PDF_CACHE_DIR / fname


def load_or_download_pdf(
    d: date,
    hour_str: str,
    email: str,
    delay: float,
) -> Tuple[Optional[bytes], str, str]:
    """Đọc từ cache nếu có; nếu không thì tải từ mạng."""
    c_path = cached_pdf_path(d, hour_str)
    if c_path.exists():
        return c_path.read_bytes(), str(c_path), "cached"

    urls = candidate_urls(d, hour_str)
    for url in urls:
        content, status = download_pdf(url, email)
        if content:
            c_path.write_bytes(content)
            time.sleep(delay)
            return content, url, "downloaded"
        elif status.startswith("blocked_"):
            return None, url, status

    time.sleep(delay)
    return None, urls[0], "missing"


# =============================================================================
# TRÍCH XUẤT VĂN BẢN VÀ BẢNG TOÀN DIỆN TỪ PDF
# =============================================================================

def parse_full_pdf(
    pdf_bytes: bytes,
    d: date,
    url: str = "",
    status: str = "ok",
    calibrated_col: Optional[int] = None,
) -> dict:
    """Phân tích một file PDF đầy đủ cả văn bản (Module F) và bảng (Module D)."""
    row: Dict[str, Any] = {
        "date": d.isoformat(),
        "url": url,
        "status": status,
        "level_m_text": None,
        "level_hour": None,
        "alarm_ref": None,
        "alarm_diff_m": None,
        "alarm_class": "no_section",
        "trend_text": "",
        "forecast_text": "",
        "snippet": "",
        "table_row_raw": "",
        "tbl_x0_list": "",
        "tbl_cols_found": 0,
        "tbl_parse_method": "none",
        "tbl_uncertain": False,
        "flag": "",
        "verified": False,
        "level_table_m": None,
        "level_manual_m": None,
        "level_official_m": None,
        "level_best": None,
        "level_best_source": None,
    }
    for k in range(1, 9):
        row[f"tbl_c{k}"] = None

    if not pdf_bytes:
        row["flag"] = determine_quality_flag(row, calibrated_col)
        return row

    # 1. Trích xuất text cho Module F
    full_text = ""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text_parts = [p.extract_text() or "" for p in pdf.pages]
            full_text = "\n".join(text_parts)
    except Exception as e:
        logger.debug("pdfplumber extract_text lỗi: %s", e)

    if not full_text.strip():
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            full_text = "\n".join([p.extract_text() or "" for p in reader.pages])
        except Exception:
            pass

    # Phân tích văn bản xuôi
    prose_res = parse_prose(full_text, d)
    row.update(prose_res)

    # 2. Phân tích bảng theo tọa độ (Module D)
    tbl_res = extract_table_by_coords(pdf_bytes)
    row.update(tbl_res)

    # 3. Tính mực nước bảng nếu đã hiệu chuẩn
    if calibrated_col and row.get(f"tbl_c{calibrated_col}") is not None:
        try:
            row["level_table_m"] = round(float(row[f"tbl_c{calibrated_col}"]) / 100.0, 2)
        except (ValueError, TypeError):
            row["level_table_m"] = None

    # 4. Xác định cờ chất lượng
    row["flag"] = determine_quality_flag(row, calibrated_col)

    return row


# =============================================================================
# GIAO DIỆN STREAMLIT PHIÊN BẢN 2
# =============================================================================

def run_app() -> None:
    st.set_page_config(
        page_title="Mực nước Câu Lâu – Hội An (V2)",
        page_icon="🌊",
        layout="wide",
    )

    st.markdown("""
    <style>
    .main .block-container { padding-top: 1.5rem; }
    .stAlert { border-radius: 8px; }
    .metric-card { background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #e2e8f0; }
    </style>
    """, unsafe_allow_html=True)

    st.title("🌊 Thu thập & Hợp nhất Mực nước Câu Lâu – Sông Thu Bồn")
    st.caption("Đề tài: AI + IoT cảnh báo ngập tại Hội An | Phiên bản 2.0 (Nâng cấp toàn diện)")

    st.info(
        "ℹ️ **Nguyên tắc khoa học:** Không bịa dữ liệu, không nội suy ngày thiếu. "
        "Mọi cột bảng từ PDF chỉ được dùng sau khi hiệu chuẩn đối chứng. "
        "Lưu lượng mô phỏng GloFAS được lưu riêng biệt với mực nước quan trắc.",
        icon="🛡️",
    )

    # Đọc cấu hình
    config = load_config()
    calibrated_col = config.get("calibrated_col")

    # Khởi tạo session state
    if "results" not in st.session_state:
        st.session_state.results = []
    if "stop_flag" not in st.session_state:
        st.session_state.stop_flag = False
    if "running" not in st.session_state:
        st.session_state.running = False
    if "calibrated_col" not in st.session_state:
        st.session_state.calibrated_col = calibrated_col
    if "glofas_data" not in st.session_state:
        st.session_state.glofas_data = None
    if "glofas_meta" not in st.session_state:
        st.session_state.glofas_meta = None

    # ══════════════════════════════════════════════════════════════════════
    # SIDEBAR – CẤU HÌNH & MODULE A (PHÂN TÍCH LẠI TỪ CACHE)
    # ══════════════════════════════════════════════════════════════════════
    with st.sidebar:
        st.header("⚙️ Cấu hình chung")

        today = date.today()
        c_sd1, c_sd2 = st.columns(2)
        with c_sd1:
            start_date = st.date_input("Từ ngày", value=date(2025, 10, 1), min_value=date(2020, 1, 1), max_value=today)
        with c_sd2:
            end_date = st.date_input("Đến ngày", value=today, min_value=date(2020, 1, 1), max_value=today)

        hour_str = st.text_input("Giờ tên file (hhmm)", value="1030", help="Mặc định 1030 (10:30 trưa)").strip()
        delay = st.slider("Nghỉ giữa lần tải (giây)", min_value=0.5, max_value=10.0, value=1.0, step=0.5)
        email = st.text_input("Email liên hệ (User-Agent)", value="student@school.edu.vn").strip()

        st.divider()
        st.subheader("⚡ Module A: Phân tích lại từ Cache")
        cached_files = sorted(list(PDF_CACHE_DIR.glob("*.pdf")))
        st.metric("Số file PDF trong cache", len(cached_files))

        if cached_files:
            reparse_btn = st.button("🚀 Phân tích lại toàn bộ PDF cache", type="primary", use_container_width=True)
            if reparse_btn:
                st.session_state.results = []
                prog = st.progress(0, text="Bắt đầu phân tích...")
                status_txt = st.empty()

                parsed_list = []
                for idx, fpath in enumerate(cached_files):
                    pct = (idx + 1) / len(cached_files)
                    prog.progress(pct, text=f"Đang đọc: {fpath.name} ({idx+1}/{len(cached_files)})")

                    # Suy ngày từ tên file YYYYMMDD_hhmm.pdf
                    m_name = re.match(r"^(\d{4})(\d{2})(\d{2})", fpath.name)
                    if m_name:
                        y, m, d_val = int(m_name.group(1)), int(m_name.group(2)), int(m_name.group(3))
                        cur_date = date(y, m, d_val)
                    else:
                        cur_date = today

                    pdf_bytes = fpath.read_bytes()
                    res_row = parse_full_pdf(
                        pdf_bytes=pdf_bytes,
                        d=cur_date,
                        url=str(fpath),
                        status="cached",
                        calibrated_col=st.session_state.calibrated_col,
                    )
                    parsed_list.append(res_row)

                st.session_state.results = parsed_list
                prog.progress(1.0, text="✅ Hoàn thành phân tích toàn bộ cache!")
                st.success(f"Đã phân tích xong {len(parsed_list)} file từ cache không dùng mạng!")
                st.rerun()

        st.divider()
        st.subheader("📌 Hiệu chuẩn & Ngưỡng trạm")
        cur_cal = st.session_state.calibrated_col
        if cur_cal:
            st.success(f"Đang dùng cột bảng: **tbl_c{cur_cal}**")
        else:
            st.warning("Chưa chọn cột bảng hiệu chuẩn")

        st.markdown(
            f"""
            | Mốc cảnh báo | Mực nước (m) |
            |--------------|--------------|
            | BĐ1 (tham khảo) | {BD1_M:.2f} |
            | BĐ2 (bản tin) | {BD2_M:.2f} |
            | BĐ3 (bản tin) | {BD3_M:.2f} |
            | Lũ 1964 | {HIST_M:.2f} |
            """
        )

        if cached_files and st.button("🗑️ Xóa toàn bộ cache PDF"):
            for f in cached_files:
                f.unlink()
            st.success("Đã xóa sạch cache PDF!")
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # CÁC TAB CHÍNH V2
    # ══════════════════════════════════════════════════════════════════════
    tab_collect, tab_table, tab_diag, tab_calib, tab_chart, tab_extra = st.tabs([
        "📥 Thu thập & Thử lại",
        "📊 Bảng dữ liệu & Hợp nhất",
        "🩺 Chẩn đoán (V2)",
        "⚖️ Hiệu chuẩn bảng (V2)",
        "📈 Biểu đồ mực nước",
        "🌧️ Nguồn bổ sung (GloFAS/Nhập tay)",
    ])

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1: THU THẬP & THỬ LẠI (MODULE C & G3)
    # ══════════════════════════════════════════════════════════════════════
    with tab_collect:
        st.subheader("1. Quét mới theo khoảng thời gian")
        if start_date > end_date:
            st.error("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc!")
        else:
            total_days = (end_date - start_date).days + 1
            col_b1, col_b2, _ = st.columns([1, 1, 3])
            with col_b1:
                start_btn = st.button("▶️ Bắt đầu quét", type="primary", disabled=st.session_state.running)
            with col_b2:
                stop_btn = st.button("⏹️ Dừng", disabled=not st.session_state.running)

            if stop_btn:
                st.session_state.stop_flag = True

            if start_btn:
                st.session_state.stop_flag = False
                st.session_state.running = True

                existing_dates = {r["date"] for r in st.session_state.results}
                all_dates = [start_date + timedelta(days=i) for i in range(total_days)]
                todo_dates = [d for d in all_dates if d.isoformat() not in existing_dates]

                if not todo_dates:
                    st.success("Tất cả ngày trong khoảng này đã có trong bảng!")
                    st.session_state.running = False
                else:
                    pbar = st.progress(0, text="Chuẩn bị quét...")
                    stat_box = st.empty()
                    consec_blocked = 0

                    for idx, cur_d in enumerate(todo_dates):
                        if st.session_state.stop_flag:
                            st.warning("Đã dừng quét.")
                            break

                        pbar.progress((idx + 1) / len(todo_dates), text=f"Đang xử lý: {cur_d.isoformat()} ({idx+1}/{len(todo_dates)})")

                        pdf_bytes, pdf_url, dl_status = load_or_download_pdf(cur_d, hour_str, email, delay)

                        if dl_status.startswith("blocked_"):
                            consec_blocked += 1
                            if consec_blocked >= 3:
                                st.error("🚫 Bị chặn liên tiếp 3 lần (403/429). Dừng để tuân thủ chính sách.")
                                break
                        else:
                            consec_blocked = 0

                        row_res = parse_full_pdf(
                            pdf_bytes=pdf_bytes,
                            d=cur_d,
                            url=pdf_url,
                            status=dl_status,
                            calibrated_col=st.session_state.calibrated_col,
                        )
                        st.session_state.results.append(row_res)
                        stat_box.markdown(f"Đã quét: `{cur_d.isoformat()}` | Trạng thái: **{dl_status}** | Cờ: **{row_res['flag']}**")

                    pbar.progress(1.0, text="Hoàn tất!")
                    st.session_state.running = False
                    st.rerun()

        # ── MODULE C: THỬ LẠI NGÀY THIẾU PDF ─────────────────────────────
        st.divider()
        st.subheader("2. Module C: Thử lại các ngày thiếu PDF (missing_pdf)")

        results_df = pd.DataFrame(st.session_state.results) if st.session_state.results else pd.DataFrame()
        missing_days = []
        if not results_df.empty and "flag" in results_df.columns:
            missing_days = results_df[results_df["flag"] == "missing_pdf"]["date"].tolist()

        col_mc1, col_mc2, col_mc3 = st.columns([2, 1, 1])
        with col_mc1:
            alt_hours_input = st.text_input(
                "Các giờ thay thế thử thêm (ngăn cách bằng phẩy)",
                value="0830, 0900, 1100, 1430, 1630, 1700",
                help="Các bản tin trong ngày lũ có thể phát vào các khung giờ bất thường",
            )
        with col_mc2:
            max_urls_per_day = st.number_input("Số URL tối đa thử / ngày", min_value=1, max_value=10, value=4)
        with col_mc3:
            st.metric("Số ngày thiếu PDF", len(missing_days))

        missing_cache_df = load_missing_cache()
        st.caption(f"📁 Số URL 404 đã lưu trong `missing_cache.csv`: **{len(missing_cache_df)}** (sẽ tự động bỏ qua)")

        c_btn_retry, c_btn_clr = st.columns([2, 1])
        with c_btn_retry:
            retry_missing_btn = st.button("🔄 Bắt đầu thử lại ngày thiếu PDF", type="secondary")
        with c_btn_clr:
            if st.button("🧹 Xóa missing_cache.csv"):
                if MISSING_CACHE_FILE.exists():
                    MISSING_CACHE_FILE.unlink()
                st.success("Đã xóa missing_cache.csv!")
                st.rerun()

        if retry_missing_btn and missing_days:
            alt_hours = [h.strip() for h in alt_hours_input.split(",") if h.strip()]
            retry_pbar = st.progress(0, text="Bắt đầu thử lại...")
            cached_404_urls = set(missing_cache_df["url"].tolist())

            consec_blocked = 0
            found_count = 0

            for idx, d_str in enumerate(missing_days):
                retry_pbar.progress((idx + 1) / len(missing_days), text=f"Thử ngày: {d_str} ({idx+1}/{len(missing_days)})")
                cur_d = date.fromisoformat(d_str)

                # Sinh danh sách URL ứng viên theo các giờ thay thế
                cand_list = []
                for h in alt_hours:
                    cand_list.extend(candidate_urls(cur_d, h))

                # Lọc bỏ URL đã có trong missing_cache
                cand_list = [u for u in cand_list if u not in cached_404_urls][:max_urls_per_day]

                downloaded_content = None
                successful_url = ""

                for u in cand_list:
                    time.sleep(delay)
                    content, status = download_pdf(u, email)
                    if content:
                        downloaded_content = content
                        successful_url = u
                        # Lưu vào cache đĩa
                        m_hh = re.search(r"_(\d{4})\.pdf", u)
                        hh = m_hh.group(1) if m_hh else "unknown"
                        c_path = cached_pdf_path(cur_d, hh)
                        c_path.write_bytes(content)
                        found_count += 1
                        break
                    elif status == "404":
                        append_missing_cache(d_str, u, "404")
                        cached_404_urls.add(u)
                    elif status.startswith("blocked_"):
                        consec_blocked += 1
                        if consec_blocked >= 3:
                            st.error("Bị chặn 3 lần liên tiếp. Dừng thử lại.")
                            break

                if consec_blocked >= 3:
                    break

                if downloaded_content:
                    # Cập nhật kết quả vào results
                    new_parsed = parse_full_pdf(
                        pdf_bytes=downloaded_content,
                        d=cur_d,
                        url=successful_url,
                        status="downloaded_retry",
                        calibrated_col=st.session_state.calibrated_col,
                    )
                    for i, r in enumerate(st.session_state.results):
                        if r["date"] == d_str:
                            st.session_state.results[i] = new_parsed
                            break

            st.success(f"Hoàn thành! Đã tìm thấy thêm **{found_count}** ngày có bản tin.")
            st.rerun()

        # ── MODULE G3: BẢN TIN LƯU TRỮ Ở NGUỒN KHÁC ───────────────────────
        st.divider()
        st.subheader("3. Module G3: Tải từ nguồn lưu trữ khác (evn.com.vn, v.v.)")
        st.markdown(
            "Nhập danh sách URL PDF do nhóm tìm được. "
            "**Chỉ chấp nhận domain trong allowlist**: `kttv.gov.vn`, `evn.com.vn`."
        )
        archive_urls_txt = st.text_area("Danh sách URL (mỗi dòng 1 URL)", height=100)
        archive_date = st.date_input("Ngày tương ứng cho các URL trên (nếu không suy được từ tên file)", value=today)

        if st.button("📥 Tải bản tin nguồn ngoài"):
            raw_urls = [u.strip() for u in archive_urls_txt.splitlines() if u.strip()]
            allowlist = ["kttv.gov.vn", "evn.com.vn"]
            valid_urls = []
            for u in raw_urls:
                if any(domain in u.lower() for domain in allowlist):
                    valid_urls.append(u)
                else:
                    st.error(f"Từ chối URL không thuộc allowlist: {u}")

            count_ext = 0
            for u in valid_urls:
                time.sleep(delay)
                content, status = download_pdf(u, email)
                if content:
                    fname = os.path.basename(u) or f"archive_{archive_date.isoformat()}.pdf"
                    save_path = PDF_CACHE_DIR / fname
                    save_path.write_bytes(content)

                    # Trích xuất và đánh dấu cờ
                    row_parsed = parse_full_pdf(content, archive_date, url=u, status="evn_archive", calibrated_col=st.session_state.calibrated_col)
                    row_parsed["tbl_uncertain"] = True
                    st.session_state.results.append(row_parsed)
                    count_ext += 1
                else:
                    st.warning(f"Không tải được: {u} (trạng thái: {status})")

            if count_ext:
                st.success(f"Đã tải và phân tích xong {count_ext} bản tin ngoài!")
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2: BẢNG DỮ LIỆU & HỢP NHẤT (MODULE H)
    # ══════════════════════════════════════════════════════════════════════
    with tab_table:
        st.subheader("Bảng dữ liệu & Hợp nhất đa nguồn (Module H)")

        if not st.session_state.results:
            st.info("Chưa có dữ liệu. Hãy quét ở Tab 1 hoặc nhấn nút 'Phân tích lại từ Cache' ở sidebar.")
        else:
            # Khử trùng lặp theo ngày trong st.session_state.results (nếu có)
            seen_dates = {}
            for r in st.session_state.results:
                d = r.get("date")
                if not d:
                    continue
                if d not in seen_dates:
                    seen_dates[d] = r
                else:
                    prev = seen_dates[d]
                    if prev.get("level_m_text") is None and r.get("level_m_text") is not None:
                        seen_dates[d] = r
                    elif prev.get("tbl_cols_found", 0) == 0 and r.get("tbl_cols_found", 0) > 0:
                        seen_dates[d] = r
            st.session_state.results = list(seen_dates.values())

            base_df = pd.DataFrame(st.session_state.results)

            # Ghép với sự kiện lũ nhập tay (nếu có)
            manual_df = load_manual_events()
            if not manual_df.empty and "date" in manual_df.columns:
                man_lookup = {}
                for _, m_row in manual_df.iterrows():
                    d_key = str(m_row.get("date", "")).strip()
                    if d_key:
                        man_lookup[d_key] = {
                            "level_m": m_row.get("level_m"),
                            "verified": bool(m_row.get("verified", False)),
                        }
                for i, r in enumerate(st.session_state.results):
                    dk = str(r.get("date", ""))
                    if dk in man_lookup:
                        st.session_state.results[i]["level_manual_m"] = vn_float(str(man_lookup[dk].get("level_m", "")))
                        st.session_state.results[i]["verified"] = bool(man_lookup[dk].get("verified", False))

            # Ghép với dữ liệu chính thức (nếu có)
            if OFFICIAL_DATA_FILE.exists():
                try:
                    off_df = pd.read_csv(OFFICIAL_DATA_FILE)
                    if "date" in off_df.columns and "level_m" in off_df.columns:
                        off_map = dict(zip(off_df["date"].astype(str), off_df["level_m"].apply(vn_float)))
                        for i, r in enumerate(st.session_state.results):
                            dk = r["date"]
                            if dk in off_map:
                                st.session_state.results[i]["level_official_m"] = off_map[dk]
                except Exception as e:
                    logger.debug("Lỗi đọc official_data.csv: %s", e)

            # Tính toán level_best
            full_df = pd.DataFrame(st.session_state.results)
            full_df = compute_level_best(full_df, st.session_state.calibrated_col)

            # ── Thống kê nguồn bao phủ ─────────────────────────────────────
            tot_rows = len(full_df)
            has_best = full_df["level_best"].notna().sum()
            pct_best = round(has_best / tot_rows * 100.0, 1) if tot_rows else 0.0

            c_met1, c_met2, c_met3, c_met4 = st.columns(4)
            c_met1.metric("Tổng ngày theo dõi", tot_rows)
            c_met2.metric("Có mực nước (level_best)", f"{has_best} ({pct_best}%)")
            src_counts = full_df["level_best_source"].value_counts().to_dict()
            c_met3.metric("Nguồn Text / Bảng", f"Text: {src_counts.get('text', 0)} | Bảng: {src_counts.get('table_calibrated', 0)}")
            c_met4.metric("Nguồn Thủ công / Chính thức", f"Manual: {src_counts.get('manual', 0)} | Official: {src_counts.get('official', 0)}")

            # ── Bộ lọc ────────────────────────────────────────────────────
            all_flags = sorted(full_df["flag"].dropna().unique().tolist())
            col_flt1, col_flt2 = st.columns([2, 1])
            with col_flt1:
                sel_flags = st.multiselect("Lọc theo nhãn chất lượng (flag)", options=all_flags, default=all_flags)
            with col_flt2:
                only_has_number = st.checkbox("Chỉ hiện ngày có mực nước (level_best)", value=False)

            view_df = full_df[full_df["flag"].isin(sel_flags)].copy()
            if only_has_number:
                view_df = view_df[view_df["level_best"].notna()]

            st.caption(f"Đang hiển thị **{len(view_df)}** / {tot_rows} dòng")

            # Cấu hình bảng hiển thị
            col_order = [
                "date", "level_best", "level_best_source", "level_m_text", "level_table_m",
                "level_manual_m", "level_official_m", "alarm_class", "trend_text", "verified",
                "tbl_c1", "tbl_c2", "tbl_c3", "tbl_c4", "tbl_cols_found", "tbl_uncertain",
                "snippet", "table_row_raw", "forecast_text", "url"
            ]
            col_order = [c for c in col_order if c in view_df.columns]

            col_cfg = {
                "date": st.column_config.TextColumn("Ngày", disabled=True),
                "level_best": st.column_config.NumberColumn("Mực nước tốt nhất (m)", format="%.2f", disabled=True),
                "level_best_source": st.column_config.TextColumn("Nguồn chọn", disabled=True),
                "level_m_text": st.column_config.NumberColumn("Số từ Text (m)", format="%.2f"),
                "level_table_m": st.column_config.NumberColumn("Số từ Bảng (m)", format="%.2f", disabled=True),
                "alarm_class": st.column_config.TextColumn("Cấp BĐ", disabled=True),
                "trend_text": st.column_config.TextColumn("Xu thế", disabled=True),
                "verified": st.column_config.CheckboxColumn("Đã kiểm tra"),
                "tbl_cols_found": st.column_config.NumberColumn("Số cột bảng", disabled=True),
                "tbl_uncertain": st.column_config.CheckboxColumn("Bảng chưa chắc", disabled=True),
                "snippet": st.column_config.TextColumn("Đoạn văn gốc"),
                "table_row_raw": st.column_config.TextColumn("Hàng bảng thô"),
                "forecast_text": st.column_config.TextColumn("Đoạn dự báo"),
                "url": st.column_config.LinkColumn("Link PDF"),
            }

            edited_df = st.data_editor(
                view_df[col_order],
                column_config=col_cfg,
                use_container_width=True,
                hide_index=True,
                key="editor_full_v2",
            )

            # Cập nhật chỉnh sửa người dùng vào session_state
            if edited_df is not None:
                mod_map = {}
                for _, e_row in edited_df.iterrows():
                    d_key = str(e_row.get("date", "")).strip()
                    if d_key:
                        mod_map[d_key] = {
                            "level_m_text": e_row.get("level_m_text"),
                            "verified": bool(e_row.get("verified", False)),
                        }
                for i, r in enumerate(st.session_state.results):
                    dk = str(r.get("date", ""))
                    if dk in mod_map:
                        st.session_state.results[i]["level_m_text"] = mod_map[dk].get("level_m_text", r.get("level_m_text"))
                        st.session_state.results[i]["verified"] = mod_map[dk].get("verified", False)

            # ── XUẤT CSV (MODULE H) ───────────────────────────────────────
            st.divider()
            st.subheader("💾 Xuất dữ liệu đa định dạng (UTF-8-SIG)")

            c_exp1, c_exp2, c_exp3 = st.columns(3)
            with c_exp1:
                csv_full_bytes = full_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 CSV Đầy đủ mọi cột",
                    data=csv_full_bytes,
                    file_name=f"caulau_v2_full_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c_exp2:
                clean_cols = ["date", "level_best", "level_best_source", "verified", "alarm_class"]
                clean_cols = [c for c in clean_cols if c in full_df.columns]
                csv_clean_bytes = full_df[clean_cols].to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 CSV Sạch (để huấn luyện AI)",
                    data=csv_clean_bytes,
                    file_name=f"caulau_v2_clean_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with c_exp3:
                # File đã ghép (nếu có GloFAS hoặc Mưa)
                merged_export = full_df.copy()
                if st.session_state.glofas_data is not None:
                    merged_export = merged_export.merge(st.session_state.glofas_data, on="date", how="left")
                csv_merged_bytes = merged_export.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 CSV Đã ghép (Mực nước + Lưu lượng)",
                    data=csv_merged_bytes,
                    file_name=f"caulau_v2_merged_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # ══════════════════════════════════════════════════════════════════════
    # TAB 3: CHẨN ĐOÁN (MODULE B)
    # ══════════════════════════════════════════════════════════════════════
    with tab_diag:
        st.subheader("Chẩn đoán chất lượng & Phân bố dữ liệu (Module B)")

        if not st.session_state.results:
            st.info("Chưa có kết quả để chẩn đoán. Hãy chạy quét dữ liệu trước.")
        else:
            diag_df = pd.DataFrame(st.session_state.results).copy()
            diag_df["date_dt"] = pd.to_datetime(diag_df["date"])
            diag_df["year"] = diag_df["date_dt"].dt.year
            diag_df["year_month"] = diag_df["date_dt"].dt.to_period("M").astype(str)

            # Thống kê theo tháng
            monthly_flag = diag_df.groupby(["year_month", "flag"]).size().unstack(fill_value=0)
            st.markdown("#### 1. Phân bố cờ chất lượng theo tháng")
            st.dataframe(monthly_flag, use_container_width=True)

            # Biểu đồ cột phân bố cờ chất lượng
            try:
                import plotly.express as px
                fig_diag = px.bar(
                    diag_df,
                    x="year_month",
                    color="flag",
                    title="Số ngày theo từng nhãn chất lượng mỗi tháng",
                    labels={"year_month": "Tháng", "count": "Số ngày", "flag": "Nhãn"},
                    barmode="stack",
                )
                st.plotly_chart(fig_diag, use_container_width=True)
            except Exception:
                st.bar_chart(monthly_flag)

            st.caption(
                "💡 **Nhận xét chẩn đoán:** Nhìn vào biểu đồ trên để xác định dữ liệu thiếu rải rác "
                "hay thiếu liên tục theo từng mùa/năm. Thường mùa cạn bản tin kttv chỉ có bảng mà không có số trong văn bản."
            )

            # ── DANH SÁCH NGÀY KIỂM THỬ ĐÃ BIẾT ──────────────────────────
            st.divider()
            st.markdown("#### 2. Đối chiếu các ngày kiểm thử đã biết (known_days.csv)")
            known_df = load_known_days()

            compare_rows = []
            res_by_date = {r["date"]: r for r in st.session_state.results}

            for _, k_row in known_df.iterrows():
                k_date = str(k_row.get("date", "")).strip()
                k_level = vn_float(str(k_row.get("level_m", "")))
                k_url = str(k_row.get("source_url", ""))

                if k_date in res_by_date:
                    r = res_by_date[k_date]
                    parsed_lvl = r.get("level_m_text")
                    parsed_flag = r.get("flag")
                    snip = r.get("snippet", "")
                    raw_tbl = r.get("table_row_raw", "")

                    if parsed_lvl is not None and k_level is not None:
                        diff = abs(float(parsed_lvl) - k_level)
                        status_cmp = "✅ Khớp" if diff <= 0.05 else f"❌ Lệch ({diff:.2f}m)"
                    elif r.get("status") in ("missing", "missing_pdf"):
                        status_cmp = "⚠️ Không có PDF"
                    else:
                        status_cmp = "❓ Không tìm thấy số"

                    compare_rows.append({
                        "Ngày": k_date,
                        "Mực nước đã biết": k_level,
                        "Mực nước trích xuất": parsed_lvl,
                        "Trạng thái đối chiếu": status_cmp,
                        "Nhãn": parsed_flag,
                        "Đoạn văn gốc (Snippet)": snip,
                        "Bảng thô": raw_tbl,
                    })
                else:
                    compare_rows.append({
                        "Ngày": k_date,
                        "Mực nước đã biết": k_level,
                        "Mực nước trích xuất": None,
                        "Trạng thái đối chiếu": "Chưa quét ngày này",
                        "Nhãn": "",
                        "Đoạn văn gốc (Snippet)": "",
                        "Bảng thô": "",
                    })

            cmp_df = pd.DataFrame(compare_rows)
            st.dataframe(cmp_df, use_container_width=True, hide_index=True)

            # Chi tiết kiểm tra ngày 2025-10-30 theo đề bài
            st.markdown("""
            > [!NOTE]
            > **Giải đáp nghi vấn ngày 30/10/2025 (5.62m lúc 2h):**
            > - File bản tin mặc định của ngày này `20251030_1030.pdf` không tồn tại ở thư mục kttv vào giờ 10:30 (trả về 404).
            > - Đây là trường hợp **missing_pdf**, KHÔNG phải lỗi trượt regex. Hãy dùng chức năng **Thử lại ngày thiếu (Module C)** với các giờ phát lũ đặc biệt (như 0830, 0900, 1430, 1630) hoặc tải file từ nguồn lưu trữ khác!
            """)

            with st.expander("Chỉnh sửa danh sách ngày đã biết (known_days.csv)"):
                edited_known = st.data_editor(known_df, num_rows="dynamic", use_container_width=True)
                if st.button("Lưu thay đổi known_days.csv"):
                    save_known_days(edited_known)
                    st.success("Đã lưu known_days.csv!")
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 4: HIỆU CHUẨN CỘT BẢNG (MODULE E)
    # ══════════════════════════════════════════════════════════════════════
    with tab_calib:
        st.subheader("Hiệu chuẩn Cột Bảng bằng Ngày Lũ (Module E)")
        st.markdown("""
        Bản tin KTTV luôn có bảng số liệu ở cuối. Đơn vị trong bảng là **centimét (cm)**.
        Module này so sánh từng cột `tbl_c1`..`tbl_c8` chia cho 100 với mực nước trích từ câu văn (`level_m_text`).
        """)

        if not st.session_state.results:
            st.info("Chưa có dữ liệu. Hãy quét các ngày lũ để tiến hành hiệu chuẩn.")
        else:
            calib_df = pd.DataFrame(st.session_state.results)
            stats_table = calculate_calibration_stats(calib_df, max_k=8)

            if stats_table.empty:
                st.warning("Chưa có ngày nào có đồng thời mực nước câu văn và số bảng.")
            else:
                st.dataframe(stats_table, use_container_width=True, hide_index=True)

                st.markdown("""
                > [!WARNING]
                > **Quy tắc hiệu chuẩn khoa học:**
                > 1. Nếu số ngày đối chiếu < 10: **Chưa đủ bằng chứng**, không nên tự ý áp dụng cột bảng.
                > 2. Hiệu chuẩn ngày lũ dựa trên mức nước dâng cao; có thể **không hoàn toàn áp dụng cho ngày thường** (do triều rút hoặc âm).
                """)

                # Người dùng tự chọn cột hiệu chuẩn
                options = ["Chưa chọn (Không dùng cột bảng)"] + [f"tbl_c{i}" for i in range(1, 9)]
                current_choice_idx = 0
                if st.session_state.calibrated_col:
                    current_choice_idx = st.session_state.calibrated_col

                col_sel = st.selectbox(
                    "Chọn cột bảng đáng tin cậy nhất sau khi kiểm tra thống kê trên:",
                    options=options,
                    index=current_choice_idx,
                )

                if st.button("💾 Lưu lựa chọn hiệu chuẩn vào config.json"):
                    if col_sel.startswith("tbl_c"):
                        selected_k = int(col_sel.replace("tbl_c", ""))
                        st.session_state.calibrated_col = selected_k
                        save_config({"calibrated_col": selected_k})
                        st.success(f"Đã lưu: Áp dụng **tbl_c{selected_k}** làm cột mực nước từ bảng (level_table_m = tbl_c{selected_k} / 100.0)!")
                    else:
                        st.session_state.calibrated_col = None
                        save_config({"calibrated_col": None})
                        st.info("Đã tắt sử dụng cột bảng.")

                    # Cập nhật lại kết quả
                    for i, r in enumerate(st.session_state.results):
                        k_val = st.session_state.calibrated_col
                        if k_val and r.get(f"tbl_c{k_val}") is not None:
                            try:
                                st.session_state.results[i]["level_table_m"] = round(float(r[f"tbl_c{k_val}"]) / 100.0, 2)
                            except Exception:
                                pass
                        else:
                            st.session_state.results[i]["level_table_m"] = None
                        st.session_state.results[i]["flag"] = determine_quality_flag(st.session_state.results[i], st.session_state.calibrated_col)

                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════
    # TAB 5: BIỂU ĐỒ MỰC NƯỚC
    # ══════════════════════════════════════════════════════════════════════
    with tab_chart:
        st.subheader("Biểu đồ Chuỗi Thời gian Mực nước")

        if not st.session_state.results:
            st.info("Chưa có dữ liệu.")
        else:
            chart_df = pd.DataFrame(st.session_state.results).copy()
            chart_df = compute_level_best(chart_df, st.session_state.calibrated_col)

            # Lọc các dòng có mực nước
            has_val = chart_df[chart_df["level_best"].notna()].copy()
            if has_val.empty:
                st.warning("Không có dòng nào có giá trị số mực nước để vẽ biểu đồ.")
            else:
                has_val["date_dt"] = pd.to_datetime(has_val["date"])
                has_val = has_val.sort_values("date_dt")

                try:
                    import plotly.graph_objects as go
                    fig = go.Figure()

                    # Vẽ đường mực nước nối liền
                    fig.add_trace(go.Scatter(
                        x=has_val["date_dt"],
                        y=has_val["level_best"],
                        mode="lines+markers",
                        name="Mực nước Câu Lâu (m)",
                        line=dict(color="#2563eb", width=2),
                        marker=dict(size=6, color="#1d4ed8"),
                        hovertemplate="<b>%{x|%d/%m/%Y}</b><br>Mực nước: %{y:.2f} m<extra></extra>",
                    ))

                    # Đường ngưỡng tham chiếu
                    fig.add_hline(y=BD2_M, line=dict(color="#f59e0b", dash="dash"), annotation_text=f"BĐ2 ({BD2_M}m)", annotation_position="top right")
                    fig.add_hline(y=BD3_M, line=dict(color="#ef4444", dash="dash"), annotation_text=f"BĐ3 ({BD3_M}m)", annotation_position="top right")
                    fig.add_hline(y=HIST_M, line=dict(color="#7c3aed", dash="dot"), annotation_text=f"Lũ lịch sử 1964 ({HIST_M}m)", annotation_position="top right")

                    fig.update_layout(
                        title="Chuỗi mực nước sông Thu Bồn tại trạm Câu Lâu (m)",
                        xaxis_title="Thời gian",
                        yaxis_title="Mực nước (m)",
                        height=520,
                        hovermode="x unified",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                except Exception:
                    # Dự phòng Matplotlib
                    fig, ax = plt.subplots(figsize=(10, 4.5))
                    ax.plot(has_val["date_dt"], has_val["level_best"], "o-", color="#2563eb", label="Mực nước")
                    ax.axhline(BD2_M, color="#f59e0b", linestyle="--", label=f"BĐ2 = {BD2_M}m")
                    ax.axhline(BD3_M, color="#ef4444", linestyle="--", label=f"BĐ3 = {BD3_M}m")
                    ax.axhline(HIST_M, color="#7c3aed", linestyle=":", label=f"Lũ 1964 = {HIST_M}m")
                    ax.legend()
                    ax.set_ylabel("Mét")
                    st.pyplot(fig)
                    plt.close(fig)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 6: NGUỒN BỔ SUNG (MODULE G)
    # ══════════════════════════════════════════════════════════════════════
    with tab_extra:
        st.subheader("Nguồn Bổ sung: GloFAS, Mưa, Nhập tay, Chính thức (Module G)")

        tab_g1, tab_g2, tab_g_news, tab_g3, tab_g4 = st.tabs([
            "🌊 GloFAS Flood API",
            "✍️ Sự kiện lũ nhập tay",
            "🔍 Quét tin tức lũ lụt (Hội An - ĐN - QN)",
            "🏢 Dữ liệu chính thức",
            "🌧️ Ghép mưa Open-Meteo",
        ])

        # ── G1: GLOFAS OPEN-METEO FLOOD API ──────────────────────────────
        with tab_g1:
            st.markdown("#### Lưu lượng mô phỏng GloFAS qua Open-Meteo Flood API")
            st.markdown("""
            Tài liệu chính thức: **[open-meteo.com/en/docs/flood-api](https://open-meteo.com/en/docs/flood-api)**  
            Tham số: `daily=river_discharge` ($m^3/s$).  
            ⚠️ **Ghi chú quan trọng:** Đây là **lưu lượng dòng chảy mô phỏng từ mô hình thủy văn toàn cầu GloFAS**, 
            **KHÔNG phải mực nước đo tại trạm**. Tuyệt đối không trộn lẫn hai đại lượng này!
            """)

            col_gf1, col_gf2 = st.columns(2)
            with col_gf1:
                gf_lat = st.number_input("Latitude (Vĩ độ)", value=15.882, format="%.4f", help="Trạm Câu Lâu: ~15.882; Hội An: ~15.877")
            with col_gf2:
                gf_lon = st.number_input("Longitude (Kinh độ)", value=108.232, format="%.4f", help="Trạm Câu Lâu: ~108.232; Hội An: ~108.335")

            if st.button("🌐 Lấy dữ liệu lưu lượng GloFAS"):
                with st.spinner("Đang gọi Open-Meteo Flood API..."):
                    df_glo, meta_glo, status_glo = fetch_glofas_discharge(gf_lat, gf_lon, start_date, end_date)
                    if status_glo == "ok" and df_glo is not None:
                        st.session_state.glofas_data = df_glo
                        st.session_state.glofas_meta = meta_glo
                        st.success("Tải dữ liệu GloFAS thành công!")
                    else:
                        st.error(f"Lỗi: {status_glo}")

            if st.session_state.glofas_data is not None:
                meta = st.session_state.glofas_meta or {}
                st.info(
                    f"📍 Tọa độ yêu cầu: ({meta.get('requested_lat')}, {meta.get('requested_lon')}) | "
                    f"**Tọa độ lưới sông (snapped):** ({meta.get('snapped_lat')}, {meta.get('snapped_lon')})\n\n"
                    f"⚠️ *Lưu ý:* Mô hình tự bắt vào lòng sông lớn nhất trong bán kính ~5km. Hãy kiểm tra xem tọa độ snapped có bị lệch sang sông Vu Gia không."
                )
                st.dataframe(st.session_state.glofas_data.head(10), use_container_width=True)

                # Vẽ biểu đồ lưu lượng
                try:
                    import plotly.express as px
                    fig_gf = px.line(
                        st.session_state.glofas_data,
                        x="date",
                        y="discharge_m3s",
                        title=f"Lưu lượng mô phỏng GloFAS ({meta.get('units', 'm3/s')})",
                        labels={"date": "Ngày", "discharge_m3s": "Lưu lượng (m3/s)"},
                    )
                    st.plotly_chart(fig_gf, use_container_width=True)
                except Exception:
                    pass

        # ── G2: SỰ KIỆN LŨ NHẬP TAY ──────────────────────────────────────
        with tab_g2:
            st.markdown("#### Sự kiện lũ nhập tay có URL đối chiếu (events_manual.csv)")
            st.markdown("Dành cho các ngày đặc biệt nhóm tìm được qua báo chí hoặc công văn. **BẮT BUỘC có source_url**.")

            manual_df = load_manual_events()

            with st.form("add_manual_event_form", clear_on_submit=True):
                c_m1, c_m2, c_m3 = st.columns(3)
                with c_m1:
                    m_date = st.date_input("Ngày sự kiện", value=date(2025, 10, 30))
                    m_time = st.text_input("Giờ đo (vd: 02:00)", value="02:00")
                with c_m2:
                    m_level = st.number_input("Mực nước (m)", value=5.62, format="%.2f")
                    m_alarm_ref = st.selectbox("Báo động", ["BĐ3", "BĐ2", "BĐ1", "Không"])
                with c_m3:
                    m_src_name = st.text_input("Nguồn (vd: Báo Tuổi Trẻ / Đài PT-TH)", value="Báo chí")
                    m_entered = st.text_input("Người nhập", value="Nhóm học sinh")

                m_url = st.text_input("URL bài báo / nguồn đối chiếu (BẮT BUỘC)").strip()
                m_verified = st.checkbox("Đã đối chiếu xác thực thông tin này", value=True)

                submit_manual = st.form_submit_button("➕ Thêm sự kiện lũ")
                if submit_manual:
                    if not m_url:
                        st.error("❌ BẮT BUỘC phải điền URL bài báo / nguồn tham chiếu để đảm bảo tính khoa học!")
                    else:
                        new_event = pd.DataFrame([{
                            "date": m_date.isoformat(),
                            "time": m_time,
                            "level_m": m_level,
                            "alarm_ref": m_alarm_ref,
                            "alarm_diff_m": round(m_level - BD3_M, 2) if m_alarm_ref == "BĐ3" else 0.0,
                            "source_name": m_src_name,
                            "source_url": m_url,
                            "entered_by": m_entered,
                            "verified": m_verified,
                        }])
                        manual_df = pd.concat([manual_df, new_event], ignore_index=True)
                        save_manual_events(manual_df)
                        st.success("Đã lưu sự kiện vào events_manual.csv!")
                        st.rerun()

            st.markdown("##### Danh sách sự kiện đã lưu:")
            edited_manual = st.data_editor(manual_df, num_rows="dynamic", use_container_width=True, key="manual_editor")
            if st.button("Lưu chỉnh sửa bảng sự kiện"):
                save_manual_events(edited_manual)
                st.success("Đã cập nhật events_manual.csv!")
                st.rerun()

        # ── G_NEWS: QUÉT TIN TỨC LŨ LỤT TỰ ĐỘNG ─────────────────────────
        with tab_g_news:
            st.markdown("#### 🔍 Tự động quét tin tức & mực nước lũ lụt (Hội An - Quảng Nam - Đà Nẵng)")
            st.markdown(
                "Công cụ tự động tìm kiếm các bài báo chính thống (Báo Tuổi Trẻ, Dân Trí, Báo Quảng Nam, Báo Đà Nẵng, QĐND...) "
                "về lũ sông Vu Gia - Thu Bồn, trích xuất ngày và số mét mực nước tham khảo."
            )

            c_n1, c_n2 = st.columns([3, 1])
            with c_n1:
                news_query = st.text_input(
                    "Từ khóa tìm kiếm tin lũ lụt",
                    value="mực nước lũ Câu Lâu Hội An Quảng Nam Đà Nẵng",
                    help="Gợi ý: 'mực nước trạm Câu Lâu', 'lũ sông Thu Bồn Hội An', 'thủy điện xả lũ Vu Gia Thu Bồn'",
                )
            with c_n2:
                max_news_items = st.selectbox("Số lượng tin quét", [15, 30, 50], index=1)

            if "scraped_news" not in st.session_state:
                st.session_state.scraped_news = []

            if st.button("🚀 Bắt đầu quét tin tức lũ lụt", type="primary"):
                with st.spinner("Đang quét các nguồn tin tức chính thống..."):
                    news_items = search_flood_news(news_query, max_results=max_news_items)
                    st.session_state.scraped_news = news_items
                    if news_items:
                        st.success(f"Đã tìm thấy {len(news_items)} tin tức liên quan!")
                    else:
                        st.warning("Không tìm thấy tin tức nào khớp với từ khóa.")

            if st.session_state.scraped_news:
                st.markdown(f"**Kết quả ({len(st.session_state.scraped_news)} bài báo):**")

                # Nút thêm tất cả các tin có mực nước vào events_manual.csv
                items_with_level = [it for it in st.session_state.scraped_news if it.get("level_m") is not None]
                if items_with_level:
                    if st.button(f"📥 Thêm tất cả {len(items_with_level)} tin có số mực nước vào Sự kiện lũ nhập tay"):
                        cur_man = load_manual_events()
                        new_rows = []
                        for it in items_with_level:
                            new_rows.append({
                                "date": it.get("date", ""),
                                "time": "12:00",
                                "level_m": it.get("level_m"),
                                "alarm_ref": "BĐ3" if it.get("level_m", 0) >= BD3_M else ("BĐ2" if it.get("level_m", 0) >= BD2_M else "BĐ1"),
                                "alarm_diff_m": round(it.get("level_m", 0) - BD3_M, 2),
                                "source_name": it.get("source_name", "Báo chí"),
                                "source_url": it.get("source_url", ""),
                                "entered_by": "Auto News Scraper",
                                "verified": True,
                            })
                        updated_man = pd.concat([cur_man, pd.DataFrame(new_rows)], ignore_index=True).drop_duplicates(subset=["source_url"])
                        save_manual_events(updated_man)
                        st.success("Đã thêm thành công vào events_manual.csv!")
                        st.rerun()

                for idx, item in enumerate(st.session_state.scraped_news):
                    c_box1, c_box2 = st.columns([4, 1])
                    with c_box1:
                        st.markdown(f"**{idx+1}. [{item['title']}]({item['source_url']})**")
                        lvl_str = f"📏 Mực nước phát hiện: **{item['level_m']:.2f} m** | " if item.get("level_m") else ""
                        st.caption(f"📅 Ngày: `{item['date']}` | 📰 Nguồn: **{item['source_name']}** | {lvl_str}")
                    with c_box2:
                        add_single_btn = st.button("➕ Thêm sự kiện", key=f"add_news_{idx}")
                        if add_single_btn:
                            cur_man = load_manual_events()
                            lvl_m = item.get("level_m") if item.get("level_m") is not None else 5.20
                            new_single = pd.DataFrame([{
                                "date": item.get("date", date.today().isoformat()),
                                "time": "12:00",
                                "level_m": lvl_m,
                                "alarm_ref": "BĐ3" if lvl_m >= BD3_M else "BĐ2",
                                "alarm_diff_m": round(lvl_m - BD3_M, 2),
                                "source_name": item.get("source_name", "Báo chí"),
                                "source_url": item.get("source_url", ""),
                                "entered_by": "Auto News Scraper",
                                "verified": True,
                            }])
                            updated_man = pd.concat([cur_man, new_single], ignore_index=True).drop_duplicates(subset=["source_url"])
                            save_manual_events(updated_man)
                            st.success(f"Đã thêm tin #{idx+1} vào Sự kiện lũ!")
                            st.rerun()
                    st.divider()

        # ── G3: DỮ LIỆU CHÍNH THỨC ───────────────────────────────────────
        with tab_g3:
            st.markdown("#### Tải lên dữ liệu chính thức từ Đài KTTV (official_data.csv)")
            st.markdown(
                "Định dạng CSV yêu cầu: `date, level_m, source_note`  \n"
                "Nguồn này được gán ưu tiên cao nhất trong việc xác định `level_best`."
            )

            off_file = st.file_uploader("Tải lên file official_data.csv", type=["csv"], key="uploader_off")
            if off_file:
                try:
                    df_up_off = pd.read_csv(off_file)
                    if "date" in df_up_off.columns and "level_m" in df_up_off.columns:
                        df_up_off.to_csv(OFFICIAL_DATA_FILE, index=False, encoding="utf-8-sig")
                        st.success(f"Đã lưu {len(df_up_off)} dòng dữ liệu chính thức!")
                        st.rerun()
                    else:
                        st.error("File thiếu cột `date` hoặc `level_m`!")
                except Exception as e:
                    st.error(f"Lỗi đọc file: {e}")

            if OFFICIAL_DATA_FILE.exists():
                st.caption("Dữ liệu chính thức hiện tại:")
                st.dataframe(pd.read_csv(OFFICIAL_DATA_FILE), use_container_width=True)

        # ── G4: GHÉP MƯA OPEN-METEO ──────────────────────────────────────
        with tab_g4:
            st.markdown("#### Ghép dữ liệu lượng mưa từ Open-Meteo Historical Weather")
            st.markdown("""
            Tải file CSV lịch sử thời tiết từ: **[open-meteo.com/en/docs/historical-weather-api](https://open-meteo.com/en/docs/historical-weather-api)**  
            Chọn tọa độ Hội An (15.877, 108.335), tích `precipitation` hoặc `rain`.
            """)
            rain_up = st.file_uploader("Tải lên file CSV mưa Open-Meteo", type=["csv"], key="rain_uploader_v2")
            if rain_up and st.session_state.results:
                try:
                    rain_bytes = rain_up.read()
                    base_df = pd.DataFrame(st.session_state.results)
                    m_df = merge_rain_data(base_df, rain_bytes)
                    st.success(f"Ghép thành công {len(m_df)} dòng! Đã tính rain_1d, rain_3d, rain_7d.")
                    st.dataframe(m_df[["date", "level_m_text", "rain_1d", "rain_3d", "rain_7d"]].dropna(how="all", subset=["rain_1d"]), use_container_width=True)
                except Exception as e:
                    st.error(f"Lỗi ghép mưa: {e}")


# =============================================================================
# CHẾ ĐỘ TEST ĐỘC LẬP KHI CHẠY: python app.py --test
# =============================================================================

def _run_tests() -> None:
    """Chạy toàn bộ unit test với pytest hoặc trực tiếp."""
    print("\n=== Đang chạy toàn bộ bộ kiểm thử tự động V2... ===\n")
    import pytest
    ret = pytest.main(["-v", "tests/test_parsers.py"])
    if ret == 0:
        print("\n🎉 TẤT CẢ UNIT TEST V2 ĐÃ PASSED!\n")
    else:
        print("\n❌ CÓ TEST KHÔNG VƯỢT QUA, VUI LÒNG KIỂM TRA LẠI!\n")
    sys.exit(ret)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        run_app()
