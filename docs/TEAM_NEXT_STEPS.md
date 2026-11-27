# Bàn giao nhóm: huấn luyện trước, hoàn thiện ứng dụng sau

> Cập nhật: 2026-11-27. Có thể gửi file này cho các bạn phụ trách frontend, backend và training.
> Repository: https://github.com/minhnnl26/Recommendation-system

## 1. Quyết định hiện tại

Ưu tiên có kết quả recommender bằng **Music4All-Onion**, chưa chờ xin Music4All gốc. ALS học từ user–track–count; nhánh content dùng genre. MP3, lời bài hát và tên nghệ sĩ không phải điều kiện để fit và đánh giá recommender.

Notebook mặc định chọn `configs/onion.json`: toàn bộ catalog ID trong genre, toàn bộ user có train, chia theo hash. Đây là thí nghiệm không thời gian; không gọi kết quả là temporal hoặc xu hướng hiện tại. Khi có timestamp, chạy một run khác với `split="temporal"`. Khi nhận Music4All gốc, dùng `configs/full.json` để kiểm tra đủ original metadata/audio/lyrics và mở rộng ứng dụng nghe nhạc.

Audio Music4All gốc là đoạn **30 giây**. Xin đủ bộ gốc không đồng nghĩa nhận được bản nhạc toàn thời lượng. Trước mắt 30 giây đủ cho demo nghe mẫu; vẫn cần điều kiện sử dụng tương ứng.

## 2. Đã có và chưa có

| Thành phần | Đã có | Việc còn lại |
|---|---|---|
| Frontend | `/catalog`, player cơ bản, `/research` với demo Item-kNN | Nối artifact ALS mới qua backend, trạng thái lỗi/loading, hoàn thiện luồng demo |
| Backend | Catalog API async; research API đọc SQLite Item-kNN | Adapter/model service cho ALS, contract response, validation, kiểm soát truy cập audio |
| Training | Notebook, prepare/train/eval, CLI inference, optional genre classifier | Chạy trên dữ liệu thật trong Kaggle, lưu model và kết quả, thí nghiệm validation |
| Dữ liệu | Count + genre + tags Onion đã tải ở máy hiện tại | Chia sẻ input riêng cho bạn training; tải timestamp nếu đánh giá temporal |
| Music4All gốc | Có hướng dẫn xin/tải/kiểm tra, chưa có archive | Liên hệ tác giả, nhận đủ metadata/audio/lyrics, kiểm tra inventory |
| Xu hướng/session | Có heuristic recent-items khi suy luận | Thu event có thời gian, aggregation trending, lưu phiên; chưa có trending hiện tại |

**Lưu ý:** CLI inference từ Kaggle chạy được không có nghĩa `/research` đã dùng model Kaggle. Phần kết nối này là đầu việc backend/frontend bên dưới.

## 3. Bạn phụ trách training — làm trước

### T1. Nhận code và input

- [ ] Clone repository, dùng branch `feat/kaggle-results` hoặc branch cá nhân.
- [ ] Đọc [KAGGLE_TRAINING.md](KAGGLE_TRAINING.md), import `recommender/notebooks/music4all_kaggle.ipynb`.
- [ ] Nhận link private Dataset/Drive của nhóm và kiểm tra đúng file, version, checksum.
- [ ] Attach code training và Onion input; chưa cần upload original audio.

**Dữ liệu phải gửi riêng cho bạn training, không đưa vào Git:**

```text
data/raw/music4all-onion/
  userid_trackid_count.tsv.bz2
  id_genres_tf-idf.tsv.bz2
```

Đây là hai file bắt buộc cho run Onion/hash. Có thể gửi thêm `README.md`, `id_tags_dict.tsv.bz2`, `download_manifest.json` nếu đã có. Không gửi file `.env`, key, token hoặc toàn thư mục backend. Không cần gửi `audit.duckdb`, frontend node_modules hay artifact demo SQLite.

Nếu muốn temporal: gửi/tải thêm `userid_trackid_timestamp.tsv.bz2`, đổi rõ `split` thành `temporal`, tạo output mới. Nếu muốn classifier: thêm audio feature TSV như `id_musicnn.tsv.bz2`; không dùng genre TF-IDF làm input dự đoán chính genre.

Đóng gói code bản mới:

```bash
uv sync --project recommender/training --dev --locked
python scripts/package_kaggle_code.py --output artifacts/kaggle/training-code-onion.zip
```

Đây là ZIP **code-only**, không có dataset. Upload nó làm private Kaggle Dataset, attach đúng một bản code và sửa `ONION` đúng đường dẫn Kaggle. Nếu tên output ZIP đã tồn tại, dùng tên version mới; script không tự ghi đè.

### T2. Chạy và kiểm tra kết quả

