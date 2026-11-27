# Last.fm 1K EDA

Phân tích **toàn bộ TSV gốc** để so sánh với metadata iTunes/Jamendo của dự án.
Last.fm cung cấp lịch sử nghe có timestamp; không thay thế catalog có album,
duration, ảnh và audio URL. Không huấn luyện mô hình hoặc gọi database trong EDA.

## Tải dữ liệu

Chạy từ repository root. File khoảng 639 MB nén, TSV giải nén khoảng 2,4 GB.
DuckDB trung gian cần thêm dung lượng và có thể spill ra đĩa.
Job đặt giới hạn bộ nhớ DuckDB 2 GB, một thread; loại trùng theo 16 bucket user
để tránh gom toàn bộ event vào một hash table lớn. Đây không phải lấy mẫu.

```bash
mkdir -p data/raw/lastfm-1k
curl -fL --retry 2 --output data/raw/lastfm-1k/events.tsv.zip \
  https://github.com/eifuentes/lastfm-dataset-1K/releases/download/v1.0/userid-timestamp-artid-artname-traid-traname.tsv.zip
curl -fL --output data/raw/lastfm-1k/README.txt \
  https://github.com/eifuentes/lastfm-dataset-1K/releases/download/v1.0/README.txt
```

Nguồn gốc: Òscar Celma, MTG/UPF, Last.fm 1K. Mirror chỉ đóng gói lại file gốc;
script kiểm tra MD5 TSV theo README (`64747b21563e3d2aa95751e0ddc46b68`).
Phải giữ dẫn nguồn Last.fm và điều kiện phi thương mại trong README đi kèm.
Không tải dữ liệu audio hoặc dữ liệu profile nhân khẩu học.

## Chạy lại

```bash
cd recommender/eda
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python lastfm_eda.py
```

`pyproject.toml` và `uv.lock` là môi trường EDA riêng, không sửa dependencies
backend. Script không truy cập mạng, không import backend settings và không đọc
file `.env`. Lệnh có thể chạy từ thư mục khác vì mặc định resolve theo source.

## Đầu ra

- `docs/eda/lastfm-1k/REPORT.md`: báo cáo tiếng Việt với đối chiếu schema,
  chất lượng raw, quyết định cleaning và ý nghĩa với recommender.
- `docs/eda/lastfm-1k/metrics.json`: số liệu chính xác có thể tái sử dụng.
- `docs/eda/lastfm-1k/manifest.json`: checksum, version, thời điểm chạy và phạm vi.
- `docs/eda/lastfm-1k/overview.png`, `missing_fields.png`: biểu đồ cho slide.
- `data/processed/lastfm-1k/eda.duckdb`: raw, normalized, eligible, events,
  user–song pairs và split preview. `csv_rejects` giữ thông tin dòng lỗi.
- `data/processed/lastfm-1k/*.csv`: số liệu user, popularity, missing và tháng.

`data/` và `.venv/` đã được root `.gitignore` loại khỏi Git. Chỉ báo cáo nhỏ,
biểu đồ, script và lockfile là ứng viên commit; task này không commit/push.

## Quy tắc phân tích

Raw được đọc đúng 6 cột, không dùng processed Parquet và không lấy mẫu. Script
đối soát số dòng parse + dòng lỗi = số dòng vật lý, rồi thống kê missing sau trim.
Tập sạch dùng track MBID đúng dạng UUID, giữ tên artist/title và user không rỗng,
timestamp UTC từ 1970 đến hết cutoff 05/05/2009 theo README nguồn. Dedupe toàn bộ
6 field, không xóa các lượt nghe lặp ở thời điểm khác nhau.

Artist ID có thể thiếu. Biến thể tên cùng track MBID không bị tách thành bài mới.
Không suy diễn skip, like, search, release date hoặc thời lượng từ các scrobble.
Global temporal split 80/10/10 là khảo sát độ khả thi, chưa phải thí nghiệm model;
tất cả thống kê đã lọc được ghi rõ phạm vi trong báo cáo.

## Kiểm tra Music4All-Onion

Dùng chung môi trường uv EDA, không thay Last.fm đã tải và không huấn luyện model.
Nguồn cố định: [Music4All-Onion v2](https://zenodo.org/records/15394646).

```bash
cd recommender/eda
# Khoảng 18 MB: README, genre TF-IDF và tags dictionary
uv run python download_music4all.py
uv run python music4all_audit.py --metadata-only

# Bổ sung file interaction count khoảng 551 MB để đo độ phủ toàn bộ
uv run python download_music4all.py --include-interactions
uv run python music4all_audit.py
```

Downloader chỉ lấy bốn file được allowlist và kiểm tra MD5 công bố. File chưa
xong có đuôi `.partial`. Audit không gọi mạng; dữ liệu lớn ở
`data/raw/music4all-onion/`, DuckDB và TSV ở `data/processed/music4all-onion/`.
Báo cáo và biểu đồ nhỏ ở `docs/eda/music4all-onion/`.

Metadata phân biệt *có dòng ID* với *có genre/tag trọng số dương*. Tags dictionary
được đọc bằng `ast.literal_eval`; ID lặp trong tags được ghi nhận và hợp nhất tập
tag dương, không đếm nhiều lần một track. Độ phủ được đo theo số track, số dòng
user–track và tổng lượt nghe. Các file count không có timestamp: chưa đo xu hướng
theo thời gian, chưa thực hiện temporal split và chưa tải audio.
