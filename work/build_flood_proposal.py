from pathlib import Path
from datetime import date

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(r"D:\Projects\tool-craw")
OUT_DIR = ROOT / "output" / "docx"
WORK_DIR = ROOT / "work" / "proposal_assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "De_xuat_va_ke_hoach_trien_khai_AI_IoT_du_bao_ngap_V1.docx"

NAVY = "17365D"
BLUE = "2F75B5"
LIGHT_BLUE = "D9EAF7"
PALE_BLUE = "EEF5FB"
GREEN = "70AD47"
PALE_GREEN = "E2F0D9"
YELLOW = "FFD966"
PALE_YELLOW = "FFF2CC"
RED = "C00000"
PALE_RED = "FCE4D6"
GRAY = "666666"
LIGHT_GRAY = "F2F2F2"
WHITE = "FFFFFF"
BLACK = "1F1F1F"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color="D9E2F3", size="6"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:color"), color)


def set_cell_margins(cell, top=100, start=120, bottom=100, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_repeat_table_header(row):
    repeat_table_header(row)


def prevent_row_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def set_run_font(run, name="Aptos", size=None, bold=None, color=None, italic=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if italic is not None:
        run.italic = italic


def set_doc_defaults(doc):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Aptos"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Aptos")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Aptos")
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Aptos")
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(BLACK)
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.08

    for style_name, size, color in (("Title", 26, NAVY), ("Heading 1", 18, NAVY), ("Heading 2", 13, BLUE), ("Heading 3", 11, NAVY)):
        style = styles[style_name]
        style.font.name = "Aptos Display" if style_name in ("Title", "Heading 1") else "Aptos"
        style._element.rPr.rFonts.set(qn("w:ascii"), style.font.name)
        style._element.rPr.rFonts.set(qn("w:hAnsi"), style.font.name)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), style.font.name)
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.space_before = Pt(12 if style_name == "Heading 1" else 8)
        style.paragraph_format.space_after = Pt(6)

    styles["List Bullet"].paragraph_format.space_after = Pt(3)
    styles["List Number"].paragraph_format.space_after = Pt(3)


def set_page_layout(doc):
    section = doc.sections[0]
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.header_distance = Cm(0.8)
    section.footer_distance = Cm(0.8)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Trang ")
    set_run_font(run, size=8.5, color=GRAY)
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr_text)
    run._r.append(fld_char2)


def add_header_footer(doc):
    section = doc.sections[0]
    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("ĐỀ XUẤT AI–IoT DỰ BÁO NGẬP CỤC BỘ  |  V1")
    set_run_font(run, size=8, bold=True, color=BLUE)
    p.paragraph_format.space_after = Pt(0)
    footer = section.footer
    fp = footer.paragraphs[0]
    add_page_number(fp)


def add_text(doc, text, bold_lead=None, align=None, italic=False, color=None, size=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    if bold_lead and text.startswith(bold_lead):
        r1 = p.add_run(bold_lead)
        set_run_font(r1, bold=True, color=color, size=size)
        r2 = p.add_run(text[len(bold_lead):])
        set_run_font(r2, italic=italic, color=color, size=size)
    else:
        r = p.add_run(text)
        set_run_font(r, italic=italic, color=color, size=size)
    return p


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.paragraph_format.left_indent = Cm(0.6 + level * 0.5)
    p.paragraph_format.first_line_indent = Cm(-0.25)
    r = p.add_run(text)
    set_run_font(r)
    return p


def add_number(doc, text):
    p = doc.add_paragraph(style="List Number")
    p.paragraph_format.left_indent = Cm(0.65)
    p.paragraph_format.first_line_indent = Cm(-0.3)
    r = p.add_run(text)
    set_run_font(r)
    return p


def add_manual_number(doc, number, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.9)
    p.paragraph_format.first_line_indent = Cm(-0.55)
    p.paragraph_format.space_after = Pt(3)
    r1 = p.add_run(f"{number}.  ")
    set_run_font(r1, bold=True)
    r2 = p.add_run(text)
    set_run_font(r2)
    return p


def add_callout(doc, title, body, fill=PALE_BLUE, accent=BLUE):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    c1 = table.rows[0].cells[0]
    set_cell_shading(c1, fill)
    set_cell_margins(c1, 130, 190, 130, 190)
    tc_pr = c1._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge, color, size in (("left", accent, "28"), ("top", fill, "0"), ("right", fill, "0"), ("bottom", fill, "0")):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), size)
        node.set(qn("w:color"), color)
        borders.append(node)
    tc_pr.append(borders)
    p = c1.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(title)
    set_run_font(r, bold=True, color=NAVY, size=11)
    p2 = c1.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    r2 = p2.add_run(body)
    set_run_font(r2, color=BLACK, size=10)
    return table


