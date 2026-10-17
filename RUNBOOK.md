# SỔ TAY VẬN HÀNH HỆ THỐNG (OPERATIONAL RUNBOOK)
## HỆ THỐNG AI + IoT DỰ BÁO NGUY CƠ NGẬP LỤT HỘI AN (TRƯỚC 24 GIỜ)
### Đề tài Nghiên cứu Khoa học Kỹ thuật – Trường THPT Trần Quý Cáp (TP. Hội An, Quảng Nam)

---

## MỤC LỤC
1. [Tổng quan Kiến trúc Hệ thống](#1-tổng-quan-kiến-trúc-hệ-thống)
2. [Yêu cầu Môi trường & Cài đặt](#2-yêu-cầu-môi-trường--cài-đặt)
3. [Quy trình Xử lý Dữ liệu Thủy văn (Data Pipeline)](#3-quy-trình-xử-lý-dữ-liệu-thủy-văn-data-pipeline)
4. [Vận hành Huấn luyện & Đánh giá Mô hình AI](#4-vận-hành-huấn-luyện--đánh-giá-mô-hình-ai)
5. [Vận hành Giao diện Giám sát Streamlit (Dashboards)](#5-vận-hành-giao-diện-giám-sát-streamlit-dashboards)
6. [Cấu hình & Vận hành Cảnh báo Telegram Real-time](#6-cấu-hình--vận-hành-cảnh-báo-telegram-real-time)
7. [Vận hành Giả lập Phần cứng IoT trên Wokwi](#7-vận-hành-giả-lập-phần-cứng-iot-trên-wokwi)
8. [Kiểm thử Tự động & Đảm bảo Chất lượng (QA)](#8-kiểm-thử-tự-động--đảm-bảo-chất-lượng-qa)
9. [Xử lý Sự cố Thường gặp & Khôi phục Hệ thống (Troubleshooting)](#9-xử-lý-sự-cố-thường-gặp--khôi-phục-hệ-thống-troubleshooting)

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG

Hệ thống hoạt động theo mô hình tích hợp đa tầng, khép kín từ tầng cảm biến thu thập đến động cơ suy luận AI và kênh phát cảnh báo cộng đồng:

```
                  +----------------------------------------------+
                  |  CẢM BIẾN TRẠM ĐO & DỮ LIỆU THỦY VĂN KTTV     |
                  |  - Mực nước sông Thu Bồn (Trạm Câu Lâu)     |
                  |  - Lưu lượng xả thượng nguồn (Đại Khách)    |
                  |  - Lượng mưa ngày & tích lũy (3 ngày, 7 ngày)|
                  +----------------------------------------------+
                                         │
                                         ▼
                  +----------------------------------------------+
                  |    TIỀN XỬ LÝ & LÀM GIÀU ĐẶC TRƯNG (PYTHON)   |
                  |  - Trích xuất 9 tham số đặc trưng vật lý     |
                  |  - Tạo đặc trưng trễ (Lags, Delta, Rolling)  |
                  |  - Chống rò rỉ dữ liệu (Target Leakage Proof)|
                  +----------------------------------------------+
                                         │
                                         ▼
                  +----------------------------------------------+
                  |          ĐỘNG CƠ TRÍ TUỆ NHÂN TẠO            |
                  |  - Logistic Regression (Mô hình Cứu sinh:    |
                  |    Recall 100% không bỏ sót đợt lũ)          |
                  |  - Random Forest (Dự báo đa lớp chính xác)   |
                  |  - Decision Tree Sensorless (Dự phòng mất đo)|
                  +----------------------------------------------+
                                         │
                     ┌───────────────────┴───────────────────┐
                     ▼                                       ▼
      +-----------------------------+         +-----------------------------+
      |      WEB DASHBOARD IOT      |         |     KÊNH CẢNH BÁO TỨC THỜI  |
      | - Streamlit Real-time Gauges|         | - Telegram Bot thông báo     |
      | - Dự báo nguy cơ trước 24h  |         |   trực tiếp đến BGH, GV, HS |
      | - Phân tích xác suất rủi ro |         | - Mạch còi hú & LED 3 màu   |
      | - Điều khiển kịch bản demo  |         |   tại khuôn viên trường     |
      +-----------------------------+         +-----------------------------+
```

---

## 2. YÊU CẦU MÔI TRƯỜNG & CÀI ĐẶT

### 2.1. Yêu cầu Hệ thống
* **Hệ điều hành:** Windows 10/11, Ubuntu 20.04+, hoặc macOS.
* **Ngôn ngữ:** Python >= 3.10 (Khuyến nghị 3.11 hoặc 3.12).
* **Trình duyệt:** Google Chrome, MS Edge, Firefox hoặc Safari.

### 2.2. Khởi tạo Môi trường Ảo & Cài đặt Thư viện

```powershell
# 1. Clone repository về máy tính
git clone https://github.com/hanngocdinh/NCKH-KT.git
cd NCKH-KT

# 2. Tạo môi trường ảo Python
python -m venv .venv

# 3. Kích hoạt môi trường ảo:
# Trên Windows PowerShell:
.venv\Scripts\Activate.ps1
# Trên Linux / macOS:
# source .venv/bin/activate

# 4. Cập nhật pip và cài đặt toàn bộ phụ thuộc
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. QUY TRÌNH XỬ LÝ DỮ LIỆU THỦY VĂN (DATA PIPELINE)

Quy trình chuẩn bị dữ liệu đảm bảo tính khách quan khoa học, loại trừ hoàn toàn rò rỉ thông tin tương lai:

### 3.1. Phân tích Khám phá (EDA) & Kỹ thuật Tạo Đặc trưng
Chạy script chuẩn hóa tập dữ liệu và xuất biểu đồ trực quan hóa:

```powershell
python analyze_and_prepare_dataset.py
```

**Đầu ra tạo thành:**
1. `hoian_flood_ai_dataset_prepared.csv`: Tập dữ liệu 366 ngày liên tục với 9 vector đặc trưng đầu vào và nhãn dự báo $t+1$ (`target_lead24h`).
2. `docs/assets/eda_hydro_timeseries.png`: Chuỗi thời gian biểu diễn sự tương quan giữa lưu lượng, mực nước và các cấp báo động.
3. `docs/assets/eda_correlation_heatmap.png`: Ma trận tương quan Pearson giữa 9 đặc trưng và nhãn nguy cơ.
4. `docs/assets/eda_boxplots_by_risk.png`: Phân phối mực nước và lượng mưa tương ứng từng cấp độ rủi ro (0: An toàn, 1: Cảnh báo, 2: Nguy hiểm).

### 3.2. Xuất Báo cáo Dữ liệu sang Excel Đa Tầng
Để phục vụ việc trình bày Hội đồng Giám khảo NCKH:

```powershell
python export_to_excel.py
```
*Tạo file `hoian_flood_ai_dataset.xlsx` gồm các sheet được định dạng chuyên nghiệp: Bảng dữ liệu chuẩn hóa, Thống kê mô tả (Mean, Std, Min, Max, IQR) và Bảng tham chiếu cấp báo động sông Thu Bồn.*

---

## 4. VẬN HÀNH HUẤN LUYỆN & ĐÁNH GIÁ MÔ HÌNH AI

### 4.1. Huấn luyện Mô hình
Chạy quy trình huấn luyện toàn diện 3 kịch bản vận hành thực tế:

```powershell
python train_ai_model.py
```

**3 Kịch bản Huấn luyện:**
* **Kịch bản 1 (Cốt lõi - Cảnh báo sớm 24h):** Sử dụng các biến thời gian $t$ để dự đoán nguy cơ tại $t+1$. 
  * Thuật toán: **Logistic Regression (Class-weight balanced)** đạt **Recall 100%** trên nhãn Nguy cơ cao, đóng vai trò **Mô hình Cứu sinh** (tuyệt đối không bỏ sót đợt ngập lũ).
  * Thuật toán: **Random Forest** đạt độ chính xác cân bằng cao trên cả 3 nhãn rủi ro.
* **Kịch bản 2 (Sensorless Hydrological):** Chỉ sử dụng lượng mưa và đặc trưng khí hậu (dự phòng trường hợp cảm biến mực nước trên sông gặp sự cố hoặc đứt kết nối cáp).
* **Kịch bản 3 (Chẩn đoán Tức thời):** Dự báo tình trạng ngập ngay trong ngày từ dữ liệu quan trắc hiện hữu.

**Hiện vật xuất ra thư mục `models/`:**
* `models/model_lead24h_logistic_regression.joblib`
* `models/model_lead24h_random_forest.joblib`
* `models/model_sensorless_decision_tree.joblib`
* `models/model_metadata.json`
* `models/training_benchmark_results.csv`
* `models/evaluation_confusion_matrices.png`

### 4.2. Kiểm thử Suy luận & Đối đầu Mô hình (Inference CLI)
Công cụ dòng lệnh cho phép kiểm tra trực tiếp mô hình mà không cần mở giao diện Web:

```powershell
# Chế độ 1: Chạy thử các kịch bản mẫu điển hình (Mùa cạn, Mưa chuyển tiếp, Bão lũ)
python test_model_inference.py --mode demo

# Chế độ 2: So sánh song song quyết định của Logistic Regression vs Random Forest
python test_model_inference.py --mode compare

# Chế độ 3: Backtesting ngẫu nhiên trên các ngày lịch sử thực tế trong năm
python test_model_inference.py --mode random --samples 5

# Chế độ 4: Tự nhập tay các thông số môi trường để kiểm tra độ nhạy
python test_model_inference.py --mode manual
```

### 4.3. Chạy Demo Giả lập Tương tác Dòng lệnh
```powershell
python simulate_ai_demo.py
```
*Cho phép chọn kịch bản 1, 2, 3 và in ra quyết định AI, xác suất tin cậy, và tín hiệu điều khiển phần cứng Wokwi.*

---

## 5. VẬN HÀNH GIAO DIỆN GIÁM SÁT STREAMLIT (DASHBOARDS)

Hệ thống cung cấp 2 ứng dụng Web chuyên dụng:

### 5.1. Dashboard Điều hành IoT & Trí tuệ Nhân tạo (Khuyên dùng chính)
Đây là màn hình trung tâm điều hành giám sát nguy cơ ngập lụt tại trường:

```powershell
streamlit run app_iot_dashboard.py
```
*Truy cập trình duyệt tại địa chỉ:* `http://localhost:8501`

**Các khối chức năng trên màn hình:**
1. **Thanh trạng thái Trạm quan trắc:** Kết nối IoT, Mực nước hiện tại, Lượng mưa 24h, Lưu lượng sông.
2. **Đồng hồ Báo động Thủy văn:** Trực quan hóa mực nước theo các mốc Báo động Trạm Câu Lâu (BĐ1: 2.0m, BĐ2: 3.0m, BĐ3: 4.0m).
3. **Bộ não Dự báo AI (Trước 24 giờ):** 
   - Đánh giá cấp độ: **Mức 0 (An toàn - Xanh)**, **Mức 1 (Cảnh báo - Vàng)**, **Mức 2 (Nguy hiểm ngập sâu - Đỏ)**.
   - Hiển thị phân phối xác suất dự báo chi tiết.
   - Khuyến nghị hành động ứng phó cho Nhà trường và Phụ huynh học sinh.
4. **Bảng Điều khiển Giả lập Thời tiết:**
   - Chọn nhanh 3 kịch bản: Mùa cạn bình thường, Mưa lớn tích lũy, Đại hồng thủy lịch sử.
   - Hoặc tùy chỉnh thủ công từng thông số bằng thanh trượt slider.
5. **Cấu hình Kênh Cảnh báo Telegram:** Đăng ký nhận tin nhắn khẩn cấp trực tiếp về điện thoại.

### 5.2. Dashboard Bóc tách & Khai phá Dữ liệu KTTV
Sử dụng cho nghiên cứu sâu về nguồn số liệu bản tin gốc và thuật toán bóc tách Regex tiếng Việt:

```powershell
streamlit run app.py
```
*Hỗ trợ xem lại lịch sử trích xuất từ hơn 500 bản tin khí tượng thủy văn dạng PDF/Text.*

---

## 6. CẤU HÌNH & VẬN HÀNH CẢNH BÁO TELEGRAM REAL-TIME

Hệ thống tích hợp module `alert_notifier.py` với cơ chế Cooldown thông minh (chống nghẽn tin nhắn):

### 6.1. Các bước Khởi tạo Bot Telegram
1. Mở ứng dụng Telegram, tìm kiếm tài khoản bot chính thức của Telegram: `@BotFather`.
2. Gửi lệnh `/newbot` và đặt tên cho Bot (ví dụ: `HoiAnFloodAlertBot`).
3. Sao chép chuỗi mã **HTTP API Token** (dạng `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
4. Lấy **Chat ID**:
   - Nếu nhận tin cá nhân: Nhắn tin bất kỳ cho bot vừa tạo, sau đó mở trình duyệt truy cập:
     `https://api.telegram.org/bot<TOKEN_CUA_BAN>/getUpdates`
   - Tìm giá trị `"id": 12345678` trong phần `"chat"`.
   - Nếu dùng cho Nhóm: Mời Bot vào nhóm chung của Ban Giám hiệu, cấp quyền admin và lấy Chat ID của nhóm (thường có dấu âm `-100xxxxxxxxx`).

### 6.2. Lưu Cấu hình
Có 2 cách kích hoạt nhận thông báo:
* **Cách 1 (Qua giao diện Web):** Mở `app_iot_dashboard.py`, cuộn xuống mục **"Cấu hình Kênh cảnh báo Telegram"**, điền Token & Chat ID, nhấn nút **"Lưu & Kiểm tra kết nối"**.
* **Cách 2 (Qua mã nguồn/file cấu hình):** Tạo file `config_alerts.json` tại thư mục gốc:
  ```json
  {
    "telegram_token": "YOUR_BOT_TOKEN_HERE",
    "telegram_chat_id": "YOUR_CHAT_ID_HERE",
    "last_alerts": {}
  }
  ```

### 6.3. Nguyên lý Chống Spam Cảnh báo (Cooldown)
* Khoảng thời gian giãn cách cảnh báo lặp lại mặc định là **15 phút**.
* Nếu trạng thái chuyển đột ngột từ *An toàn* lên *Nguy cấp*, tin nhắn khẩn cấp sẽ được phát ngay lập tức không bị giữ lại bởi Cooldown.

---

## 7. VẬN HÀNH GIẢ LẬP PHẦN CỨNG IOT TRÊN WOKWI

Mã nguồn nhúng và sơ đồ đấu nối được đặt trong thư mục `simulation_wokwi/`.

### 7.1. Bảng Đấu nối Phần cứng (Pinout Mapping)

| Thiết bị / Linh kiện | Chân ESP32 | Ghi chú vật lý |
| :--- | :--- | :--- |
| **HC-SR04 Trigger** | GPIO 5 | Xung kích phát siêu âm |
| **HC-SR04 Echo** | GPIO 18 | Đo thời gian sóng dội |
| **DHT22 Data** | GPIO 4 | Đo nhiệt độ & độ ẩm không khí |
| **LED Xanh (Safe)** | GPIO 25 | Sáng khi Nguy cơ = 0 (An toàn) |
| **LED Vàng (Warning)** | GPIO 26 | Sáng khi Nguy cơ = 1 (Báo động) |
| **LED Đỏ (High Risk)** | GPIO 27 | Chớp nháy khi Nguy cơ = 2 (Nguy hiểm) |
| **Còi Buzzer (+)** | GPIO 33 | Phát tín hiệu âm thanh cảnh báo ngập |
| **LCD 1602 SDA** | GPIO 21 | Giao tiếp I2C hiển thị mực nước |
| **LCD 1602 SCL** | GPIO 22 | Giao tiếp I2C xung nhịp |

### 7.2. Vận hành trên Wokwi Online
1. Truy cập [Wokwi ESP32 Simulator](https://wokwi.com/).
2. Chọn dự án ESP32 C++.
3. Dán nội dung `simulation_wokwi/sketch.ino` vào tab Code.
4. Dán nội dung `simulation_wokwi/diagram.json` vào tab Diagram.
5. Thêm các thư viện được liệt kê trong `simulation_wokwi/libraries.txt` (`LiquidCrystal I2C`, `DHT sensor library`).
6. Nhấn nút **Play (Start Simulation)** để quan sát phản hồi của mạch cảm biến.

---

## 8. KIỂM THỬ TỰ ĐỘNG & ĐẢM BẢO CHẤT LƯỢNG (QA)

Toàn bộ hệ thống được bảo vệ bởi bộ kiểm thử tự động toàn diện:

### 8.1. Chạy Tất cả Kiểm thử
```powershell
pytest -v
```
*(Yêu cầu kết quả: 54/54 passed 100%).*

### 8.2. Danh mục Bộ Kiểm thử
1. `tests/test_dataset_preparation.py`:
   - Xác thực cấu trúc 366 dòng liên tục của chuỗi thời gian.
   - Đảm bảo 100% không có ô trống rỗng (missing values) ở 9 đặc trưng.
   - Kiểm tra tính đơn điệu tăng dần của trục thời gian ($t$).
2. `tests/test_model_training.py`:
   - Kiểm tra định dạng lưu trữ file `.joblib`.
   - Kiểm tra tính tương thích vector đầu vào và shape ma trận dự báo.
3. `tests/test_iot_dashboard.py`:
   - Kiểm định cỗ máy trạng thái `iot_core_engine.py`.
   - Kiểm thử logic phân cấp rủi ro và các kịch bản thời tiết giả lập.
4. `tests/test_parsers.py`:
   - Kiểm thử thuật toán bóc tách tiếng Việt trên các mẫu câu thủy văn phức tạp.
5. `tests/test_mini_flood_api.py` & `tests/test_mini_flood_features.py`:
   - Xác thực authentication `X-Device-Key`, mã lỗi 401/422.
   - Chống trùng lặp dữ liệu (`device_id + sequence_no`).
   - Kiểm định cửa sổ trượt tính 8 đặc trưng và tỷ lệ dữ liệu thiếu.
6. `tests/test_e2e_iot_flow.py` (E2E 3 Kịch bản Thí nghiệm Thực tế):
   - **Kịch bản 1 (Bình thường):** Mưa nhỏ, mực nước thấp (< 15 cm) -> AI dự báo Mức 0, không có cảnh báo nào sinh ra.
   - **Kịch bản 2 (Mưa lớn & Nước dâng):** Mưa 45 mm/h, dâng > 3 cm/5ph -> Nâng mức lên Cảnh báo (Mức 1), tự động kích hoạt `escalation` alert và tạo `delivery_attempts`.
   - **Kịch bản 3 (Ngập nguy hiểm):** Mực nước 30 cm vượt ngưỡng 25 cm -> Kích hoạt Safety Rule Override Mức 2 tức thì từ bản ghi đầu tiên không cần qua warmup.
7. `tests/test_e2e_alert_delivery.py` (Kênh Cảnh báo & Vòng đời Sự cố):
   - Tính độc lập giữa Telegram và Email: Lỗi kết nối SMTP không ngăn cản việc gửi tin nhắn qua Telegram.
   - Cơ chế nhắc lại (`reminder`): Tự động gửi lại sau 30 phút nếu tình trạng nguy hiểm cấp 2 kéo dài.
   - Cơ chế phục hồi (`recovery`): Yêu cầu tối thiểu 2 chu kỳ an toàn liên tiếp trước khi phát thông báo hoàn lưu an toàn.
8. `tests/test_e2e_offline_buffer.py` (Đệm Ngoại tuyến & Kết nối lại):
   - Mô phỏng mất Wi-Fi, lưu đệm vào hàng đợi và tự động đẩy dồn (flush) khi có mạng trở lại.
   - Gắn cờ `stale_timestamp` và gán trạng thái `unknown` khi bản ghi bị trễ trên 10 phút.


---

## 9. XỬ LÝ SỰ CỐ THƯỜNG GẶP & KHÔI PHỤC HỆ THỐNG (TROUBLESHOOTING)

### Sự cố 1: "Chưa tìm thấy mô hình trong thư mục models"
* **Hiện tượng:** Khi chạy `simulate_ai_demo.py` hoặc Dashboard báo lỗi không tìm thấy file `.joblib`.
* **Khắc phục:** Chạy lại script huấn luyện một lần duy nhất:
  ```powershell
  python train_ai_model.py
  ```

### Sự cố 2: Lỗi xung đột cổng Streamlit (Port 8501 is already in use)
* **Hiện tượng:** Máy tính đã có một tiến trình Streamlit đang chạy nền.
* **Khắc phục:** Chỉ định một cổng mới khi khởi chạy:
  ```powershell
  streamlit run app_iot_dashboard.py --server.port 8502
  ```

### Sự cố 3: Không nhận được thông báo Telegram
* **Hiện tượng:** Bấm gửi cảnh báo nhưng điện thoại không có chuông/tin nhắn.
* **Khắc phục:**
  1. Kiểm tra lại chuỗi Token: Đảm bảo không bị dính khoảng trắng thừa ở đầu/cuối.
  2. Bắt buộc phải bấm `/start` nhắn tin riêng cho Bot trước để Bot có quyền gửi tin.
  3. Kiểm tra kết nối mạng Internet của máy tính.

### Sự cố 4: Reset bộ nhớ Lịch sử Cảm biến IoT
* **Hiện tượng:** File `iot_telemetry_history.json` bị phình to hoặc muốn xóa trắng dữ liệu thử nghiệm cũ để đo từ đầu.
* **Khắc phục:**
  Xóa file `iot_telemetry_history.json` (hệ thống sẽ tự động khởi tạo lại file mới khi Dashboard chạy):
  ```powershell
  Remove-Item -Path "iot_telemetry_history.json" -ErrorAction SilentlyContinue
  ```

---

*Hệ thống được phát triển với tinh thần khoa học thực nghiệm, hướng đến ứng dụng thực tiễn bảo vệ an toàn cho nhà trường và người dân thành phố Hội An.*
