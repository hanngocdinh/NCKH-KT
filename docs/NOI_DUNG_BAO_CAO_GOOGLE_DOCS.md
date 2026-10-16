# BẢN MÔ TẢ ĐỀ TÀI: HỆ THỐNG AI + IoT CẢNH BÁO SỚM NGẬP LỤT HỘI AN
*(Dành cho học sinh, giáo viên, phụ huynh và Ban Giám hiệu trường THPT Trần Quý Cáp)*

---

## 1. MỤC TIÊU CỦA ĐỀ TÀI LÀ GÌ?
* **Tên đề tài**: Ứng dụng Trí tuệ Nhân tạo (AI) và Cảm biến Thông minh (IoT) nhằm Dự báo Nguy cơ Ngập lụt Cục bộ tại Trường THPT Trần Quý Cáp (TP. Hội An, Quảng Nam).
* **Mô hình AI**: Machine Learning (Học máy).
* **Ngôn ngữ lập trình**: Python.
* **Mục tiêu thực tế lớn nhất**: Giúp Ban Giám hiệu nhà trường biết trước nguy cơ ngập lụt **trước 24 giờ** để kịp thời:
  1. Cho toàn bộ học sinh nghỉ học ở nhà an toàn trước khi nước tràn vào trường.
  2. Kê cao bàn ghế, chuyển hồ sơ học sinh và máy tính từ tầng 1 lên tầng 2.

---

## 2. HIỂU VỀ "AI DỰ BÁO NGẬP" MỘT CÁCH ĐƠN GIẢN
* Bình thường, con người dự báo ngập dựa vào kinh nghiệm: "Thấy mưa dầm mấy ngày, nghe tin thủy điện xả lũ thì chuẩn bị dọn đồ".
* **AI trong dự án này đóng vai trò như một chuyên gia thời tiết tự động**:
  * Hệ thống cho máy tính "đọc và học" toàn bộ số liệu thời tiết thực tế của 366 ngày trong năm qua (từ các bản tin của Đài Khí tượng Thủy văn Quốc gia và vệ tinh châu Âu).
  * Máy tính sẽ tự tìm ra quy luật: Khi nào thì mưa và dòng chảy sông Thu Bồn bắt đầu vượt ngưỡng nguy hiểm để phát chuông báo động.

---

## 3. MÔ HÌNH AI CẦN BIẾT NHỮNG GÌ ĐỂ DỰ BÁO?
Để dự báo chính xác nguy cơ ngập của ngày mai, máy tính chỉ cần nhìn vào **3 nhóm thông tin quen thuộc**:

1. **Trời mưa to hay nhỏ?**
   * Lượng mưa đo được trong ngày hôm nay.
   * Lượng mưa dầm dề tích lũy trong 3 ngày qua (vì đất ngấm no nước thì nước mới tràn lên sân trường).
2. **Nước sông Thu Bồn từ thượng nguồn dồn về thế nào?**
   * Lưu lượng dòng chảy của sông Thu Bồn (qua dữ liệu dự báo quốc tế GloFAS).
   * Tốc độ xả lũ của các hồ chứa thủy điện trên núi dồn về hạ lưu.
3. **Mực nước thực tế tại trường học:**
   * Cảm biến siêu âm gắn ở cống rãnh trường học đo xem nước đang ở mức bao nhiêu cm và đang dâng nhanh hay chậm.

---

## 4. KẾT QUẢ DỰ BÁO ĐƯỢC CHIA LÀM 3 MỨC ĐỘ RÕ RÀNG

Hệ thống phân chia thành 3 mức độ cảnh báo giống như đèn tín hiệu giao thông:

| Cấp độ | Tên gọi | Dấu hiệu nhận biết | Phản hồi thiết bị | Nhà trường cần làm gì? |
| :---: | :--- | :--- | :---: | :--- |
| **Mức 0** | **AN TOÀN** *(Xanh)* | Trời nắng ráo hoặc chỉ mưa nhỏ, nước dưới cống thấp. | Đèn XANH bật, còi tắt. | Dạy và học bình thường. |
| **Mức 1** | **CÓ NGUY CƠ** *(Vàng)* | Mưa bắt đầu lớn, cống rãnh thoát nước chậm, mấp mé sân. | Đèn VÀNG bật, còi tắt. | Kê cao thiết bị phòng máy tính tầng 1, nạo vét cống rãnh. |
| **Mức 2** | **LŨ NGUY CƠ CAO** *(Đỏ)* | Mưa 3 ngày rất lớn, thủy điện xả tràn dồn dập, nước dâng nhanh. | **Đèn ĐỎ nhấp nháy, CÒI HÚ LIÊN TỤC**. | **[KHẨN CẤP] THÔNG BÁO CHO TOÀN TRƯỜNG NGHỈ HỌC VÀO NGÀY MAI**, ngắt cầu dao điện tầng 1. |

---

## 5. VÌ SAO CHỌN MÔ HÌNH NÀY? (AN TOÀN TÍNH MẠNG LÀ TRÊN HẾT)
* Trong các mô hình AI thử nghiệm, nhóm nghiên cứu chọn **mô hình ưu tiên bảo vệ tính mạng con người**.
* **Đặc tính vượt trội của mô hình được chọn**:
  * Phát hiện đúng **100% tất cả các trận lũ lớn nguy hiểm** trước 24 giờ (tuyệt đối không bỏ sót trận lũ nào).
  * Thà báo sớm hơn một chút để thầy cô và học sinh chủ động phòng tránh, còn hơn là im lặng để nước lũ tràn vào bất ngờ.

---

## 6. BO MẠCH Ở TRƯỜNG VÀ MÁY CHỦ PHỐI HỢP THẾ NÀO?
* **Bo mạch điện tử đặt tại trường (ESP32)** đóng vai trò là **"Giác quan"**:
  * Đo mực nước tại sân trường.
  * Khi có báo động nguy hiểm, nó bật đèn đỏ và hú còi cảnh báo tại chỗ.
  * Nếu bão làm đứt cáp quang mất mạng Internet, bo mạch vẫn tự động hú còi nếu phát hiện nước dâng vượt mức nguy hiểm.
* **Máy tính / Máy chủ trên mạng** đóng vai trò là **"Bộ não"**:
  * Nơi tổng hợp tin bão, lượng mưa toàn tỉnh và thông báo xả lũ của các hồ thủy điện trên núi.
  * Chạy mô hình AI để đưa ra cảnh báo sớm trước 24 giờ gửi về điện thoại của Ban Giám hiệu.

---

## 7. KẾT LUẬN
Đề tài đã xây dựng thành công một giải pháp công nghệ thiết thực, chi phí thấp, giúp biến những số liệu khí tượng phức tạp thành những cảnh báo màu sắc và âm thanh dễ hiểu, góp phần bảo vệ an toàn cho thầy và trò trường THPT Trần Quý Cáp trước mùa mưa bão miền Trung.
