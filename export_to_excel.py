# -*- coding: utf-8 -*-
"""
export_to_excel.py
=============================================================================
Công cụ xuất toàn bộ dữ liệu dự án sang bảng tính Excel (.xlsx) đa trang:
  - Sheet 1: Dataset_AI_Chuan_Hoa (Dữ liệu đã làm giàu đặc trưng 366 ngày)
  - Sheet 2: Hieu_Nang_Model_AI (Bảng so sánh hiệu năng các thuật toán)
  - Sheet 3: Tu_Dien_Thuoc_Tinh (Giải thích ý nghĩa, đơn vị và ký hiệu các biến)
Được định dạng chuyên nghiệp phục vụ báo cáo khoa học, trình chiếu và in ấn.
"""

import sys
from pathlib import Path
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

PREPARED_CSV = Path("hoian_flood_ai_dataset_prepared.csv")
BENCHMARK_CSV = Path("models/training_benchmark_results.csv")
OUTPUT_EXCEL = Path("hoian_flood_ai_dataset.xlsx")


def create_data_dictionary() -> pd.DataFrame:
    """Tạo bảng từ điển dữ liệu giải thích tường minh từng thuộc tính."""
    dict_data = [
        {
            "Tên cột trong Dataset": "date",
            "Ký hiệu đề tài": "T",
            "Đơn vị": "YYYY-MM-DD",
            "Nhóm thông tin": "Thời gian",
            "Ý nghĩa vật lý / Chức năng": "Ngày ghi nhận quan trắc chuỗi thời gian liên tục 1 năm (2024-2025)"
        },
        {
            "Tên cột trong Dataset": "rain_daily_mm",
            "Ký hiệu đề tài": "X2",
            "Đơn vị": "mm",
            "Nhóm thông tin": "Khí tượng",
            "Ý nghĩa vật lý / Chức năng": "Lượng mưa tổng cộng đo được trong 24 giờ của ngày đó"
        },
        {
            "Tên cột trong Dataset": "rain_max_hourly_mmh",
            "Ký hiệu đề tài": "X2'",
            "Đơn vị": "mm/h",
            "Nhóm thông tin": "Khí tượng",
            "Ý nghĩa vật lý / Chức năng": "Cường độ mưa giờ lớn nhất trong ngày (phát hiện mưa dông cục bộ)"
        },
        {
            "Tên cột trong Dataset": "rain_3d_accum_mm",
            "Ký hiệu đề tài": "X1",
            "Đơn vị": "mm",
            "Nhóm thông tin": "Khí tượng",
            "Ý nghĩa vật lý / Chức năng": "Lượng mưa tích lũy 3 ngày liên tiếp (độ ngậm nước của lưu vực sông)"
        },
        {
            "Tên cột trong Dataset": "rain_7d_accum_mm",
            "Ký hiệu đề tài": "X1'",
            "Đơn vị": "mm",
            "Nhóm thông tin": "Khí tượng",
            "Ý nghĩa vật lý / Chức năng": "Lượng mưa tích lũy 7 ngày (độ bão hòa đất nền trung hạn)"
        },
        {
            "Tên cột trong Dataset": "water_level_cm",
            "Ký hiệu đề tài": "X3",
            "Đơn vị": "cm",
            "Nhóm thông tin": "Thủy văn",
            "Ý nghĩa vật lý / Chức năng": "Mực nước thực đo hoặc mô phỏng tại trạm Câu Lâu (sông Thu Bồn)"
        },
        {
            "Tên cột trong Dataset": "water_level_m",
            "Ký hiệu đề tài": "X3'",
            "Đơn vị": "m",
            "Nhóm thông tin": "Thủy văn",
            "Ý nghĩa vật lý / Chức năng": "Mực nước trạm Câu Lâu quy đổi ra mét"
        },
        {
            "Tên cột trong Dataset": "delta_water_level_cm",
            "Ký hiệu đề tài": "X4",
            "Đơn vị": "cm/ngày",
            "Nhóm thông tin": "Thủy văn",
            "Ý nghĩa vật lý / Chức năng": "Tốc độ dâng/rút mực nước trong 24 giờ qua (Δh/Δt)"
        },
        {
            "Tên cột trong Dataset": "river_discharge_m3s",
            "Ký hiệu đề tài": "X5",
            "Đơn vị": "m³/s",
            "Nhóm thông tin": "Thủy văn",
            "Ý nghĩa vật lý / Chức năng": "Lưu lượng dòng chảy sông Thu Bồn từ mô hình toàn cầu GloFAS"
        },
        {
            "Tên cột trong Dataset": "discharge_3d_mean_m3s",
            "Ký hiệu đề tài": "X5'",
            "Đơn vị": "m³/s",
            "Nhóm thông tin": "Thủy văn",
            "Ý nghĩa vật lý / Chức năng": "Lưu lượng trung bình 3 ngày qua của sông Thu Bồn"
        },
        {
            "Tên cột trong Dataset": "delta_discharge_m3s",
            "Ký hiệu đề tài": "ΔQ",
            "Đơn vị": "m³/s",
            "Nhóm thông tin": "Động lực học",
            "Ý nghĩa vật lý / Chức năng": "Gia tốc biến thiên lưu lượng dồn lũ thượng nguồn (Q_t - Q_t-1)"
        },
        {
            "Tên cột trong Dataset": "water_level_lag1_cm",
            "Ký hiệu đề tài": "H_t-1",
            "Đơn vị": "cm",
            "Nhóm thông tin": "Đặc trưng trễ",
            "Ý nghĩa vật lý / Chức năng": "Mực nước quan trắc ngày hôm trước"
        },
        {
            "Tên cột trong Dataset": "river_discharge_lag1_m3s",
            "Ký hiệu đề tài": "Q_t-1",
            "Đơn vị": "m³/s",
            "Nhóm thông tin": "Đặc trưng trễ",
            "Ý nghĩa vật lý / Chức năng": "Lưu lượng dòng chảy ngày hôm trước"
        },
        {
            "Tên cột trong Dataset": "rain_intensity_ratio",
            "Ký hiệu đề tài": "R_ratio",
            "Đơn vị": "Tỷ số",
            "Nhóm thông tin": "Động lực học",
            "Ý nghĩa vật lý / Chức năng": "Tỷ số giữa mưa giờ cực đại và mưa ngày (xung kích mưa dông)"
        },
        {
            "Tên cột trong Dataset": "flood_risk_label",
            "Ký hiệu đề tài": "Y_sameday",
            "Đơn vị": "Cấp [0, 1, 2]",
            "Nhóm thông tin": "Nhãn mục tiêu",
            "Ý nghĩa vật lý / Chức năng": "Nhãn nguy cơ ngập cùng ngày (0: An toàn, 1: Có nguy cơ, 2: Nguy cơ cao)"
        },
        {
            "Tên cột trong Dataset": "target_lead24h",
            "Ký hiệu đề tài": "Y_t+1",
            "Đơn vị": "Cấp [0, 1, 2]",
            "Nhóm thông tin": "Mục tiêu dự báo",
            "Ý nghĩa vật lý / Chức năng": "Cấp độ nguy cơ ngập vào 24 giờ tiếp theo (Cảnh báo sớm cho trường học)"
        },
        {
            "Tên cột trong Dataset": "target_lead24h_desc",
            "Ký hiệu đề tài": "Mô tả",
            "Đơn vị": "Chuỗi văn bản",
            "Nhóm thông tin": "Mục tiêu dự báo",
            "Ý nghĩa vật lý / Chức năng": "Mô tả bằng chữ của nhãn dự báo sớm ngày mai"
        },
        {
            "Tên cột trong Dataset": "water_level_source",
            "Ký hiệu đề tài": "Source",
            "Đơn vị": "Nguồn",
            "Nhóm thông tin": "Dữ liệu gốc",
            "Ý nghĩa vật lý / Chức năng": "bulletin_table_hmax (bản tin KTTV thực đo) hoặc hydrologic_model_baseflow"
        }
    ]
    return pd.DataFrame(dict_data)


