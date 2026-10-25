# Runbook Mini Flood AI V2

> Tất cả lệnh bên dưới được chạy tại thư mục gốc của repository, trừ khi có ghi
> chú khác. Không dùng đường dẫn tuyệt đối theo máy cá nhân.

## 1. Chạy backend

**Windows:**

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

**macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn mini_flood_api:app --host 0.0.0.0 --port 8000
```

Kiểm tra API bằng PowerShell hoặc Terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v2/health
```

```bash
curl http://127.0.0.1:8000/api/v2/health
```

API phải trả `status: ok`. Luôn dùng `--host 0.0.0.0` để ESP32 có thể kết nối.

Chạy dashboard trong Terminal khác:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app_mini_flood_dashboard.py
```

```bash
source .venv/bin/activate
streamlit run app_mini_flood_dashboard.py
```

## 2. Cài PlatformIO và nạp ESP32

### 2.1. Cài PlatformIO

1. Cài Visual Studio Code.
2. Mở **Extensions** (`Ctrl+Shift+X` trên Windows hoặc `Cmd+Shift+X` trên macOS).
3. Cài **PlatformIO IDE** (`platformio.platformio-ide`).
4. Reload VS Code và đợi PlatformIO cài đặt xong.
5. Mở thư mục `EPS32_PROJECT` bằng **File > Open Folder**.

Có thể cài extension bằng lệnh:

```powershell
code --install-extension platformio.platformio-ide
```

### 2.2. Tạo cấu hình thiết bị

Tạo hai file cấu hình nếu chúng chưa tồn tại:

**Windows:**

```powershell
if (-not (Test-Path .\EPS32_PROJECT\include\secrets.h)) {
  Copy-Item .\EPS32_PROJECT\include\secrets.h.example .\EPS32_PROJECT\include\secrets.h
}
if (-not (Test-Path .\EPS32_PROJECT\include\hardware_config.h)) {
  Copy-Item .\EPS32_PROJECT\include\hardware_config.h.example .\EPS32_PROJECT\include\hardware_config.h
}
```

**macOS:**

```bash
test -f EPS32_PROJECT/include/secrets.h || \
  cp EPS32_PROJECT/include/secrets.h.example EPS32_PROJECT/include/secrets.h
test -f EPS32_PROJECT/include/hardware_config.h || \
  cp EPS32_PROJECT/include/hardware_config.h.example EPS32_PROJECT/include/hardware_config.h
```

Sửa `EPS32_PROJECT/include/secrets.h`:

```cpp
#define MINI_FLOOD_WIFI_SSID "ten-wifi-2.4GHz"
#define MINI_FLOOD_WIFI_PASSWORD "mat-khau-wifi"
#define MINI_FLOOD_BACKEND_MDNS_HOST "mini-flood-backend"
#define MINI_FLOOD_BACKEND_MDNS_PORT 8000
#define MINI_FLOOD_DEVICE_KEY "device-key-giong-backend"
```

Yêu cầu:

- Dùng Wi-Fi 2.4 GHz.
- Device key phải giống backend.
- Host mDNS không có hậu tố `.local`.
- Không commit `secrets.h` vì file chứa thông tin bí mật.

### 2.3. Tìm cổng USB và upload

Cắm ESP32 bằng cáp USB data rồi chạy trong **PlatformIO Core CLI**:

```powershell
pio device list
```

Ghi lại cổng của ESP32 rồi chạy lệnh phù hợp.

**Windows**, ví dụ `COM6`:

```powershell
pio run --project-dir EPS32_PROJECT -e real_hardware
pio run --project-dir EPS32_PROJECT -e real_hardware -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Thay `COM6` bằng cổng thực tế. Nếu upload báo cổng đang bận, đóng Serial Monitor
rồi thử lại. Nếu dừng ở `Connecting...`, giữ nút **BOOT** khi bắt đầu upload.

**macOS**, ví dụ `/dev/cu.usbserial-0001`:

```bash
pio run --project-dir EPS32_PROJECT -e real_hardware
pio run --project-dir EPS32_PROJECT -e real_hardware -t upload \
  --upload-port /dev/cu.usbserial-0001
pio device monitor --port /dev/cu.usbserial-0001 --baud 115200
```

Cổng trên macOS thường bắt đầu bằng `/dev/cu.usbserial`, `/dev/cu.SLAB_USBtoUART`
hoặc `/dev/cu.wchusbserial`. Dùng đúng giá trị do `pio device list` trả về.

## 3. Cấu hình backend và mDNS

ESP32 tìm backend trong cùng mạng bằng mDNS:

```text
Service: _mini-flood._tcp.local
Host:    mini-flood-backend.local
Port:    8000
```

Trong `.env` của backend:

```dotenv
MINI_FLOOD_DEVICE_KEY=device-key-giong-esp32
MINI_FLOOD_MDNS_ENABLED=true
MINI_FLOOD_MDNS_HOSTNAME=mini-flood-backend
MINI_FLOOD_MDNS_PORT=8000
```

Hostname, port và device key phải khớp với `secrets.h`. Đây là mDNS nội bộ,
không phải DNS public; ESP32 và backend phải ở cùng LAN/VLAN có hỗ trợ multicast.

