# BẢN THUYẾT MINH ĐỀ TÀI STEM (CẤP THPT)
# HỆ THỐNG IoT VÀ HỌC MÁY CẢNH BÁO SỚM NGẬP CỤC BỘ TẠI SÂN TRƯỜNG

**Tên đề tài**: Thiết kế và chế tạo trạm IoT kết hợp Học máy (AI) cảnh báo sớm nguy cơ ngập cục bộ trước 15 - 30 phút tại Trường THPT Trần Quý Cáp  
**Lĩnh vực**: Hệ thống nhúng - Trí tuệ nhân tạo - Kỹ thuật môi trường  
**Đối tượng áp dụng**: Học sinh, Giáo viên, Ban Giám hiệu trường THPT Trần Quý Cáp và Hội đồng Chấm thi STEM  

---

## 1. LÝ DO CHỌN ĐỀ TÀI & TÍNH THỰC TIỄN
* **Thực trạng**: Trường THPT Trần Quý Cáp nằm ở khu vực địa hình trũng thấp tại TP. Hội An. Vào mùa mưa, hệ thống thoát nước xung quanh thường bị quá tải hoặc rác lá cây bịt miệng cống, khiến nước dâng nhanh tràn vào sân trường và các phòng chức năng tầng 1 chỉ sau 15–30 phút mưa lớn.
* **Hạn chế của cách làm cũ**: Con người chỉ phát hiện khi nước đã tràn vào lớp học; việc di dời máy tính, tài liệu và sơ tán học sinh diễn ra bị động, dễ trơn trượt và nguy cơ chập điện.
* **Mục tiêu sản phẩm**: Tạo ra một thiết bị cảnh báo thông minh, chi phí thấp, hoạt động tự động tại chỗ:
  1. Đo liên tục mực nước trong cống và cường độ mưa sân trường.
  2. Dự báo nguy cơ ngập trước **15 đến 30 phút** để nhà trường chủ động kê cao đồ đạc và khơi thông cống rãnh.
  3. Báo động tự động bằng đèn LED 3 màu, còi hú và tin nhắn Telegram.

---

## 2. NGUYÊN LÝ CỐT LÕI: DỰ BÁO TRƯỚC (NOWCASTING) KHÁC GÌ CẢNH BÁO TỨC THỜI?

Một sai lầm phổ biến của các hệ thống cảnh báo đơn giản là **"thấy nước ngập rồi mới hú còi"** (Cảnh báo tức thời). Khi nước đã tràn vào sân trường thì mọi việc đã quá muộn, thiết bị phòng máy đã ướt và không còn thời gian trở tay.

**Điểm sáng tạo của đề tài nằm ở năng lực DỰ BÁO TRƯỚC 15 ĐẾN 30 PHÚT**:
* **Tại thời điểm hiện tại ($t$)**: Nước dưới cống mới chỉ mấp mé $10\text{ cm}$ (sân trường hoàn toàn khô ráo, mắt thường nhìn vào thấy rất an toàn).
* **Mô hình AI phân tích động học**: Kết hợp **Mực nước hiện tại** + **Vận tốc nước dâng** ($\Delta h / \Delta t$) + **Cường độ mưa xối xả**.
* **Dự phóng tương lai**: AI tính toán được sau 15–20 phút nữa, với tốc độ dâng này thì nước chắc chắn sẽ chạm vạch $25\text{ cm}$ (tràn sân).
* **Phát lệnh báo động Đỏ đón đầu ngay từ phút thứ 0**: Giúp nhà trường có trọn vẹn **15 đến 30 phút vàng** để kịp kê cao máy vi tính, ngắt cầu dao điện và khơi thông rác miệng cống trước khi nước kịp tràn vào!

---

## 3. BỘ 4 THAM SỐ ĐẦU VÀO CỐT LÕI (CHỈ TỪ 2 CẢM BIẾN TẠI TRƯỜNG)

Hệ thống rút gọn tối đa, chỉ theo dõi 4 biến trạng thái sinh ra trực tiếp từ 2 cảm biến:

| STT | Tên tham số | Đơn vị | Nguồn gốc | Ý nghĩa trong dự báo trước |
| :---: | :--- | :---: | :--- | :--- |
| **1** | `water_level_cm` | cm | Cảm biến siêu âm | Mực nước nền hiện tại ở hố ga trường ($h_t$). |
| **2** | `water_rise_5m_cm` | cm/5p | Hiệu số: $h_t - h_{t-5}$ | Vận tốc dâng nước $v = \Delta h / 5$. Đây là **"gia tốc cảnh báo sớm"** giúp phát hiện cống bị tắc rác. |
| **3** | `rain_rate_mmh` | mm/h | Cảm biến mưa | Cường độ mưa trút xuống, cung cấp thêm năng lượng sinh dòng chảy tràn. |
| **4** | `rain_sum_15m` | mm | Cộng dồn 15 phút | Tổng lượng nước đã trút xuống sân gần nhất, đo độ ngậm nước của mặt sân. |

---

## 4. MA TRẬN DỰ BÁO ĐÓN ĐẦU TRƯỚC 15 - 30 PHÚT (HỐ GA SÂU 40CM)

| Cấp độ | Tín hiệu thiết bị | Điều kiện AI kích hoạt (Khi nước sân VẪN CHƯA NGẬP) | Dự báo cho 15 - 30 phút tới | Hành động của nhà trường |
| :---: | :---: | :--- | :--- | :--- |
| **Mức 0: AN TOÀN** | **Đèn XANH**<br>Còi TẮT | * $h < 15\text{ cm}$<br>* Tốc độ dâng: $< 2\text{ cm/5p}$<br>* Mưa nhỏ hoặc không mưa | Trong 30 phút tới nước không thể tràn, cống thoát tốt. | Giảng dạy và sinh hoạt bình thường. |
| **Mức 1: CÓ NGUY CƠ** | **Đèn VÀNG**<br>Còi TẮT | * Hiện tại $15 \le h < 20\text{ cm}$<br>* **HOẶC** dự báo $h_{t+15} \ge 15\text{ cm}$<br>* **HOẶC** nước dâng nhanh $\ge 3\text{ cm/5p}$<br>* **HOẶC** mưa to $\ge 25\text{ mm/h}$ | Nước sẽ dâng quá nửa hố ga sau 15–30 phút, có nguy cơ ngập mép sân. | 1. Bác bảo vệ đi kiểm tra cào rác ở miệng cống.<br>2. Thầy cô phòng máy tầng 1 kê thiết bị lên bàn.<br>3. Theo dõi bảng tin. |
| **Mức 2: BÁO ĐỘNG ĐỎ** | **ĐÈN ĐỎ CHỚP**<br>**CÒI HÚ LIÊN TỤC** | * Mực nước dự phóng $\mathbf{h_{t+15} \ge 25\text{ cm}}$<br>* **HOẶC** nước dâng xiết $\mathbf{\ge 6\text{ cm/5p}}$ (nước cống dâng cực nhanh do tắc nghẽn)<br>* **HOẶC** $h \ge 18\text{ cm}$ kết hợp mưa xối xả $> 40\text{ mm/h}$ | **Chắc chắn nước sẽ tràn lên sân trường và phòng học tầng 1 sau 15 phút nữa!** | **[HÀNH ĐỘNG KHẨN CẤP]**<br>1. Hú còi di tản học sinh lên tầng 2.<br>2. Ngắt cầu dao điện tầng 1 phòng chống chập cháy, giật điện.<br>3. Chốt cổng không cho học sinh ra sân. |

---

## 5. THUẬT TOÁN HỌC MÁY CỦA ĐỀ TÀI: CÂY QUYẾT ĐỊNH DỰ BÁO TRƯỚC (PREDICTIVE DECISION TREE)

Nhóm nghiên cứu lựa chọn thuật toán **Cây quyết định (Decision Tree)** vì đây là mô hình "Hộp trắng" (White-box model), minh bạch 100%, có thể nạp thẳng vào bộ nhớ vi điều khiển ESP32:

