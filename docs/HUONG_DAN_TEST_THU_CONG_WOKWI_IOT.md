# Sổ tay kiểm thử Wokwi và thiết bị IoT

## 1. Khởi động backend

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Mở `http://localhost:8000/api/v2/health`. Kết quả phải có `status: ok` và model version hồi quy hiện hành.

## 2. Chạy dashboard

```powershell
streamlit run app_mini_flood_dashboard.py
```

Kiểm tra form cấu hình trạm:

- Mức tràn mặc định: 40 cm.
- Vùng đệm: 10 cm.
- Hysteresis: 2 cm.
- Thời gian ổn định: 120 giây.

Thử đổi mức tràn và xác nhận hai đường ngưỡng trên biểu đồ thay đổi sau khi lưu.

## 3. Wokwi

Firmware gửi tới:

```cpp
const char* API_URL = "http://host.wokwi.internal:8000/api/v2/telemetry";
```

`SENSOR_MOUNT_HEIGHT_CM` là khoảng cách từ đầu dò xuống đáy. Nó không phải mức tràn của backend.

Sau khi chạy mô phỏng, terminal API phải xuất hiện `POST /api/v2/telemetry 200 OK`; dashboard phải cập nhật mực nước và mưa theo thời gian thực.

## 4. Kịch bản kiểm thử

### An toàn

- Giữ nước thấp và mưa nhỏ.
- Forecast 15/30 phút phải thấp hơn ngưỡng cảnh báo.
- `alert_label` là `An toàn` và không tạo escalation.

### Cảnh báo

- Tăng mưa và cho nước dâng đều.
- Khi giá trị lớn nhất trong hiện tại/forecast chạm ngưỡng warning, trạng thái tăng ngay lên `Cảnh báo`.
- Tin nhắn phải chứa forecast theo cm và mức tràn.

### Nguy hiểm

- Cho mực nước hiện tại hoặc forecast chạm mức tràn.
- Trạng thái phải là `Nguy hiểm`.
- Nếu mực nước hiện tại chạm mức tràn trong giai đoạn warming-up, `safety_override` vẫn phải bật.

### Hạ mức

- Sau trạng thái Nguy hiểm, cho nước xuống dưới `overflow - hysteresis`.
- Trạng thái chỉ hạ một mức sau khi duy trì đủ 120 giây.
- Cho nước dâng trở lại trong thời gian chờ để xác nhận timer bị hủy.

### Mất Wi-Fi

- Ngắt Wi-Fi, tạo nhiều phép đo rồi kết nối lại.
- ESP32 phải gửi lại queue theo thứ tự.
- Backend chỉ lưu một bản ghi cho mỗi bộ `device_id`/`boot_id`/`sequence_no`.
- `boot_id` đổi sau mỗi lần ESP32/Wokwi khởi động, nên `sequence_no` có thể quay lại 1 mà không bị nhầm là gói trùng.

## 5. Simulator không cần Wokwi

```powershell
python simulate_iot_stream.py --scenario normal --count 20 --speedup 0
python simulate_iot_stream.py --scenario warning --count 20 --speedup 0
python simulate_iot_stream.py --scenario danger --count 20 --speedup 0
python simulate_iot_stream.py --scenario flow --speedup 0
```

Kịch bản `flow` tự tính timestamp từ đúng số bản ghi thực tế, nên bản ghi cuối trùng thời điểm hiện tại và không bị gắn cờ tương lai.

## 6. Nghiệm thu tự động

```powershell
pytest -q
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run --project-dir EPS32_PROJECT
```

Tất cả test phải thành công và firmware phải tạo được `EPS32_PROJECT/.pio/build/esp32dev/firmware.bin`.