### Mở port trên Windows

Mở PowerShell bằng **Run as administrator**:

```powershell
Get-NetAdapter | Where-Object Status -eq "Up"
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private

New-NetFirewallRule -DisplayName "Mini Flood Backend TCP 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Private
New-NetFirewallRule -DisplayName "Mini Flood mDNS UDP 5353" -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5353 -RemoteAddress LocalSubnet -Profile Private
```

Nếu card mạng không tên `Wi-Fi`, thay bằng tên lấy từ `Get-NetAdapter`.

### Cho phép kết nối trên macOS

Trong **System Settings > Privacy & Security > Local Network**, cho phép Terminal
hoặc VS Code truy cập mạng nội bộ. Nếu macOS Firewall hỏi, chọn cho phép Python
nhận kết nối đến. Không cần tạo rule bằng lệnh nếu các quyền này đã được cấp.

### Kiểm tra port trên Windows

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000
Get-NetUDPEndpoint -LocalPort 5353 -ErrorAction SilentlyContinue
Test-NetConnection 127.0.0.1 -Port 8000
```

Từ một máy khác cùng mạng, thay IP ví dụ bằng IP của backend rồi kiểm tra:

```powershell
$backendIp = "192.168.1.20"
Test-NetConnection $backendIp -Port 8000
Invoke-RestMethod "http://${backendIp}:8000/api/v2/health"
```

`TcpTestSucceeded` phải là `True` và API phải trả `status: ok`.

### Kiểm tra port trên macOS

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iUDP:5353
nc -vz 127.0.0.1 8000
curl http://127.0.0.1:8000/api/v2/health
ipconfig getifaddr en0
```

Từ máy khác cùng mạng, thay IP ví dụ bằng IP của backend:

```bash
backend_ip="192.168.1.20"
nc -vz "$backend_ip" 8000
curl "http://$backend_ip:8000/api/v2/health"
```

Nếu `ipconfig getifaddr en0` không trả IP, dùng
`networksetup -listallhardwareports` để tìm interface Wi-Fi đúng.

## 4. Khi chuyển sang Wi-Fi khác

1. Kết nối máy backend vào mạng mới.
2. Đảm bảo mạng có Wi-Fi 2.4 GHz và không bật AP/client isolation.
3. Windows: đặt mạng thành `Private`. macOS: cấp quyền **Local Network**.
   Sau đó kiểm tra TCP 8000 và UDP 5353.
4. Đổi `MINI_FLOOD_WIFI_SSID` và `MINI_FLOOD_WIFI_PASSWORD` trong `secrets.h`.
5. Kiểm tra hostname, port mDNS và device key vẫn khớp với backend.
6. Build và upload lại ESP32.
7. Khởi động lại backend.
8. Kiểm tra Serial Monitor và trang `http://<IP-ESP32>/health`.

Phải upload lại khi đổi SSID, mật khẩu, device key, hostname hoặc port. Không
cần upload lại nếu chỉ IP của backend thay đổi; ESP32 sẽ tự tìm IP mới qua mDNS.

Log thành công:

```text
[BOOT] Hardware profile: real_hardware
[WiFi] Da ket noi, IP=...
[mDNS] Backend: mini-flood-backend.local -> http://<IP-BACKEND>:8000/api/v2/telemetry
[HTTP] Phan hoi 200
```

Trang `/health` của ESP32 phải có:

```json
{
  "wifi": {"connected": true},
  "backend": {"connected": true, "last_http_status": 200}
}
```

## 5. Cấu hình trạm

**Windows:**

```powershell
$headers = @{ "X-Device-Key" = "device-key-giong-esp32" }
$config = @{
  overflow_level_cm = 40
  warning_margin_cm = 10
  hysteresis_cm = 2
  recovery_hold_seconds = 120
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
  -Uri http://localhost:8000/api/v2/stations/mini-flood-station-01/config `
  -Headers $headers -ContentType "application/json" -Body $config
```

**macOS:**

```bash
curl -X PUT http://localhost:8000/api/v2/stations/mini-flood-station-01/config \
  -H "X-Device-Key: device-key-giong-esp32" \
  -H "Content-Type: application/json" \
  -d '{"overflow_level_cm":40,"warning_margin_cm":10,"hysteresis_cm":2,"recovery_hold_seconds":120}'
```

## 6. Kiểm tra nhanh và xử lý lỗi

```powershell
pytest -q
pio run --project-dir EPS32_PROJECT -e real_hardware
```

| Lỗi | Cách kiểm tra |
|---|---|
| Không thấy COM | Đổi cáp USB data/cổng USB; kiểm tra driver CP210x hoặc CH340. |
| Không vào được Wi-Fi | Kiểm tra SSID, mật khẩu, băng tần 2.4 GHz rồi upload lại. |
| Không tìm thấy mDNS | Kiểm tra cùng mạng, UDP 5353, firewall và client isolation. |
| `connection refused` | Kiểm tra backend chạy với `0.0.0.0:8000`. |
| HTTP `401` | Device key của backend và ESP32 không giống nhau. |
| HTTP `200` nhưng dashboard không đổi | Kiểm tra `device_id` và telemetry trên backend. |
