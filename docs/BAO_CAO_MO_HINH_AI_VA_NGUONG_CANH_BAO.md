# BÁO CÁO MÔ HÌNH HỌC MÁY & MA TRẬN NGƯỠNG CẢNH BÁO
## HỆ THỐNG IoT CẢNH BÁO SỚM NGẬP CỤC BỘ TẠI SÂN TRƯỜNG (THPT TRẦN QUÝ CÁP)

**Phạm vi đề tài**: Nghiên cứu khoa học kỹ thuật cấp THPT (Học sinh lớp 10 - 12)  
**Phần cứng thực thi**: Vi điều khiển ESP32 + Cảm biến siêu âm (HC-SR04/JSN) + Cảm biến mưa  
**Mục tiêu dự báo**: Cảnh báo sớm nguy cơ ngập cục bộ tại hố ga / sân trường trước **15 đến 30 phút** (Nowcasting)  

---

## 1. TẠI SAO CẦN TINH GỌN MÔ HÌNH VỀ ĐÚNG TẦM HỌC SINH CẤP 3?

Trong giai đoạn đầu nghiên cứu, nhóm từng thử nghiệm các mô hình nạp tham số thủy văn vĩ mô (như lưu lượng sông Thu Bồn, xả lũ thủy điện vùng núi và dữ liệu vệ tinh châu Âu). Tuy nhiên, qua phân tích thực tế kỹ thuật và phản biện khoa học, nhóm đã **loại bỏ hoàn toàn các biến vĩ mô này** vì 3 lý do sống còn:

1. **Vấn đề nguồn dữ liệu**: Bo mạch IoT của học sinh đặt tại trường không có cách nào lấy được số liệu xả lũ thời gian thực từ các nhà máy thủy điện vùng cao.
2. **Sai lệch bài toán**: Ngập tại sân trường THPT Trần Quý Cáp trong những cơn mưa giông thường diễn ra do **cống thoát nước bị quá tải cục bộ hoặc rác lá cây bịt miệng hố ga**. Đây là bài toán thủy lực cục bộ vi mô trong phạm vi 15–30 phút, không phải bài toán lũ lụt sông ngòi liên tỉnh.
3. **Tính độc lập & an toàn**: Khi mưa bão xảy ra đứt cáp quang mất mạng Internet, hệ thống phải tự đo và tự ra quyết định độc lập tại chỗ trên chip ESP32.

---

## 2. PHẦN CỨNG & 4 ĐẶC TRƯNG ĐẦU VÀO CỐT LÕI

Hệ thống hoạt động chỉ với **2 cảm biến giá rẻ, dễ lắp đặt** và trích xuất đúng **4 tham số cốt lõi**:

```
[ CẢM BIẾN MƯA SÂN TRƯỜNG ] ─────────▶ 1. Cường độ mưa (rain_rate_mmh)
                                      └──▶ 2. Mưa tích lũy 15 phút (rain_sum_15m)
                                      
[ CẢM BIẾN SIÊU ÂM HỐ GA ]  ─────────▶ 3. Mực nước cống (water_level_cm)
                                      └──▶ 4. Tốc độ nước dâng 5 phút (water_rise_5m_cm)
```

| STT | Đặc trưng | Đơn vị | Phương pháp đo | Dải hoạt động |
| :---: | :--- | :---: | :--- | :---: |
| **1** | `water_level_cm` | cm | Cảm biến siêu âm chiếu tia xuống hố ga ($h = H_{\text{gắn}} - d_{\text{đo}}$) | $0 - 40\text{ cm}$ |
| **2** | `water_rise_5m_cm` | cm/5p | Hiệu số giữa mực nước hiện tại và mực nước 5 phút trước | $-10 \to +20\text{ cm}$ |
| **3** | `rain_rate_mmh` | mm/h | Tốc độ mưa đo được từ cảm biến mưa theo chu kỳ 1 phút | $0 - 100\text{ mm/h}$ |
| **4** | `rain_sum_15m` | mm | Tổng lượng mưa tích lũy trong 15 phút gần nhất | $0 - 40\text{ mm}$ |