def add_table(doc, headers, rows, widths=None, header_fill=NAVY):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for i, text in enumerate(headers):
        cell = hdr.cells[i]
        if widths:
            cell.width = Cm(widths[i])
        set_cell_shading(cell, header_fill)
        set_cell_border(cell, WHITE, "5")
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(str(text))
        set_run_font(r, bold=True, color=WHITE, size=9.2)
    for row_idx, values in enumerate(rows):
        row = table.add_row()
        prevent_row_split(row)
        for i, value in enumerate(values):
            cell = row.cells[i]
            if widths:
                cell.width = Cm(widths[i])
            set_cell_shading(cell, WHITE if row_idx % 2 == 0 else LIGHT_GRAY)
            set_cell_border(cell)
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            r = p.add_run(str(value))
            set_run_font(r, size=8.9)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def add_section_label(doc, label):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run(label.upper())
    set_run_font(r, bold=True, color=BLUE, size=8.5)
    return p


def page_break(doc):
    doc.add_page_break()


def get_font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\aptos.ttf" if not bold else r"C:\Windows\Fonts\aptos-bold.ttf",
        r"C:\Windows\Fonts\arial.ttf" if not bold else r"C:\Windows\Fonts\arialbd.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def rounded(draw, box, radius, fill, outline, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_centered(draw, box, text, font, fill, spacing=4):
    x1, y1, x2, y2 = box
    lines = text.split("\n")
    heights = []
    for line in lines:
        bb = draw.textbbox((0, 0), line, font=font)
        heights.append(bb[3] - bb[1])
    total = sum(heights) + spacing * (len(lines) - 1)
    y = y1 + (y2 - y1 - total) / 2
    for line, h in zip(lines, heights):
        bb = draw.textbbox((0, 0), line, font=font)
        w = bb[2] - bb[0]
        draw.text((x1 + (x2 - x1 - w) / 2, y), line, font=font, fill=fill)
        y += h + spacing


def make_architecture_diagram(path):
    img = Image.new("RGB", (1800, 930), "white")
    draw = ImageDraw.Draw(img)
    title_font = get_font(36, True)
    box_font = get_font(25, True)
    small_font = get_font(21, False)
    tiny_font = get_font(18, False)
    draw.text((80, 40), "Luồng dữ liệu và hai lớp ra quyết định", font=title_font, fill="#17365D")

    boxes = [
        ((80, 160, 360, 330), "Cảm biến", "Mưa\nMực nước"),
        ((450, 160, 730, 330), "ESP32", "Đọc dữ liệu\nMỗi 1 phút"),
        ((820, 160, 1110, 330), "FastAPI", "Kiểm tra\nLưu SQLite"),
        ((1200, 160, 1510, 330), "Feature Engine", "Tạo 4 đầu vào\ntừ lịch sử"),
        ((1280, 490, 1630, 680), "Random Forest", "Model 15 phút\nModel 30 phút"),
        ((760, 490, 1120, 680), "Chính sách cảnh báo", "Confidence + ngưỡng an toàn\nChọn mức cao hơn"),
        ((250, 490, 610, 680), "Phản hồi người dùng", "Đèn và còi\nDashboard\nThông báo"),
    ]
    for box, head, body in boxes:
        rounded(draw, box, 24, "#EEF5FB", "#2F75B5", 3)
        x1, y1, x2, y2 = box
        draw_centered(draw, (x1, y1 + 14, x2, y1 + 70), head, box_font, "#17365D")
        draw.line((x1 + 25, y1 + 78, x2 - 25, y1 + 78), fill="#B4C7E7", width=2)
        draw_centered(draw, (x1 + 10, y1 + 88, x2 - 10, y2 - 12), body, small_font, "#333333")

    def arrow(x1, y1, x2, y2, label=None):
        draw.line((x1, y1, x2, y2), fill="#2F75B5", width=6)
        import math
        a = math.atan2(y2 - y1, x2 - x1)
        s = 18
        p1 = (x2 - s * math.cos(a - 0.55), y2 - s * math.sin(a - 0.55))
        p2 = (x2 - s * math.cos(a + 0.55), y2 - s * math.sin(a + 0.55))
        draw.polygon([(x2, y2), p1, p2], fill="#2F75B5")
        if label:
            bb = draw.textbbox((0, 0), label, font=tiny_font)
            tx = (x1 + x2 - (bb[2] - bb[0])) / 2
            ty = (y1 + y2) / 2 - 30
            draw.rectangle((tx - 8, ty - 3, tx + (bb[2] - bb[0]) + 8, ty + (bb[3] - bb[1]) + 5), fill="white")
            draw.text((tx, ty), label, font=tiny_font, fill="#555555")

    arrow(360, 245, 450, 245)
    arrow(730, 245, 820, 245, "HTTP POST")
    arrow(1110, 245, 1200, 245)
    arrow(1430, 330, 1460, 490)
    arrow(1280, 585, 1120, 585)
    arrow(760, 585, 610, 585)

    # Offline fallback lane
    rounded(draw, (450, 760, 1120, 865), 20, "#FFF2CC", "#BF9000", 3)
    draw_centered(draw, (470, 770, 1100, 855), "Mất mạng: ESP32 dùng cây quyết định/ngưỡng để vẫn điều khiển đèn và còi", small_font, "#7F6000")
    arrow(590, 330, 590, 760)
    arrow(760, 812, 610, 680)

    img.save(path, quality=95)


