# ESP32 HTTP telemetry

## Hai profile phần cứng tách biệt

| Profile | Lệnh build | Đầu vào cảm biến |
|---|---|---|
| `simulation` | `pio run -e simulation` | Wokwi: HC-SR04 nước, HC-SR04/biến trở mưa |
| `real_hardware` | `pio run -e real_hardware` | HC-SR04 GPIO18/19 đo nước, UART2 GPIO16/17 mưa Modbus |

`simulation` là môi trường mặc định và là artifact được `wokwi.toml` sử dụng.
Khi nạp bo thật phải chỉ rõ `-e real_hardware` để không nạp nhầm driver mô phỏng:

```powershell
pio run -e real_hardware -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Trong log boot, kiểm tra bắt buộc:

```text
[BOOT] Hardware profile: real_hardware
```

Nếu log ghi `simulation`, không dùng số đo đó cho dữ liệu thật hoặc huấn luyện AI.

Firmware `src/main.cpp` thực hiện bốn nhiệm vụ:

1. Đọc cảm biến mưa và mực nước.
2. Gửi telemetry đến `POST /api/v2/telemetry` mỗi 5 giây trong chế độ test; khi vận hành thật nên đổi thành 60 giây.
3. Lưu đệm tối đa 100 bản ghi trong RAM khi mất Wi-Fi và gửi lại sau.
4. Tự chẩn đoán Wi-Fi, backend và từng đầu vào cảm biến qua trang `/health`.

## Cấu hình riêng cho thiết bị thật

Sao chép `include/secrets.h.example` thành `include/secrets.h`, sau đó điền Wi-Fi
và device key. URL trong file này dùng cho profile mô phỏng; profile
`real_hardware` tự tìm backend bằng mDNS. File `secrets.h` đã bị Git bỏ qua để
không đưa mật khẩu lên repository.

Không cố định COM trong `platformio.ini` vì số cổng có thể đổi khi cắm lại USB. Khi cần có thể nạp bằng `pio run -t upload --upload-port COM6` và mở monitor bằng `pio device monitor --port COM6`.

Ngoài `secrets.h`, sao chép `include/hardware_config.h.example` thành
`include/hardware_config.h`. File này chứa hai nhóm hiệu chuẩn:

- Loại cảm biến nước; cấu hình hiện tại dùng HC-SR04 TRIG GPIO18/ECHO GPIO19.
- Slave ID, baud/parity, function code, register và scale của cảm biến mưa.

### Tự tìm backend khi IP laptop thay đổi

Profile `real_hardware` không dùng IP laptop cố định. Sau khi vào Wi-Fi, ESP32
truy vấn service `_mini-flood._tcp.local` và tạo URL telemetry từ IP/port được
backend quảng bá. Tên ổn định mặc định là `mini-flood-backend.local`.

Backend cần chạy với:

```powershell
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Windows phải cho phép TCP 8000 và mDNS UDP 5353 trên mạng LAN. Chạy PowerShell
với quyền Administrator một lần:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
New-NetFirewallRule -DisplayName "Mini Flood Backend TCP 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Private
New-NetFirewallRule -DisplayName "Mini Flood mDNS UDP 5353" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5353 -RemoteAddress LocalSubnet -Profile Private
```

ESP32 lưu URL tìm được gần nhất trong `Preferences`. Nếu laptop đổi IP, một lỗi
kết nối sẽ làm firmware bỏ URL cũ và tìm service mDNS lại. Wokwi vẫn dùng
`host.wokwi.internal`, không dùng mDNS.

Mặc định profile thật dùng `MINI_FLOOD_WATER_SENSOR_HCSR04=1`. Các biến
`MINI_FLOOD_WATER_CALIBRATED` chỉ áp dụng cho lựa chọn cảm biến analog dự phòng.
`MINI_FLOOD_RAIN_MODBUS_CONFIGURED=0` là khóa an toàn cho cảm biến mưa: firmware
vẫn build được nhưng gắn `quality_flags` cho đến khi register map đã được đối
chiếu đúng datasheet.

`MINI_FLOOD_RS485_PROBE_ENABLED=1` là phép kiểm tra kết nối chỉ-đọc. Mỗi chu kỳ
firmware gửi một request tới Slave 1, function `0x03`, register `0x0000` và in
khung TX/RX dạng hex trên Serial Monitor. Một response có CRC đúng, kể cả
Modbus exception do register chưa đúng, xác nhận ESP32, module và cảm biến đang
giao tiếp. Probe không được chuyển thành `rain_rate_mmh`; dữ liệu mưa chỉ được
tin cậy sau khi `MINI_FLOOD_RAIN_MODBUS_CONFIGURED=1` với register map đã xác
nhận.

Nếu chưa nhận được byte, profile thật tự gửi lệnh lookup địa chỉ chỉ-đọc
`FF 03 07 D0 00 01 91 59` lần lượt ở 2400, 4800 và 9600 baud. Khi nhận frame
đúng CRC, firmware tự dùng baud và Slave ID tìm được; không gửi function `06`
và không thay đổi cấu hình cảm biến. Nếu không tìm thấy, quá trình được thử lại
sau 60 giây. `/health` hiển thị `rs485.discovered`, `baud` và `slave_id`.

Thiết bị đang dùng được nhận diện từ tem là `SW-3001-GYL-N01` (cùng protocol
với tài liệu `SN-3001-GYL-N01`): nguồn 9–30 V DC, Modbus RTU mặc định 4800
baud/8N1/Slave 1. Register `0x0000`, function `0x03`, trả tổng lượng mưa với
độ phân giải 0,1 mm. Firmware lấy chênh lệch giữa hai lần đọc để tính
`rain_rate_mmh`; lần đọc đầu tiên sau khi khởi động chỉ thiết lập mốc và trả 0.

## Sơ đồ LED chẩn đoán

Mỗi LED ngoài phải mắc `GPIO -> điện trở 220-330 ohm -> chân dương LED`, chân âm LED về `GND`:

| LED đề nghị | GPIO | Sáng khi |
|---|---:|---|
| Xanh dương — Wi-Fi | 25 | ESP32 đã vào Wi-Fi |
| Xanh lá — Backend | 26 | Lần gửi gần nhất nhận HTTP 2xx |
| Vàng — Mực nước | 27 | HC-SR04 nhận ít nhất 2/3 xung Echo hợp lệ |
| Trắng — Mưa | 33 | Simulation: Echo hợp lệ; real: thiết bị trả frame Modbus đúng CRC |

LED D2 trên bo là trạng thái tổng hợp:

- Sáng liên tục: cả bốn cụm đều OK.
- Một chớp chậm: Wi-Fi hoặc backend lỗi.
- Hai chớp nhanh: mạng OK nhưng có ít nhất một cảm biến lỗi.

Đây là LED chẩn đoán kết nối, không biểu thị mức An toàn/Cảnh báo/Nguy hiểm.

Mỗi HC-SR04 được TRIG ba lần và chỉ được coi là kết nối khi ít nhất hai Echo nằm trong khoảng 2-400 cm. Hai lần TRIG cách nhau 60 ms để hạn chế nhiễu chéo giữa cảm biến.

## Kiểm tra từng cụm trên thiết bị thật

Sau khi Serial Monitor in địa chỉ IP, mở `http://<IP-ESP32>/health`. Kết quả JSON cho biết:

- `wifi.connected`: ESP32 đã vào Wi-Fi hay chưa.
- `backend.connected`: lần gửi HTTP gần nhất có được backend chấp nhận hay không.
- `hardware_profile`: `simulation` hoặc `real_hardware`.
- `water_sensor.connected`: cả hai profile kiểm tra HC-SR04 qua xung Echo; profile thật yêu cầu ít nhất 2/3 lần đo hợp lệ.
- `water_sensor.distance_cm`: khoảng cách HC-SR04 đo từ đầu dò tới mặt nước.
- `rain_sensor.verified`: chỉ `true` trên profile thật khi nhận frame Modbus đúng CRC và giá trị hợp lệ.
- `rs485.configured`: cấu hình register map đã được người dùng xác nhận hay chưa.
- `rs485.probe_enabled`: ESP32 có đang tự gửi request kiểm tra chỉ-đọc hay không.
- `rs485.connected`: có nhận được frame từ đúng Slave ID và CRC hợp lệ hay không.
- `rs485.last_exception`: mã exception gần nhất; `0` nghĩa không có exception.
- `rs485.last_response_ms`: thời điểm uptime nhận phản hồi Modbus hợp lệ gần nhất.

Serial cũng in một dòng tổng hợp sau mỗi lần đo, ví dụ:

```text
[HEALTH] profile=real_hardware wifi=OK backend=OK(http=200) water=OK rain=modbus_crc_ok rs485=OK
```

Không dùng `ping` mạng để kiểm tra mọi thiết bị: HC-SR04 được kiểm tra bằng xung Echo, RS485 bằng request/response Modbus hợp lệ, Wi-Fi bằng trạng thái kết nối và backend bằng HTTP 2xx.

Wokwi có thể dùng biến trở để mô phỏng cường độ mưa. Với cảm biến mưa RS485
thật, phải đối chiếu datasheet rồi khai báo đúng Slave ID, baud, function,
register, scale và kiểu giá trị trong `include/hardware_config.h`; không lấy
cấu hình của model khác chỉ vì hình dáng giống nhau.

`SENSOR_MOUNT_HEIGHT_CM` là khoảng cách từ đầu dò đến đáy dùng để tính `water_level_cm`. Ngưỡng nước tràn là `overflow_level_cm` trong cấu hình backend/dashboard; hai giá trị này không nên bị hiểu là một.

## Mô phỏng bằng Wokwi Extension trên VS Code

1. Luôn mở Wokwi từ thư mục gốc của dự án; đây là nơi duy nhất chứa `wokwi.toml` và `diagram.json`.
2. Build bằng `pio run --project-dir EPS32_PROJECT -e simulation`. Wokwi nạp artifact V2 trong `EPS32_PROJECT/.pio/build/simulation`.
3. File sơ đồ mạch chuẩn: [diagram.json](../diagram.json) (đã khai báo ESP32, HC-SR04 ở chân 18-19, biến trở mưa ở chân 34).
4. Khi chạy trong Wokwi VS Code Extension, ESP32 kết nối về backend trên laptop qua địa chỉ:
   ```cpp
   const char* API_URL = "http://host.wokwi.internal:8000/api/v2/telemetry";
   ```
   (`host.wokwi.internal` là hostname ảo do Wokwi tự động ánh xạ về localhost của máy tính).

Serial Monitor phải hiện `[BOOT] Mini Flood firmware V2`, sau đó là trạng thái Wi-Fi và dòng `POST`/`Phan hoi`. Nếu chạy Wokwi trên trình duyệt thay vì Extension, `host.wokwi.internal` không trỏ về backend cục bộ; cần dùng một URL HTTPS public/tunnel cho `API_URL`.