- [ ] Để `PROFILE='onion'` trong notebook; mặc định `original_root=null`, `require_full_original=false`, `split='hash'`.
- [ ] Chạy chuẩn bị → fit ALS → so sánh popularity/content/ALS/hybrid → inference mẫu.
- [ ] Xác nhận `catalog_source=onion`, số user/item, train/validation/test, và `max_users` đúng run thực tế.
- [ ] Ghi Recall@10, NDCG@10, MRR@10, Precision@10, coverage, fit/eval time.
- [ ] Kiểm tra kết quả không trả bài đã thấy trong lịch sử train; đầu ra Onion có tên/audio null là đúng.
- [ ] Save Version có output; tải hoặc lưu private Dataset chứa **toàn bộ thư mục run**.

Các artifact phải bàn giao cho backend qua link private:

```text
<run-id>/
  config.json
  prepared/catalog.json
  prepared/item_ids.json
  prepared/user_ids.json
  prepared/genre_names.json
  prepared/genre.npz
  prepared/train.npz
  prepared/validation.npz
  prepared/test.npz
  prepared/manifest.json
  prepared/original_inventory.json
  model/als.npz
  metrics.json
  artifact_manifest.json
```

Không chỉ gửi `als.npz`: backend cần mapping ID và feature/history đúng version. Tệp `original_inventory.json` ở chế độ Onion ghi rõ **không kiểm tra original**, không phải chứng nhận đủ MP3.

### T3. Thí nghiệm và báo cáo

- [ ] So sánh tối thiểu popularity, content, ALS và hybrid trên cùng tập chia.
- [ ] Thử factors/regularization/weights bằng validation; không chọn theo test.
- [ ] Ghi dataset hash, seed, cấu hình, máy/runtime và số user thực sự eval.
- [ ] Ghi rõ nếu giới hạn user để smoke test; không gọi run nhỏ là train toàn bộ.
- [ ] Khi có timestamp, bổ sung run temporal riêng; không sửa nhãn hash thành temporal.

**Cần commit:** notebook đã xóa output, source/config thay đổi, test, báo cáo nhỏ `docs/experiments/<run-id>.md` và bảng metric tổng hợp đã kiểm tra, không chứa user history/đường dẫn private/credentials.

**Không commit:** raw dataset, notebook output thô, factor/model/CSR `.npz`, archive, metadata/history chi tiết của run. Gửi qua Drive/private Dataset, ghi artifact version + SHA-256 trong báo cáo.

## 4. Bạn phụ trách backend

### B1. Chốt contract cùng frontend

- [ ] Chốt route gợi ý mới hoặc version hóa route research hiện có; đây là đề xuất, chưa có endpoint ALS serving.
- [ ] Request gồm user nghiên cứu tùy chọn, genre, tối đa 5 recent track ID, limit.
- [ ] Response gồm track ID, `display_name`, title/artist/album nullable, genres, score, thành phần điểm, lý do, model version và khả năng phát.
- [ ] Giữ Music4All ID dạng chuỗi, phân biệt hoa thường. Không ép thành UUID hoặc ghép với UUID Supabase khi chưa mapping.

### B2. Tích hợp model

- [ ] Nhận toàn bộ artifact, kiểm tra checksum và version; đặt ngoài Git dưới `artifacts/`.
- [ ] Nạp model/mapping một lần khi startup/lifespan, không train trong request.
- [ ] Bọc CLI logic `Recommender` trong service nhỏ; không import project training nặng tùy tiện vào production dependency mà chưa chốt version.
- [ ] Tác vụ I/O dùng async phù hợp; CPU inference chạy thread/worker hoặc được giới hạn, không chặn event loop.
- [ ] Chặn thiếu model bằng lỗi chung, không lộ đường dẫn nội bộ/credential; không fallback cloud.
- [ ] Unit test mock + integration với artifact nhỏ: known user, cold start, genre, session, bài đã thấy, ID lạ, limit, thiếu artifact.

### B3. Sau khi có original

- [ ] Nối metadata theo ID xác minh; không bịa tên bài hoặc ghép ngẫu nhiên theo tên.
- [ ] Thiết kế resolver audio theo ID và quyền truy cập, hỗ trợ đoạn nghe mẫu; kiểm tra URL/path trước khi phát.
- [ ] Sau khi chốt mới thêm migration cho event/session, RLS và index; không create table khi FastAPI startup.
- [ ] Chưa chạy migration cloud, deploy hoặc reset database khi chưa được giao rõ.

**Cần commit:** API/service/repository adapter, response models, test, dependencies + lock, `.env.example` chỉ chứa tên biến/giá trị mẫu, migration và tài liệu contract.

**Không commit:** `.env`, production credentials, model, audio, dump database hoặc user events thật.

## 5. Bạn phụ trách frontend

