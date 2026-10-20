# Kế Hoạch Vận Hành: Thu Thập Dữ Liệu Thật, Huấn Luyện AI và Cảnh Báo Telegram

> **MÃ TÀI LIỆU:** SOP-MF-01  
> **PHIÊN BẢN:** 1.0.0 (Dành cho Mini Flood AI V1)  
> **PHẠM VI:** Mô hình thử nghiệm vật lý thu nhỏ (hố ga / rãnh thoát nước trường học)  
> **DISCLAIMER BẮT BUỘC:** `[MÔ PHỎNG THỬ NGHIỆM]` – Kết quả phục vụ kiểm chứng nguyên lý giải pháp AI–IoT cục bộ, không dùng để dự báo vận hành thiên tai thực tế cho Hội An hay các lưu vực sông lớn.

---

## Phần I: Bối Cảnh, Mục Tiêu và Phạm Vi Áp Dụng

### 1.1. Bối cảnh
Trước đây, hệ thống Mini Flood AI sử dụng tập dữ liệu giả lập (`training_data_synthetic.csv`) để kiểm chứng luồng hoạt động từ nhận telemetry, trích xuất đặc trưng đến suy luận model và kích hoạt thông báo. Nhằm chuẩn hóa hệ thống sang giai đoạn chạy thử nghiệm vật lý thật, tài liệu này quy định chi tiết:
1. Quy trình thiết lập mô hình vật lý và thu thập chuỗi thời gian thực nghiệm qua vi điều khiển ESP32.
2. Quy trình trích xuất dữ liệu thực tế, làm sạch, tính toán đặc trưng và huấn luyện lại 2 mô hình Logistic Regression (15 phút và 30 phút).
3. Quy trình cấu hình, kiểm thử và vận hành cảnh báo tự động tức thời qua Telegram Bot.

### 1.2. Mục tiêu kỹ thuật
- **Đạt độ phủ kịch bản:** Thu thập tối thiểu 3 lần chạy hợp lệ cho mỗi kịch bản rủi ro (`normal`, `warning`, `danger`), mỗi lần chạy kéo dài $\ge 46$ phút (đáp ứng 15 phút cửa sổ lịch sử và 30 phút dự báo tương lai).
- **Chất lượng mô hình AI:** Mô hình huấn luyện trên dữ liệu thật phải vượt qua quy tắc ngưỡng cơ sở (Baseline Rule):
  - $\text{Macro-F1}_{\text{AI}} > \text{Macro-F1}_{\text{Baseline}}$ trên cả 2 khung dự báo (15m và 30m).
  - $\text{Recall}_{\text{Danger (AI)}} \ge \text{Recall}_{\text{Danger (Baseline)}}$ (không bỏ sót tình huống ngập sâu nguy hiểm).
- **Độ tin cậy cảnh báo Telegram:**
  - Gửi tin nhắn leo thang cấp độ (Escalation) trong vòng $\le 15$ giây từ khi phát hiện nguy cơ.
  - Tự động gửi tin nhắc lại (Reminder) mỗi 30 phút nếu tình trạng nguy hiểm duy trì liên tục.
  - Tự động gửi thông báo an toàn (Recovery) khi mực nước rút và hệ thống ghi nhận 2 chu kỳ đo an toàn liên tiếp.

---

## Phần II: Chuẩn Hóa Thiết Lập Mô Hình Vật Lý & Trạm Đo ESP32

```
       [ Cảm biến Mưa ]       [ Cảm biến Siêu âm HC-SR04 ]
              │                              │
              └──────────────┬───────────────┘
                             │ (GPIO)
                             ▼
                    ┌─────────────────┐
                    │   ESP32 DevKit  │ ◄─── Nguồn 5V/2A ổn định
                    └────────┬────────┘
                             │ Wi-Fi (HTTP POST mỗi 60s)
                             ▼
                    ┌─────────────────┐
                    │ Backend FastAPI │ (Laptop / Server cục bộ)
                    └─────────────────┘
```

