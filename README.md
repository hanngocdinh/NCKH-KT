# 🌊 HỆ THỐNG AI + IoT DỰ BÁO NGUY CƠ NGẬP LỤT HỘI AN (TRƯỚC 24 GIỜ)
### Đề tài Nghiên cứu Khoa học Kỹ thuật – Trường THPT Trần Quý Cáp (TP. Hội An, Quảng Nam)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Dashboard-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Hardware](https://img.shields.io/badge/IoT-ESP32%20Wokwi-00979D.svg)](https://wokwi.com/)
[![Tests](https://img.shields.io/badge/Tests-35%2F35%20Passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Dự án phát triển hệ thống trí tuệ nhân tạo (AI) kết hợp cảm biến vạn vật (IoT) nhằm **cảnh báo sớm nguy cơ ngập lụt cục bộ trước 24 giờ** tại khu vực trường học THPT Trần Quý Cáp, hạ lưu lưu vực sông Thu Bồn, TP. Hội An, tỉnh Quảng Nam.

> **Cập nhật prototype:** model 24 giờ trong tài liệu cũ hiện được giữ ở trạng thái `legacy_reference_only`. Pipeline đang phát triển chính là mô hình vật lý thu nhỏ nhận dữ liệu HTTP và dự báo 15/30 phút. Kết quả là mô phỏng thử nghiệm, không phải cảnh báo vận hành cho Hội An.

---

## 🌟 ĐIỂM NỔI BẬT CỦA ĐỀ TÀI

1. **Dự báo Sớm trước 24 giờ ($t \to t+1$):** Không dừng lại ở việc báo động tức thời khi nước đã tràn, hệ thống tận dụng dữ liệu trễ và biến thiên thủy văn thượng nguồn để cảnh báo trước 1 ngày, giúp Ban Giám hiệu chủ động cho học sinh nghỉ học hoặc kê cao tài sản.
2. **Mô hình Cứu sinh (Recall 100%):** Huấn luyện mô hình Logistic Regression và Random Forest với kỹ thuật *Class-weight Balancing*, ưu tiên độ nhạy tối đa cho nhãn Nguy cơ cao — triệt tiêu tình trạng bỏ sót các đợt lũ quét, lũ ống nguy hiểm.
3. **Cơ chế Dự phòng Không Cảm biến (Sensorless Fallback):** Trang bị cây quyết định độc lập (Decision Tree) chỉ dựa trên lượng mưa và khí hậu vi mô, giúp hệ thống vẫn cảnh báo chính xác ngay cả khi trạm đo mực nước trên sông gặp sự cố đứt cáp hoặc mất điện.
4. **Mô phỏng Phần cứng IoT Toàn diện (Wokwi ESP32):** Tích hợp cảm biến siêu âm HC-SR04 đo mực nước ngập sân trường, cảm biến nhiệt ẩm DHT22, cụm đèn LED giao thông 3 màu và còi hú cảnh báo khẩn cấp.
5. **Kênh Cảnh báo Đa phương tiện:** Tích hợp Telegram Bot gửi tin nhắn tự động đến nhóm điều hành nhà trường và phụ huynh với cơ chế Cooldown 15 phút chống nghẽn tin nhắn.
6. **Kiểm thử Khoa học Nghiêm ngặt:** 100% mã nguồn được bảo vệ bởi 35 bài kiểm thử tự động (`pytest`), cam kết tính toàn vẹn dữ liệu, chống rò rỉ thông tin tương lai (Target Leakage Proof).

---

## 🏛️ KIẾN TRÚC HỆ THỐNG

```
[ DỮ LIỆU ĐẦU VÀO ]
  ├── Quan trắc trạm Câu Lâu (Mực nước H, Biến thiên delta H)
  ├── Thủy điện xả thượng nguồn (Lưu lượng Q, Q trung bình 3 ngày)
  └── Trạm khí tượng (Mưa ngày, Mưa giờ đỉnh, Mưa tích lũy 3d, 7d)
            │
            ▼
[ TIỀN XỬ LÝ & LÀM GIÀU ĐẶC TRƯNG ]
  ├── Chuẩn hóa chuỗi thời gian 366 ngày liên tục
  ├── Trích xuất vector 9 đặc trưng thủy văn
  └── Gán nhãn mục tiêu tương lai (Target Lead-24h)
            │
            ▼
[ ĐỘNG CƠ TRÍ TUỆ NHÂN TẠO ]
  ├── Logistic Regression (Mô hình Cứu sinh - Recall 100%)
  ├── Random Forest (Độ chính xác cao trên đa lớp)
  └── Sensorless Decision Tree (Chế độ dự phòng khi mất cảm biến)
            │
      ┌─────┴────────────────────────────────┐
      ▼                                      ▼
[ GIAO DIỆN ĐIỀU HÀNH ]             [ THIẾT BỊ PHẦN CỨNG IOT ]
  ├── Streamlit IoT Dashboard         ├── ESP32 Microcontroller
  ├── Đồng hồ thủy văn Câu Lâu        ├── Cảm biến siêu âm HC-SR04
  ├── Phân tích xác suất AI           ├── Đèn LED 3 trạng thái
  └── Telegram Bot Alerts             └── Còi báo động khẩn cấp
```

---

## 📚 TÀI LIỆU CHI TIẾT DỰ ÁN

* 📘 **[Cẩm nang Vận hành Toàn diện (RUNBOOK.md)](RUNBOOK.md):** Hướng dẫn từng bước từ cài đặt, huấn luyện, chạy dashboard, thiết lập Telegram bot đến gỡ lỗi thực tế.
* 📖 **[Cẩm nang Lý thuyết Phân tích Dữ liệu & AI (docs/AI_DATASET_ANALYTICS_AND_CONCEPTS.md)](docs/AI_DATASET_ANALYTICS_AND_CONCEPTS.md):** Bản chất thủy văn sông Thu Bồn, EDA, ma trận tương quan, giải pháp mất cân bằng nhãn ($88.5\%$ an toàn vs $11.5\%$ ngập) và toán học thuật toán.
* 🚀 **[Hướng dẫn Thiết kế & Vận hành Demo Giả lập (docs/SIMULATION_AND_DEMO_GUIDE.md)](docs/SIMULATION_AND_DEMO_GUIDE.md):** Kiến trúc luồng dữ liệu, vector 9 đặc trưng và kết nối mô phỏng phần cứng Wokwi.
* 📝 **[Tóm tắt Báo cáo Khoa học (docs/NOI_DUNG_BAO_CAO_GOOGLE_DOCS.md)](docs/NOI_DUNG_BAO_CAO_GOOGLE_DOCS.md):** Đề cương báo cáo khoa học nộp Hội đồng Đánh giá.

---

## 📂 CẤU TRÚC THƯ MỤC DỰ ÁN

```
.
├── docs/                                    # Cẩm nang khoa học & hướng dẫn vận hành
│   ├── assets/                              # Biểu đồ phân tích dữ liệu trực quan
│   ├── AI_DATASET_ANALYTICS_AND_CONCEPTS.md # Lý thuyết EDA, thủy văn & thuật toán AI
│   ├── SIMULATION_AND_DEMO_GUIDE.md         # Hướng dẫn thiết kế và chạy demo giả lập
│   └── NOI_DUNG_BAO_CAO_GOOGLE_DOCS.md      # Đề cương báo cáo khoa học
│
├── models/                                  # Thư mục lưu trữ mô hình AI sản xuất
│   ├── model_lead24h_logistic_regression.joblib  # Mô hình Cứu sinh (Recall 100%)
│   ├── model_lead24h_random_forest.joblib        # Mô hình Random Forest đa lớp
│   ├── model_sensorless_decision_tree.joblib     # Mô hình dự phòng mất cảm biến
│   ├── model_metadata.json                       # Siêu dữ liệu và lịch sử huấn luyện
│   ├── training_benchmark_results.csv            # Bảng so sánh chỉ số đánh giá
│   └── evaluation_confusion_matrices.png         # Ma trận nhầm lẫn trực quan
│
├── simulation_wokwi/                        # Mạch mô phỏng phần cứng vi điều khiển
│   ├── diagram.json                         # Sơ đồ đấu nối chân ESP32, cảm biến, LED, còi
│   ├── libraries.txt                        # Danh sách thư viện Wokwi
│   └── sketch.ino                           # Firmware nhúng C++ cho ESP32
│
├── tests/                                   # Bộ kiểm thử tự động hệ thống (35 tests)
│   ├── test_dataset_preparation.py          # Kiểm thử tính toàn vẹn dữ liệu
│   ├── test_iot_dashboard.py                # Kiểm thử cỗ máy trạng thái IoT
│   ├── test_model_training.py               # Kiểm thử cấu trúc mô hình AI
│   └── test_parsers.py                      # Kiểm thử thuật toán bóc tách dữ liệu
│
├── alert_notifier.py                        # Module phát cảnh báo tự động qua Telegram Bot
├── analyze_and_prepare_dataset.py           # Phân tích EDA, tạo đặc trưng trễ & xuất biểu đồ
├── app.py                                   # Web Dashboard bóc tách & hiệu chuẩn dữ liệu KTTV
├── app_iot_dashboard.py                     # Web Dashboard Giám sát IoT & Cảnh báo Sớm AI
├── collect_and_build_dataset.py             # Pipeline thu thập chuỗi thời gian khí tượng
├── export_to_excel.py                       # Xuất tập dữ liệu chuẩn hóa sang file Excel đa sheet
├── hoian_flood_ai_dataset_prepared.csv      # Tập dữ liệu huấn luyện đã làm giàu đặc trưng
├── hoian_flood_ai_dataset_365days.csv       # Tập dữ liệu gốc chuỗi thời gian 366 ngày
├── iot_core_engine.py                       # Cỗ máy tính toán trạng thái và đo đạc IoT
├── parsers.py                               # Bộ bóc tách thông tin bản tin KTTV tiếng Việt
├── simulate_ai_demo.py                      # Công cụ chạy kịch bản giả lập trên Terminal
├── test_model_inference.py                  # CLI kiểm thử suy luận & backtesting mô hình
├── train_ai_model.py                        # Script huấn luyện & so sánh 3 kịch bản AI
├── RUNBOOK.md                               # Cẩm nang vận hành và triển khai chi tiết
├── requirements.txt                         # Danh sách thư viện phụ thuộc
└── README.md                                # Tài liệu giới thiệu tổng quan đề tài
```

---

## ⚡ HƯỚNG DẪN KHỞI CHẠY NHANH (QUICK START)

### Prototype mới: mô hình mini dự báo 15/30 phút qua HTTP

Pipeline mới chạy độc lập với model 24 giờ legacy:

```powershell
$env:MINI_FLOOD_DEVICE_KEY = "replace-with-a-long-random-key"
uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Dashboard:

```powershell
streamlit run app_mini_flood_dashboard.py
```

Xem hướng dẫn đầy đủ tại [docs/MINI_FLOOD_HTTP_GUIDE.md](docs/MINI_FLOOD_HTTP_GUIDE.md).

### 1. Cài đặt Môi trường
Yêu cầu Python >= 3.10. Khuyến nghị tạo môi trường ảo:

```powershell
# Tạo và kích hoạt môi trường ảo
python -m venv .venv
.venv\Scripts\Activate.ps1   # Trên Windows

# Cài đặt tất cả phụ thuộc
pip install -r requirements.txt
```

### 2. Khởi chạy Giao diện Giám sát IoT & Cảnh báo Sớm AI
```powershell
streamlit run app_iot_dashboard.py
```
*Truy cập trình duyệt tại `http://localhost:8501` để xem đồng hồ đo mực nước thời gian thực, điều khiển kịch bản giả lập bão lũ và quan sát dự báo rủi ro ngập lụt trước 24 giờ của AI.*

### 3. Huấn luyện Lại Mô hình AI (Tùy chọn)
```powershell
python train_ai_model.py
```
*Tự động huấn luyện 3 kịch bản, tối ưu hóa siêu tham số, xuất file trọng số `.joblib` và cập nhật biểu đồ ma trận nhầm lẫn trong `models/`.*

### 4. Kiểm thử Suy luận bằng Dòng lệnh (CLI Inference)
```powershell
python test_model_inference.py --mode demo
```

### 5. Chạy Toàn bộ Kiểm thử Tự động
```powershell
pytest -v
```
*(Hiện tại 35/35 tests passed đạt 100%).*

---

## 📊 KẾT QUẢ HUẤN LUYỆN MÔ HÌNH

| Kịch bản | Mô hình | Độ chính xác (Accuracy) | Macro F1-Score | Recall (Nguy hiểm ngập) | Đánh giá vai trò |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Cảnh báo sớm 24h** | **Logistic Regression** | **94.5%** | **0.86** | **100.0%** | **Mô hình Cứu sinh (Ưu tiên)** |
| **Cảnh báo sớm 24h** | **Random Forest** | **95.9%** | **0.89** | **92.3%** | **Dự báo đa lớp chính xác cao** |
| **Dự phòng Sensorless** | **Decision Tree** | **90.4%** | **0.78** | **84.6%** | **Dự phòng khi mất trạm đo sông** |

> [!NOTE]
> Trong bài toán phòng chống thiên tai bảo vệ tính mạng con người, **Recall (Độ nhạy) của nhãn Nguy hiểm là chỉ số tối thượng**. Việc cảnh báo nhầm mức 1 lên mức 2 gây tốn ít công chuẩn bị, nhưng việc bỏ sót lũ lụt (False Negative) sẽ gây thiệt hại khó lường. Do đó, mô hình Logistic Regression cân bằng trọng số được thiết kế làm chốt chặn cứu sinh hàng đầu.

---

## 👥 THÔNG TIN TÁC GIẢ & BẢN QUYỀN

* **Đề tài:** Hệ thống AI + IoT Dự báo Nguy cơ Ngập lụt Sớm tại TP. Hội An.
* **Đơn vị thực hiện:** Trường THPT Trần Quý Cáp – TP. Hội An, Tỉnh Quảng Nam.
* **Lĩnh vực:** Hệ thống nhúng & Phần mềm hệ thống / Trí tuệ nhân tạo (Cuộc thi Nghiên cứu Khoa học Kỹ thuật dành cho học sinh trung học).
* **Bản quyền:** Mã nguồn được phát hành theo giấy phép mã nguồn mở MIT License.
