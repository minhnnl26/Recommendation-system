# Huấn luyện Music4All trên Kaggle — từ dữ liệu đến model có thể nạp lại

Cần kết quả đầu tiên sớm: dùng [Kaggle V1 Quickstart](KAGGLE_V1_QUICKSTART.md) và notebook tự chứa code, chỉ attach count + genre. Các bước bên dưới là workflow code Dataset và cấu hình đầy đủ, không bắt buộc để chạy V1.

## Chạy ngay: chưa cần audio/lyrics gốc

Notebook hiện mặc định `PROFILE='onion'`, đọc `configs/onion.json`. Chỉ cần **`userid_trackid_count.tsv.bz2` và `id_genres_tf-idf.tsv.bz2`** để chuẩn bị, fit ALS, đánh giá và tạo gợi ý. ID lấy từ toàn bộ file genre; title/artist/album và audio path là null, nhãn giao diện `Track <ID>`. Không kiểm tra hoặc cần `original_root` trong chế độ này.

Mặc định Onion dùng **hash leave-two-out**, không phải chia theo thời gian. `max_users=null` giữ toàn bộ user có train; inference/eval vẫn dùng cùng pipeline. Nếu có timestamp, sửa rõ `config['split']='temporal'`, tạo run mới; không tự đổi kiểu chia khi thiếu file. Profile `full` vẫn giữ gate original + temporal cho giai đoạn sau.

```bash
# Chỉ tải core không timestamp cho thí nghiệm chạy trước
uv run --project recommender/training python recommender/training/download_onion.py \
  --output data/raw/music4all-onion --counts-only
```

Tạo code ZIP phiên bản mới, attach code + hai file bắt buộc, import notebook rồi sửa `ONION`. Không cần attach original hoặc gọi `validate_original.py` khi `PROFILE='onion'`. Việc còn lại của từng bạn và danh sách file cần commit nằm trong [TEAM_NEXT_STEPS.md](TEAM_NEXT_STEPS.md).

## Phạm vi và trạng thái

Notebook: [`music4all_kaggle.ipynb`](../recommender/notebooks/music4all_kaggle.ipynb).

Pipeline không dùng giới hạn 3.000 track hoặc 1.000 user của demo local. Profile `onion` lấy toàn bộ catalog genre; profile `full` yêu cầu inventory đầy đủ Music4All gốc (109.269 bài, audio 30 giây + lyrics + metadata). Cả hai dùng tất cả user Onion có lịch sử train nếu `max_users=null`. Không train ALS trên audio; ALS dùng tương tác, còn genre phục vụ content ranking. Bài không có tương tác vẫn ở catalog và có thể được chấm điểm nội dung.

Các bước này đã có source và test local với dữ liệu tổng hợp. **Chưa chạy toàn bộ Music4All trên Kaggle**, chưa có metric full-scale hoặc thời gian chạy được đo trên Kaggle. Chưa có bản gốc trong workspace; cần nhận bộ gốc từ tác giả theo [hướng dẫn dữ liệu](MUSIC4ALL_DATASET_SETUP.md). Không tuyên bố đã tải hoặc huấn luyện toàn bộ khi chỉ có code.

## 1. Chuẩn bị máy local

Yêu cầu: Git, Python **3.10–3.12**, uv; Node/npm chỉ cần khi chạy frontend. Hệ training có uv project/lock riêng, không làm thay đổi dependencies backend.

```bash
git clone https://github.com/minhnnl26/Recommendation-system.git
cd Recommendation-system
uv sync --project recommender/training --dev --locked
```

Để chạy trước, chỉ tải Onion counts + genre. Để chạy profile full sau này, tải đầy đủ **Music4All gốc**, xác minh inventory và tải timestamp; xem [MUSIC4ALL_DATASET_SETUP.md](MUSIC4ALL_DATASET_SETUP.md). Không dùng file `audit.duckdb` của EDA làm input Kaggle; pipeline đọc trực tiếp các file được attach.

## 2. Những gì phải upload/attach