def add_picture_with_alt(doc, image_path, width_inches, alt_text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    inline = run.add_picture(str(image_path), width=Inches(width_inches))
    doc_pr = inline._inline.docPr
    doc_pr.set("descr", alt_text)
    p.paragraph_format.space_after = Pt(3)
    return p


doc = Document()
set_doc_defaults(doc)
set_page_layout(doc)
add_header_footer(doc)

# Cover
doc.add_paragraph().paragraph_format.space_after = Pt(28)
add_section_label(doc, "Bản đề xuất dự án và kế hoạch triển khai")
p = doc.add_paragraph(style="Title")
p.alignment = WD_ALIGN_PARAGRAPH.LEFT
p.paragraph_format.space_after = Pt(12)
r = p.add_run("Hệ thống AI–IoT dự báo nguy cơ ngập cục bộ trước 15 đến 30 phút")
set_run_font(r, name="Aptos Display", size=27, bold=True, color=NAVY)

p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(28)
r = p.add_run("Phiên bản 1  |  Prototype mô hình hố ga trường học")
set_run_font(r, size=14, bold=True, color=BLUE)

add_callout(
    doc,
    "Mục tiêu ưu tiên",
    "Xây dựng một hệ thống chạy được từ cảm biến đến cảnh báo: đo mưa và mực nước, dự báo nguy cơ ngập trước 15 và 30 phút, sau đó điều khiển đèn và còi. Phạm vi được giới hạn để nhóm có thể thu thập dữ liệu, huấn luyện mô hình và trình diễn trực tiếp.",
    fill=PALE_BLUE,
    accent=BLUE,
)
doc.add_paragraph().paragraph_format.space_after = Pt(20)

meta = add_table(
    doc,
    ["Hạng mục", "Nội dung"],
    [
        ["Mô hình AI chính", "Random Forest cho hai mốc 15 phút và 30 phút"],
        ["Lớp dự phòng", "Cây quyết định/ngưỡng chạy trực tiếp trên ESP32"],
        ["Dữ liệu thực tế", "Cảm biến mưa và cảm biến siêu âm đo mực nước"],
        ["Phạm vi", "Một mô hình hố ga/rãnh thoát nước; không dự báo toàn Hội An"],
        ["Kết quả", "Ba mức An toàn, Có nguy cơ, Nguy hiểm cao"],
    ],
    widths=[4.0, 12.0],
)

doc.add_paragraph().paragraph_format.space_after = Pt(26)
p = doc.add_paragraph()
r = p.add_run("Ngày cập nhật  ")
set_run_font(r, size=9, bold=True, color=GRAY)
r = p.add_run("17 tháng 10 năm 2026")
set_run_font(r, size=9, color=GRAY)

page_break(doc)

# 1
doc.add_heading("1  Tóm tắt đề xuất", level=1)
add_text(doc, "Đề tài xây dựng prototype AI–IoT để dự báo nguy cơ ngập cục bộ tại một hố ga hoặc rãnh thoát nước trường học. Hệ thống lấy dữ liệu từ hai cảm biến, tạo bốn tham số đầu vào, chạy hai mô hình Random Forest và đưa ra cảnh báo sớm cho 15 phút và 30 phút tiếp theo.")
add_text(doc, "ESP32 vẫn chạy một cây quyết định đơn giản dựa trên ngưỡng an toàn. Cơ chế này cho phép đèn và còi hoạt động khi Wi-Fi hoặc máy chủ mất kết nối. Khi hệ thống trực tuyến, mức cảnh báo cuối cùng là mức cao hơn giữa kết quả AI và quy tắc an toàn.")

doc.add_heading("2  Vấn đề cần giải quyết", level=1)
add_text(doc, "Mưa lớn có thể làm nước trong hố ga hoặc rãnh thoát nước dâng nhanh. Nếu chỉ quan sát khi nước đã tràn, nhà trường có ít thời gian để khơi thông cống, kê cao thiết bị hoặc đưa học sinh đến vị trí an toàn. Đề tài tập trung vào việc phát hiện xu hướng dâng nước sớm bằng dữ liệu đo tại chỗ.")

doc.add_heading("3  Mục tiêu phiên bản 1", level=1)
add_bullet(doc, "Đo cường độ mưa và mực nước theo chu kỳ một phút.")
add_bullet(doc, "Tính tốc độ dâng nước trong 5 phút và lượng mưa tích lũy trong 15 phút.")
add_bullet(doc, "Dự báo ba mức rủi ro cho 15 phút và 30 phút tiếp theo bằng Random Forest.")
add_bullet(doc, "Điều khiển đèn xanh, vàng, đỏ và còi theo mức cảnh báo cuối cùng.")
add_bullet(doc, "Lưu dữ liệu để kiểm tra, tái huấn luyện và trình bày kết quả thí nghiệm.")

add_callout(doc, "Kết quả cần chứng minh", "Nhóm phải trình diễn được một vòng khép kín: rót nước hoặc tạo mưa mô phỏng → cảm biến ghi nhận → hệ thống phân tích → đèn/còi thay đổi → dữ liệu và dự báo hiển thị trên dashboard.")

doc.add_heading("4  Phạm vi triển khai", level=1)
add_table(
    doc,
    ["Trong phạm vi V1", "Để lại cho giai đoạn sau"],
    [
        ["Một bộ ESP32 và một mô hình hố ga sâu 40 cm", "Dự báo cho từng phường hoặc toàn thành phố Hội An"],
        ["Hai cảm biến mưa và mực nước", "Mực triều, lưu lượng sông Thu Bồn, xả thủy điện"],
        ["Dự báo 15 phút và 30 phút", "Dự báo 1 đến 3 giờ"],
        ["HTTP qua Wi-Fi, backend chạy trên laptop", "GloFAS, ảnh vệ tinh và bản đồ ngập"],
        ["Dashboard và cảnh báo tại chỗ", "Triển khai vận hành như hệ thống cảnh báo thiên tai"],
    ],
    widths=[8.0, 8.0],
)
p = add_text(doc, "Mọi màn hình và thông báo phải ghi “[MÔ PHỎNG THỬ NGHIỆM]”. V1 không dự báo ngập toàn Hội An.", italic=True, color=RED, size=9)
p.paragraph_format.space_before = Pt(2)

page_break(doc)

# Inputs
doc.add_heading("5  Dữ liệu đầu vào cho AI", level=1)
add_text(doc, "Hai cảm biến tạo ra bốn tham số thực tế. ESP32 gửi giá trị thô; backend sử dụng lịch sử đo để tính các tham số theo cửa sổ thời gian.")
add_table(
    doc,
    ["Tham số", "Nguồn", "Ý nghĩa", "Đơn vị"],
    [
        ["water_level_cm", "Cảm biến siêu âm", "Mực nước hiện tại trong hố ga", "cm"],
        ["water_rise_5m_cm", "Tính từ mực nước", "Mức tăng của mực nước trong 5 phút", "cm/5 phút"],
        ["rain_rate_mmh", "Cảm biến mưa", "Cường độ mưa tức thời", "mm/giờ"],
        ["rain_sum_15m", "Tính từ dữ liệu mưa", "Tổng lượng mưa trong 15 phút gần nhất", "mm"],
    ],
    widths=[4.0, 3.4, 6.3, 2.3],
)

doc.add_heading("6  Luồng dữ liệu của hệ thống", level=1)
diagram_path = WORK_DIR / "architecture.png"
make_architecture_diagram(diagram_path)
add_picture_with_alt(
    doc,
    diagram_path,
    6.6,
    "Sơ đồ luồng dữ liệu từ cảm biến đến ESP32, FastAPI, bộ tạo đặc trưng, Random Forest, chính sách cảnh báo và phản hồi; có nhánh dự phòng chạy trên ESP32 khi mất mạng.",
)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Hình 1  Kiến trúc V1 với AI trên laptop và lớp an toàn trên ESP32")
set_run_font(r, italic=True, size=8.5, color=GRAY)

doc.add_heading("7  Dữ liệu HTTP", level=1)
add_text(doc, "ESP32 gửi một bản ghi mỗi phút đến POST /api/v1/telemetry. Mỗi bản ghi có device_id, sequence_no, timestamp, rain_interval_mm, rain_rate_mmh, water_level_cm và quality_flags. Backend kiểm tra khóa thiết bị, phạm vi giá trị và bản ghi trùng trước khi lưu SQLite.")
add_callout(doc, "Quy tắc dữ liệu", "Giá trị thiếu hoặc lỗi cảm biến phải được đánh dấu là không xác định. Không thay dữ liệu thiếu bằng 0 vì 0 có nghĩa là không mưa hoặc không có nước.", fill=PALE_YELLOW, accent="BF9000")

page_break(doc)

# Model
doc.add_heading("8  Thiết kế mô hình Random Forest", level=1)
add_text(doc, "Hệ thống dùng hai mô hình độc lập. Model 15 phút dự báo mức nước cao nhất trong 15 phút kế tiếp; model 30 phút dùng cửa sổ 30 phút. Mỗi model nhận cùng bốn tham số đầu vào và trả về xác suất của ba lớp.")

add_table(
    doc,
    ["Lớp", "Nhãn", "Ý nghĩa"],
    [
        ["0", "An toàn", "Chưa có dấu hiệu nước dâng đến mức cần can thiệp"],
        ["1", "Có nguy cơ", "Cần theo dõi và thực hiện hành động phòng ngừa"],
        ["2", "Nguy hiểm cao", "Có nguy cơ tràn hoặc nước đang dâng rất nhanh"],
    ],
    widths=[2.0, 4.0, 10.0],
)

doc.add_heading("9  Quy đổi confidence thành cảnh báo", level=1)
add_text(doc, "Random Forest trả về ba xác suất P0, P1 và P2. Phiên bản đầu dùng ngưỡng confidence 0,60 để hạn chế việc phát cảnh báo từ dự đoán thiếu chắc chắn.")
add_number(doc, "Nếu P2 ≥ 0,60, chọn Mức 2.")
add_number(doc, "Nếu P1 + P2 ≥ 0,60, chọn Mức 1.")
add_number(doc, "Nếu hai điều kiện trên không đạt, chọn Mức 0.")
add_number(doc, "Nếu xác suất cao nhất < 0,60, đánh dấu AI chưa chắc chắn và ưu tiên kết quả từ ngưỡng an toàn.")
add_number(doc, "Mức cảnh báo cuối cùng bằng mức cao hơn giữa AI và quy tắc an toàn.")

add_callout(doc, "Nguyên tắc an toàn", "AI không được phép hạ mức cảnh báo khi cảm biến hiện tại đã vượt ngưỡng nguy hiểm. Ngưỡng 0,60 là cấu hình ban đầu và chỉ được điều chỉnh sau khi đánh giá trên tập kiểm thử.", fill=PALE_RED, accent=RED)

doc.add_heading("10  Quy tắc an toàn cho hố ga sâu 40 cm", level=1)
add_table(
    doc,
    ["Mức", "Điều kiện kích hoạt", "Phản hồi"],
    [
        ["0  AN TOÀN", "Nước < 15 cm, dâng < 2 cm/5 phút và mưa < 25 mm/giờ", "Đèn xanh; còi tắt; dạy học bình thường"],
        ["1  CÓ NGUY CƠ", "Nước 15 đến < 25 cm HOẶC dâng ≥ 3 cm/5 phút HOẶC mưa ≥ 25 mm/giờ", "Đèn vàng; còi tắt; khơi thông cống và kê cao thiết bị"],
        ["2  NGUY HIỂM CAO", "Nước ≥ 25 cm HOẶC dâng ≥ 6 cm/5 phút HOẶC nước ≥ 20 cm kèm mưa > 40 mm/giờ", "Đèn đỏ chớp; còi hú; đưa học sinh lên cao và xử lý điện theo quy trình nhà trường"],
    ],
    widths=[3.0, 7.2, 5.8],
)
add_text(doc, "Các ngưỡng trên chỉ phù hợp với mô hình hố ga sâu 40 cm đã nêu. Khi thay đổi kích thước mô hình hoặc vị trí lắp đặt, nhóm phải đo lại chiều sâu và hiệu chuẩn ngưỡng.", italic=True, color=GRAY)

page_break(doc)

# Data collection
doc.add_heading("11  Thu thập dữ liệu và tạo nhãn", level=1)
add_text(doc, "Random Forest chỉ có ý nghĩa khi dữ liệu huấn luyện bao phủ đủ trạng thái. Nhóm dùng cùng một mô hình vật lý và chạy lần lượt ba kịch bản. Mỗi kịch bản cần ít nhất ba lần chạy độc lập.")
add_table(
    doc,
    ["Kịch bản", "Cách mô phỏng", "Kết quả mong đợi"],
    [
        ["Bình thường", "Không mưa hoặc mưa nhẹ; mực nước thấp và ổn định", "An toàn"],
        ["Mưa lớn, nước đang dâng", "Tăng nước đầu vào; mực nước chưa vượt ngưỡng nhưng tăng nhanh", "Có nguy cơ"],
        ["Ngập nguy hiểm", "Duy trì mưa lớn; mực nước cao hoặc gần tràn", "Nguy hiểm cao"],
    ],
    widths=[4.0, 8.0, 4.0],
)

doc.add_heading("12  Phương pháp tạo nhãn", level=1)
add_bullet(doc, "Tại thời điểm t, tạo vector gồm bốn đặc trưng chỉ từ dữ liệu tại hoặc trước t.")
add_bullet(doc, "Nhãn 15 phút dựa trên mực nước lớn nhất trong khoảng (t, t + 15 phút].")
add_bullet(doc, "Nhãn 30 phút dựa trên mực nước lớn nhất trong khoảng (t, t + 30 phút].")
add_bullet(doc, "Loại các dòng cuối của mỗi lần chạy nếu không đủ dữ liệu tương lai để tạo nhãn.")
add_bullet(doc, "Chia train/test theo lần chạy thí nghiệm; không chia ngẫu nhiên từng dòng để tránh rò rỉ dữ liệu.")

doc.add_heading("13  Chỉ số đánh giá", level=1)
add_text(doc, "Nhóm không dùng Accuracy làm chỉ số duy nhất vì lớp nguy hiểm có thể ít hơn lớp an toàn. Báo cáo phải tách riêng cho model 15 phút và model 30 phút.")
add_table(
    doc,
    ["Chỉ số", "Mục đích"],
    [
        ["Recall lớp Nguy hiểm cao", "Đo tỷ lệ tình huống nguy hiểm được phát hiện"],
        ["Precision lớp Nguy hiểm cao", "Đo tỷ lệ cảnh báo nguy hiểm là đúng"],
        ["Macro-F1", "Đánh giá cân bằng trên cả ba lớp"],
        ["Số cảnh báo giả", "Kiểm tra mức gây phiền và khả năng sử dụng"],
        ["Số phút cảnh báo sớm", "Đo thời gian từ cảnh báo đến khi nước vượt ngưỡng"],
    ],
    widths=[5.0, 11.0],
)
add_callout(doc, "Điều kiện chọn model", "Chỉ dùng Random Forest làm model chính khi Recall lớp Nguy hiểm cao và Macro-F1 tốt hơn baseline theo ngưỡng trên tập kiểm thử. Nếu chưa đạt, hệ thống vẫn vận hành bằng quy tắc an toàn và tiếp tục thu thập dữ liệu.")

page_break(doc)

# Implementation plan
doc.add_heading("14  Kế hoạch triển khai", level=1)
add_text(doc, "Kế hoạch được chia thành sáu giai đoạn. Mỗi giai đoạn tạo ra một sản phẩm có thể kiểm tra trước khi chuyển sang bước tiếp theo.")
add_table(
    doc,
    ["Giai đoạn", "Công việc chính", "Sản phẩm bàn giao", "Điều kiện hoàn thành"],
    [
        ["1  Phần cứng và hiệu chuẩn", "Lắp ESP32, cảm biến mưa, cảm biến siêu âm, đèn và còi; đo năm mức nước biết trước", "Bộ thiết bị đọc ổn định", "Sai số được ghi nhận; không có giá trị nhảy bất thường"],
        ["2  Thu nhận dữ liệu", "Gửi HTTP mỗi phút; kiểm tra khóa, dữ liệu trùng, mất Wi-Fi và bộ đệm", "API FastAPI và SQLite", "Bản ghi hợp lệ được lưu đúng; gửi lại không tạo bản ghi trùng"],
        ["3  Cảnh báo an toàn", "Cài cây quyết định/ngưỡng trên ESP32; điều khiển đèn và còi", "Demo ngoại tuyến", "Rút Wi-Fi nhưng thiết bị vẫn đổi mức đúng"],
        ["4  Thí nghiệm", "Chạy ba kịch bản, mỗi kịch bản ít nhất ba lần; ghi nhật ký", "Dataset theo phút", "Có mã lần chạy, timestamp và quality flags đầy đủ"],
        ["5  Huấn luyện AI", "Tạo đặc trưng và nhãn; huấn luyện Random Forest 15 phút và 30 phút; so sánh baseline", "Hai model và báo cáo đánh giá", "Model đạt tiêu chí chọn hoặc ghi rõ chưa đạt"],
        ["6  Tích hợp và trình diễn", "Kết hợp AI, quy tắc an toàn, dashboard và thông báo; chạy thử toàn hệ thống", "Prototype V1 hoàn chỉnh", "Hoàn thành các ca kiểm thử và demo khép kín"],
    ],
    widths=[2.8, 5.1, 3.6, 4.5],
)

doc.add_heading("15  Thứ tự ưu tiên", level=1)
add_table(
    doc,
    ["Ưu tiên", "Hạng mục", "Lý do"],
    [
        ["P0", "Cảm biến → ESP32 → đèn/còi", "Chứng minh phần cứng và quy tắc an toàn hoạt động"],
        ["P0", "ESP32 → HTTP → SQLite", "Tạo chuỗi dữ liệu tin cậy để huấn luyện"],
        ["P1", "Random Forest 15 phút và 30 phút", "Bổ sung dự báo sớm sau khi dữ liệu đủ"],
        ["P1", "Dashboard", "Giúp quan sát dữ liệu và giải thích kết quả"],
        ["P2", "Telegram và email", "Chỉ tích hợp sau khi logic cảnh báo ổn định"],
        ["P3", "Dữ liệu thủy văn và dự báo diện rộng", "Ngoài phạm vi V1"],
    ],
    widths=[2.0, 6.0, 8.0],
)

page_break(doc)

doc.add_heading("16  Mốc tiến độ đề xuất", level=1)
add_table(
    doc,
    ["Tuần", "Mục tiêu"],
    [
        ["Tuần 1", "Lắp phần cứng, hiệu chuẩn cảm biến và hoàn thiện ngưỡng ESP32"],
        ["Tuần 2", "Hoàn thiện HTTP, SQLite, bộ đệm khi mất mạng và dashboard cơ bản"],
        ["Tuần 3", "Chạy thí nghiệm, kiểm tra chất lượng và chốt dataset"],
        ["Tuần 4", "Huấn luyện Random Forest, đánh giá và chọn cấu hình"],
        ["Tuần 5", "Tích hợp toàn hệ thống, kiểm thử lỗi và luyện trình diễn"],
    ],
    widths=[3.0, 13.0],
)
add_text(doc, "Tiến độ có thể kéo dài nếu dữ liệu thí nghiệm chưa đủ số mẫu cho lớp Có nguy cơ hoặc Nguy hiểm cao. Khi đó, nhóm ưu tiên bổ sung lần chạy thay vì hạ tiêu chí đánh giá.", italic=True, color=GRAY)

# Test plan
doc.add_heading("17  Kế hoạch kiểm thử", level=1)
add_table(
    doc,
    ["Nhóm kiểm thử", "Ca kiểm tra bắt buộc", "Kết quả đạt"],
    [
        ["Cảm biến", "Đo tại năm mức nước biết trước; lặp lại; rút cảm biến; gửi giá trị ngoài phạm vi", "Sai số được ghi; lỗi được gắn cờ; không tạo cảnh báo từ dữ liệu hỏng"],
        ["HTTP", "Payload hợp lệ; sai khóa; thiếu trường; trùng sequence_no; mất và có lại Wi-Fi", "200/401/422 đúng; không trùng bản ghi; dữ liệu đệm được gửi lại"],
        ["Tạo đặc trưng", "Kiểm tra rain_sum_15m và water_rise_5m_cm bằng dữ liệu tính tay; chu kỳ gửi không đều", "Kết quả đúng; không dùng dữ liệu tương lai; thiếu dữ liệu trả unknown"],
        ["Model", "Tách train/test theo lần chạy; confusion matrix cho hai mốc; so sánh baseline", "Có Recall, Precision, Macro-F1, cảnh báo giả và số phút báo trước"],
        ["Cảnh báo", "Chuyển mức; mất mạng; AI confidence thấp; nước vượt ngưỡng nguy hiểm", "Chọn mức cao hơn; ESP32 vẫn phát cảnh báo khi backend không hoạt động"],
        ["Thông báo", "Chuyển từ An toàn lên mức cao hơn; nguy hiểm kéo dài; kênh Telegram lỗi", "Không gửi lặp; nhắc lại sau 30 phút; email vẫn hoạt động độc lập"],
    ],
    widths=[3.0, 7.2, 5.8],
)

doc.add_heading("18  Tiêu chí nghiệm thu V1", level=1)
add_bullet(doc, "Hai cảm biến tạo dữ liệu ổn định và có kết quả hiệu chuẩn.")
add_bullet(doc, "ESP32 gửi dữ liệu theo phút, chống trùng và lưu đệm khi mất Wi-Fi.")
add_bullet(doc, "Đèn và còi phản ứng đúng theo ngưỡng ngay cả khi ngắt kết nối backend.")
add_bullet(doc, "Backend tạo đúng bốn đầu vào và không sử dụng dữ liệu tương lai.")
add_bullet(doc, "Hai model Random Forest trả xác suất và mức dự báo cho 15 phút và 30 phút.")
add_bullet(doc, "Báo cáo đánh giá có confusion matrix, Recall lớp nguy hiểm và Macro-F1.")
add_bullet(doc, "Dashboard hiển thị nhãn “[MÔ PHỎNG THỬ NGHIỆM]”.")
add_bullet(doc, "Nhóm hoàn thành một bài trình diễn khép kín và một bài kiểm thử mất mạng.")

doc.add_heading("19  Rủi ro và phương án xử lý", level=1)
add_table(
    doc,
    ["Rủi ro", "Tác động", "Cách xử lý"],
    [
        ["Ít mẫu nguy hiểm", "Model thiên về lớp An toàn", "Tăng số lần chạy kịch bản nguy hiểm; đánh giá theo từng lớp"],
        ["Cảm biến mưa không quy đổi được mm", "Đầu vào sai đơn vị", "Hiệu chuẩn bằng lượng nước biết trước; lưu hệ số và phiên bản hiệu chuẩn"],
        ["Siêu âm bị nhiễu bởi bọt hoặc mặt nước", "Mực nước dao động", "Lọc trung vị nhiều lần đo; gắn quality flag khi biến động bất thường"],
        ["Mất Wi-Fi hoặc laptop dừng", "Không có dự báo AI", "ESP32 tiếp tục dùng cây quyết định/ngưỡng và lưu đệm dữ liệu"],
        ["AI quá tự tin trên dữ liệu mới", "Cảnh báo sai", "Giữ ngưỡng an toàn làm lớp bảo vệ; theo dõi confidence và tái huấn luyện"],
    ],
    widths=[4.0, 5.0, 7.0],
)

# Final
doc.add_heading("20  Kịch bản trình diễn đề tài", level=1)
add_manual_number(doc, 1, "Khởi động hệ thống ở trạng thái nước thấp. Đèn xanh bật và còi tắt.")
add_manual_number(doc, 2, "Tăng lượng nước đầu vào để mô phỏng mưa lớn. Dashboard hiển thị mưa, mực nước và tốc độ dâng.")
add_manual_number(doc, 3, "Khi điều kiện Mức 1 xuất hiện, đèn chuyển vàng. Hệ thống giải thích nguyên nhân kích hoạt.")
add_manual_number(doc, 4, "Tiếp tục tăng nước đến Mức 2. Đèn đỏ chớp và còi hú.")
add_manual_number(doc, 5, "Ngắt Wi-Fi để chứng minh cây quyết định trên ESP32 vẫn bảo vệ tại chỗ.")
add_manual_number(doc, 6, "Kết nối lại Wi-Fi. Dữ liệu đã lưu đệm được gửi lên và AI tiếp tục dự báo.")

doc.add_heading("21  Kết quả đầu ra của đề tài", level=1)
add_bullet(doc, "Một mô hình vật lý hố ga hoặc rãnh thoát nước có cảm biến.")
add_bullet(doc, "Firmware ESP32 gồm đọc cảm biến, HTTP, lưu đệm, cây quyết định và điều khiển cảnh báo.")
add_bullet(doc, "Backend FastAPI, cơ sở dữ liệu SQLite và dashboard.")
add_bullet(doc, "Dataset thí nghiệm có mô tả cách thu thập và hiệu chuẩn.")
add_bullet(doc, "Hai model Random Forest cho 15 phút và 30 phút cùng báo cáo đánh giá.")
add_bullet(doc, "Tài liệu hướng dẫn lắp đặt, vận hành và kiểm thử.")

doc.add_heading("22  Giới hạn kết luận", level=1)
add_text(doc, "Đề tài chứng minh nguyên lý dự báo ngập cục bộ bằng AI và IoT trong điều kiện mô phỏng. Kết quả không được diễn giải thành dự báo ngập cho toàn thành phố Hội An. Việc mở rộng ra thực địa cần dữ liệu tại nhiều điểm, hiệu chuẩn theo từng vị trí và tích hợp thêm dữ liệu thủy văn đáng tin cậy.")

add_callout(
    doc,
    "Quyết định triển khai",
    "V1 chỉ được xem là hoàn thành khi hệ thống chạy ổn định từ cảm biến đến cảnh báo và có bằng chứng kiểm thử. Các tính năng diện rộng, bản đồ và dữ liệu bên ngoài chỉ bắt đầu sau khi vòng khép kín này đạt yêu cầu.",
    fill=PALE_GREEN,
    accent=GREEN,
)

doc.core_properties.title = "Đề xuất và kế hoạch triển khai hệ thống AI–IoT dự báo ngập cục bộ V1"
doc.core_properties.subject = "Prototype Random Forest 15 và 30 phút với lớp an toàn trên ESP32"
doc.core_properties.author = "Nhóm dự án"
doc.core_properties.keywords = "AI, IoT, ESP32, Random Forest, dự báo ngập, nowcasting"

doc.save(OUT_FILE)
print(OUT_FILE)