### 2.1. Thông số mô hình vật lý
- **Kết cấu buồng đo:** Thùng chứa hoặc mô hình rãnh nước/hố ga vật lý có chiều sâu tổng thể $40\text{ cm}$.
- **Mức cảnh báo quy chuẩn:**
  - **Mức Bình thường (Safe - Lớp 0):** Mực nước $< 15.0\text{ cm}$.
  - **Mức Có nguy cơ (Warning - Lớp 1):** $15.0\text{ cm} \le \text{Mực nước} < 25.0\text{ cm}$.
  - **Mức Nguy hiểm cao (Danger - Lớp 2):** $\text{Mực nước} \ge 25.0\text{ cm}$.

### 2.2. Bố trí và hiệu chuẩn cảm biến
1. **Cảm biến siêu âm (HC-SR04 / JSN-SR04T):**
   - Vị trí lắp: Đặt cố định ở miệng trên của mô hình, hướng thẳng góc vuông xuống đáy hố.
   - Khoảng cách từ cảm biến tới đáy hố khi cạn nước: $H_{\text{total}} = 40.0\text{ cm}$.
   - Công thức tính mực nước hiện tại:
     $$\text{water\_level\_cm} = H_{\text{total}} - \text{khoảng\_cách\_đo\_được\_cm}$$
   - Yêu cầu lọc nhiễu: Firmware lấy trung vị (median) của 5 lần đọc liên tiếp trong 2 giây trước khi gửi.
2. **Cảm biến mưa (Module cảm biến giọt mưa hoặc Tipping bucket):**
   - Đặt ở vị trí tiếp xúc tự do, kết nối chân Analog (ADC) và Digital (ngắt xung nếu là gầu lật).
   - Tốc độ mưa tức thời: $\text{rain\_rate\_mmh}$ (mm/h).
   - Lượng mưa trong chu kỳ 1 phút: $\text{rain\_interval\_mm}$ (mm).