```
[SƠ ĐỒ CÂY QUYẾT ĐỊNH DỰ BÁO TRƯỚC 15 PHÚT NẠP VÀO ESP32]

              [ Nước dự phóng sau 15p: h_15m >= 25 cm HOẶC h_now >= 25 cm? ]
                                      /          \
                                    ĐÚNG         SAI
                                    /              \
                      [ CẤP 2: ĐỎ - HÚ CÒI ]     [ h_15m >= 15 cm HOẶC Mưa >= 30 mm/h? ]
                      (Báo trước 15-30 phút)               /              \
                                                         ĐÚNG             SAI
                                                         /                  \
                                             [ CẤP 1: VÀNG - CẢNH BÁO ]  [ CẤP 0: XANH ]
                                             (Theo dõi khơi thông cống)   (An toàn)
```

* **Đoạn mã C++ thực thi dự báo trước trên ESP32**:
```cpp
// Tính toán dự phóng tương lai 15 phút ngay tại thời điểm t
float v_rise = (water_rise_5m_cm > 0) ? (water_rise_5m_cm / 5.0) : 0.0; // cm/phút
float rain_impact = (rain_rate_mmh > 30.0) ? (rain_rate_mmh * 0.05) : 0.0;
float projected_15m = water_level_cm + (v_rise * 15.0) + rain_impact;

if (water_level_cm >= 25.0 || projected_15m >= 25.0 || (water_level_cm >= 15.0 && v_rise >= 0.8)) {
    risk_level = 2; // ĐỎ: HÚ CÒI BÁO ĐỘNG ĐÓN ĐẦU TRƯỚC 15 PHÚT!
} else if (water_level_cm >= 15.0 || projected_15m >= 15.0 || rain_rate_mmh >= 30.0) {
    risk_level = 1; // VÀNG: Cảnh báo theo dõi chuẩn bị
} else {
    risk_level = 0; // XANH: An toàn
}
```

* **Khả năng hoạt động khi mất mạng**: Nếu mưa bão làm mất sóng WiFi hoặc đứt cáp Internet, chip ESP32 vẫn tự động chạy đoạn mã Cây quyết định này để tính toán ngoại suy và hú còi đón đầu tại chỗ, không phụ thuộc máy chủ.

---

## 6. SƠ ĐỒ ĐẤU NỐI PHẦN CỨNG THỰC TẾ

```
               ┌──────────────────────────────────────────────┐
               │         BO MẠCH ĐIỀU KHIỂN ESP32             │
               └───────┬──────────────┬──────────────┬────────┘
                       │              │              │
       ┌───────────────┘              │              └───────────────┐
       ▼                              ▼                              ▼
[ CẢM BIẾN SIÊU ÂM ]         [ CẢM BIẾN MƯA ]             [ CỤM PHÁT TÍN HIỆU ]
• Chân TRIG: GPIO 18         • Chân Analog: GPIO 34       • LED Xanh : GPIO 25
• Chân ECHO: GPIO 19         • Đo mưa tức thời            • LED Vàng : GPIO 26
• Đo khoảng cách nước                                     • LED Đỏ   : GPIO 27
                                                          • Còi hú   : GPIO 32
                                                          • LCD 1602 : I2C (SDA/SCL)
```

---

## 7. KẾT LUẬN & ĐIỂM SÁNG KHI ĐI THI STEM

1. **Đúng tầm học sinh cấp 3**: Không dùng dữ liệu viển vông, tự làm mạch, tự lập trình, giải quyết đúng nỗi lo ngập sân trường có thật của trường mình.
2. **Trực quan dễ chấm thi**: Tại bàn thuyết trình, chỉ cần dùng một ca nước đổ vào mô hình hố ga để cảm biến đo, đèn LED và còi hú sẽ lập tức nhảy trạng thái theo đúng kịch bản trước mắt ban giám khảo.
3. **Chi phí tiết kiệm**: Toàn bộ linh kiện phần cứng (ESP32, cảm biến siêu âm, cảm biến mưa, đèn còi, nguồn) chỉ dao động dưới **300.000 – 400.000 VNĐ**, hoàn toàn nằm trong khả năng tự trang bị của học sinh.
