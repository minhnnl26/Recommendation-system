# Kiểm tra bộ training Kaggle — 2026-11-27

## Đã kiểm tra

| Lệnh/kiểm tra | Kết quả |
|---|---|
| `uv sync --project recommender/training --dev` | Cài thành công môi trường riêng và tạo uv.lock; Python 3.10 |
| `uv run --project recommender/training pytest -c recommender/training/pyproject.toml recommender/training/tests -q` | **7 passed** |
| `ruff check recommender/training scripts/package_kaggle_code.py` | Passed |
| `ruff format --check recommender/training scripts/package_kaggle_code.py` | Passed |
| `python -m compileall -q recommender/training scripts/package_kaggle_code.py` | Passed |
| Notebook JSON + parse từng code cell | Passed; mọi execution_count null, outputs rỗng |
| Code-only Kaggle package | 12 file theo allowlist; không có env/data/model |
| Gate ứng dụng `scripts/check_research_demo.py` | 36 unit + 1 real-artifact integration passed; backend Ruff/compileall passed |
| Frontend `npm run lint`, `npm run build` trong bản sao bỏ env | Passed; `/research` và `/catalog` build được |
| `git diff --check` | Passed |
| Kiểm tra candidate source theo credential patterns | Không phát hiện credential thật; các URL loopback/test giả được phân biệt |
| Kiểm tra đường dẫn file môi trường riêng trong reachable Git history | Không phát hiện; không đọc các file env bị cấm |

Test training dùng dữ liệu **tổng hợp**, bao gồm cả file giả chỉ để kiểm tra inventory, không phải MP3 có thể phát. Hai test thực sự fit/lưu/nạp lại ALS, kiểm tra hash/temporal split không giao nhau, warm/cold/session inference, điểm hữu hạn và không trả bài train. Các test khác kiểm tra thiếu audio, thiếu timestamp không fallback, chuẩn hóa, giữ toàn bộ file khi shard và classifier đa nhãn có val/test.

Gate ứng dụng được chạy trong bản sao loại mọi `.env*`, không chạy Supabase cloud integration. Có một cảnh báo deprecation từ Starlette/AnyIO trong TestClient, không làm test thất bại. Lần gọi pytest đầu tiên thiếu `-c` đã collect nhầm nhiều project; hướng dẫn và lệnh cuối đã được sửa để chỉ dùng config/tests training. Temporal test phát hiện dependency `pytz` còn thiếu; đã bổ sung vào cả pyproject và requirements trước lần pass cuối.

## Chưa được xác minh

- Chưa nhận bộ Music4All gốc đầy đủ từ tác giả; không tuyên bố đã tải đủ 109.269 audio/lyrics.
- Chưa có file Onion timestamp đầy đủ trong workspace, chưa chạy prepare/ALS full-scale trên dữ liệu thật.
- Chưa chạy notebook bằng tài khoản Kaggle, chưa đo RAM/disk/time trên runtime Kaggle.
- Chưa kiểm thử GPU/CUDA hoặc bộ classifier bằng embedding âm thanh thật.
- Chưa decode toàn bộ MP3; inventory không chứng minh audio hợp lệ hoặc quyền phát.
- Chưa tích hợp artifact ALS mới vào FastAPI/frontend; CLI inference có sẵn, `/research` vẫn dùng baseline Item-kNN hiện tại.
- Chưa có training deep encoder, LightFM, trending worker, authentication, session persistence hoặc production deployment trong thay đổi này.

Những giới hạn trên được giữ rõ trong [hướng dẫn Kaggle](KAGGLE_TRAINING.md) và [hướng dẫn tải dữ liệu](MUSIC4ALL_DATASET_SETUP.md). Không sửa `.env`, không tạo/reset database, không gọi Supabase cloud.