### 2.3. Cấu hình Firmware ESP32
Mở file [`firmware/esp32_http/mini_flood_station.ino`](file:///d:/Projects/tool-craw/firmware/esp32_http/mini_flood_station.ino) và cập nhật thông số kết nối:

```cpp
const char* WIFI_SSID     = "Ten_Wifi_Thuc_Nghiem";
const char* WIFI_PASSWORD = "Mat_Khau_Wifi";
const char* API_URL       = "http://192.168.1.100:8000/api/v1/telemetry"; // IP Laptop chạy backend
const char* DEVICE_KEY    = "chuoi-bi-mat-x-device-key-da-tao";
const char* DEVICE_ID     = "mini-flood-station-01";
const int   INTERVAL_MS   = 60000; // Chu kỳ đo chuẩn 60 giây (1 phút)
```

> [!IMPORTANT]
> **Nguyên tắc thiết kế ESP32 trong V1:** ESP32 chỉ thực hiện chức năng thu thập và truyền telemetry một chiều lên Backend. ESP32 không nhận lệnh điều khiển hay nhận diện cấp nguy cơ từ backend.


---

## Phần III: Giao Thức Thu Thập Dữ Liệu Thực Nghiệm (Data Collection Protocol)

### 3.1. Ma trận kịch bản thực nghiệm (Experiment Matrix)

Hệ thống yêu cầu dữ liệu chuỗi thời gian liên tục đại diện cho cả 3 tình thái thủy văn để tránh mất cân bằng lớp (class imbalance) và đảm bảo cửa sổ trượt hợp lệ.

| Kịch bản | Mã kịch bản | Số phiên tối thiểu | Thời lượng / phiên | Mực nước mục tiêu | Cường độ mưa mô phỏng |
|---|---|---|---|---|---|
| **Bình thường (Normal)** | `normal` | 3 phiên (`exp-real-n01` .. `n03`) | $\ge 46$ phút | $2.0 - 12.0\text{ cm}$ | $0.0 - 5.0\text{ mm/h}$ |
| **Có nguy cơ (Warning)** | `warning` | 3 phiên (`exp-real-w01` .. `w03`) | $\ge 46$ phút | $15.0 - 24.5\text{ cm}$ | $10.0 - 30.0\text{ mm/h}$ |
| **Nguy hiểm cao (Danger)**| `danger` | 3 phiên (`exp-real-d01` .. `d03`) | $\ge 46$ phút | $25.0 - 38.0\text{ cm}$ | $40.0 - 80.0\text{ mm/h}$ |

> [!NOTE]
> **Giải thích yêu cầu 46 phút:** Để tạo ra một mẫu dữ liệu học máy đầy đủ nhãn:
> - Cần **15 phút** dữ liệu quá khứ để làm ấm bộ lọc trượt (tính `rain_sum_5m`, `water_rise_2m_cm`, v.v.).
> - Cần **30 phút** dữ liệu kế tiếp để gán nhãn tương lai cực đại (`target_15m` và `target_30m`).
> - Do đó, một phiên đo ngắn hơn 46 phút sẽ không thể tạo ra bất kỳ mẫu huấn luyện có nhãn 30 phút nào.

### 3.2. Quy trình điều khiển phiên đo qua API

Trước khi bắt đầu cấp nước hoặc tạo mưa cho mô hình, kỹ thuật viên thực hiện các bước sau:

#### Bước 1: Khởi động phiên đo (Start Experiment)
Gửi request HTTP POST tới API Backend kèm theo định danh phiên và loại kịch bản:

```powershell
$headers = @{
    "Content-Type" = "application/json"
    "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY
}
$body = @{
    "device_id"     = "mini-flood-station-01"
    "experiment_id" = "exp-real-n01"
    "scenario"      = "normal"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/experiments/start" `
    -Method Post `
    -Headers $headers `
    -Body $body
```

Backend sẽ đánh dấu mọi gói tin telemetry tiếp theo từ trạm `mini-flood-station-01` gắn kèm `experiment_id = exp-real-n01`.

#### Bước 2: Quan sát quá trình đo
- Theo dõi trên Dashboard Streamlit (`http://localhost:8501`) hoặc lệnh lắng nghe SSE:
  ```powershell
  python listen_realtime_stream.py --device-id mini-flood-station-01
  ```
- Duy trì điều kiện thực nghiệm trong suốt ít nhất 46 phút.

#### Bước 3: Dừng phiên đo (Stop Experiment)
Sau khi hoàn thành thời lượng thí nghiệm:

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/experiments/stop?device_id=mini-flood-station-01" `
    -Method Post `
    -Headers $headers
```

### 3.3. Trích xuất dữ liệu thực nghiệm ra CSV (Export Dataset)
Sau khi đã hoàn thành tối thiểu 9 phiên đo ($3 \times 3$), thực hiện xuất toàn bộ dữ liệu telemetry thực tế ra file CSV chuẩn:

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
Invoke-WebRequest `
    -Uri "http://localhost:8000/api/v1/experiments/export.csv?device_id=mini-flood-station-01" `
    -Headers $headers `
    -OutFile "telemetry_experiments_real.csv"
```

#### Tiêu chuẩn kiểm tra tính hợp lệ của CSV xuất ra:
- **Cấu trúc cột:** Phải chứa đủ 8 cột bắt buộc:
  `experiment_id`, `device_id`, `sequence_no`, `timestamp`, `rain_interval_mm`, `rain_rate_mmh`, `water_level_cm`, `quality_flags`.
- **Độ liên tục:** Kiểm tra số thứ tự `sequence_no` liên tục, không bị nhảy bước do mất gói mạng.
- **Giá trị vật lý:** `water_level_cm` nằm trong dải $0.0 - 40.0\text{ cm}$; `rain_rate_mmh` $\ge 0.0$.


---

## Phần IV: Quy Trình Huấn Luyện AI Trên Dữ Liệu Thật & Nghiệm Thu Chất Lượng

### 4.1. Cấu trúc đặc trưng và gán nhãn chuỗi thời gian

Mô hình AI chỉ sử dụng 4 đặc trưng cốt lõi mang ý nghĩa thủy lực trực tiếp, không phụ thuộc vào các biến suy diễn phức tạp:

| Đặc trưng | Đơn vị | Ý nghĩa vật lý | Cách tính từ chuỗi đo 1 phút |
|---|---|---|---|
| `rain_rate_mmh` | mm/h | Cường độ mưa hiện tại | Đo trực tiếp từ cảm biến mưa tại thời điểm $t$ |
| `rain_sum_5m` | mm | Lượng mưa tích lũy 5 phút | $\sum_{i=0}^{4} \text{rain\_interval\_mm}(t - i)$ |
| `water_level_cm` | cm | Mực nước hiện tại | Đo trực tiếp từ cảm biến siêu âm tại thời điểm $t$ |
| `water_rise_2m_cm`| cm | Tốc độ dâng nước trong 2 phút | $\text{water\_level}(t) - \text{water\_level}(t - 2)$ |

#### Cơ chế gán nhãn dự báo tương lai (Lead horizons 15m & 30m):
Với mỗi mẫu quan trắc tại thời điểm $t$, nhãn mục tiêu tương lai $H \in \{15, 30\}$ phút được xác định theo mực nước cao nhất trong khoảng $[t+1, t+H]$:
$$\text{MaxLevel}_H = \max_{k \in [1, H]} \text{water\_level}(t + k)$$
$$\text{target\_}Hm = \begin{cases} 
0 \text{ (An toàn)} & \text{khi } \text{MaxLevel}_H < 15.0\text{ cm} \\
1 \text{ (Có nguy cơ)} & \text{khi } 15.0\text{ cm} \le \text{MaxLevel}_H < 25.0\text{ cm} \\
2 \text{ (Nguy hiểm cao)} & \text{khi } \text{MaxLevel}_H \ge 25.0\text{ cm}
\end{cases}$$

### 4.2. Chiến lược chia dữ liệu (Chronological Experiment Split)
- **Quy tắc bất di bất dịch:** Tuyệt đối không xáo trộn ngẫu nhiên (random shuffle) hoặc dùng k-fold truyền thống vì sẽ vi phạm giả định chuỗi thời gian và gây rò rỉ dữ liệu (data leakage).
- **Phân chia theo phiên thực nghiệm:**
  - **Tập Train (khoảng 70%):** Chứa các phiên chạy đầu tiên của từng kịch bản (ví dụ: `exp-real-n01`, `n02`, `w01`, `w02`, `d01`, `d02`).
  - **Tập Test (khoảng 30%):** Chứa các phiên chạy độc lập sau cùng của mỗi kịch bản (ví dụ: `exp-real-n03`, `w03`, `d03`).

### 4.3. Lệnh huấn luyện mô hình AI
Sử dụng script chính thức [`train_mini_flood_models.py`](file:///d:/Projects/tool-craw/train_mini_flood_models.py):

```powershell
python train_mini_flood_models.py `
    --input telemetry_experiments_real.csv `
    --output-dir models `
    --warning-cm 15.0 `
    --danger-cm 25.0
```

### 4.4. Tiêu chí chấp nhận mô hình (Acceptance Criteria)

Script huấn luyện được tích hợp cơ chế bảo vệ an toàn (Safety Gate). Mô hình mới chỉ được lưu đè vào thư mục `models/` nếu thỏa mãn đồng thời 3 điều kiện:

1. **Hiệu năng tổng thể:** $\text{Macro-F1}$ của Multinomial Logistic Regression cao hơn mô hình cơ sở theo quy tắc ngưỡng (Baseline):
   $$\text{Macro-F1}_{\text{Model}} > \text{Macro-F1}_{\text{Baseline}}$$
2. **Không bỏ sót nguy hiểm:** Chỉ số $\text{Recall}$ đối với lớp Nguy hiểm cao (Lớp 2 - Danger) không được thấp hơn Baseline:
   $$\text{Recall}_{\text{Danger (Model)}} \ge \text{Recall}_{\text{Danger (Baseline)}}$$
3. **Độ bao phủ nhãn:** Tập kiểm thử (Test set) phải chứa đầy đủ cả 3 nhãn ($0, 1, 2$).

> [!WARNING]
> Nếu dữ liệu thực nghiệm không thỏa mãn tiêu chí trên (do thu thập thiếu kịch bản hoặc nhiễu cảm biến quá lớn), script sẽ báo lỗi từ chối ghi đè model. Trong trường hợp đó, hệ thống Backend sẽ tiếp tục sử dụng Baseline quy tắc ngưỡng để đảm bảo an toàn.

### 4.5. Sản phẩm đầu ra sau huấn luyện (Artifacts)
Khi quá trình huấn luyện thành công, 5 tệp sau sẽ được cập nhật trong thư mục [`models/`](file:///d:/Projects/tool-craw/models/):
- `mini_flood_15m.joblib`: Pipeline Scikit-Learn chuẩn hóa và Logistic Regression cho 15 phút.
- `mini_flood_30m.joblib`: Pipeline Scikit-Learn chuẩn hóa và Logistic Regression cho 30 phút.
- `mini_flood_metadata.json`: Metadata phiên bản, danh sách đặc trưng, tập thí nghiệm train/test, thời điểm train.
- `mini_flood_benchmark.csv`: Bảng đối sánh chi tiết F1-macro, Precision, Recall, Log Loss giữa Model và Baseline.
- `mini_flood_confusion_matrices.png`: Ma trận nhầm lẫn trực quan trên tập Test cho cả 15m và 30m.

### 4.6. Nạp mô hình vào Runtime Backend
Khởi động lại FastAPI Backend:

```powershell
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Kiểm tra trạng thái nạp mô hình:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
```

Xác nhận kết quả JSON trả về:
```json
{
  "status": "ok",
  "simulation": true,
  "model_ready": true,
  "model_version": "mini-flood-v1-YYYYMMDDHHMMSS"
}
```


---

## Phần V: Cấu Hình Telegram Bot, Kịch Bản Cảnh Báo & Vận Hành Tự Động

### 5.1. Thiết lập Bot và lấy Chat ID

Hệ thống Mini Flood AI sử dụng Telegram Bot API chính thức để gửi thông báo tức thời tới cá nhân quản trị hoặc nhóm phản ứng nhanh.

```
       ┌────────────────────────┐
       │   MiniFloodService     │
       │  (Ingest & Predict)    │
       └───────────┬────────────┘
                   │
                   ▼ (Tạo cảnh báo)
       ┌────────────────────────┐
       │   AlertManager         │ ───► Ghi SQLite: `alerts`
       │  (Stateful Filter)     │ ───► Ghi SQLite: `deliveries` (status = pending)
       └────────────────────────┘
                   │
                   ▼ (Quét mỗi 15s)
       ┌────────────────────────┐
       │   DeliveryWorker       │
       │  (Background Thread)   │
       └───────────┬────────────┘
                   │ HTTPS POST
                   ▼
       ┌────────────────────────┐
       │ Telegram Bot API       │ ───► Nhóm / Kênh Telegram
       └────────────────────────┘
```

#### Bước 1: Tạo Bot qua BotFather
1. Mở ứng dụng Telegram, tìm kiếm tài khoản chính thức `@BotFather`.
2. Gửi lệnh `/newbot` và làm theo hướng dẫn:
   - Đặt tên hiển thị (Name): ví dụ `Mini Flood Early Warning`.
   - Đặt username (kết thúc bằng `bot`): ví dụ `mini_flood_alert_bot`.
3. Lưu lại chuỗi **API Token** được cấp, có dạng: `7123456789:AAFlkBz...example...xyz`.

#### Bước 2: Lấy Chat ID nhận cảnh báo
- **Đối với cá nhân:**
  1. Tìm bot vừa tạo và bấm **Start** (hoặc gửi tin nhắn `/start`).
  2. Truy cập đường dẫn trên trình duyệt:  
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
  3. Tìm khóa `"chat":{"id": 123456789}`. Chuỗi `123456789` chính là Chat ID cá nhân.
- **Đối với nhóm (Khuyến nghị cho kíp trực):**
  1. Tạo nhóm Telegram (ví dụ: `[Trực Ban] Cảnh Báo Ngập Cục Bộ`).
  2. Mời Bot vào nhóm và cấp quyền gửi tin nhắn (Send Messages).
  3. Gửi một tin nhắn bất kỳ vào nhóm (ví dụ: `xin chào bot`).
  4. Truy cập lại link `getUpdates`, tìm ID của nhóm (thường có dấu âm đứng đầu, ví dụ `-1001987654321`).

### 5.2. Cấu hình biến môi trường Backend

Thiết lập các biến môi trường trước khi khởi động FastAPI:

```powershell
$env:MINI_FLOOD_TELEGRAM_TOKEN            = "7123456789:AAFlkBz...example...xyz"
$env:MINI_FLOOD_TELEGRAM_CHAT_ID          = "-1001987654321"
$env:MINI_FLOOD_REMINDER_MINUTES          = "30"    # Chu kỳ nhắc lại khi ngập nguy hiểm (phút)
$env:MINI_FLOOD_NOTIFICATION_WORKER       = "true"  # Bật worker nền
$env:MINI_FLOOD_NOTIFICATION_POLL_SECONDS = "15"    # Chu kỳ quét hàng đợi gửi tin (giây)
```

> [!CAUTION]
> Tuyệt đối không commit trực tiếp Token hoặc Chat ID vào mã nguồn Git. Sử dụng biến môi trường hoặc file `.env` nằm trong danh sách `.gitignore`.

### 5.3. Cơ chế phân cấp cảnh báo & Phòng chống Spam (Anti-Spam State Machine)

Bộ máy [`AlertManager`](file:///d:/Projects/tool-craw/mini_flood/notifications.py#L68) duy trì trạng thái lịch sử (`alert_state:{device_id}`) trong SQLite để thực hiện điều tiết tin nhắn:

1. **Cảnh báo Leo thang (Escalation):**
   - Kích hoạt **ngay lập tức** khi cấp rủi ro hiện tại tăng cao hơn cấp rủi ro trước đó (ví dụ từ An toàn lên Có nguy cơ, hoặc từ Có nguy cơ lên Nguy hiểm).
2. **Cảnh báo Nhắc lại (Reminder):**
   - Khi tình trạng Nguy hiểm cao (Lớp 2) duy trì liên tục kéo dài, hệ thống không gửi tin mỗi phút gây quá tải điện thoại, mà định kỳ nhắc lại sau mỗi `MINI_FLOOD_REMINDER_MINUTES` (mặc định 30 phút).
3. **Cảnh báo Phục hồi (Recovery):**
   - Khi nước rút về mức An toàn (Lớp 0), hệ thống **bắt buộc kiểm tra 2 chu kỳ đo liên tiếp an toàn** (`safe_streak >= 2`, tức 2 phút ổn định). Khi đó mới phát thông báo phục hồi và giải tỏa cảnh báo.

### 5.4. Định dạng tin nhắn quy chuẩn

Mọi tin nhắn gửi đi qua Telegram bắt buộc tuân theo cấu trúc nhận diện chuẩn:

```text
[MÔ PHỎNG THỬ NGHIỆM]

CẢNH BÁO NGUY CƠ NGẬP
Dự báo 15 phút: Nguy hiểm cao (91.4%)
Dự báo 30 phút: Nguy hiểm cao (87.2%)
Mực nước hiện tại: 26.5 cm
Tốc độ dâng 2 phút: +3.2 cm
Nguyên nhân: Mực nước hiện tại đã vượt ngưỡng nguy hiểm (>= 25cm)
Thời gian đo: 2026-10-19T13:30:00+07:00
```

Khi trạng thái an toàn trở lại:
```text
[MÔ PHỎNG THỬ NGHIỆM]

TRẠNG THÁI ĐÃ AN TOÀN
Dự báo 15 phút: An toàn (98.1%)
Dự báo 30 phút: An toàn (95.0%)
Mực nước hiện tại: 8.2 cm
Tốc độ dâng 2 phút: -1.5 cm
Nguyên nhân: Mực nước đã rút dưới mức cảnh báo và duy trì an toàn
Thời gian đo: 2026-10-19T14:15:00+07:00
```

### 5.5. Kiểm tra nhanh kết nối Telegram qua API
Trước khi bắt đầu thu thập hoặc diễn tập, gửi tin nhắn kiểm tra qua API để xác nhận cấu hình:

```powershell
$headers = @{ "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/notifications/test?device_id=mini-flood-station-01" `
    -Method Post `
    -Headers $headers
```

Nếu thành công, phản hồi trả về:
```json
{
  "queued": true,
  "alert_id": 1,
  "deliveries_processed": 1
}
```
Và tin nhắn mẫu sẽ lập tức xuất hiện trong kênh Telegram.


---

## Phần VI: Kịch Bản Diễn Tập End-to-End Toàn Trình (Operational Drill)

Nhằm đảm bảo toàn bộ mắt xích từ cảm biến thực tế, truyền tin Wi-Fi, suy luận AI đến cảnh báo Telegram hoạt động trơn tru trước khi nghiệm thu, kíp vận hành tiến hành diễn tập theo quy trình 6 bước khép kín:

```
[Khởi động Hệ thống] ──► [Bật Experiment] ──► [Mô phỏng Ngập] ──► [Nhận Tin Telegram] ──► [Xả Nước / Recovery] ──► [Xuất Dữ liệu]
```

### Bước 1: Khởi động hệ sinh thái phần mềm
Terminal 1 (Backend):
```powershell
$env:MINI_FLOOD_DEVICE_KEY = "khao-sat-thuc-nghiem-2026"
$env:MINI_FLOOD_TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
$env:MINI_FLOOD_TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Terminal 2 (Dashboard trực quan):
```powershell
streamlit run app_mini_flood_dashboard.py
```

### Bước 2: Thiết lập phiên đo lường
Gửi request kích hoạt phiên kịch bản nguy hiểm:
```powershell
$headers = @{ "Content-Type" = "application/json"; "X-Device-Key" = $env:MINI_FLOOD_DEVICE_KEY }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/experiments/start" `
    -Method Post -Headers $headers `
    -Body '{"device_id":"mini-flood-station-01","experiment_id":"exp-drill-01","scenario":"danger"}'
```

### Bước 3: Diễn tập sự kiện ngập vật lý
1. **Phút 0 - 15 (Ổn định ban đầu):** Để thùng cạn nước ($< 5\text{ cm}$), không mưa. Dashboard hiển thị trạng thái Bình thường (Xanh lá). Telegram không phát cảnh báo.
2. **Phút 16 - 20 (Mưa to & Nước dâng nhanh):**
   - Kích hoạt bình phun nước lên cảm biến mưa ($\text{rain\_rate} \ge 35\text{ mm/h}$).
   - Bơm nước vào hố ga để mực nước dâng từ $5\text{ cm} \to 18\text{ cm}$.
   - **Xác minh Telegram:** Bot gửi tin nhắn cảnh báo leo thang: `Dự báo 15 phút: Có nguy cơ / Nguy hiểm`.
3. **Phút 21 - 25 (Đạt đỉnh nguy hiểm cao):**
   - Tiếp tục cấp nước để mực nước chạm mốc $27\text{ cm}$ ($\ge 25\text{ cm}$).
   - **Xác minh Telegram:** Bot lập tức gửi tin nhắn leo thang: `Dự báo 15 phút & 30 phút: Nguy hiểm cao`.
4. **Phút 26 - 55 (Duy trì ngập & Kiểm tra nhắc lại):**
   - Giữ mực nước ở mức $27\text{ cm}$.
   - Sau 30 phút duy trì trạng thái nguy hiểm (mốc phút thứ 51-55), **xác minh Telegram** nhận được tin nhắn nhắc lại (Reminder).

### Bước 4: Diễn tập xả nước & Phục hồi an toàn (Recovery)
1. Mở van xả đáy hố ga để nước rút nhanh về $< 10\text{ cm}$.
2. Dừng cấp mưa.
3. Sau 2 chu kỳ đo liên tiếp (2 phút) ghi nhận mực nước an toàn, **xác minh Telegram** nhận được tin thông báo: `TRẠNG THÁI ĐÃ AN TOÀN`.

### Bước 5: Kết thúc phiên và trích xuất dữ liệu
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/experiments/stop?device_id=mini-flood-station-01" `
    -Method Post -Headers $headers

Invoke-WebRequest `
    -Uri "http://localhost:8000/api/v1/experiments/export.csv?device_id=mini-flood-station-01" `
    -Headers $headers -OutFile "telemetry_drill_01.csv"
```

---

## Phần VII: Bảng Tra Cứu Sự Cố (Troubleshooting Matrix) & Nhật Ký Mẫu

### 7.1. Bảng tra cứu sự cố kỹ thuật

| Mã lỗi / Hiện tượng | Nguyên nhân gốc rễ | Hướng dẫn khắc phục |
|---|---|---|
| **HTTP 401 Unauthorized** khi ESP32 gửi dữ liệu | Header `X-Device-Key` không khớp với biến `$env:MINI_FLOOD_DEVICE_KEY` trên backend. | Kiểm tra lại chuỗi khóa trong file `.ino` và terminal chạy FastAPI. |
| **API trả status: warming_up** | Chưa đủ 15 phút lịch sử dữ liệu để tính toán đặc trưng cửa sổ trượt. | Chờ trạm đo gửi đều đặn ít nhất 15 phút. Không ngắt kết nối giữa chừng. |
| **Telegram HTTP 400 Bad Request** | Chat ID không đúng định dạng hoặc người dùng chưa từng bấm `/start` với bot. | Nhắn tin `/start` cho bot hoặc kiểm tra lại dấu âm `-` trong ID nhóm. |
| **Telegram HTTP 401 Unauthorized** | Token của Bot Telegram bị nhập sai hoặc đã bị thu hồi trên BotFather. | Tạo lại token mới bằng lệnh `/token` trên `@BotFather` và cập nhật biến môi trường. |
| **Telegram HTTP 403 Forbidden** | Bot bị xóa khỏi nhóm hoặc người dùng đã chặn (block) bot. | Kiểm tra quyền thành viên của Bot trong nhóm Telegram, đảm bảo quyền Send Messages. |
| **Không nhận được tin dù nước đã dâng** | Worker gửi tin bị tắt hoặc kịch bản không thỏa mãn điều kiện leo thang. | 1. Kiểm tra `$env:MINI_FLOOD_NOTIFICATION_WORKER="true"`.<br>2. Kiểm tra log cơ sở dữ liệu bảng `deliveries`. |
| **ESP32 mất kết nối Wi-Fi** | Sóng Wi-Fi yếu hoặc router cấp lại IP làm đổi IP laptop. | ESP32 tự động lưu đệm dữ liệu vào bộ nhớ offline và gửi bù khi có mạng. Cố định IP tĩnh cho laptop. |

### 7.2. Truy vấn nhật ký cảnh báo trực tiếp trong SQLite
Khi cần kiểm tra chi tiết các cảnh báo đã tạo và trạng thái gửi tin trong SQLite:

```powershell
# Xem 5 cảnh báo mới nhất
python -c "import sqlite3; conn = sqlite3.connect('mini_flood.sqlite3'); cur = conn.cursor(); cur.execute('SELECT id, event_type, risk_level, created_at FROM alerts ORDER BY id DESC LIMIT 5'); print(cur.fetchall())"

# Xem 5 lần gửi tin gần nhất kèm lỗi nếu có
python -c "import sqlite3; conn = sqlite3.connect('mini_flood.sqlite3'); cur = conn.cursor(); cur.execute('SELECT id, alert_id, channel, status, last_error FROM deliveries ORDER BY id DESC LIMIT 5'); print(cur.fetchall())"
```

### 7.3. Biểu mẫu nhật ký thực nghiệm mẫu (Run Log Sheet)

| Trường thông tin | Giá trị ghi nhận |
|---|---|
| **Ngày thực nghiệm:** | 2026-10-19 |
| **Người thực hiện:** | Kỹ sư vận hành hệ thống |
| **Mã phiên (Experiment ID):** | `exp-real-d01` |
| **Kịch bản (Scenario):** | `danger` |
| **Thiết bị (Device ID):** | `mini-flood-station-01` |
| **Thời gian bắt đầu:** | 14:00:00 (Sequence 0) |
| **Thời gian kết thúc:** | 14:50:00 (Sequence 50 - Đạt 50 phút) |
| **Mực nước cực đại:** | $28.4\text{ cm}$ (tại phút thứ 28) |
| **Cường độ mưa cao nhất:** | $45.2\text{ mm/h}$ |
| **Thời điểm nhận cảnh báo Telegram:** | 14:18 (Escalation Warning), 14:26 (Escalation Danger), 14:48 (Recovery) |
| **Trạng thái xuất CSV:** | Thành công (`telemetry_experiments_real.csv`, 51 bản ghi hợp lệ) |
| **Ghi chú bất thường:** | Không mất gói, không có lỗi cảm biến. |
