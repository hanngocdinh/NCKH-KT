# Sổ tay kiểm thử thiết bị IoT

## 1. Khởi động backend

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Mở `http://localhost:8000/api/v2/health`. Kết quả phải có `status: ok` và
model version hồi quy hiện hành.

## 2. Chạy dashboard

```powershell
streamlit run app_mini_flood_dashboard.py
```

Kiểm tra form cấu hình trạm, biểu đồ mực nước và hai đường ngưỡng cảnh báo.

## 3. Kiểm tra ESP32 thật

Build và nạp firmware:

```powershell
pio run --project-dir EPS32_PROJECT -e real_hardware
pio run --project-dir EPS32_PROJECT -e real_hardware -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Serial Monitor phải ghi `Hardware profile: real_hardware`, kết nối Wi-Fi,
tìm backend qua mDNS và nhận HTTP 2xx. Mở `http://<IP-ESP32>/health` để kiểm tra
HC-SR04, RS485, backend và hàng đợi telemetry.

`SENSOR_MOUNT_HEIGHT_CM` là khoảng cách từ đầu dò xuống đáy, không phải mức
tràn của backend.

## 4. Kịch bản kiểm thử

### An toàn

- Giữ nước thấp và mưa nhỏ.
- Forecast 15/30 phút phải thấp hơn ngưỡng cảnh báo.
- `alert_label` là `An toàn` và không tạo escalation.

### Cảnh báo và nguy hiểm

- Tăng lượng mưa và cho nước dâng đều.
- Khi hiện tại hoặc forecast chạm ngưỡng warning, trạng thái phải tăng ngay lên `Cảnh báo`.
- Khi hiện tại hoặc forecast chạm mức tràn, trạng thái phải là `Nguy hiểm`.
- Tin nhắn phải chứa forecast theo cm và mức tràn.

### Hạ mức

- Cho nước xuống dưới `overflow - hysteresis`.
- Trạng thái chỉ hạ một mức sau khi duy trì đủ thời gian ổn định đã cấu hình.
- Cho nước dâng lại trong thời gian chờ để xác nhận timer bị hủy.

### Mất Wi-Fi

- Ngắt Wi-Fi, tạo nhiều phép đo rồi kết nối lại.
- ESP32 phải gửi lại queue theo thứ tự.
- Backend chỉ lưu một bản ghi cho mỗi bộ `device_id`/`boot_id`/`sequence_no`.
- `boot_id` đổi sau mỗi lần ESP32 khởi động, nên `sequence_no` có thể quay lại 1 mà không bị xem là gói trùng.

## 5. Simulator backend tùy chọn

Simulator Python chỉ kiểm thử API/backend, không phải firmware ESP32:

```powershell
python simulate_iot_stream.py --scenario normal --count 20 --speedup 0
python simulate_iot_stream.py --scenario warning --count 20 --speedup 0
python simulate_iot_stream.py --scenario danger --count 20 --speedup 0
python simulate_iot_stream.py --scenario flow --speedup 0
```

## 6. Nghiệm thu tự động

```powershell
pytest -q
pio run --project-dir EPS32_PROJECT -e real_hardware
```

Tất cả test phải thành công và firmware phải tạo được
`EPS32_PROJECT/.pio/build/real_hardware/firmware.bin`.
