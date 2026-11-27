# V1: kết quả sơ bộ trên dữ liệu Onion thật, chạy local

Ngày: 2026-11-27. Chạy cùng `quick_v1.py` được nhúng trong notebook Kaggle V1, trên Python 3.10 CPU. **Không phải kết quả thực thi Kaggle**; nhóm cần chạy lại notebook trên Kaggle để xác nhận runtime đó.

## Dữ liệu và cấu hình

- Đọc 500.000 dòng đầu count, chọn user theo thứ tự xuất hiện, giữ tối đa 100 cặp/user; user có ít nhất 5 cặp. Đây là mẫu có thiên lệch thứ tự nguồn, không ngẫu nhiên và không đại diện toàn dataset.
- Giữ được 694 user, 62.609 cặp; 61.221 train, 694 validation, 694 test.
- Catalog giữ 109.269 ID genre, nhưng **không có nghĩa 109.269 bài có tương tác train**. Chưa có original metadata/audio.
- Hash leave-two-out, seed 42, không temporal. Chỉ train dùng để fit và tính popularity/profile; test mask thêm validation.
- ALS 32 factors, 8 iterations, regularization 0,05, confidence alpha 20, CPU 4 threads.
- Hybrid weights 0,5 ALS / 0,4 content / 0,1 popularity; chưa tune bằng kết quả test.
- Đánh giá 100/694 eligible user mỗi split, cùng seed/sample cho các phương pháp; xét toàn catalog ứng viên.

## Kết quả

| Split | Phương pháp | Recall@10 | NDCG@10 | MRR@10 | Precision@10 |
|---|---|---:|---:|---:|---:|
| Validation | Popularity | 0,000 | 0,00000 | 0,00000 | 0,000 |
| Validation | Content | 0,010 | 0,00315 | 0,00125 | 0,001 |
| Validation | ALS | 0,140 | 0,06360 | 0,04070 | 0,014 |
| Validation | Hybrid | 0,130 | 0,07046 | 0,05186 | 0,013 |
| Test | Popularity | 0,010 | 0,01000 | 0,01000 | 0,001 |
| Test | Content | 0,000 | 0,00000 | 0,00000 | 0,000 |
| Test | ALS | 0,120 | 0,06934 | 0,05354 | 0,012 |
| Test | Hybrid | 0,160 | 0,10073 | 0,08208 | 0,016 |

Thời gian riêng fit ALS khoảng 0,42 giây, evaluation khoảng 0,95 giây validation và 0,90 giây test trên môi trường local này. **Không bao gồm** đọc prefix, tải thư viện, chuẩn bị/chuẩn hóa toàn bộ genre, tạo mapping, export/hashing artifact; không dùng các con số này để hứa notebook Kaggle chạy trong vài giây.

## Diễn giải và giới hạn

Mỗi user có một bài holdout ở mỗi split nên Recall@10 bằng tỷ lệ user có bài holdout xuất hiện trong Top-10. Hybrid tìm lại bài test cho 16/100 user trong mẫu này. Content bằng 0 trên test là kết quả cần giữ nguyên; không đủ để kết luận content vô ích, vì genre đơn giản, nhiều bài có vector giống nhau, nhiều cold item và sample nhỏ có thể làm metric nhạy với thứ tự/tập ứng viên.

Đây chỉ là baseline kiểm tra pipeline bằng dữ liệu thật. Không khẳng định hybrid tốt hơn trên mọi tập, không báo cáo temporal/trending hoặc production quality. Không điều chỉnh cấu hình dựa trên test sau khi nhìn kết quả; khi mở rộng thí nghiệm, dùng validation và giữ đánh giá test cuối độc lập.

Artifact model/mapping/sparse matrix và ví dụ gợi ý giữ ngoài Git trong thư mục `artifacts/`; chỉ commit báo cáo tổng hợp này. Thực hiện 12 unit/integration training tests: passed; notebook kiểm tra syntax, source nhúng khớp source gốc, outputs rỗng: passed; Ruff/compileall/diff check: passed.
