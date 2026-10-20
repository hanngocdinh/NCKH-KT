# SỔ TAY KỊCH BẢN KIỂM THỬ THỦ CÔNG: TỪ WOKWI ĐẾN THIẾT BỊ IOT THỰC TẾ

Tài liệu này hướng dẫn chi tiết quy trình **kiểm thử bằng tay trên mô phỏng Wokwi**, đồng thời đối chiếu trực quan với **cách thức thực nghiệm trên phần cứng thật (ESP32 + Cảm biến)** khi triển khai tại hiện trường hoặc phòng thí nghiệm.

---

## I. Nguyên lý quy đổi giữa Wokwi và Mạch thật

Hệ thống trạm đo ngập mini sử dụng **nguyên lý đo khoảng cách từ trên đỉnh dọi xuống**:

```text
[ Cảm biến siêu âm gắn trên nắp ] (Độ cao gắn cố định = 40 cm)
      │
      ▼ (Khoảng cách đo được d)
 ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  Mặt nước
      ▲
      │ (Mực nước ngập h = 40 - d)
[ Đáy hố ga / Thùng nước ]
```

* **Công thức cốt lõi:**
  $$\text{Mực nước thực tế (cm)} = 40 - \text{Khoảng cách đo được (cm)}$$
  *(Nếu khoảng cách đo được $\ge 40\text{ cm}$, mực nước được tính là $0\text{ cm}$ - cạn đáy).*

### Bảng đối chiếu cấu hình phần cứng

| Thành phần | Trên Wokwi (Mô phỏng) | Trên thiết bị IoT thật (Hiện trường) |
|---|---|---|
| **Cảm biến mực nước** | Kéo thanh trượt `distance` trên linh kiện `ultrasonic_water` (HC-SR04) | Cảm biến siêu âm chống nước (JSN-SR04T) gắn cố định trên miệng thùng/hố ga. Mực nước dâng làm giảm khoảng cách tới mặt nước. |
| **Cảm biến mưa** | Vặn núm xoay biến trở `rain_pot` (0 - 120 mm/h) | Cảm biến đo mưa gầu lật (tipping bucket) hoặc cảm biến quang học RS485. Kiểm thử bằng cách bơm nước/nhỏ giọt vào phễu. |
| **Đường truyền dữ liệu** | Gửi qua Wi-Fi ảo của Wokwi về máy chủ nội bộ | ESP32 kết nối Wi-Fi thực tế (hoặc 4G/LTE), gửi bản ghi JSON HTTP POST về máy chủ Backend. |

---

## II. Chuẩn bị môi trường trước khi kiểm thử

1. **Khởi động Backend FastAPI:**
   ```powershell
   python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
   ```
   *Kiểm tra sức khỏe hệ thống:* `http://localhost:8000/api/v1/health` (phải trả về `model_ready: true`).

