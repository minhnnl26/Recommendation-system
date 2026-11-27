# Bản thuyết trình bổ sung dữ liệu Music4All-Onion

File: `HUST_Music_Recommendation_Data_Updated.pptx`.

- Giữ template HUST, các slide và hình gốc; thêm 5 slide, tổng cộng 19 slide.
- Phần dữ liệu nằm ở slide 6–13: nguồn, schema TSV thật, genre/tags, chất lượng,
  phân bố thể loại, độ phủ và xử lý dự kiến. Ba biểu đồ được vẽ từ EDA đã đo.
- Chuyển slide iTunes/Jamendo gốc vào cuối phần dữ liệu, trước kiến trúc.
- Điều chỉnh mô tả đầu vào ALS/content-based cho khớp play count và genre hiện có.
- Giữ nội dung phần giới thiệu, chỉnh cỡ chữ để vừa textbox.
- Có speaker notes giải thích phạm vi, mẫu số và hạn chế cho phần bổ sung.
- Đã mở bằng Microsoft PowerPoint, kết xuất toàn bộ 19 slide và kiểm tra chiều cao
  text/ô bảng: không còn cảnh báo tràn. Đã kiểm tra ảnh xem trước.
- SHA-256 file gốc và snapshot trùng nhau: file gốc không bị sửa.

Số liệu sử dụng từ `docs/eda/music4all-onion/metrics.json`. Không trình bày kết quả
huấn luyện, xu hướng thời gian hoặc playback như tính năng đã hoàn thành.

## Tạo lại

```bash
cd recommender/eda
uv run --with python-pptx==1.0.2 python build_data_slides.py
```

Script mặc định đọc bản snapshot ở `data/presentations/source_snapshot.pptx`, tạo
file mới ở `docs/presentations/`. Dữ liệu raw và thư mục preview nằm trong `data/`
đã Git ignore. `presentation_manifest.json` ghi checksum và số slide;
`preview_data_slides.jpg` là ảnh xem nhanh slide 6–13.
