# Chuẩn bị toàn bộ Music4All gốc và Music4All-Onion

## Yêu cầu của dự án lớn

Bản nghiên cứu lớn yêu cầu **toàn bộ catalog Music4All gốc**, gồm metadata, audio và lyrics của **109.269 bài**, cộng dữ liệu tương tác và đặc trưng từ Music4All-Onion. Không thay bộ gốc bằng tập demo 3.000 bài. Toàn bộ Music4All gốc vẫn là **đoạn nhạc 30 giây**, không phải toàn bộ thời lượng bài hát.

Không đồng nhất “có toàn bộ dataset” với “mọi mô hình phải đọc mọi file”. ALS học từ tương tác; audio phục vụ nghe mẫu/đặc trưng và bộ phân loại. Bản đầy đủ giữ mọi ID trong catalog, kể cả bài không có tương tác train. ALS không học được vector sở thích đáng tin cậy cho bài chưa có tương tác; nhánh nội dung xử lý trường hợp này.

## 1. Nhận bộ Music4All gốc

Nguồn chính thức: [Music4All: A New Music Database](https://sites.google.com/view/contact4music4all). Trang tác giả hướng dẫn gửi yêu cầu tới `contact4music4all@gmail.com`. [Bài báo gốc](https://www.din.uem.br/yandre/IWSSIP_2020_Music4All.pdf) mô tả audio 30 giây, metadata và lyrics.

Bạn cần tự gửi yêu cầu từ tài khoản của mình, nêu trường/lớp, mục đích nghiên cứu, nhu cầu nhận toàn bộ audio + metadata + lyrics, cách tải và điều kiện sử dụng. Agent không tự gửi email, không đoán mật khẩu và không tải từ mirror không xác minh.

Sau khi tác giả cấp link hoặc archive/mật khẩu, tải **đủ mọi phần** của bộ gốc. Giữ README, giấy phép và checksum do tác giả cung cấp trong kho dữ liệu riêng. Nếu archive có mật khẩu, nhập tương tác khi giải nén; không đưa mật khẩu vào lệnh, notebook, Git hoặc log. Ví dụ dùng 7-Zip:

```bash
# Ví dụ cho một archive nhận từ tác giả; nhập mật khẩu tại prompt nếu được hỏi.
7z x music4all.zip -odata/raw/music4all-original
```

Nếu link được cấp là riêng tư/có thời hạn, không đưa link vào README, GitHub hoặc Dataset public. Mọi archive chia phần phải được ghép/giải nén theo hướng dẫn đi kèm của tác giả.

## 2. Cấu trúc sau giải nén

Truyền `--root` trỏ đúng thư mục chứa `id_information.csv`, không phải thư mục cha:

```text
data/raw/music4all-original/music4all/
├── id_information.csv       ID, tên bài, nghệ sĩ, album
├── id_metadata.csv          Metadata âm nhạc do bộ gốc cung cấp
├── id_genres.csv
├── id_tags.csv
├── id_lang.csv
├── listening_history.csv    Lịch sử của bộ gốc; không trộn ID user với Onion
├── audios/
│   ├── <track_id>.mp3        Đoạn âm thanh 30 giây
│   └── ...                  109.269 ID bài
└── lyrics/
    ├── <track_id>.txt
    └── ...                  109.269 ID tương ứng
```

Các trường có thể có tên khác nhẹ giữa bản phân phối. Loader hỗ trợ `id/track_id`, `song/name/track_name/title`, `artist/artist_name`, `album/album_name`, delimiter tab/comma/semicolon. Nếu khác hơn nữa, kiểm tra header và sửa adapter có test; không tự đoán cách ghép theo tên.

```bash
uv sync --project recommender/training --dev --locked
uv run --project recommender/training python recommender/training/validate_original.py \
  --root data/raw/music4all-original/music4all \
  --report data/manifests/music4all-original.json
```

Gate xác nhận 109.269 catalog ID không trùng, sáu CSV không rỗng, mỗi ID có MP3/TXT không rỗng và không có file audio/lyrics lặp ID. **Đây là kiểm tra inventory, chưa decode mọi MP3**, chưa xác minh từng nội dung audio, độ dài 30 giây hoặc quyền phát. Không có bản gốc thì gate thất bại; không chuyển sang dữ liệu giả.

Giữ toàn bộ bản được tác giả cấp. Công cụ không tự tải 109.269 audio vì hiện chưa có quyền truy cập/link tác giả trong phiên làm việc này.

## 3. Tải Music4All-Onion từ nguồn chính thức

[Music4All-Onion v2 trên Zenodo](https://zenodo.org/records/15394646), DOI `10.5281/zenodo.15394646`.

```bash
# Đủ cho pipeline recommendation mặc định, gồm cả timestamp (~2,2 GB nén)
uv run --project recommender/training python recommender/training/download_onion.py \
  --output data/raw/music4all-onion

# Nếu muốn lưu toàn bộ bản Onion, khoảng 19,9 GB NÉN
uv run --project recommender/training python recommender/training/download_onion.py \
  --output data/raw/music4all-onion --all
```

Script kiểm tra size + MD5 theo manifest Zenodo, không ghi đè file đã có sai checksum. File đang tải có đuôi `.partial`; chạy lại tải lại file chưa hoàn thành, chưa hỗ trợ resume HTTP từng byte. Không giải nén toàn bộ 19,9 GB vào notebook output.

| File | Bắt buộc cho cấu hình mặc định? | Vai trò |
|---|---|---|
| `userid_trackid_timestamp.tsv.bz2` | Có | 252.984.396 lượt nghe có thời gian; temporal split |
| `id_genres_tf-idf.tsv.bz2` | Có | Vector thể loại nội dung |
| `userid_trackid_count.tsv.bz2` | Tải kèm | 50.016.042 cặp tổng hợp; thí nghiệm hash split/EDA |
| `id_tags_dict.tsv.bz2` | Tải kèm | Tags/EDA; chưa dùng để fit ALS |
| `README.md` | Có | Mô tả nguồn |
| `id_musicnn.tsv.bz2` | Tùy chọn | Đặc trưng âm thanh cho bộ phân loại thể loại |
| Các đặc trưng audio/lyrics/video khác | Tùy thí nghiệm | Không cần nạp tất cả vào RAM cùng lúc |

Giữ phân biệt **109.269 bài có đặc trưng/catalog** và **56.512 bài có tương tác Onion**. Music4All gốc và Onion không có cùng tập user; pipeline chỉ dùng tương tác Onion, nối với catalog gốc theo track ID chính xác, phân biệt hoa/thường. Nó báo số dòng tương tác nằm ngoài catalog thay vì âm thầm coi mọi ID đã nối thành công.

## 4. Dung lượng và vị trí lưu

Không chốt dung lượng Music4All gốc khi chưa nhận archive thực tế. MP3, lyrics, archive nén, bản giải nén và bản sao upload có thể chiếm nhiều lần kích thước ban đầu. **Dự trù 150–250 GiB cho kho làm việc đầy đủ là ước lượng kế hoạch**, không phải dung lượng đã đo hoặc yêu cầu RAM.

```bash
du -sh data/raw/music4all-original data/raw/music4all-onion
df -h .
```

Khi temporal preparation chạy, cần thêm chỗ cho TSV giải nén, DuckDB và spill trong scratch. Đặt `scratch_root` trên đĩa còn trống, không phải thư mục output cần lưu. Nếu hết dung lượng: dừng, dùng scratch lớn hơn và chạy với output mới; không tự giảm dataset.

| Nơi lưu | Nên chứa gì? |
|---|---|
| GitHub | Source, notebook không output, config mẫu, hướng dẫn, tests |
| SSD/Drive riêng | Toàn bộ original archive + bản giải nén + manifest nguồn |
| Kaggle Dataset riêng tư | Dữ liệu đầu vào đã được phép đưa lên Kaggle |
| `/kaggle/input` | Input chỉ đọc; không cần copy toàn bộ sang working |
| Scratch `/tmp` | File trung gian có thể tái tạo; không tự được lưu sau phiên |
| `/kaggle/working` | Model, sparse matrices, mapping ID, metrics, manifest |

## 5. Chia dữ liệu thành shard để upload/lưu Drive

```bash
uv run --project recommender/training python recommender/training/package_original.py \
  --root data/raw/music4all-original/music4all \
  --output data/upload/music4all-original-shards --shard-gib 2
```

Script chạy gate đầy đủ trước, đóng gói toàn bộ cây nguồn thành các ZIP độc lập khoảng 2 GiB theo tổng source bytes, kèm SHA-256 mỗi shard. ZIP có overhead nhỏ nên size cuối có thể vượt nhẹ mốc. Không cắt một file ra nhiều phần. Không dùng output nằm trong source root, không ghi đè shard đã có. Cần thêm dung lượng tương ứng cho bản đóng gói.

Kaggle có thể giải nén archive khi tạo Dataset. Các shard giữ đường dẫn `music4all/...`; sau upload cần kiểm tra tất cả shard đã được giải nén vào cùng một cây hoàn chỉnh rồi chạy gate. Nếu UI không gộp được các ZIP có chung root, upload thư mục đã giải nén bằng Kaggle CLI theo tài liệu chính thức hoặc ghép các input vào một cây bằng symlink trong scratch và truyền cây đó làm `original_root`; không copy audio vào output.

## 6. Google Drive khi lưu lượng dữ liệu lớn

Drive có thể làm **kho lưu riêng**, nhưng không tự tăng dung lượng runtime Kaggle. Giữ thư mục:

```text
MyDrive/MusicRecommendation/
├── original-archives/
├── original-shards/
├── onion/
└── training-artifacts/<run-id>/
```

Bạn có thể upload shards bằng Drive Desktop/trình duyệt, tải về khi cần và đối chiếu SHA-256. Nếu dùng rclone, tự cấu hình OAuth ngoài notebook/source, không commit file cấu hình hoặc in token; đường dẫn `remote:` là tên remote do bạn tự đặt.

**Kaggle không có `google.colab.drive.mount` như Colab.** Phương án ưu tiên là chuẩn bị private Kaggle Dataset từ dữ liệu bạn có quyền đưa lên, rồi attach nó. Nếu chỉ được lưu trên Drive, có thể chạy cùng script trong Colab với `original_root` trỏ Drive, hoặc dùng cơ chế tải có xác thực riêng được cấu hình qua secret store; không biến archive gốc thành link public để tiện tải.

Điều kiện truy cập bản gốc quyết định bạn có được upload/chia sẻ với cộng tác viên hay không. Quyền sử dụng nghiên cứu không tự động là quyền phát audio công khai; không đưa audio gốc lên GitHub hoặc website công khai chỉ vì đã tải được.

## Nguồn tham khảo

- [Music4All chính thức và cách yêu cầu bộ gốc](https://sites.google.com/view/contact4music4all).
- [Music4All-Onion v2 và checksum từng file](https://zenodo.org/records/15394646).
- [Kaggle Datasets: input, archive và privacy](https://www.kaggle.com/docs/datasets).
- [Kaggle Notebooks: working/scratch và lưu output](https://www.kaggle.com/docs/notebooks).

Hướng dẫn thao tác notebook: [KAGGLE_TRAINING.md](KAGGLE_TRAINING.md).