2. **Khởi động Dashboard giám sát:**
   ```powershell
   streamlit run app_mini_flood_dashboard.py
   ```
   *Truy cập giao diện:* [http://localhost:8501](http://localhost:8501).

3. **Mở trình mô phỏng Wokwi:**
   Mở file [diagram.json](file:///d:/Projects/tool-craw/firmware/esp32_http/diagram.json) trong VS Code hoặc trên Wokwi.

---

## III. Kịch bản 5 pha kiểm thử chi tiết

### PHA 1: Khởi động hệ thống & Warm-up (3 chu kỳ đầu)

* **Mục tiêu:** Kiểm tra cơ chế Warm-up. Hệ thống AI cần tối thiểu **3 bản ghi lịch sử liên tục** để tính toán cửa sổ đặc trưng ($\le 5$ phút) trước khi đưa ra dự báo rủi ro đầu tiên.
* **Thao tác:**
  * **Trên Wokwi:** Nhấp vào `ultrasonic_water`, đặt khoảng cách = **35 cm** (nước đáy chỉ 5 cm). Núm mưa = **0**. Bấm nút Chạy (Play tam giác xanh).
  * **Trên thiết bị thật:** Cố định cảm biến cách đáy xô 35 cm (chưa đổ nước). Bật nguồn ESP32.
* **Kỳ vọng:**
  * **Chu kỳ 1 và 2:**
    - Terminal Backend: Hiện `POST /api/v1/telemetry 200 OK`.
    - Dashboard: Ô dự báo 15m và 30m hiển thị **"Đang khởi động"**, chưa tính toán rủi ro để tránh suy diễn khi thiếu dữ liệu.
  * **Đến chu kỳ 3:**
    - Dashboard lập tức nhảy số: **Dự báo 15 phút: An toàn**, **Dự báo 30 phút: An toàn** (Độ tin cậy > 90%).

---

### PHA 2: Trạng thái Bình thường (Mưa nhỏ, nước không ngập)

* **Mục tiêu:** Kiểm tra phản ứng khi thời tiết bình thường, đảm bảo hệ thống không phát sinh cảnh báo ảo (False Positive).
* **Thao tác:**
  * **Trên Wokwi:** Kéo khoảng cách nước dao động trong khoảng **33 - 36 cm** (mực nước 4 - 7 cm). Vặn nhẹ núm mưa lên mức 5 - 10 mm/h.
  * **Trên thiết bị thật:** Nhỏ vài giọt nước mô phỏng mưa lất phất, mực nước trong thùng giữ thấp dưới đáy (< 10 cm).
* **Kỳ vọng:**
  * Dashboard hiển thị mực nước ~ 5 - 7 cm, mưa ~ 5 - 10 mm/h.
  * Cả 2 mốc 15 phút và 30 phút duy trì màu xanh **"An toàn"**.
  * Không có tin nhắn/email cảnh báo nào được gửi đi.

---

### PHA 3: Mưa dồn dập & Nước dâng - Kích hoạt Cảnh báo (Mức 1)

* **Mục tiêu:** Kiểm nghiệm khả năng **dự báo sớm của mô hình AI** khi nước chưa ngập đến mức nguy hiểm nhưng tốc độ dâng và lượng mưa cho thấy nguy cơ ngập sắp xảy ra.
* **Thao tác:**
  * **Trên Wokwi:**
    1. Vặn núm biến trở mưa lên **35 - 45 mm/h** (mô phỏng mưa rào lớn).
    2. Sau 1 chu kỳ, kéo thanh khoảng cách nước từ 35 cm xuống **23 cm** (tương đương nước dâng nhanh lên **17 cm**, vượt mốc cảnh báo 15 cm).
  * **Trên thiết bị thật:**
    1. Bơm nước liên tục vào phễu cảm biến mưa.
    2. Đổ thêm nước vào thùng sao cho mực nước tăng vọt lên mức 16 - 18 cm.
* **Kỳ vọng:**
  * AI tính toán thấy `water_rise_2m_cm` tăng mạnh và `rain_sum_5m` tích lũy cao.
  * Dashboard chuyển trạng thái sang màu vàng: **Dự báo 15 phút: Cảnh báo (Mức 1)**.
  * Dashboard hiển thị dòng cảnh báo: *"Nguyên nhân chính: Mưa lớn và nước đang dâng nhanh"*.
  * Hệ thống đẩy tin cảnh báo mức 1 ra Console / Telegram.

---

### PHA 4: Ngập khẩn cấp - Ghi đè an toàn (Safety Rule Override - Mức 2)

* **Mục tiêu:** Kiểm tra cơ chế an toàn kép: Khi mực nước thực tế chạm ngưỡng nguy hiểm $\ge 25\text{ cm}$, hệ thống **không phụ thuộc vào độ trễ của model xác suất** mà tự động cưỡng chế chuyển sang mức Nguy hiểm khẩn cấp ngay lập tức.
* **Thao tác:**
  * **Trên Wokwi:** Kéo nhanh thanh khoảng cách cảm biến nước xuống **10 cm** (mực nước = 40 - 10 = **30 cm**, vượt ngưỡng nguy hiểm 25 cm).
  * **Trên thiết bị thật:** Đổ nước đầy thùng hoặc đưa một vật cản phẳng (tấm bìa) chắn cách cảm biến 10 cm.
* **Kỳ vọng:**
  * Dashboard chuyển sang màu đỏ: **Dự báo 15 phút: Nguy hiểm**, **Dự báo 30 phút: Nguy hiểm**.
  * Trong mục "Thông tin kỹ thuật", `latest_model_version` được gắn thêm đuôi: `...-v1+safety-rule`.
  * Chuông/còi hoặc tin nhắn khẩn cấp được kích hoạt ngay chu kỳ này.

---

### PHA 5: Tạnh mưa, nước rút & Phục hồi an toàn (Recovery Hysteresis)

* **Mục tiêu:** Kiểm tra cơ chế chống chập chờn (Anti-flapping). Sóng nước trong cống thường dao động dập dềnh; nếu vừa xuống dưới 15 cm mà báo an toàn ngay thì còi báo động sẽ bật/tắt liên tục. Hệ thống bắt buộc phải duy trì **2 chu kỳ an toàn liên tiếp** mới thông báo an toàn.
* **Thao tác:**
  * **Trên Wokwi:** Vặn mưa về 0 mm/h. Kéo khoảng cách nước về lại **35 cm** (nước rút còn 5 cm).
  * **Trên thiết bị thật:** Rút van xả đáy thùng để nước chảy hết ra ngoài.
* **Kỳ vọng:**
  * **Chu kỳ an toàn thứ 1:** Mực nước đo được là 5 cm nhưng hệ thống vẫn giữ trạng thái cảnh giác, chưa phát đi thông báo an toàn.
  * **Chu kỳ an toàn thứ 2 liên tiếp:** Hệ thống chính thức xác nhận bình thường hóa, phát thông báo: *"TRẠNG THÁI ĐÃ AN TOÀN - Nước đã rút dưới ngưỡng cảnh báo"*.

---

## IV. Kiểm thử sự cố thực địa dành riêng cho Thiết bị IoT thật

Trên thực tế, trạm đo ngoài trời rất dễ bị **mất sóng Wi-Fi/4G khi mưa bão**. Firmware [mini_flood_station.ino](file:///d:/Projects/tool-craw/firmware/esp32_http/mini_flood_station.ino) đã được tích hợp bộ đệm vòng (`pending queue` 100 bản ghi).

* **Quy trình kiểm thử:**
  1. Khi trạm đang chạy bình thường, ngắt Wi-Fi máy tính hoặc rút dây phát mạng Access Point.
  2. Mạch ESP32 sẽ nhấp nháy đèn báo mất kết nối nhưng **vẫn tiếp tục lấy mẫu đo đều đặn mỗi chu kỳ** và lưu trữ tạm thời vào RAM/Flash (với số thứ tự `sequence_no` tăng dần).
  3. Bật lại Wi-Fi: ESP32 phát hiện mạng trở lại và lập tức gửi xả toàn bộ các bản ghi bị nghẽn (FIFO) lên Backend.
  4. Backend nhận đủ dữ liệu bù, cơ chế deduplication ngăn trùng lặp, đồ thị trên Dashboard tự động vẽ liền mạch không bị đứt đoạn.

---

## V. Bảng ghi nhận kết quả kiểm thử (Test Log Sheet)

| Bước | Hành động trên cảm biến | Mực nước đo | Vũ lượng mưa | Trạng thái mong đợi trên Dashboard | Kết quả |
|:---:|---|:---:|:---:|---|:---:|
| **1** | Mới bật nguồn (chờ 3 chu kỳ) | 5 cm | 0 mm/h | Đang khởi động $\rightarrow$ An toàn | ĐẠT [ ] |
| **2** | Giữ nước đáy, mưa nhỏ | 5 - 8 cm | 5 mm/h | An toàn (Màu xanh) | ĐẠT [ ] |
| **3** | Tăng mưa, dâng nước lên 17 cm | 17 cm | 40 mm/h | Cảnh báo (Màu vàng) | ĐẠT [ ] |
| **4** | Nước dâng vượt 28 cm | 28 cm | 80 mm/h | Nguy hiểm + Safety Rule (Màu đỏ) | ĐẠT [ ] |
| **5** | Rút nước (chu kỳ 1) | 5 cm | 0 mm/h | Chờ xác nhận chu kỳ 2 | ĐẠT [ ] |
| **6** | Rút nước (chu kỳ 2 liên tiếp) | 5 cm | 0 mm/h | Thông báo "Đã an toàn" | ĐẠT [ ] |
| **7** | Ngắt Wi-Fi rồi bật lại | Tùy biến | Tùy biến | Nhận đủ bản ghi đệm, không trùng lặp | ĐẠT [ ] |
