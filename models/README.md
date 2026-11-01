# Model runtime

Thư mục current chứa đúng bundle đang dùng:

- mini_flood_15s.joblib
- mini_flood_30s.joblib
- mini_flood_60s.joblib
- mini_flood_metadata.json

Đây là bundle candidate-v2 đã train trước, nguồn synthetic, demo_approved=true và promoted=false. Metadata giữ provenance, metrics, feature signature, horizon, phiên bản thư viện và SHA256 từng artifact. Không sửa metadata để bỏ kiểm tra.

BE chỉ nạp khi mode/config phù hợp; dự báo qua model, không cần code training. Các file này cần được giữ cùng source runtime. Loader kiểm tra hash và cùng major/minor scikit-learn; requirements.txt pin phiên bản đã dùng.

Model/schema/feature window không khớp hoặc predict lỗi trả null/lý do. Mode real từ chối bundle synthetic. Không có fallback online.

Model và dataset thử nghiệm cũ đã chuyển sang archive/ai_training, không còn trong đường nạp model mặc định.