### F1. Hoàn thiện luồng gợi ý

- [ ] Dùng contract đã chốt với backend, không gọi Supabase hoặc mở model trực tiếp trong browser.
- [ ] Chọn genre, hồ sơ mẫu, xem lịch sử và các bài vừa chọn; hiển thị Top-N và lý do dễ hiểu.
- [ ] Dùng `Track <ID>` khi thiếu tên; không hiển thị `null`/`undefined` cho user.
- [ ] Có loading, empty, error/retry; hủy hoặc bỏ response cũ khi đổi query/user nhanh.
- [ ] Phân trang, bố cục mobile, keyboard labels và contrast đủ đọc.
- [ ] Ghi rõ nguồn dữ liệu và model đang dùng; đừng để user tưởng Item-kNN demo là artifact ALS mới.

### F2. Player sau khi có audio

- [ ] Chỉ hiện Play khi backend xác nhận bài có preview/audio được phép phát.
- [ ] Không tạo link `audios/<id>.mp3` trong frontend để đoán file tồn tại.
- [ ] Giữ play/pause/seek/queue, xử lý loading/error/end; không autoplay khi vào trang.
- [ ] Ghi rõ “đoạn nghe thử 30 giây” nếu nguồn là audio Music4All gốc.
- [ ] Kiểm thử đổi bài liên tục và lỗi URL bằng browser thực tế.

**Cần commit:** page/component/style, API client/types, test có ích, tài liệu demo, package manifest/lock nếu đổi dependencies.

**Không commit:** `.env.local`, key/service role, audio, build `.next`, node_modules hoặc thông tin truy cập Dataset.

## 6. Phối hợp và thứ tự thực hiện

| Ưu tiên | Chủ trì | Deliverable để người tiếp theo dùng |
|---|---|---|
| P0 | Training | Kaggle run thật, metric rõ split, artifact private có hash |
| P0 song song | Frontend + backend | Contract request/response và UI trạng thái chưa có audio |
| P1 | Backend | API nạp artifact và trả Top-N có model version |
| P1 | Frontend | Luồng xem gợi ý từ API ALS, xử lý thiếu metadata |
| P2 | Data | Nhận đủ original, xác minh inventory và mapping |
| P2 | Backend + frontend | Nghe preview 30 giây, không cần chờ để hoàn thành P0 |
| P3 | Cả nhóm | Temporal eval, event/session, trending và bài mới |

Chưa gán tên người vào vai trò vì nhóm chưa chốt phân công. Mỗi bạn nhận một nhánh, tránh cả nhóm sửa cùng notebook/config. Ưu tiên demo dùng được và metric tái lập trước khi thêm deep learning.

## 7. Quy trình commit và gửi cho nhóm

Trước mỗi commit:

```bash
git status --short
git diff --check
# Chỉ add các file thuộc việc đã làm, không git add -f dữ liệu bị ignore
git add <file-source> <file-test> <file-doc>
git diff --cached --stat
git diff --cached --check
git commit -m "feat: describe the completed change"
```

Notebook commit phải có `outputs=[]`, `execution_count=null` trong mọi code cell. Không commit kết quả chạy có token, đường dẫn chia sẻ riêng hoặc dữ liệu thô. Push branch cá nhân và mở PR sau khi kiểm tra; không force-push `main`.

| Loại thay đổi | Commit? | Nơi lưu/gửi |
|---|---|---|
| Source, notebook sạch, configs không secret, tests, docs | Có | GitHub/PR |
| Báo cáo metric tổng hợp nhỏ, nguồn và checksum | Có sau khi review | `docs/experiments/` |
| Raw Music4All/Onion, MP3/lyrics, CSR/model | Không | Kho riêng/Drive/private Dataset |
| API key, `.env`, token, mật khẩu archive | Không | Kênh riêng/secret store phù hợp |
| node_modules, virtualenv, `.next`, cache | Không | Tái tạo từ lock files |

## 8. Lệnh kiểm tra theo vai trò

```bash
# Training, từ root
uv run --project recommender/training pytest -c recommender/training/pyproject.toml recommender/training/tests -q
uv run --project recommender/training ruff check recommender/training scripts/package_kaggle_code.py
uv run --project recommender/training ruff format --check recommender/training scripts/package_kaggle_code.py

# Backend + frontend gate trong bản sao không chứa app .env
uv run --project backend python scripts/check_research_demo.py

# Chỉ frontend
npm --prefix frontend run lint
npm --prefix frontend run build
```

**Điều kiện hoàn thành mốc sắp tới:** có run thật và bảng metric, nhóm nạp lại được artifact, backend trả gợi ý và frontend hiển thị đúng. Có thể hoàn thành mốc này trước khi có audio; không báo đã phát nhạc hoặc đã có xu hướng hiện tại nếu chưa triển khai.
