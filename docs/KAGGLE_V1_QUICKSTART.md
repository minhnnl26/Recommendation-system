# Kaggle V1: chạy trước để có model và bảng kết quả

Notebook tự chứa code: [`music4all_kaggle_v1_quick.ipynb`](../recommender/notebooks/music4all_kaggle_v1_quick.ipynb). Không cần upload code ZIP, clone GitHub hoặc xin audio trước. Nhu cầu full Music4All vẫn giữ cho giai đoạn sau.

## Các bước gửi cho bạn training

1. Nhận hai file Onion: `userid_trackid_count.tsv.bz2` và `id_genres_tf-idf.tsv.bz2`. Không gửi `.env`, key, token hoặc mật khẩu. Không cần audio/lyrics/timestamp cho V1.
2. Kaggle → New Notebook → Import Notebook → chọn notebook V1. Có thể tải file notebook từ GitHub bằng Download raw file.
3. Tạo private Dataset chứa hai file còn đuôi `.tsv.bz2`; Add Input vào notebook. Chỉ attach một bản mỗi file để auto-find không chọn nhầm.
4. Bật Internet để cài thư viện. Dùng CPU, Python 3.10–3.12; không cần bật GPU.
5. Chạy Run All. Cell đầu ghi code đã nhúng vào working và cài requirements; các bước training chạy trong subprocess mới, không cần chỉnh đường dẫn code.
6. Khi hoàn tất, xem bảng validation/test của popularity, content, ALS, hybrid; xem 10 bài gợi ý ví dụ. Nếu metric thấp/bằng 0, giữ nguyên kết quả.
7. Save Version → Save & Run All để lưu outputs; tải ZIP được notebook tạo hoặc lấy ZIP trong Output. Không đóng phiên chưa lưu.
8. Gửi nhóm `metrics_summary.csv`, `config.json`, `v1_sampling.json`, `prepared/manifest.json`, ảnh bảng kết quả; gửi cả ZIP model/mapping qua Drive/private Dataset cho backend.

## V1 giới hạn gì để chạy nhẹ hơn?

| Tham số | Giá trị mặc định |
|---|---:|
| Dòng đầu count được đọc tối đa | 500.000 |
| User lấy theo thứ tự file tối đa | 1.000 |
| Cặp user–bài giữ tối đa mỗi user | 100 |
| Số cặp tối thiểu để giữ một user | 5 |
| Số chiều ALS | 32 |
| Số vòng ALS | 8 |
| User đánh giá tối đa mỗi split | 100 |
| Top-K | 10 |

Đây là **sample theo prefix/thứ tự file**, không ngẫu nhiên, có thể thiên lệch và **không phải train toàn bộ dataset**. Giữ mọi ID genre trong catalog, nhưng chỉ sample tương tác để fit. Chia hash leave-two-out, chưa có temporal split hoặc xu hướng gần đây. Hai lần chạy cùng input/config cho cùng sample/split; floating-point/thread có thể gây khác biệt số học nhỏ.

Không hứa thời gian cụ thể trên Kaggle khi chưa đo runtime đó. V1 giảm khối lượng fit/eval và không scan toàn bộ 50 triệu dòng; lần cài thư viện/upload input vẫn có thể mất thời gian. Sau khi có baseline, tăng sample hoặc chuyển notebook đầy đủ, không sửa số liệu hay gọi V1 là full.

## Kết quả cần có

- `model/als.npz`: model.
- `prepared/`: mapping ID, genre và ma trận train/validation/test.
- `metrics.json`, `metrics_summary.csv`: metric/time của các phương pháp.
- `v1_sampling.json`, `config.json`: mẫu và cấu hình thực tế.
- `artifact_manifest.json`: hashes các artifact training.
- `recommendations_example.json`: ví dụ gợi ý do notebook tạo sau training; không nằm trong manifest training ban đầu.

Không có tên bài/audio trong input nên response là `Track <ID>`, metadata/audio path null. Đây là kết quả gợi ý nghiên cứu, chưa phát nhạc hoặc tự thay model trong `/research`.

## Việc của các bạn khác khi training chạy

- **Backend:** chốt contract ID dạng chuỗi, nạp artifact/mapping đúng version một lần, thêm API ALS và tests; không train trong request, không tự tạo/reset database.
- **Frontend:** chuẩn bị UI chọn genre/user, danh sách Top-N và lý do, loading/error/empty; hiển thị Track ID khi thiếu metadata, không bật Play khi chưa có audio.
- **Người tổng hợp báo cáo:** ghi đúng sample/hash split, số user/item/pairs, so sánh metric; dùng validation để chọn cấu hình, giữ test cho báo cáo cuối.
- **Data:** xin Music4All gốc, bổ sung metadata/audio 30 giây sau; tải timestamp khi làm đánh giá theo thời gian.

**Commit:** source/config/tests, notebook xóa output và báo cáo metric tổng hợp nhỏ đã review. **Không commit:** raw data, model/CSR, ZIP, `.env`, token, notebook output chứa lịch sử/đường dẫn riêng. Chia sẻ artifact qua kho riêng. Checklist chi tiết ở [TEAM_NEXT_STEPS.md](TEAM_NEXT_STEPS.md).

## Chạy cùng V1 ở máy local

```bash
uv sync --project recommender/training --dev --locked
uv run --project recommender/training python recommender/training/quick_v1.py \
  --onion-root data/raw/music4all-onion \
  --output artifacts/music4all-v1-run-001 \
  --scratch /tmp/music4all-v1-run-001
```

Output và scratch phải là đường dẫn mới. Script không ghi đè run cũ. Notebook tự đặt run ID theo thời gian để tránh lỗi này.
