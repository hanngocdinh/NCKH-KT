# HƯỚNG DẪN THIẾT KẾ & VẬN HÀNH DEMO GIẢ LẬP HỆ THỐNG AI CẢNH BÁO NGẬP HỘI AN

**Dự án**: AI + IoT Dự báo Nguy cơ Ngập lụt Cục bộ tại TP. Hội An (THPT Trần Quý Cáp)  
**Công cụ giả lập thực thi**: [`simulate_ai_demo.py`](file:///d:/Projects/tool-craw/simulate_ai_demo.py)  
**Mã nguồn vi điều khiển ESP32**: [`simulation_wokwi/sketch.ino`](file:///d:/Projects/tool-craw/simulation_wokwi/sketch.ino)  
**Tập dữ liệu chuẩn bị**: [`hoian_flood_ai_dataset_prepared.csv`](file:///d:/Projects/tool-craw/hoian_flood_ai_dataset_prepared.csv)  

---

## MỤC LỤC
1. [Kiến trúc Tổng thể Hệ thống Giả lập](#1-kiến-trúc-tổng-thể-hệ-thống-giả-lập)
2. [Chi tiết Vector 9 Đặc trưng Cung cấp cho Model](#2-chi-tiết-vector-9-đặc-trưng-cung-cấp-cho-model)
3. [Nguồn Cung cấp Giá trị: Phần cứng vs Đám mây](#3-nguồn-cung-cấp-giá-trị-phần-cứng-vs-đám-mây)
4. [3 Kịch bản Giả lập Chuẩn để Thuyết trình Demo](#4-3-kịch-bản-giả-lập-chuẩn-để-thuyết-trình-demo)
5. [Quy trình Vận hành Demo Từng Bước](#5-quy-trình-vận-hành-demo-từng-bước)
6. [Tích hợp với Mạch Giả lập Wokwi ESP32](#6-tích-hợp-với-mạch-giả-lập-wokwi-esp32)

---

## 1. Kiến trúc Tổng thể Hệ thống Giả lập

```
                      HỆ THỐNG CẢNH BÁO SỚM THỜI GIAN THỰC (DEMO PIPELINE)
                      
   [ 1. NGUỒN DỮ LIỆU ĐẦU VÀO ]
   ┌────────────────────────────────┐         ┌────────────────────────────────┐
   │    TRẠM ĐO IoT TẠI TRƯỜNG      │         │     DỊCH VỤ DỮ LIỆU ĐÁM MÂY    │
   │  - Cảm biến siêu âm HC-SR04    │         │  - Mưa tích lũy 3 ngày / 7 ngày│
   │  - Cảm biến mưa RS485 / Pot    │         │  - Lưu lượng GloFAS thượng nguồn│
   └───────────────┬────────────────┘         └───────────────┬────────────────┘
                   │                                          │
                   └────────────────────┬─────────────────────┘
                                        ▼
   [ 2. BỘ XỬ LÝ TIỀN XỬ LÝ & TẠO ĐẶC TRƯNG ]
   ┌───────────────────────────────────────────────────────────────────────────┐
   │ Tính toán vi phân: Δh (tốc độ dâng cm/ngày) | ΔQ (gia tốc dồn lũ m³/s)    │
   │ Đóng gói thành Vector 9 đặc trưng chuẩn: input_df [1 x 9]                 │
   └────────────────────────────────────┬──────────────────────────────────────┘
                                        ▼
   [ 3. ĐỘNG CƠ SUY LUẬN AI (INFERENCE ENGINE) ]
   ┌───────────────────────────────────────────────────────────────────────────┐
   │ Mô hình: Random Forest (Balanced) / Logistic Regression (StandardScaler)  │
   │ Dự báo: Nhãn nguy cơ ngày mai (t+1) + Phân bố xác suất tin cậy (Confidence)│
   └────────────────────────────────────┬──────────────────────────────────────┘
                                        ▼
   [ 4. PHẢN HỒI THIẾT BỊ & HÀNH ĐỘNG ]
   ┌────────────────────────────────────┴──────────────────────────────────────┐
   │                                                                           │
   ▼                                                                           ▼
[ THIẾT BỊ PHẦN CỨNG WOKWI ]                               [ HÀNH ĐỘNG NHÀ TRƯỜNG ]
* Lớp 0: LED XANH sáng, còi tắt                             * Dạy học bình thường
* Lớp 1: LED VÀNG sáng, còi tắt                             * Kê cao bàn ghế, nạo vét cống
* Lớp 2: LED ĐỎ chớp nháy + CÒI HÚ LIÊN TỤC                 * THÔNG BÁO CHO HỌC SINH NGHỈ HỌC
```

---

## 2. Chi tiết Vector 9 Đặc trưng Cung cấp cho Model

Khi gọi mô hình AI suy luận, bắt buộc phải truyền vào đúng bảng 9 thuộc tính sau:

| STT | Tên đặc trưng (`feature_name`) | Đơn vị | Dải giá trị thực tế | Mô tả chức năng |
| :---: | :--- | :---: | :---: | :--- |
| **1** | `rain_daily_mm` | mm | $0.0 - 180.0$ | Lượng mưa đo được trong 24 giờ qua |
| **2** | `rain_max_hourly_mmh` | mm/h | $0.0 - 40.0$ | Cường độ mưa giờ cực đại (phát hiện mưa giông cực đoan) |
| **3** | `rain_3d_accum_mm` | mm | $0.0 - 300.0$ | Mưa tích lũy 3 ngày (thước đo độ bão hòa đất thượng nguồn) |
| **4** | `rain_7d_accum_mm` | mm | $0.0 - 350.0$ | Mưa tích lũy 7 ngày (đánh giá nguy cơ ngập úng kéo dài) |
| **5** | `water_level_cm` | cm | $30.0 - 500.0$ | Mực nước thực đo tại trạm / hố ga trường học |
| **6** | `delta_water_level_cm` | cm/ngày | $-400.0 - +370.0$ | Tốc độ biến thiên mực nước ($\Delta h = h_t - h_{t-1}$) |
| **7** | `river_discharge_m3s` | m³/s | $140.0 - 7,500.0$ | Lưu lượng sông Thu Bồn từ mô hình GloFAS |
| **8** | `discharge_3d_mean_m3s`| m³/s | $140.0 - 5,500.0$ | Lưu lượng dòng chảy trung bình 3 ngày qua |
| **9** | `delta_discharge_m3s` | m³/s | $-2,500.0 - +2,000.0$| Xung kích biến thiên xả lũ thượng nguồn ($\Delta Q = Q_t - Q_{t-1}$) |

---

## 3. Nguồn Cung cấp Giá trị: Phần cứng vs Đám mây

Trong một hệ thống triển khai thực tế cũng như buổi diễn tập demo:

```
                ┌──────────────────────────────────────────────┐
                │        CƠ CHẾ PHỐI HỢP DỮ LIỆU HYBRID        │
                └──────────────────────────────────────────────┘
                               │                │
            ┌──────────────────┘                └──────────────────┐
            ▼                                                      ▼
  [ TRẠM CẢM BIẾN IoT ]                                  [ MÁY CHỦ CLOUD ]
  - Đo mực nước tại chỗ                                  - Tải mưa tích lũy vệ tinh
  - Đo mưa tức thời hố ga                                - Tải lưu lượng xả lũ hồ chứa
            │                                                      │
            └──────────────────────┬───────────────────────────────┘
                                   ▼
                         [ BỘ ĐỆM ĐỒNG BỘ ]
               Ghép thành 1 hàng dữ liệu duy nhất
                    Cung cấp cho Model AI
```

### 1. Dữ liệu từ Mạch cảm biến IoT tại trường (Cung cấp các biến $5, 6, 1, 2$):
* **Mực nước (`water_level_cm`)**: Cảm biến siêu âm gắn trên nắp hố ga/cống trường học chiếu tia xuống mặt nước.
  $$\text{water\_level\_cm} = \text{Chiều cao đặt cảm biến} - \text{Khoảng cách đo}$$
* **Tốc độ dâng nước (`delta_water_level_cm`)**: Bộ đệm nhớ lưu lại mực nước 24h trước và tính hiệu số.
* **Cường độ mưa (`rain_max_hourly_mmh`)**: Cảm biến mưa lật chao (Tipping Bucket) đếm số xung trong 1 giờ.

### 2. Dữ liệu từ Đám mây / API dự báo (Cung cấp các biến $3, 4, 7, 8, 9$):
* **Mưa tích lũy 3 ngày & 7 ngày**: Máy chủ tự động cộng dồn lượng mưa từ API Open-Meteo của tọa độ Hội An.
* **Lưu lượng sông GloFAS & $\Delta Q$**: Máy chủ tự động cập nhật số liệu dự báo xả lũ từ API Copernicus Flood Service và thông báo xả tràn của các hồ thủy điện (Sông Tranh 2, Đak Mi 4).

---

## 4. 3 Kịch bản Giả lập Chuẩn để Thuyết trình Demo

Khi trình diễn trước Hội đồng khoa học / Ban giám khảo, bạn hãy nạp tuần tự 3 kịch bản:

### Bảng Ma trận Tham số 3 Kịch bản:

| Tham số | Kịch bản 1: Mùa cạn | Kịch bản 2: Mưa lớn chuyển tiếp | Kịch bản 3: Bão lớn & Xả lũ |
| :--- | :---: | :---: | :---: |
| `rain_daily_mm` | $0.0\text{ mm}$ | $32.6\text{ mm}$ | **$140.0\text{ mm}$** |
| `rain_max_hourly_mmh` | $0.0\text{ mm/h}$ | $4.4\text{ mm/h}$ | **$28.0\text{ mm/h}$** |
| `rain_3d_accum_mm` | $2.0\text{ mm}$ | $36.3\text{ mm}$ | **$270.0\text{ mm}$** |
| `rain_7d_accum_mm` | $12.0\text{ mm}$ | $70.2\text{ mm}$ | **$320.0\text{ mm}$** |
| `water_level_cm` | $60.0\text{ cm}$ | $85.0\text{ cm}$ | **$280.0\text{ cm}$** |
| `delta_water_level_cm` | $+1.0\text{ cm}$ | $-20.0\text{ cm}$ | **$+95.0\text{ cm}$** |
| `river_discharge_m3s` | $220.0\text{ m}^3/\text{s}$ | $520.0\text{ m}^3/\text{s}$ | **$3,400.0\text{ m}^3/\text{s}$** |
| `discharge_3d_mean_m3s`| $235.0\text{ m}^3/\text{s}$ | $915.0\text{ m}^3/\text{s}$ | **$2,200.0\text{ m}^3/\text{s}$** |
| `delta_discharge_m3s` | $-5.0\text{ m}^3/\text{s}$ | $-150.0\text{ m}^3/\text{s}$ | **$+1,600.0\text{ m}^3/\text{s}$** |
| **DỰ BÁO AI (T+1)** | **Lớp 0: AN TOÀN** | **Lớp 1: CÓ NGUY CƠ** | **Lớp 2: LŨ NGUY CƠ CAO** |
| **Xác suất tin cậy** | **$100.0\%$ An toàn** | **$72.5\%$ Có nguy cơ** | **$75.0\%$ Lũ nguy cơ cao** |
| **Tín hiệu LED** | **XANH** | **VÀNG** | **ĐỎ (NHẤP NHÁY)** |
| **Còi Buzzer** | Tắt | Tắt | **HÚ BÁO ĐỘNG LIÊN TỤC** |
| **Hành động nhà trường** | Dạy học bình thường | Kê cao đồ đạc tầng 1 | **CHO HỌC SINH NGHỈ HỌC** |

---

## 5. Quy trình Vận hành Demo Từng Bước

### Bước 1: Khởi động công cụ giả lập trên máy tính
Mở PowerShell tại thư mục dự án và chạy:
```powershell
python simulate_ai_demo.py
```

### Bước 2: Quan sát kết quả in ra màn hình
Mô hình sẽ nạp file `model_lead24h_rf.joblib` và in ra kết quả cho từng kịch bản:
* Các giá trị đầu vào vật lý
* Nhãn dự báo rủi ro cho ngày mai
* Xác suất tin cậy phần trăm
* Trạng thái thiết bị phản hồi
* Hướng dẫn chỉ đạo cụ thể cho Ban Giám hiệu nhà trường.

### Bước 3: Thay đổi thông số kiểm thử tự do (Custom Scenario)
Bạn có thể mở tệp [`simulate_ai_demo.py`](file:///d:/Projects/tool-craw/simulate_ai_demo.py), sửa các giá trị trong hàm `predict_and_explain()` để kiểm tra độ nhạy của mô hình với bất kỳ bộ số liệu thời tiết nào.

---

## 6. Tích hợp với Mạch Giả lập Wokwi ESP32

Trong thư mục [`simulation_wokwi/`](file:///d:/Projects/tool-craw/simulation_wokwi/), hệ thống đã có sẵn:
1. `diagram.json`: Sơ đồ đấu nối chân ESP32 với cảm biến HC-SR04, chiết áp xoay Potentiometer giả lập mưa, 3 LED cảnh báo, còi buzzer và màn hình LCD 1602 I2C.
2. `sketch.ino`: Mã nhúng C++ điều khiển thiết bị, xuất chuỗi JSON qua cổng Serial:

```json
{"rain_accum_mm": 67.5, "rain_rate_mmh": 27.0, "water_level_cm": 285.0, "delta_h_cm": 95.0, "risk_level": 2, "status": "NGUY CO CAO"}
```

Khi kết nối cổng Serial giữa máy tính và ESP32 (hoặc qua giao thức Wokwi Gateway), máy tính sẽ đọc gói tin JSON này, nạp vào mô hình AI và gửi trả lại lệnh điều khiển bật LED/Còi tương ứng với cấp dự báo sớm 24 giờ.