| Thành phần | Cách đưa lên | Có bắt buộc? |
|---|---|---|
| Notebook `.ipynb` | Kaggle → New Notebook → Import Notebook | Có |
| Code training | Private Dataset từ `training-code.zip` | Có |
| Toàn bộ Music4All gốc | Private Dataset, đủ cây metadata/audio/lyrics | Chỉ profile full; chưa cần cho Onion |
| Onion counts + genre | Private Dataset chứa file `.tsv.bz2` còn nén | Có cho profile Onion/hash |
| Onion timestamp + genre | Private Dataset | Có nếu chọn temporal; không cần cho hash |
| `id_musicnn.tsv.bz2` hoặc numeric audio features | Dataset input riêng hoặc cùng Onion | Có nếu chạy classifier |
| `.env`, key, token, raw model của demo cũ | **Không upload** | Không |

Đóng gói code an toàn bằng allowlist:

```bash
python scripts/package_kaggle_code.py
# Output: artifacts/kaggle/training-code.zip
```

Archive code chỉ chứa các script training, requirements, pyproject, uv.lock và config. Nó không copy toàn repository, không chứa dataset, app env, token hoặc notebook output. Upload ZIP này làm Dataset, ví dụ tên `music4all-training-code`. Kaggle sẽ cho thấy thư mục `training/` sau giải nén. Giữ đúng một bản code Dataset attach để notebook không chọn nhầm version.

Ví dụ các đường dẫn sau upload:

```text
/kaggle/input/music4all-training-code/training/
  requirements-kaggle.txt
  prepare.py
  train.py
  predict.py
  ...
/kaggle/input/music4all-original/music4all/
  id_information.csv
  audios/<id>.mp3
  lyrics/<id>.txt
  ...
/kaggle/input/music4all-onion/
  id_genres_tf-idf.tsv.bz2
  userid_trackid_timestamp.tsv.bz2
  userid_trackid_count.tsv.bz2
  ...
```

Tên folder thực tế do Kaggle tạo có thể khác; sửa `ORIGINAL` và `ONION` ở cell cấu hình. Input private và notebook private có quyền chia sẻ riêng; mời người cộng tác notebook không tự cấp quyền input Dataset.

## 3. Thiết lập notebook

1. Import `recommender/notebooks/music4all_kaggle.ipynb`.
2. Add Input: code và Onion counts + genre; chỉ attach original nếu chạy profile full. Giữ private theo điều kiện sử dụng dữ liệu.
3. Chọn runtime Python 3.10–3.12. Cell đầu sẽ chặn version chưa hỗ trợ.
4. Bật Internet để cài dependencies từ `requirements-kaggle.txt`. Nếu phiên không có Internet, chuẩn bị wheelhouse đúng Python/Linux và dùng `pip install --no-index --find-links <wheelhouse> -r ...`; không tự bỏ dependency.
5. **CPU là mặc định đã kiểm thử.** Có thể bật GPU và `use_gpu=True` để thử ALS GPU nếu wheel/CUDA tương thích; nếu không, sửa rõ về CPU, không coi có GPU là tự dùng GPU.
6. Kiểm tra dung lượng input/scratch/working; không giải nén original vào working.
7. Chạy từng cell lần đầu. Sau khi mọi đường dẫn đúng, dùng Save Version → Save & Run All để lưu phiên có output.