---

## 3. CƠ CHẾ DỰ BÁO TRƯỚC (NOWCASTING 15–30 PHÚT) THAY VÌ CẢNH BÁO TỨC THỜI

Nếu chỉ so sánh mực nước hiện tại $h \ge 25\text{ cm}$ để hú còi, đó chỉ là **cảnh báo tức thời (phát hiện khi sự cố đã xảy ra)**.

Mô hình AI trong đề tài này thực hiện **Dự báo trước 15 đến 30 phút** bằng cách tính toán mực nước dự phóng trong tương lai ($h_{t+15}$):
$$h_{t+15}^{\text{dự báo}} = h_t + \left( \frac{\Delta h_{5\text{p}}}{5} \times 15 \right) + f(R)$$
* **$h_t$**: Mực nước hiện tại ở đáy hố ga ($0 - 40\text{ cm}$).
* **$\frac{\Delta h_{5\text{p}}}{5}$**: Vận tốc dâng nước trong 5 phút gần nhất ($\text{cm/phút}$).
* **$f(R)$**: Lượng nước dồn bổ sung từ cường độ mưa hiện tại $R$ ($\text{mm/h}$).

### Bảng Ma Trận Ngưỡng Dự Báo Đón Đầu:

| Cấp độ | Nhãn AI | Phản hồi thiết bị | Điều kiện kích hoạt AI (Tại thời điểm $t$) | Dự báo sau 15–30 phút | Hành động của nhà trường |
| :---: | :---: | :---: | :--- | :--- | :--- |
| **Mức 0** | **An toàn** | **LED XANH**<br>Còi TẮT | * $h < 15\text{ cm}$<br>* $\Delta h_{5\text{p}} < 2\text{ cm}$<br>* Mưa nhỏ hoặc tạnh | Trong 30 phút tới nước không thể tràn, cống thoát tốt. | Dạy và học bình thường. |
| **Mức 1** | **Có nguy cơ** | **LED VÀNG**<br>Còi TẮT | * $h \ge 15\text{ cm}$<br>* **HOẶC** $h_{t+15} \ge 15\text{ cm}$<br>* **HOẶC** $\Delta h_{5\text{p}} \ge 3\text{ cm/5p}$<br>* **HOẶC** $R \ge 25\text{ mm/h}$ | Nước sẽ dâng quá nửa hố ga sau 15–30p, mấp mé mép sân. | 1. Bác bảo vệ đi khơi thông miệng hố ga.<br>2. Thầy cô tầng 1 kê máy tính lên bàn.<br>3. Theo dõi bảng tin. |
| **Mức 2** | **Nguy hiểm cao** | **LED ĐỎ CHỚP**<br>**CÒI HÚ LIÊN TỤC** | * **$h_{t+15} \ge 25\text{ cm}$**<br>* **HOẶC** dâng xiết $\Delta h_{5\text{p}} \ge 6\text{ cm/5p}$<br>* **HOẶC** $h \ge 18\text{ cm}$ kèm mưa $> 40\text{ mm/h}$ | **Chắc chắn nước sẽ tràn lên sân trường và phòng học sau 15 phút nữa!** | **[HÀNH ĐỘNG KHẨN CẤP]**<br>1. Hú còi di tản học sinh lên tầng 2.<br>2. Ngắt cầu dao điện tầng 1 phòng giật điện.<br>3. Chốt cổng không cho ra sân. |

---

## 4. THUẬT TOÁN CÂY QUYẾT ĐỊNH DỰ BÁO TRƯỚC NẠP VÀO ESP32

Mô hình được huấn luyện với nhãn mục tiêu là **mực nước tương lai $t+15$ phút**, sau đó được biên dịch thành mã C++ gọn nhẹ chạy trực tiếp trên vi điều khiển ESP32:

```cpp
// Logic Cây quyết định DỰ BÁO ĐÓN ĐẦU TRƯỚC 15 PHÚT trên ESP32
int predictFutureRisk15m(float water_level_cm, float water_rise_5m_cm, float rain_rate_mmh) {
    // 1. Vận tốc dâng nước (cm/phút)
    float v_rise = (water_rise_5m_cm > 0) ? (water_rise_5m_cm / 5.0) : 0.0;
    
    // 2. Dự phóng mực nước sau 15 phút tới
    float rain_impact = (rain_rate_mmh > 30.0) ? (rain_rate_mmh * 0.05) : 0.0;
    float projected_15m = water_level_cm + (v_rise * 15.0) + rain_impact;

    // 3. Phân nhánh dự báo trước
    // Cấp 2: ĐỎ - Dù hiện tại chưa ngập nhưng 15 phút tới sẽ vượt 25cm (tràn sân)
    if (water_level_cm >= 25.0 || projected_15m >= 25.0 || (water_level_cm >= 15.0 && v_rise >= 0.8)) {
        return 2; // BÁO ĐỘNG ĐỎ ĐÓN ĐẦU TRƯỚC 15 PHÚT
    }

    // Cấp 1: VÀNG - Dự kiến 15 phút tới nước dâng quá nửa hố ga
    if (water_level_cm >= 15.0 || projected_15m >= 15.0 || rain_rate_mmh >= 30.0 || water_rise_5m_cm >= 3.0) {
        return 1; // CẢNH BÁO THEO DÕI
    }

    return 0; // AN TOÀN
}
```

---

## 5. KỊCH BẢN THỰC NGHIỆM ĐỂ THUYẾT TRÌNH VỚI BAN GIÁM KHẢO

Khi đi thi khoa học kỹ thuật STEM, học sinh chuẩn bị một sa bàn thu nhỏ gồm:
* 01 hộp mica giả lập hố ga cống rãnh (có gắn cảm biến siêu âm ở nắp).
* 01 cảm biến mưa đặt bên cạnh.
* 01 cụm mạch ESP32 nối với màn hình LCD 1602, 3 bóng LED Xanh/Vàng/Đỏ và còi buzzer.

**Quy trình biểu diễn trực tiếp (Demo):**
1. **Trạng thái ban đầu**: Hộp mica cạn nước $\rightarrow$ Màn hình hiện `Muc nuoc: 2 cm`, **LED Xanh sáng**, còi tắt.
2. **Diễn tập Mức 1 (Vàng)**: Rót nước từ từ vào hộp đạt mức $17\text{ cm}$ $\rightarrow$ **LED Vàng lập tức bật sáng**, LCD hiện `CANH BAO NGUY CO`.
3. **Diễn tập Mức 2 (Đỏ)**: Rót tiếp nước chạm vạch $26\text{ cm}$ $\rightarrow$ **LED Đỏ nhấp nháy, còi buzzer hú to liên tục**, đồng thời bot Telegram trên điện thoại nhận ngay tin nhắn: `⚠️ [KHẨN CẤP] Nước hố ga mấp mé sân trường (26cm), kích hoạt sơ tán!`.

---

## 6. KẾT LUẬN

Việc tinh giản mô hình từ 9 tham số lý thuyết xa vời xuống **4 tham số cục bộ đo được bằng 2 cảm biến giá rẻ**:
* Đưa đề tài về đúng bản chất khoa học kỹ thuật của học sinh phổ thông: **Tự thiết kế - Tự đo đạc - Tự lập trình - Kiểm chứng được ngay**.
* Đảm bảo tính khả thi $100\%$ khi triển khai thực tế tại Trường THPT Trần Quý Cáp với chi phí linh kiện chỉ khoảng **350.000 VNĐ**.
