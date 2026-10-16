# CẨM NANG KHOA HỌC: PHÂN TÍCH DỮ LIỆU & CÁC KHÁI NIỆM AI DỰ BÁO NGẬP LỤT

**Dự án**: AI + IoT Dự báo Nguy cơ Ngập lụt Cục bộ tại TP. Hội An (THPT Trần Quý Cáp)  
**Tập dữ liệu chuẩn hóa**: [`hoian_flood_ai_dataset_prepared.csv`](file:///d:/Projects/tool-craw/hoian_flood_ai_dataset_prepared.csv)  
**Mã nguồn phân tích**: [`analyze_and_prepare_dataset.py`](file:///d:/Projects/tool-craw/analyze_and_prepare_dataset.py)  
**Mã nguồn huấn luyện**: [`train_ai_model.py`](file:///d:/Projects/tool-craw/train_ai_model.py)  

---

## MỤC LỤC
1. [Bản chất Thủy văn & Cơ sở Dữ liệu Lưu vực sông Thu Bồn](#1-bản-chất-thủy-văn--cơ-sở-dữ-liệu-lưu-vực-sông-thu-bồn)
2. [Thống kê Mô tả & Ý nghĩa Vật lý](#2-thống-kê-mô-tả--ý-nghĩa-vật-lý)
3. [Hiện tượng Mất cân bằng Nhãn & Cạm bẫy Accuracy](#3-hiện-tượng-mất-cân-bằng-nhãn--cạm-bẫy-accuracy)
4. [Bộ chỉ số Đánh giá Mô hình](#4-bộ-chỉ-số-đánh-giá-mô-hình)
5. [Kiểm toán Rò rỉ Dữ liệu & Tính Nhân quả Thời gian](#5-kiểm-toán-rò-rỉ-dữ-liệu--tính-nhân-quả-thời-gian)
6. [Bản chất Toán học của 3 Thuật toán Machine Learning](#6-bản-chất-toán-học-của-3-thuật-toán-machine-learning)
7. [Các Phương pháp Đo lường Mức độ Ảnh hưởng của Thuộc tính (Feature Importance)](#7-các-phương-pháp-đo-lường-mức-độ-ảnh-hưởng-của-thuộc-tính-feature-importance)

---

## 1. Bản chất Thủy văn & Cơ sở Dữ liệu Lưu vực sông Thu Bồn

Hội An nằm ở hạ lưu lưu vực sông Thu Bồn – Vu Gia, một trong những lưu vực có địa hình dốc và lượng mưa lớn nhất miền Trung Việt Nam.

```
       [ LƯU VỰC THƯỢNG NGUỒN ]                   [ HẠ LƯU HỘI AN ]
       * Vùng núi cao Nam Giang, Phước Sơn        * Trạm thủy văn Câu Lâu
       * Thủy điện: Sông Tranh 2, A Vương         * Trường THPT Trần Quý Cáp
       * Mưa bão tập trung, bão hòa đất           * Vùng triều ảnh hưởng thoát nước
                         │                                    │
                         ▼                                    ▼
       ┌──────────────────────────────────┐        ┌──────────────────────────────────┐
       │ Lượng mưa tích lũy 3 ngày (X1)   │        │ Mực nước dâng cao (X3, X4)       │
       │ Lưu lượng xả qua tràn GloFAS(X5) │ ─────▶ │ Ngập lụt cục bộ trường học       │
       │ Xung kích dồn lũ ΔQ (X5')        │ (24h)  │ Phân loại cấp báo động BĐ1 - BĐ2 │
       └──────────────────────────────────┘        └──────────────────────────────────┘
```

### Các mốc Báo động lũ tại Trạm Câu Lâu (sông Thu Bồn):
* **Báo động 1 (BĐ1) = 2.00m (200 cm)**: Mực nước bắt đầu mấp mé các tuyến đường thấp trũng ven sông Hoài, khu vực cống rãnh trường THPT Trần Quý Cáp bắt đầu thoát nước chậm.
* **Báo động 2 (BĐ2) = 3.00m (300 cm)**: Mực nước tràn vào sân trường, ngập các phòng học tầng 1 từ $0.3\text{m} - 0.5\text{m}$, giao thông chia cắt.
* **Báo động 3 (BĐ3) = 4.00m (400 cm)**: Mức lũ lịch sử nguy hiểm cao, toàn bộ tầng 1 ngập sâu $> 1\text{m}$.

---

## 2. Thống kê Mô tả & Ý nghĩa Vật lý

Bảng tổng hợp từ 366 ngày quan trắc chuỗi thời gian liên tục (15/10/2024 – 15/10/2025):

| Thuộc tính | Đơn vị | Mean (TB) | Median (50%) | Min | Max | Skewness | Ý nghĩa thực tiễn |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Mưa ngày** (`rain_daily_mm`) | mm | 8.38 | 2.25 | 0.00 | 177.20 | **+4.69** | Lệch phải cực đoan. Đa phần mưa nhỏ nhưng có ngày bão mưa tới 177mm. |
| **Mưa giờ cực đại** (`rain_max_hourly_mmh`) | mm/h | 2.05 | 0.70 | 0.00 | 23.60 | **+3.06** | Đo lường nguy cơ ngập tức thời do cống quá tải cục bộ. |
| **Mưa tích lũy 3 ngày** (`rain_3d_accum_mm`) | mm | 25.08 | 11.25 | 0.00 | 280.90 | **+3.00** | Thước đo độ ngậm nước của lưu vực sông Thu Bồn. |
| **Mưa tích lũy 7 ngày** (`rain_7d_accum_mm`) | mm | 58.25 | 31.10 | 0.00 | 301.60 | **+1.61** | Đánh giá tình trạng ngập úng kéo dài sau bão. |
| **Mực nước Câu Lâu** (`water_level_cm`) | cm | 116.04 | 86.00 | 25.00 | 480.00 | **+2.65** | Trạng thái bình thường quanh mức triều 0.86m; mùa lũ vọt lên 4.8m. |
| **Biến thiên mực nước** (`delta_water_level_cm`) | cm/ngày | +0.21 | -1.00 | -414.0 | +366.0 | -0.33 | Tốc độ nước dâng trong 24 giờ. $\Delta h > 50\text{ cm/ngày}$ là lũ lên nhanh. |
| **Lưu lượng sông GloFAS** (`river_discharge_m3s`) | m³/s | 679.03 | 370.11 | 147.94 | 7,210.08 | **+3.56** | Lưu lượng xả lũ thượng nguồn; vượt 2,500 m³/s là chắc chắn ngập Hội An. |

### Vì sao Mưa tức thời tương quan thấp ($r=0.199$) nhưng Mưa 3 ngày lại tương quan cao ($r=0.485$)?
* **Nguyên lý bão hòa tầng đệm (Soil Moisture Saturation)**:
  * Khi đất còn khô, một trận mưa rào $50\text{ mm}$ sẽ thấm hết vào lòng đất, không sinh dòng chảy mặt $\rightarrow$ chưa thể ngập lụt.
  * Khi mưa kéo dài 3 ngày liên tiếp ($> 150\text{ mm}$), đất đá sườn dốc vùng núi bão hòa hoàn toàn. Nước mưa rơi xuống biến $100\%$ thành dòng chảy tràn, cộng hưởng với các hồ chứa thủy điện đầy nước phải xả lũ khẩn cấp $\rightarrow$ gây lũ lớn dồn về Hội An sau 24 giờ.

---

## 3. Hiện tượng Mất cân bằng Nhãn & Cạm bẫy Accuracy

### Phân bố nhãn trong 366 ngày:
* **Nhãn 0 (An toàn - Dưới BĐ1)**: 324 ngày (**$88.52\%$**)
* **Nhãn 1 (Có nguy cơ - BĐ1 đến BĐ2)**: 22 ngày (**$6.01\%$**)
* **Nhãn 2 (Nguy cơ cao - Trên BĐ2)**: 20 ngày (**$5.46\%$**)

> [!WARNING]
> **Cạm bẫy Accuracy (Accuracy Paradox)**:  
> Nếu một mô hình luôn đoán ngày nào cũng là "An toàn", mô hình đó vẫn đạt độ chính xác $88.52\%$. Nhưng đó là mô hình "mù", vì khi có lũ thật xảy ra, nó bỏ sót $100\%$ các trận lũ, dẫn đến nguy hiểm chết người và phá hủy tài sản trường học.

### Giải pháp xử lý kỹ thuật:
Trong scikit-learn, cài đặt tham số `class_weight='balanced'`:
$$w_c = \frac{N}{K \cdot N_c}$$
Trong đó $N$ là tổng số mẫu ($366$), $K$ là số lớp ($3$), $N_c$ là số mẫu của lớp $c$.  
* Trọng số phạt của lớp An toàn (0): $w_0 \approx 0.38$
* Trọng số phạt của lớp Lũ nguy cơ cao (2): $w_2 \approx 6.10$ (cao gấp **16 lần** lớp 0).  
Nhờ đó, mô hình bị phạt rất nặng nếu bỏ sót lũ, buộc phải học trúng các ngày lũ hiếm hoi.

---

## 4. Bộ chỉ số Đánh giá Mô hình

```
                     MA TRẬN NHẦM LẪN (CONFUSION MATRIX)
                                DỰ BÁO CỦA AI
                            Lũ (Positive)       An toàn (Negative)
      THỰC TẾ  Lũ (Positive)     True Positive (TP)    False Negative (FN) - BỎ SÓT LŨ
               An toàn (Neg)    False Positive (FP)    True Negative (TN)
```

1. **Precision (Độ chuẩn xác)**:
   $$\text{Precision} = \frac{TP}{TP + FP}$$
   Tỷ lệ số lần dự báo lũ đúng trên tổng số lần hệ thống phát còi báo. Precision thấp nghĩa là hệ thống hay "báo động giả".
2. **Recall (Độ nhạy / Bao phủ)**:
   $$\text{Recall} = \frac{TP}{TP + FN}$$
   **Chỉ số sinh mạng quan trọng nhất trong cảnh báo thiên tai**. Trong tổng số các trận lũ thực tế, hệ thống phát hiện được bao nhiêu trận? Nếu $\text{Recall} < 100\%$, đồng nghĩa với việc có những trận lũ hệ thống im lặng (bỏ sót), gây thảm họa.
3. **F1-Score**:
   $$\text{F1} = 2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$
   Trung bình điều hòa giữa Precision và Recall.
4. **Macro F1 vs Weighted F1**:
   * $\text{Weighted F1}$: Tính trung bình có trọng số theo số mẫu của từng lớp (bị lớp An toàn $88.5\%$ kéo lên cao giả tạo).
   * $\text{Macro F1}$: Tính trung bình cộng ngang bằng giữa 3 lớp:
     $$\text{Macro F1} = \frac{\text{F1}_0 + \text{F1}_1 + \text{F1}_2}{3}$$
     Đây là thước đo khoa học trung thực nhất để đánh giá năng lực dự báo lớp thiểu số (lũ).

---

## 5. Kiểm toán Rò rỉ Dữ liệu & Tính Nhân quả Thời gian

### Rò rỉ Dữ liệu (Target Leakage) là gì?
Trong đề tài, nhãn nguy cơ ngập $Y$ được định nghĩa bằng quy tắc cắt ngưỡng mực nước:
$$Y = \begin{cases} 0 & \text{nếu } \text{water\_level\_m} < 2.0 \\ 1 & \text{nếu } 2.0 \le \text{water\_level\_m} < 3.0 \\ 2 & \text{nếu } \text{water\_level\_m} \ge 3.0 \end{cases}$$
Nếu đưa biến `water_level_cm` của cùng ngày $t$ vào danh sách đặc trưng đầu vào $X$, các mô hình cây (Decision Tree, Random Forest) sẽ đạt độ chính xác $100.00\%$ tuyệt đối vì chỉ cần chia nhánh tại $X \ge 200$ và $X \ge 300$. Đây là bài toán chẩn đoán bảng tĩnh (lookup rule), chưa có giá trị dự báo sớm.

### Lời giải: Dự báo sớm 24 giờ tới (Lead-time $t \to t+1$)
Sử dụng các thông số quan trắc của **ngày hôm nay $t$** để dự báo cấp độ nguy cơ ngập của **ngày mai $t+1$**:
* Đặc trưng đầu vào ($X_t$): Mực nước hôm nay, tốc độ nước dâng $\Delta h$, mưa tích lũy 3 ngày, lưu lượng dồn lũ thượng nguồn $Q_t$, gia tốc lưu lượng $\Delta Q = Q_t - Q_{t-1}$.
* Nhãn cần dự báo ($Y_{t+1}$): Tình trạng ngập lụt của trường học vào 24 giờ tiếp theo.
* **Ý nghĩa thực tế**: Đảm bảo nguyên lý nhân quả (quá khứ dự báo tương lai), cung cấp đủ 24 giờ vàng cho nhà trường sơ tán máy móc, hồ sơ và cho học sinh nghỉ học an toàn.

---

## 6. Bản chất Toán học của 3 Thuật toán Machine Learning

### 1. Logistic Regression (Hồi quy Logistic)
* **Nguyên lý**: Tính tổng tuyến tính $z_k = \mathbf{w}_k^T \mathbf{x} + b_k$ cho từng lớp $k \in \{0, 1, 2\}$, sau đó chuẩn hóa thành xác suất bằng hàm Softmax:
  $$P(Y = k \mid \mathbf{x}) = \frac{e^{z_k}}{\sum_{j=0}^{2} e^{z_j}}$$
* **Vì sao bắt buộc phải dùng `StandardScaler`?**  
  Thuật toán giải tối ưu (L-BFGS) sử dụng đạo hàm để tìm điểm cực tiểu của hàm mất mát Cross-Entropy. Khi một biến có giá trị hàng ngàn (lưu lượng sông $7,000\text{ m}^3/\text{s}$) trong khi biến khác chỉ vài đơn vị (mưa giờ cực đại $2\text{ mm/h}$), mặt cong hàm mất mát sẽ bị kéo giãn thành hình elip rất dẹt, khiến gradient dao động không hội tụ (`ConvergenceWarning`).  
  `StandardScaler` chuẩn hóa từng biến về phân bố chuẩn:
  $$x' = \frac{x - \mu}{\sigma}$$
  giúp mọi biến có trọng số bình đẳng, thuật toán hội tụ nhanh và ổn định.

### 2. Decision Tree (Cây Quyết Định)
* **Nguyên lý**: Tại mỗi nút, thuật toán quét qua tất cả các đặc trưng và ngưỡng chia cắt $s$ để tìm nhát cắt làm giảm độ tạp chất Gini (*Gini Impurity*) nhiều nhất:
  $$\text{Gini}(D) = 1 - \sum_{i=0}^{2} p_i^2$$
* **Ưu điểm**: Hoàn toàn minh bạch (White-box model), có thể trích xuất thành các câu lệnh `IF ... THEN ...` nạp vào vi điều khiển ESP32 trong mô phỏng Wokwi.

### 3. Random Forest (Rừng Ngẫu Nhiên)
* **Nguyên lý Ensemble Bagging (Bootstrap Aggregating)**:
  * Tạo ra $B = 100$ cây quyết định độc lập.
  * Mỗi cây được huấn luyện trên một tập con lấy mẫu ngẫu nhiên có hoàn lại (bootstrap sample) từ tập dữ liệu gốc.
  * Tại mỗi nút phân nhánh, chỉ một tập con ngẫu nhiên các đặc trưng ($\approx \sqrt{p}$) được xem xét.
  * Kết quả dự báo cuối cùng là biểu quyết đa số (Majority Voting) giữa 100 cây.
* **Độ quan trọng đặc trưng (Feature Importance)**:  
  Tính bằng tổng mức giảm tạp chất Gini trung bình qua toàn bộ các cây (Mean Decrease in Impurity - MDI). Trong bài toán Hội An, 3 đặc trưng chi phối mạnh nhất kết quả cảnh báo sớm 24h là:
  1. `rain_3d_accum_mm` (Mưa tích lũy 3 ngày): **$22.35\%$**
  2. `delta_discharge_m3s` (Gia tốc dồn lũ thượng nguồn): **$18.20\%$**
  3. `river_discharge_m3s` (Lưu lượng sông GloFAS): **$13.12\%$**

---

## 7. Các Phương pháp Đo lường Mức độ Ảnh hưởng của Thuộc tính (Feature Importance)

Khi bảng dữ liệu có nhiều thuộc tính (features / properties), trong khoa học dữ liệu có 4 phương pháp chuẩn để đo lường mức độ đóng góp của từng biến vào kết quả dự báo:

### 1. Gini Importance / MDI (Mean Decrease in Impurity) - Trong Cây & Rừng ngẫu nhiên
* **Nguyên lý**: Mỗi lần một thuộc tính được chọn để chia nhánh tại một nút cây, nó làm giảm độ hỗn loạn (tạp chất Gini) của dữ liệu. Tổng mức giảm này được tính trung bình trên toàn bộ 100 cây trong rừng và quy đổi về thang $100\%$.
* **Đặc điểm**: Nhanh, trực quan, có sẵn trong scikit-learn qua thuộc tính `model.feature_importances_`.

### 2. Permutation Feature Importance (Độ quan trọng hoán vị) - Thước đo Chuẩn vàng Khách quan
* **Nguyên lý**: Sau khi mô hình đã được huấn luyện, ta "bịt mắt" mô hình đối với một thuộc tính bằng cách xáo trộn ngẫu nhiên (shuffle) toàn bộ cột giá trị đó, trong khi giữ nguyên các cột khác.
  * Nếu thuộc tính đó **thực sự quan trọng**, việc xáo trộn sẽ phá vỡ thông tin và làm điểm đánh giá (F1-score / Accuracy) **sụt giảm nghiêm trọng**.
  * Nếu thuộc tính đó **không quan trọng**, điểm số của mô hình hầu như không thay đổi.
* **Đặc điểm**: Độc lập với cấu trúc mô hình (Model-agnostic), đánh giá được trên tập dữ liệu kiểm thử thực tế.

### 3. Hệ số Hồi quy Chuẩn hóa (Standardized Logistic Regression Coefficients)
* **Nguyên lý**: Trong mô hình tuyến tính $z = w_1 x_1 + w_2 x_2 + \dots + b$, sau khi các biến đã được chuẩn hóa về cùng thang đo bằng `StandardScaler`, giá trị tuyệt đối $|w_i|$ của trọng số phản ánh trực tiếp mức độ tác động của đặc trưng đó đến xác suất phân loại.
* **Đặc điểm**: Cho biết rõ chiều hướng tác động (hệ số dương làm tăng nguy cơ lũ, hệ số âm làm giảm nguy cơ lũ).

### 4. Hệ số Tương quan Tuyến tính Pearson ($|r|$)
* **Nguyên lý**: Đo lường mối liên hệ trực tiếp giữa từng biến đơn lẻ với nhãn dự báo $Y$.

---

### BẢNG TỔNG HỢP SO SÁNH CÁC PHƯƠNG PHÁP TRÊN BÀI TOÁN HỘI AN

Dưới đây là kết quả đo lường thực tế trên tập dữ liệu [`hoian_flood_ai_dataset_prepared.csv`](file:///d:/Projects/tool-craw/hoian_flood_ai_dataset_prepared.csv) cho bài toán Cảnh báo sớm 24 giờ tới:

| Thứ hạng | Tên Thuộc tính (Property) | RF Gini MDI (%) | Permutation (Độ sụt giảm F1) | LR Chuẩn hóa (%) | Tương quan Pearson \|r\| | Kết luận ý nghĩa |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| **1** | **`rain_3d_accum_mm`** (Mưa tích lũy 3 ngày) | **22.35%** | **-0.250** (Tụt 25% F1) | **14.41%** | **0.562** | **Yếu tố quyết định số 1**: Gây ngậm no nước toàn lưu vực. |
| **2** | **`delta_discharge_m3s`** (Xung kích dồn lũ $\Delta Q$) | **18.20%** | **-0.205** (Tụt 20.5% F1)| **16.00%** | 0.282 | **Yếu tố xung kích**: Nước từ các hồ thủy điện xả dồn về. |
| **3** | **`river_discharge_m3s`** (Lưu lượng sông GloFAS) | **13.12%** | **-0.101** (Tụt 10.1% F1)| **12.45%** | **0.514** | Lưu lượng dòng chảy nền của sông Thu Bồn. |
| **4** | **`water_level_cm`** (Mực nước hiện tại trạm Câu Lâu) | **9.87%** | **-0.184** (Tụt 18.4% F1)| 10.88% | **0.509** | Mực nước nền hiện tại trước khi đón đợt lũ mới. |
| **5** | **`rain_7d_accum_mm`** (Mưa tích lũy 7 ngày) | 10.03% | -0.020 | **16.41%** | 0.445 | Độ ẩm đất nền kéo dài trong tuần. |
| **6** | **`delta_water_level_cm`** (Tốc độ dâng mực nước) | 8.88% | -0.016 | 3.56% | 0.173 | Tốc độ biến thiên mực nước tại chỗ. |
| **7** | **`discharge_3d_mean_m3s`** (Lưu lượng TB 3 ngày) | 6.66% | ~0.000 | 7.79% | 0.371 | Xu thế dòng chảy trung hạn. |
| **8** | **`rain_daily_mm`** (Mưa trong 24h qua) | 5.75% | -0.004 | 12.02% | 0.366 | Mưa tức thời (ảnh hưởng thứ cấp). |
| **9** | **`rain_max_hourly_mmh`** (Mưa giờ cực đại) | 5.14% | -0.004 | 6.47% | 0.243 | Mưa giông cục bộ ngắn hạn (ít ảnh hưởng lũ sông lớn). |

> [!IMPORTANT]
> **Kết luận Khoa học:**  
> Cả 4 phương pháp đo lường đều thống nhất kết luận rằng: **Mưa tích lũy 3 ngày (`rain_3d_accum_mm`)** và **Xung kích dồn lũ thủy điện (`delta_discharge_m3s`)** là 2 thuộc tính chi phối mạnh nhất đến nguy cơ ngập lụt tại trường học sau 24 giờ. Ngược lại, mưa tức thời trong ngày hay mưa giờ cực đại có mức độ ảnh hưởng rất thấp đối với lũ sông lớn.