Tại thời điểm kiểm tra tài liệu Kaggle, output tự lưu trong `/kaggle/working` có giới hạn 20 GB; scratch ngoài working không được tự lưu. Hạn mức runtime/account có thể đổi, hãy kiểm tra UI trước khi chạy. Không lấy dung lượng input Dataset làm dung lượng output khả dụng. [Tài liệu Kaggle](https://www.kaggle.com/docs/notebooks).

## 4. Notebook chạy các bước nào?

### A. Cài thư viện và kiểm tra nguồn

Các version runtime được pin trong requirements và uv.lock. Không import Supabase, không đọc app `.env`, không tạo table FastAPI hoặc gọi cloud của dự án.

Profile Onion bỏ qua gate original một cách tường minh và ghi `full_original_verified=false`. Profile full kiểm tra đầy đủ inventory. Chưa decode mọi audio; có file không đồng nghĩa đã xác minh quyền phát. Nếu cấu trúc nguồn khác, sửa config/adapter theo header thực tế trước khi train.

### B. Chuẩn bị sparse matrix và các profile chia dữ liệu

**Mặc định Onion/hash:** item universe là toàn bộ ID trong genre; không đọc `id_information.csv`. File count được tách hai cặp/user đủ lịch sử theo hash có seed cho validation/test, các cặp còn lại train. Không có tổng hợp theo thời gian. Phần bên dưới mô tả **profile full/temporal hoặc Onion chọn temporal**:

1. Dùng toàn bộ ID trong `id_information.csv` cho full, hoặc ID file genre cho Onion; nối theo ID chính xác.
2. Chuẩn hóa genre L2; vector rỗng vẫn giữ bài, chỉ không có tín hiệu nội dung.
3. Stream giải nén timestamp vào scratch; DuckDB giới hạn memory 4 GB, spill trên scratch. Không load 253 triệu dòng thành DataFrame Python.
4. Chọn hai cutoff toàn cục theo phân vị 80%/90% thời gian của các event trong catalog.
5. Train: event trước cutoff 80%. Validation: event từ cutoff 80% đến trước cutoff 90%. Test: phần còn lại. Các event trùng timestamp nằm cùng phía cutoff, nên số dòng không nhất thiết chính xác 80/10/10.
6. Tổng hợp count **chỉ từ từng khoảng tương ứng**; train count không dùng tổng count của tương lai.
7. Đánh giá bài chưa thấy: validation chỉ giữ cặp chưa có trong train; test chỉ giữ cặp chưa có trong train và validation. Đây là **unseen-item discovery**, không đo khả năng phát lại bài đã từng nghe.
8. Chỉ user có tương tác train mới có vector ALS; user chưa có train được thống kê là ngoài warm-user evaluation. Catalog không bị lọc chỉ còn bài phổ biến.
9. Xuất CSR qua các buffer disk-backed để tránh danh sách 50 triệu Python tuple. Matrix train/validation/test không chuyển sang dense user×item.

`max_users=null` là đầy đủ user có train. Nếu cần smoke run, bạn phải chủ động tạo config khác với số user giới hạn; manifest lưu cấu hình đó. **Không gọi run giới hạn là full**.

Nếu chỉ có count và muốn thí nghiệm không thời gian, tạo config mới với `split="hash"`. Cách này giữ riêng hai cặp/user đủ lịch sử cho validation/test, còn lại train. Không dùng kết quả đó để khẳng định dự báo xu hướng hoặc chất lượng temporal. Pipeline không tự fallback khi thiếu timestamp.

### C. Huấn luyện Implicit ALS

Ma trận đầu vào là user×item CSR, giá trị trên các cặp train có quan sát:

```text
confidence = 1 + alpha * log1p(train_count)
```

Mô hình `implicit` nhận `alpha=1` vì đã tính confidence tường minh, tránh nhân alpha hai lần. Mặc định: 64 factors, 20 iterations, regularization 0,05, confidence alpha 20, seed 42, CPU 4 threads. Đây là cấu hình khởi đầu, chưa tối ưu. `factors` là số chiều vector ẩn, không phải số thể loại.

CPU/GPU fit checkpoint được lưu **trước evaluation**. GPU model được chuyển về CPU để xuất artifact tương thích inference CPU. Mô hình không biến các ô chưa quan sát thành bằng chứng chắc chắn user ghét bài.

### D. Hybrid và đánh giá

- ALS: tích vô hướng vector user và item, clip điểm âm về 0, chia max trong request. Bài không có train observations không nhận điểm CF đáng tin cậy.
- Content: hồ sơ user từ genre của các bài train với trọng số `log1p(count)`, chuẩn hóa và tính cosine.
- Popularity: tổng lượt nghe train, log-transform và chia max.
- Hybrid mặc định: `0.5 ALS + 0.4 content + 0.1 popularity`; nhánh không có điểm dương bị bỏ, chuẩn hóa lại trọng số còn lại.
- Mask bài train; khi test mask thêm bài đã thấy ở validation. Không fit lại mô hình bằng validation trong run hiện tại.
- So sánh popularity, content, ALS và hybrid trên cùng user sample cố định bằng seed. Mặc định tối đa 1.000 eligible user mỗi split; ghi cả tổng eligible và số thực sự đánh giá. **Train đầy đủ không có nghĩa eval tất cả user**. Tăng `eval_users` nếu muốn báo cáo toàn bộ và chấp nhận chi phí inference.
- Xuất Recall@10, NDCG@10, MRR@10, Precision@10, catalog coverage và thời gian. Chưa có thí nghiệm cold-item riêng hoặc artist-disjoint evaluation; không tuyên bố các metric này chứng minh cold-start.

Chỉ điều chỉnh factors/alpha/weights bằng validation, giữ test làm báo cáo cuối. Mỗi cấu hình dùng output root mới; không chọn cấu hình dựa vào metric test. Tất cả bài trong catalog là candidates, không dùng sampled negatives cho báo cáo hiện tại.

## 5. Output nào cần tải về?

```text
music4all-run/
├── config.json
├── prepared/
│   ├── catalog.json                  Tên bài/nghệ sĩ/album từ original
│   ├── item_ids.json                 Thứ tự item khớp mọi matrix và factors
│   ├── user_ids.json
│   ├── genre_names.json
│   ├── train.npz
│   ├── validation.npz
│   ├── test.npz
│   ├── genre.npz
│   ├── original_inventory.json
│   └── manifest.json                 Source hashes, split, coverage
├── model/als.npz                     Checkpoint model
├── metrics.json
└── artifact_manifest.json            SHA-256 của từng artifact + versions
```

Giữ **toàn bộ thư mục run**, không chỉ `als.npz`; thiếu mapping sẽ gợi ý sai ID. Artifact không chứa MP3 hoặc lời bài hát. Có user interaction và metadata nên giữ private theo điều kiện nguồn, không commit artifact lên GitHub.

Notebook không tự upload Drive vì cần tài khoản/quyền riêng. Bạn lưu output thành private Dataset hoặc tải thư mục run về Drive. Không chỉ đóng tab sau một phiên interactive chưa lưu output. Nếu evaluation ngắt sau khi fit, checkpoint đã có nhưng `artifact_manifest.json` chỉ xuất hiện khi train+eval hoàn tất; đừng báo run đó là hoàn thành.

## 6. Chạy inference local với model từ Kaggle

Giải nén run vào `artifacts/music4all/<run-id>/`. Không sửa hoặc đổi thứ tự mapping.

```bash
uv run --project recommender/training python recommender/training/predict.py \
  --run artifacts/music4all/run-001 --user-id '<ID có trong user_ids.json>' --limit 10

# Người mới chọn thể loại; kiểm tra tên trong genre_names.json
uv run --project recommender/training python recommender/training/predict.py \
  --run artifacts/music4all/run-001 --genre rock --limit 10
```

Có thể thêm `--recent '<track ID>'` tối đa 5 lần, mới nhất trước. Với session input, inference fold-in vector user bằng confidence cùng thang đo train; genre được chọn bổ sung tín hiệu nội dung. Với user hoàn toàn mới không có tín hiệu, fallback popularity.

Response CLI có điểm thành phần. Profile original có tên bài/nghệ sĩ/album và đường dẫn tương đối `audios/<id>.mp3`; profile Onion trả các trường metadata/audio là null và `display_name='Track <ID>'`. Đường dẫn trong original **không phải URL public hoặc xác nhận quyền stream**. Nếu audio ở thư mục con, cần resolver theo ID khi tích hợp serving.

**Chưa tự thay model của `/research` hoặc API production.** Entry point FastAPI hiện vẫn dùng SQLite Item-kNN của demo. Việc nạp ALS vào API, giới hạn truy cập audio và logging tương tác là bước tích hợp tiếp theo. Đây là bộ training + CLI inference, không phải deployment.

## 7. Bộ phân loại thể loại mở rộng — độc lập với recommender

Một user có thể thích nhiều thể loại; bài hát cũng có thể mang nhiều nhãn. Script `train_genre_classifier.py` dùng **One-vs-Rest SGD logistic multi-label**, dự đoán genre từ vector âm thanh có cùng ID.

```bash
uv run --project recommender/training python recommender/training/train_genre_classifier.py \
  --prepared artifacts/music4all/run-001/prepared \
  --audio-features data/raw/music4all-onion/id_musicnn.tsv.bz2 \
  --output artifacts/music4all/genre-classifier-001
```

Input audio TSV phải có header `id` rồi các cột số; nếu nguồn khác format, chuyển đổi bằng adapter được kiểm tra, không đổi tên file để vượt validation. Chưa trích embedding từ MP3 trong pipeline này; dùng embedding được cung cấp sẵn hoặc một file numerical feature do bạn tự tạo đúng schema. Không dùng genre/tag TF-IDF làm input dự đoán chính genre vì gây leakage.

Chia track train/validation/test 80/10/10 bằng seed; scaler fit train-only. Nhãn phải có ít nhất 20 ví dụ dương và 20 ví dụ âm trong train; nhãn hiếm được báo cáo là loại khỏi experiment. Chọn threshold bằng micro-F1 validation, đánh giá test một lần; báo micro/macro-F1. Split chưa tách artist, nên có nguy cơ kết quả lạc quan do cùng artist ở train/test. Đây là dự đoán nhãn dataset, chưa phải bộ đánh giá mood do con người gán.

Output `genre_classifier.npz` gồm coefficients, intercepts, scale, labels, feature_names, threshold. Cách nạp khi cần triển khai classifier: chuẩn hóa mỗi cột `x / scale`, tính logits `x @ coefficients.T + intercepts`, sigmoid rồi so threshold. File không dùng pickle.

Nâng cấp tiếp: artist-disjoint split; audio encoder fine-tune; lyrics/audio multimodal; LightFM-Hybrid để so sánh với ALS + content rerank. Các nâng cấp này là kế hoạch, chưa có code training deep model trong task này.

## 8. Mức đáp ứng yêu cầu dự án

| Nhu cầu | Pipeline này cung cấp | Còn cần làm |
|---|---|---|
| Lịch sử và gu dài hạn | ALS trên Onion train interactions | Pilot bằng interaction website |
| Thể loại yêu thích | Content cosine và genre preference | Đánh giá/điều chỉnh trọng số bằng validation |
| Bài mới ít tương tác | Có thể chấm điểm nội dung nếu đã có feature | Ingestion và extractor cho bài ngoài catalog |
| Ý định hiện tại | Recent-item heuristic và fold-in trong CLI | Search intent, lưu session, đo online |
| Trào lưu gần đây | Có timestamp, temporal data preparation | Trending aggregation và kết nối nguồn cập nhật; lịch sử benchmark không phải xu hướng hôm nay |
| Có nhạc/tên bài | Gate toàn bộ original + catalog metadata | Audio serving riêng, điều kiện quyền phát |
| Phân loại thể loại | Classifier multi-label tùy chọn | Thí nghiệm embedding thật và kiểm định mở rộng |

Không có một bộ phân loại duy nhất tự đáp ứng mọi yêu cầu. Hệ gợi ý, phân loại nội dung, dữ liệu cập nhật và phục vụ sản phẩm là những thành phần cần phối hợp.

## 9. Kiểm thử và chạy không dùng Kaggle

```bash
# Từ root repo; chỉ định config pytest để không collect nhầm tests backend
uv run --project recommender/training pytest \
  -c recommender/training/pyproject.toml recommender/training/tests -q
uv run --project recommender/training ruff check recommender/training scripts/package_kaggle_code.py
uv run --project recommender/training ruff format --check recommender/training scripts/package_kaggle_code.py
uv run --project recommender/training python -m compileall -q recommender/training scripts/package_kaggle_code.py
git diff --check
```

Để chạy full local, copy `configs/full.json` sang `data/configs/full-local.json`, sửa đường dẫn và output/scratch; không thay expected 109269 hoặc bỏ gate để gọi là full:

```bash
uv run --project recommender/training python recommender/training/prepare.py --config data/configs/full-local.json
uv run --project recommender/training python recommender/training/train.py --config data/configs/full-local.json
```

Nếu một bước thất bại, dữ liệu nguồn không bị reset. Dùng output mới cho lần chuẩn bị lại, giữ log không có credentials để kiểm tra. Pipeline chưa có resume preprocessing/ALS giữa chừng; checkpoint sau fit chỉ bảo toàn model trước evaluation.

## Tài liệu kỹ thuật

- [Implicit ALS: user×item confidence matrix, save/load và inference](https://benfred.github.io/implicit/api/models/cpu/als.html).
- [Kaggle Datasets](https://www.kaggle.com/docs/datasets).
- [Kaggle Notebooks](https://www.kaggle.com/docs/notebooks).
- [Nguồn và yêu cầu tải toàn bộ Music4All](MUSIC4ALL_DATASET_SETUP.md).