def style_worksheet(ws, header_fill_color="1F497D"):
    """Định dạng phông chữ, đường viền, màu nền tiêu đề và độ rộng cột tự động."""
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_body = Font(name="Calibri", size=10)
    fill_header = PatternFill(start_color=header_fill_color, end_color=header_fill_color, fill_type="solid")
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    border_thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    # Định dạng hàng tiêu đề (Hàng 1)
    ws.row_dimensions[1].height = 26
    for cell in ws[1]:
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center

    # Định dạng dữ liệu các hàng tiếp theo
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
        ws.row_dimensions[row[0].row].height = 20
        for cell in row:
            cell.font = font_body
            cell.border = border_thin
            # Canh lề theo kiểu dữ liệu
            if isinstance(cell.value, (int, float)):
                cell.alignment = align_right
                if isinstance(cell.value, float):
                    cell.number_format = "#,##0.00"
            elif isinstance(cell.value, str) and (len(cell.value) <= 10 and "-" in cell.value):
                cell.alignment = align_center
            else:
                cell.alignment = align_left

    # Tự động co giãn độ rộng cột
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Đóng băng dòng tiêu đề
    ws.freeze_panes = "A2"


def export_all_to_excel():
    print("=" * 75)
    print("XUẤT TOÀN BỘ TẬP DỮ LIỆU SANG MICROSOFT EXCEL (.XLSX)")
    print("=" * 75)

    if not PREPARED_CSV.exists():
        print(f"Lỗi: Không tìm thấy {PREPARED_CSV}!")
        return

    df_prepared = pd.read_csv(PREPARED_CSV)
    print(f"-> Đã đọc {len(df_prepared)} dòng dữ liệu từ: {PREPARED_CSV}")

    # Đọc kết quả benchmark mô hình nếu có
    if BENCHMARK_CSV.exists():
        df_benchmark = pd.read_csv(BENCHMARK_CSV)
        print(f"-> Đã đọc {len(df_benchmark)} dòng kết quả benchmark từ: {BENCHMARK_CSV}")
    else:
        df_benchmark = pd.DataFrame([{"Thông báo": "Chạy train_ai_model.py để cập nhật"}])

    df_dictionary = create_data_dictionary()
    print(f"-> Đã tạo bảng từ điển thuộc tính: {len(df_dictionary)} thuộc tính")

    # Xuất ra tệp Excel đa trang bằng openpyxl
    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        df_prepared.to_excel(writer, sheet_name="Dataset_AI_Chuan_Hoa", index=False)
        df_benchmark.to_excel(writer, sheet_name="Hieu_Nang_Model_AI", index=False)
        df_dictionary.to_excel(writer, sheet_name="Tu_Dien_Thuoc_Tinh", index=False)

    # Mở lại workbook để định dạng giao diện chuyên nghiệp
    wb = openpyxl.load_workbook(OUTPUT_EXCEL)
    style_worksheet(wb["Dataset_AI_Chuan_Hoa"], header_fill_color="1F497D")  # Xanh dương đậm
    style_worksheet(wb["Hieu_Nang_Model_AI"], header_fill_color="274E13")    # Xanh lá cây đậm
    style_worksheet(wb["Tu_Dien_Thuoc_Tinh"], header_fill_color="8C5611")    # Nâu cam đậm
    wb.save(OUTPUT_EXCEL)

    print(f"\n[THÀNH CÔNG] Đã xuất tệp Excel hoàn chỉnh tại:")
    print(f"👉 {OUTPUT_EXCEL.resolve()}")
    print(f"   * Kích thước: {OUTPUT_EXCEL.stat().st_size / 1024:.1f} KB")
    print("   * Gồm 3 Sheets:")
    print("     1. Sheet 'Dataset_AI_Chuan_Hoa': 366 ngày quan trắc x 29 thuộc tính")
    print("     2. Sheet 'Hieu_Nang_Model_AI'   : Bảng đối đầu Accuracy, Precision, Recall, F1")
    print("     3. Sheet 'Tu_Dien_Thuoc_Tinh'  : Bảng tra cứu ý nghĩa, đơn vị và công thức")
    print("=" * 75)


if __name__ == "__main__":
    export_all_to_excel()
