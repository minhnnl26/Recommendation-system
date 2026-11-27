"""Audit Music4All-Onion metadata and exact interaction coverage without training."""

import argparse
import ast
import bz2
import csv
import json
import math
import shutil
from collections import Counter
from datetime import datetime, timezone

import duckdb
from download_music4all import FILES, RAW_DIR, RECORD_URL, ROOT, file_hash
from lastfm_eda import plt

OUT_DIR = ROOT / "docs/eda/music4all-onion"
PROCESSED = ROOT / "data/processed/music4all-onion"


def metadata(raw_dir):
    genre_ids = set()
    genre_nonempty = set()
    genre_counts = Counter()
    genre_frequency = Counter()
    genre_bad_rows = 0
    with bz2.open(raw_dir / "id_genres_tf-idf.tsv.bz2", "rt", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        if header[0] != "id" or len(set(header)) != len(header):
            raise ValueError("Unexpected genre header")
        labels = header[1:]
        for row in reader:
            if len(row) != len(header) or not row[0]:
                raise ValueError("Invalid genre row structure")
            track = row[0]
            if track in genre_ids:
                raise ValueError("Duplicate genre track ID")
            genre_ids.add(track)
            try:
                weights = [float(value) for value in row[1:]]
                valid = all(math.isfinite(v) and v >= 0 for v in weights)
            except ValueError:
                valid = False
            if not valid:
                genre_bad_rows += 1
                continue
            active = [label for label, weight in zip(labels, weights) if weight > 0]
            genre_counts[len(active)] += 1
            if active:
                genre_nonempty.add(track)
                genre_frequency.update(active)
    tag_ids = set()
    tags_nonempty = set()
    tag_counts = Counter()
    tag_frequency = Counter()
    tag_bad_rows = 0
    tag_rows = 0
    duplicate_tag_rows = 0
    conflicting_tag_ids = set()
    merged_tags = {}
    with bz2.open(raw_dir / "id_tags_dict.tsv.bz2", "rt", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        if next(reader) != ["id", "(tag, weight)"]:
            raise ValueError("Unexpected tags header")
        for row in reader:
            tag_rows += 1
            if len(row) != 2 or not row[0]:
                raise ValueError("Invalid tags row structure")
            track = row[0]
            if track in tag_ids:
                duplicate_tag_rows += 1
            tag_ids.add(track)
            try:
                tags = ast.literal_eval(row[1])
                valid = isinstance(tags, dict) and all(
                    isinstance(k, str)
                    and k.strip()
                    and isinstance(v, (int, float))
                    and not isinstance(v, bool)
                    and math.isfinite(v)
                    and v >= 0
                    for k, v in tags.items()
                )
            except (ValueError, SyntaxError):
                valid = False
            if not valid:
                tag_bad_rows += 1
                continue
            active = {k.strip().casefold() for k, v in tags.items() if v > 0}
            if track in merged_tags and merged_tags[track] != active:
                conflicting_tag_ids.add(track)
            merged_tags.setdefault(track, set()).update(active)
    for track, active in merged_tags.items():
        tag_counts[len(active)] += 1
        if active:
            tags_nonempty.add(track)
            tag_frequency.update(active)
    stats = {
        "genre_rows": len(genre_ids),
        "genre_dimensions": len(labels),
        "genre_tracks_nonzero": len(genre_nonempty),
        "genre_tracks_zero": genre_counts[0],
        "genre_invalid_vectors": genre_bad_rows,
        "tag_rows": tag_rows,
        "tag_unique_ids": len(tag_ids),
        "duplicate_tag_id_rows": duplicate_tag_rows,
        "conflicting_tag_ids": len(conflicting_tag_ids),
        "tag_tracks_nonempty": len(tags_nonempty),
        "tag_tracks_empty": tag_counts[0],
        "tag_invalid_dicts": tag_bad_rows,
        "unique_positive_tags": len(tag_frequency),
        "metadata_id_intersection": len(genre_ids & tag_ids),
        "metadata_both_nonempty": len(genre_nonempty & tags_nonempty),
        "genres_per_track_distribution": dict(sorted(genre_counts.items())),
        "tags_per_track_distribution": dict(sorted(tag_counts.items())),
        "top_genres": genre_frequency.most_common(20),
        "top_tags": tag_frequency.most_common(20),
    }
    rows = [
        (
            track,
            track in genre_ids,
            track in genre_nonempty,
            track in tag_ids,
            track in tags_nonempty,
        )
        for track in sorted(genre_ids | tag_ids)
    ]
    return stats, rows


def coverage(con, path, rows):
    with path.open(encoding="utf-8", newline="") as stream:
        if next(csv.reader(stream, delimiter="\t")) != ["user_id", "track_id", "count"]:
            raise ValueError("Unexpected interaction header")
    con.execute(
        "CREATE OR REPLACE TABLE features "
        "(track_id VARCHAR PRIMARY KEY, genre_row BOOLEAN, has_genre BOOLEAN, "
        "tag_row BOOLEAN, has_tags BOOLEAN)"
    )
    con.execute("BEGIN TRANSACTION")
    con.executemany("INSERT INTO features VALUES (?, ?, ?, ?, ?)", rows)
    con.execute("COMMIT")
    con.execute(
        """CREATE OR REPLACE TABLE raw_interactions AS
        SELECT * FROM read_csv(?, delim='\t', header=true,
          columns={'user_id':'VARCHAR', 'track_id':'VARCHAR', 'count':'VARCHAR'},
          quote='', escape='', ignore_errors=false, parallel=false)""",
        [str(path)],
    )
    con.execute(
        """CREATE OR REPLACE TABLE interactions AS
        SELECT nullif(trim(user_id), '') user_id,
               nullif(trim(track_id), '') track_id,
               try_cast(count AS BIGINT) plays
        FROM raw_interactions"""
    )
    invalid = con.execute(
        "SELECT count(*) FROM raw_interactions WHERE nullif(trim(user_id),'') IS NULL "
        "OR nullif(trim(track_id),'') IS NULL "
        "OR NOT regexp_full_match(trim(count), '[0-9]+') "
        "OR try_cast(count AS BIGINT) IS NULL OR try_cast(count AS BIGINT) <= 0"
    ).fetchone()[0]
    if invalid:
        raise ValueError(
            f"Found {invalid} invalid interaction rows; define cleaning first"
        )
    con.execute(
        """CREATE OR REPLACE TABLE track_totals AS
        SELECT track_id, count(*) pair_rows, sum(plays)::BIGINT plays
        FROM interactions GROUP BY 1"""
    )
    con.execute(
        """CREATE OR REPLACE TABLE track_coverage AS
        SELECT t.*, coalesce(f.genre_row, false) genre_row,
          coalesce(f.has_genre, false) has_genre,
          coalesce(f.tag_row, false) tag_row,
          coalesce(f.has_tags, false) has_tags
        FROM track_totals t LEFT JOIN features f USING(track_id)"""
    )
    totals = con.execute(
        "SELECT count(*), count(DISTINCT user_id), sum(plays)::BIGINT FROM interactions"
    ).fetchone()
    result = {
        "pair_rows": totals[0],
        "users": totals[1],
        "total_plays": totals[2],
        "tracks": con.execute("SELECT count(*) FROM track_totals").fetchone()[0],
        "invalid_rows": invalid,
        "coverage": {},
    }
    # Exact distinct-pair count is partitioned by user to bound hash-table memory.
    distinct_pairs = 0
    for bucket in range(16):
        distinct_pairs += con.execute(
            "SELECT count(*) FROM (SELECT DISTINCT user_id, track_id FROM interactions "
            "WHERE hash(user_id) % 16 = ?)",
            [bucket],
        ).fetchone()[0]
    result["unique_pairs"] = distinct_pairs
    result["duplicate_pair_rows"] = totals[0] - distinct_pairs
    result["sparsity"] = 1 - distinct_pairs / (totals[1] * result["tracks"])
    for label, condition in {
        "genre_row": "genre_row",
        "nonzero_genre": "has_genre",
        "tag_row": "tag_row",
        "nonempty_tags": "has_tags",
        "both_nonempty": "has_genre AND has_tags",
    }.items():
        n, pairs, plays = con.execute(
            f"SELECT count(*), coalesce(sum(pair_rows),0)::BIGINT, "
            f"coalesce(sum(plays),0)::BIGINT FROM track_coverage WHERE {condition}"
        ).fetchone()
        result["coverage"][label] = {
            "tracks": n,
            "track_fraction": n / result["tracks"],
            "pair_rows": pairs,
            "pair_row_fraction": pairs / result["pair_rows"],
            "plays": plays,
            "play_fraction": plays / result["total_plays"],
        }
    result["genre_feature_tracks_without_interactions"] = con.execute(
        "SELECT count(*) FROM features f WHERE f.has_genre "
        "AND NOT EXISTS (SELECT 1 FROM track_totals t WHERE t.track_id=f.track_id)"
    ).fetchone()[0]
    result["users_with_both_features"] = con.execute(
        "SELECT count(DISTINCT i.user_id) FROM interactions i "
        "JOIN features f USING(track_id) WHERE f.has_genre AND f.has_tags"
    ).fetchone()[0]
    return result


def charts(stats, interactions, output):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    top = stats["top_genres"][:15][::-1]
    axes[0].barh([v[0] for v in top], [v[1] for v in top], color="#247e74")
    axes[0].set(title="Top 15 genres: tracks with positive TF-IDF", xlabel="Tracks")
    if interactions:
        labels = ["Nonzero genre", "Nonempty tags", "Both"]
        keys = ["nonzero_genre", "nonempty_tags", "both_nonempty"]
        x = list(range(3))
        axes[1].bar(
            [v - 0.18 for v in x],
            [100 * interactions["coverage"][k]["track_fraction"] for k in keys],
            width=0.36,
            label="Tracks",
            color="#426da6",
        )
        axes[1].bar(
            [v + 0.18 for v in x],
            [100 * interactions["coverage"][k]["play_fraction"] for k in keys],
            width=0.36,
            label="Play counts",
            color="#bb7837",
        )
        axes[1].set_xticks(x, labels)
        axes[1].set(
            ylim=(0, 110),
            ylabel="Coverage (%)",
            title="Coverage within the interaction catalog",
        )
        axes[1].legend()
    else:
        axes[1].bar(
            ["Genre rows", "Nonzero genre", "Nonempty tags", "Both"],
            [
                stats["genre_rows"],
                stats["genre_tracks_nonzero"],
                stats["tag_tracks_nonempty"],
                stats["metadata_both_nonempty"],
            ],
            color=["#426da6", "#247e74", "#bb7837", "#8558a2"],
        )
        axes[1].set(title="Metadata availability", ylabel="Tracks")
    fig.savefig(output / "coverage.png", dpi=150)
    plt.close(fig)


def report(stats, interactions, manifest):
    number = lambda x: f"{x:,}"
    percent = lambda x: f"{100 * x:.2f}%"
    top = "\n".join(
        f"| {name.replace('|', '/')} | {number(count)} |"
        for name, count in stats["top_genres"][:15]
    )
    checks = "\n".join(
        f"| `{name}` | {number(item['bytes'])} | Đạt |"
        for name, item in manifest["files"].items()
    )
    interaction_text = "Chưa tải interaction: chưa có bằng chứng về độ phủ user–song."
    decision = "Chưa kết luận chuyển dataset trước khi đo độ phủ interaction."
    if interactions:
        genre = interactions["coverage"]["nonzero_genre"]
        both = interactions["coverage"]["both_nonempty"]
        decision = (
            "Với mục tiêu thử hệ lai có thể loại, dữ liệu đã đo phù hợp hơn Last.fm 1K "
            "không có sẵn genre. Nên bắt đầu với genre làm feature chính: giữ "
            f"{number(genre['tracks'])} bài, bao phủ {percent(genre['play_fraction'])} "
            "lượt nghe. Tags là feature bổ sung; nếu bắt buộc có cả hai thì chỉ giữ "
            f"{percent(both['track_fraction'])} bài nhưng giữ "
            f"{percent(both['play_fraction'])} lượt nghe, nên có nguy cơ thiên về "
            "bài phổ biến. Chưa kết luận mô hình chính xác hơn khi chưa train và đánh giá."
        )
        names = {
            "genre_row": "Có dòng genre (kể cả vector rỗng)",
            "nonzero_genre": "Có ít nhất một genre trọng số dương",
            "tag_row": "Có dòng tags",
            "nonempty_tags": "Có ít nhất một tag trọng số dương",
            "both_nonempty": "Có cả genre và tags hữu dụng",
        }
        cov = "\n".join(
            f"| {names[k]} | {number(v['tracks'])} | {percent(v['track_fraction'])} "
            f"| {percent(v['pair_row_fraction'])} | {percent(v['play_fraction'])} |"
            for k, v in interactions["coverage"].items()
        )
        interaction_text = f"""Đã phân tích **toàn bộ file interaction count**, không lấy mẫu.

| Chỉ tiêu đo trực tiếp | Kết quả |
|---|---:|
| Dòng user–track–count | {number(interactions["pair_rows"])} |
| Cặp user–track khác nhau | {number(interactions["unique_pairs"])} |
| Dòng cặp bị lặp | {number(interactions["duplicate_pair_rows"])} |
| Người dùng | {number(interactions["users"])} |
| Bài xuất hiện trong interaction | {number(interactions["tracks"])} |
| Tổng lượt nghe từ sum(count) | {number(interactions["total_plays"])} |
| Độ thưa user–song | {percent(interactions["sparsity"])} |
| User có tương tác với bài đủ genre và tags | {number(interactions["users_with_both_features"])} |

Một dòng là một cặp user–track với tổng lượt nghe, không phải một event riêng lẻ.
Độ phủ theo cặp và độ phủ theo lượt nghe có mẫu số khác nhau.

| Điều kiện | Bài | % bài trong interaction | % dòng cặp | % lượt nghe |
|---|---:|---:|---:|---:|
{cov}

Có {number(interactions["genre_feature_tracks_without_interactions"])} bài có genre
nhưng không có interaction trong file count này. Có thể dùng để nghiên cứu item
không có tương tác, nhưng không gọi đó là bài mới phát hành vì chưa có release date.
"""
    return f"""# Kiểm tra Music4All-Onion trước khi chọn làm dataset chính

> Phạm vi: metadata genre/tags và file user–track–count nếu có. Không training,
> không tải audio, không gọi iTunes/Jamendo/Supabase và không thay dataset hiện có.
> Thời điểm UTC: {manifest["analyzed_at_utc"]}.

## 1. Nguồn và tính toàn vẹn

[Music4All-Onion v2, DOI 10.5281/zenodo.15394646]({RECORD_URL}) là nguồn phát hành.
Script so MD5 các file nén với checksum công bố, đồng thời lưu SHA-256 trong manifest.
Không tải toàn bộ các feature audio/video/lyrics khoảng 20 GB.

| File | Dung lượng nén (bytes) | Kiểm tra MD5 |
|---|---:|---|
{checks}

README nguồn giải thích cấu trúc feature và interaction. Điều kiện sử dụng của
metadata/feature không tự cấp quyền phát các bản nhạc gốc. Bước này chỉ phân tích
các file nghiên cứu, chưa xác nhận khả năng playback hoặc metadata tên bài đầy đủ.

## 2. Cấu trúc dữ liệu thật

### Genre TF-IDF

```text
id    genre_1    genre_2    ...    genre_N
```

Header thực tế có {stats["genre_dimensions"]} cột genre ngoài cột ID. Mỗi hàng là
một vector feature của bài hát. Trọng số dương thể hiện genre có mặt trong biểu diễn;
trọng số TF-IDF không phải xác suất và không bắt buộc nằm trong [0,1].

### Tags

```text
id    (tag, weight)
```

Cột thứ hai chứa dictionary theo cú pháp Python, ví dụ `{{'pop': 100}}`, không phải
JSON chuẩn. Script dùng `ast.literal_eval`, không dùng `eval`. Tags có thể là genre,
mood, địa điểm hoặc nhãn cá nhân; không xem mọi tag đều là thể loại âm nhạc.

### Interaction

```text
user_id    track_id    count
```

ID của các file trong Music4All-Onion được so khớp theo chuỗi ID nội bộ. Chưa có
bằng chứng các ID này trùng MusicBrainz ID của Last.fm 1K hoặc ID của Jamendo.
Không join chéo các dataset theo ID chỉ vì cả hai đều có cột `trackid`.

## 3. Chất lượng metadata

| Chỉ tiêu | Kết quả |
|---|---:|
| Dòng genre | {number(stats["genre_rows"])} |
| Bài có vector genre khác 0 | {number(stats["genre_tracks_nonzero"])} |
| Bài có vector genre toàn 0 | {number(stats["genre_tracks_zero"])} |
| Vector genre không hợp lệ | {number(stats["genre_invalid_vectors"])} |
| Dòng tags | {number(stats["tag_rows"])} |
| ID khác nhau trong file tags | {number(stats["tag_unique_ids"])} |
| Dòng lặp ID trong file tags | {number(stats["duplicate_tag_id_rows"])} |
| ID có tập tag dương khác nhau giữa các dòng lặp | {number(stats["conflicting_tag_ids"])} |
| Bài có ít nhất một tag dương | {number(stats["tag_tracks_nonempty"])} |
| Dictionary tags không hợp lệ | {number(stats["tag_invalid_dicts"])} |
| Số tên tag dương khác nhau sau trim/casefold | {number(stats["unique_positive_tags"])} |
| Giao ID của hai file metadata | {number(stats["metadata_id_intersection"])} |
| Bài có cả genre và tags hữu dụng | {number(stats["metadata_both_nonempty"])} |

Script yêu cầu ID không rỗng; từ chối lỗi cấu trúc và ID genre trùng. Với tags,
ID lặp được đếm rõ và hợp nhất tập tag dương, không cộng dồn trọng số hoặc đếm
một track nhiều lần trong biểu đồ tần suất. Vector genre
chỉ hợp lệ nếu mọi phần tử hữu hạn, không âm. Trọng số tags được kiểm tra tương tự.
Vector toàn 0 hoặc dict không có tag dương là metadata không hữu dụng, dù vẫn có ID.

## 4. Độ phủ interaction với metadata

{interaction_text}

## 5. Phân bố thể loại

| Genre | Số bài có trọng số dương |
|---|---:|
{top}

Đây là phân bố theo file genre toàn catalog, không chỉ tập interaction. Một bài có
thể có nhiều genre nên không cộng số lượt nhãn thành số bài. Các nhãn thưa và lệch
phân bố cần được xét khi chọn baseline và đánh giá theo genre.

![Genre và độ phủ dữ liệu](coverage.png)

## 6. Khả năng đáp ứng đề tài

| Yêu cầu | Khả năng của các file đã kiểm tra |
|---|---|
| Lọc cộng tác từ lịch sử | File count cho phép tạo ma trận sparse user–song |
| Gợi ý theo genre/tags | Dùng vector genre và tags sau xử lý thiếu/rỗng |
| Cá nhân hóa content | Tổng hợp feature từ bài user nghe để tạo user profile |
| Xu hướng gần đây | Chưa đo được bằng count tổng; cần timestamp |
| Thứ tự phiên, temporal split | Chưa làm vì chưa tải file timestamp |
| Skip, like, search | Không có trong các file đang phân tích |
| Audio, phát nhạc trên website | Không có trong các file đã tải |
| Tên bài, artist, album cho UI | Chưa xác nhận trong các file hiện có; cần metadata gốc |
| Bài mới từ Jamendo | Cần importer và mapping catalog riêng |

So với Last.fm 1K, ưu điểm là có feature genre/tags và interaction dùng cùng hệ ID
nội bộ. Chỉ đo độ phủ thực tế, không suy ra mọi bài trong catalog đều có lịch sử.
Đây vẫn là dữ liệu lịch sử và không phản ánh xu hướng hiện nay.

## 7. Hướng sử dụng sau kiểm tra

{decision}

1. Dùng phần giao có metadata hữu dụng để thử popularity, content-based và ALS.
2. Báo riêng kết quả khi giữ hoặc loại bài thiếu genre; tránh chỉ chọn nhóm thuận lợi.
3. Genre TF-IDF được cung cấp sẵn là biến đổi của tác giả; chưa tái lập IDF trên train.
   Khi cần protocol nghiêm ngặt, cân nhắc xây lại feature từ nhãn gốc hoặc binarize
   có giải thích. Không dùng lượt nghe trong test để tạo profile hoặc score xu hướng.
4. Tải timestamp như bước riêng sau khi chốt dataset; kiểm tra ngày và temporal split.
5. Dùng Jamendo cho nhánh ứng dụng, chưa gắn model benchmark trực tiếp vào catalog
   provider nếu chưa kiểm tra mapping và quyền playback.

## 8. Tái lập

```bash
cd recommender/eda
uv run python download_music4all.py --include-interactions
uv run python music4all_audit.py
```

Script audit không có truy cập mạng. File lớn nằm ở `data/` đã Git ignore. Báo cáo,
biểu đồ, metrics và manifest ở `docs/eda/music4all-onion/`. Không huấn luyện model.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    names = [
        name
        for name in FILES
        if not name.startswith("userid_") or not args.metadata_only
    ]
    manifest = {
        "record": RECORD_URL,
        "sampled": False,
        "files": {},
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    for name in names:
        path = RAW_DIR / name
        if file_hash(path) != FILES[name]:
            raise ValueError(f"Source checksum mismatch: {name}")
        manifest["files"][name] = {
            "bytes": path.stat().st_size,
            "md5": FILES[name],
            "sha256": file_hash(path, "sha256"),
        }
    print("Auditing complete genre and tag metadata...", flush=True)
    stats, rows = metadata(RAW_DIR)
    interactions = None
    if not args.metadata_only:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        path = PROCESSED / "userid_trackid_count.tsv"
        if not path.exists():
            print("Decompressing original interaction counts...", flush=True)
            partial = path.with_suffix(".tsv.partial")
            with (
                bz2.open(RAW_DIR / "userid_trackid_count.tsv.bz2", "rb") as src,
                partial.open("wb") as dest,
            ):
                shutil.copyfileobj(src, dest, length=8 * 1024 * 1024)
            partial.replace(path)
        print("Measuring exact coverage over all interaction rows...", flush=True)
        with duckdb.connect(str(PROCESSED / "audit.duckdb")) as con:
            con.execute("SET memory_limit='2GB'")
            con.execute("SET threads=1")
            con.execute("SET preserve_insertion_order=false")
            interactions = coverage(con, path, rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metrics = {"metadata": stats, "interactions": interactions}
    for name, value in (("metrics.json", metrics), ("manifest.json", manifest)):
        (OUT_DIR / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    charts(stats, interactions, OUT_DIR)
    (OUT_DIR / "REPORT.md").write_text(
        report(stats, interactions, manifest), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "genre_rows": stats["genre_rows"],
                "genre_nonempty": stats["genre_tracks_nonzero"],
                "tags_nonempty": stats["tag_tracks_nonempty"],
                "interaction_tracks": interactions["tracks"] if interactions else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
