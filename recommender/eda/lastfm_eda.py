"""Analyze the full original TSV, preserving the distinction between events and songs."""

import argparse
import hashlib
import json
import math
import os
import shutil
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data/cache/matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW_DIR = ROOT / "data/raw/lastfm-1k"
REPORT_DIR = ROOT / "docs/eda/lastfm-1k"
MEMBER = "userid-timestamp-artid-artname-traid-traname.tsv"
EXPECTED_MD5 = "64747b21563e3d2aa95751e0ddc46b68"
SOURCE = (
    "https://github.com/eifuentes/lastfm-dataset-1K/releases/download/v1.0/"
    "userid-timestamp-artid-artname-traid-traname.tsv.zip"
)
COLUMNS = [
    "user_id",
    "timestamp_raw",
    "artist_id",
    "artist_name",
    "track_id",
    "track_name",
]
UUID_PATTERN = "^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$"


def fingerprint(path):
    md5 = hashlib.md5()  # Integrity against the original README, not cryptography.
    sha = hashlib.sha256()
    lines = 0
    last = b""
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            md5.update(block)
            sha.update(block)
            lines += block.count(b"\n")
            last = block[-1:]
    return {
        "md5": md5.hexdigest(),
        "sha256": sha.hexdigest(),
        "bytes": path.stat().st_size,
        "physical_lines": lines + int(bool(last) and last != b"\n"),
    }


def prepare_input(archive):
    target = archive.parent / MEMBER
    if not target.exists():
        # Extract only the known member; never unpack arbitrary archive paths.
        with zipfile.ZipFile(archive) as bundle:
            members = [name for name in bundle.namelist() if Path(name).name == MEMBER]
            if len(members) != 1:
                raise ValueError("Expected exactly one original events TSV")
            partial = target.with_suffix(".tsv.partial")
            with bundle.open(members[0]) as source, partial.open("wb") as dest:
                shutil.copyfileobj(source, dest, length=8 * 1024 * 1024)
            partial.replace(target)
    return target


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def load_events(con, path, cutoff):
    definitions = ", ".join(f"'{name}': 'VARCHAR'" for name in COLUMNS)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw AS
        SELECT * FROM read_csv(?, delim='\t', header=false,
            columns={{{definitions}}}, quote='', escape='',
            nullstr='', ignore_errors=true, store_rejects=true,
            rejects_table='csv_rejects', rejects_scan='csv_scans',
            rejects_limit=0, parallel=false, strict_mode=true)
        """,
        [str(path)],
    )
    names = ", ".join(f"nullif(trim({name}), '') AS {name}" for name in COLUMNS)
    con.execute(
        "CREATE OR REPLACE TABLE normalized AS SELECT *, "
        "try_cast(timestamp_raw AS TIMESTAMPTZ) AS occurred_at "
        f"FROM (SELECT {names} FROM raw)"
    )
    # Strict MusicBrainz track identity avoids silently merging homonymous songs.
    con.execute(
        """
        CREATE OR REPLACE TABLE eligible AS
        SELECT user_id, occurred_at, lower(artist_id) AS artist_id,
               artist_name, lower(track_id) AS track_id, track_name
        FROM normalized
        WHERE user_id IS NOT NULL AND artist_name IS NOT NULL
          AND track_name IS NOT NULL
          AND regexp_full_match(track_id, ?)
          AND occurred_at >= TIMESTAMPTZ '1970-01-01'
          AND occurred_at < (CAST(? AS DATE) + INTERVAL 1 DAY)::TIMESTAMPTZ
        """,
        [UUID_PATTERN, cutoff],
    )
    con.execute("CREATE OR REPLACE TABLE events AS SELECT * FROM eligible WHERE false")
    # A user's events stay in one bucket, so DISTINCT remains globally exact.
    for bucket in range(16):
        con.execute(
            "INSERT INTO events SELECT DISTINCT * FROM eligible "
            "WHERE hash(user_id) % 16 = ?",
            [bucket],
        )
    con.execute(
        """
        CREATE OR REPLACE TABLE pairs AS
        SELECT user_id, track_id, count(*) AS plays FROM events GROUP BY 1,2
        """
    )


def distribution(con, sql):
    row = con.execute(
        f"""SELECT min(n), median(n), avg(n), quantile_cont(n, 0.9),
                   quantile_cont(n, 0.99), max(n) FROM ({sql})"""
    ).fetchone()
    return dict(zip(["min", "median", "mean", "p90", "p99", "max"], row))


def analyze(con, cutoff):
    raw_count = one(con, "SELECT count(*) FROM raw")
    missing = {
        name: one(con, f"SELECT count(*) FROM normalized WHERE {name} IS NULL")
        for name in COLUMNS
    }
    n = one(con, "SELECT count(*) FROM events")
    users = one(con, "SELECT count(DISTINCT user_id) FROM events")
    tracks = one(con, "SELECT count(DISTINCT track_id) FROM events")
    pairs = one(con, "SELECT count(*) FROM pairs")
    top_tracks = con.execute(
        """WITH names AS (
            SELECT track_id, track_name, artist_name, count(*) n,
                   row_number() OVER (
                     PARTITION BY track_id ORDER BY count(*) DESC, track_name, artist_name
                   ) AS rank
            FROM events GROUP BY 1,2,3
        ), counts AS (SELECT track_id, sum(plays) plays FROM pairs GROUP BY 1)
        SELECT names.track_name, names.artist_name, counts.plays
        FROM counts JOIN names USING(track_id) WHERE names.rank=1
        ORDER BY counts.plays DESC, names.track_id LIMIT 10"""
    ).fetchall()
    bounds = con.execute(
        "SELECT min(occurred_at), max(occurred_at) FROM normalized"
    ).fetchone()
    clean_bounds = con.execute(
        "SELECT min(occurred_at), max(occurred_at) FROM events"
    ).fetchone()
    invalid_time = one(con, "SELECT count(*) FROM normalized WHERE occurred_at IS NULL")
    after_cutoff = con.execute(
        "SELECT count(*) FROM normalized WHERE occurred_at >= "
        "(CAST(? AS DATE) + INTERVAL 1 DAY)::TIMESTAMPTZ",
        [cutoff],
    ).fetchone()[0]
    invalid_ids = con.execute(
        "SELECT count(*) FROM normalized WHERE track_id IS NOT NULL "
        "AND NOT regexp_full_match(track_id, ?)",
        [UUID_PATTERN],
    ).fetchone()[0]
    eligible = one(con, "SELECT count(*) FROM eligible")
    top_count = max(1, math.ceil(tracks * 0.01))
    concentration = con.execute(
        "SELECT sum(n) FROM (SELECT sum(plays) n FROM pairs "
        "GROUP BY track_id ORDER BY n DESC LIMIT ?)",
        [top_count],
    ).fetchone()[0]
    repeat_events = n - pairs
    train_boundary, val_boundary = con.execute(
        "SELECT quantile_disc(occurred_at, 0.8), "
        "quantile_disc(occurred_at, 0.9) FROM events"
    ).fetchone()
    con.execute(
        """CREATE OR REPLACE TABLE split_preview AS
        SELECT *, CASE WHEN occurred_at < ? THEN 'train'
                       WHEN occurred_at < ? THEN 'validation' ELSE 'test' END AS split
        FROM events""",
        [train_boundary, val_boundary],
    )
    splits = dict(
        con.execute("SELECT split, count(*) FROM split_preview GROUP BY 1").fetchall()
    )
    cold = con.execute(
        """WITH train AS (SELECT DISTINCT track_id FROM split_preview WHERE split='train')
        SELECT count(*), count(DISTINCT e.track_id) FROM split_preview e
        WHERE e.split='test' AND NOT EXISTS
        (SELECT 1 FROM train t WHERE t.track_id=e.track_id)"""
    ).fetchone()
    new_users = one(
        con,
        """SELECT count(DISTINCT e.user_id) FROM split_preview e WHERE split='test'
        AND NOT EXISTS (SELECT 1 FROM split_preview t
                        WHERE t.split='train' AND t.user_id=e.user_id)""",
    )
    con.execute(
        """CREATE OR REPLACE TABLE train_seen_repeat AS
        SELECT e.user_id, e.track_id FROM split_preview e WHERE e.split='test'
        AND EXISTS (SELECT 1 FROM split_preview t WHERE t.split='train'
                    AND t.user_id=e.user_id AND t.track_id=e.track_id)"""
    )
    return {
        "parsed_rows": raw_count,
        "raw_users": one(con, "SELECT count(DISTINCT user_id) FROM normalized"),
        "raw_nonempty_track_ids": one(
            con, "SELECT count(DISTINCT track_id) FROM normalized"
        ),
        "malformed_lines": one(con, "SELECT count(DISTINCT line) FROM csv_rejects"),
        "missing": missing,
        "raw_time_range": [str(x) for x in bounds],
        "invalid_timestamps": invalid_time,
        "before_1970": one(
            con,
            "SELECT count(*) FROM normalized "
            "WHERE occurred_at < TIMESTAMPTZ '1970-01-01'",
        ),
        "after_source_cutoff": after_cutoff,
        "invalid_nonempty_track_ids": invalid_ids,
        "eligible_before_dedup": eligible,
        "exact_duplicates_removed": eligible - n,
        "clean_events": n,
        "users": users,
        "tracks": tracks,
        "artists_with_mbid": one(
            con,
            "SELECT count(DISTINCT artist_id) FROM events WHERE artist_id IS NOT NULL",
        ),
        "unique_user_song_pairs": pairs,
        "sparsity": 1 - pairs / (users * tracks),
        "retention": n / raw_count,
        "repeat_event_fraction": repeat_events / n,
        "top_one_percent_track_share": concentration / n,
        "singleton_track_count": one(
            con,
            "SELECT count(*) FROM "
            "(SELECT track_id FROM pairs GROUP BY 1 HAVING sum(plays)=1)",
        ),
        "track_ids_with_multiple_names": one(
            con,
            "SELECT count(*) FROM "
            "(SELECT track_id FROM events GROUP BY 1 "
            "HAVING count(DISTINCT track_name)>1)",
        ),
        "clean_time_range": [str(x) for x in clean_bounds],
        "events_per_user": distribution(
            con, "SELECT count(*) n FROM events GROUP BY user_id"
        ),
        "distinct_songs_per_user": distribution(
            con, "SELECT count(*) n FROM pairs GROUP BY user_id"
        ),
        "events_per_track": distribution(
            con, "SELECT sum(plays) n FROM pairs GROUP BY track_id"
        ),
        "top_tracks": top_tracks,
        "temporal_preview": {
            "train_validation_boundary": str(train_boundary),
            "validation_test_boundary": str(val_boundary),
            "events": splits,
            "cold_test_events": cold[0],
            "cold_test_tracks": cold[1],
            "cold_test_users": new_users,
            "test_events_previously_seen_user_song": one(
                con, "SELECT count(*) FROM train_seen_repeat"
            ),
        },
    }


def csv_export(con, sql, path):
    con.execute("COPY (" + sql + ") TO ? (HEADER, DELIMITER ',')", [str(path)])


def make_outputs(con, out):
    out.mkdir(parents=True, exist_ok=True)
    exports = {
        "monthly": "SELECT date_trunc('month', occurred_at)::DATE AS month_start, count(*) events "
        "FROM events GROUP BY 1 ORDER BY 1",
        "users": "SELECT user_id, count(*) events, count(DISTINCT track_id) songs "
        "FROM events GROUP BY 1 ORDER BY events DESC, user_id",
        "track_popularity": "SELECT track_id, sum(plays) events, count(*) listeners "
        "FROM pairs GROUP BY 1 ORDER BY events DESC, track_id",
        "missing": "SELECT column_name, missing_count FROM ("
        + " UNION ALL ".join(
            f"SELECT '{name}' column_name, count(*) missing_count "
            f"FROM normalized WHERE {name} IS NULL"
            for name in COLUMNS
        )
        + ")",
    }
    for name, query in exports.items():
        csv_export(con, query, out / f"{name}.csv")
    monthly = con.execute(exports["monthly"]).fetchall()
    user_events = [r[1] for r in con.execute(exports["users"]).fetchall()]
    track_events = [r[1] for r in con.execute(exports["track_popularity"]).fetchall()]
    plt.rcParams.update({"font.size": 10, "figure.dpi": 150})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    axes[0, 0].plot([r[0] for r in monthly], [r[1] for r in monthly], color="#187a68")
    axes[0, 0].set(title="Listening events by month (cleaned subset)", ylabel="Events")
    axes[0, 0].tick_params(axis="x", rotation=25)
    last_day = one(con, "SELECT max(occurred_at)::DATE FROM events")
    axes[0, 0].annotate(
        f"Data ends {last_day.isoformat()}",
        xy=(monthly[-1][0], monthly[-1][1]),
        xytext=(-150, 30),
        textcoords="offset points",
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": "#555555"},
    )
    axes[0, 1].hist(user_events, bins=35, color="#3f6fab")
    axes[0, 1].set(title="Activity per user", xlabel="Listening events", ylabel="Users")
    axes[1, 0].loglog(range(1, len(track_events) + 1), track_events, color="#b14b62")
    axes[1, 0].set(
        title="Long tail of track popularity",
        xlabel="Track rank (log)",
        ylabel="Events (log)",
    )
    total = sum(track_events)
    running = 0
    cumulative = []
    for count in track_events:
        running += count
        cumulative.append(running / total)
    axes[1, 1].plot(
        [100 * (i + 1) / len(track_events) for i in range(len(track_events))],
        [100 * v for v in cumulative],
        color="#8654a0",
    )
    axes[1, 1].set(
        title="Concentration of listening",
        xlabel="Top tracks (%)",
        ylabel="Cumulative events (%)",
    )
    fig.savefig(out / "overview.png")
    plt.close(fig)
    missing = con.execute(exports["missing"]).fetchall()
    raw_count = one(con, "SELECT count(*) FROM raw")
    fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
    ax.barh(
        [r[0] for r in missing],
        [100 * r[1] / raw_count for r in missing],
        color="#bd6c36",
    )
    ax.set(title="Missing fields in parsed original events", xlabel="Missing (%)")
    for i, row in enumerate(missing):
        ax.text(
            100 * row[1] / raw_count + 0.1,
            i,
            f"{100 * row[1] / raw_count:.2f}%",
            va="center",
        )
    ax.set_xlim(0, max(5, max(100 * r[1] / raw_count for r in missing) * 1.25))
    fig.savefig(out / "missing_fields.png")
    plt.close(fig)


def markdown_report(m, manifest):
    fmt = lambda n: f"{n:,}"
    pct = lambda x: f"{x * 100:.2f}%"
    missing = "\n".join(
        f"| `{k}` | {fmt(v)} | {pct(v / m['parsed_rows'])} |"
        for k, v in m["missing"].items()
    )
    distributions = "\n".join(
        f"| {label} | {d['min']:,.0f} | {d['median']:,.1f} | {d['mean']:,.1f} "
        f"| {d['p90']:,.1f} | {d['p99']:,.1f} | {d['max']:,.0f} |"
        for label, d in [
            ("Lượt nghe/user", m["events_per_user"]),
            ("Bài khác nhau/user", m["distinct_songs_per_user"]),
            ("Lượt nghe/bài", m["events_per_track"]),
        ]
    )

    def escape(s):
        return str(s).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    top = "\n".join(
        f"| {escape(t)} | {escape(a)} | {fmt(n)} |" for t, a, n in m["top_tracks"]
    )
    split = m["temporal_preview"]
    split_rows = "\n".join(
        f"| {k} | {fmt(split['events'].get(k, 0))} |"
        for k in ("train", "validation", "test")
    )
    return f"""# EDA Last.fm 1K và đối chiếu catalog iTunes/Jamendo

> Báo cáo được tạo từ file gốc đầy đủ, không lấy mẫu và không dùng bản Parquet đã làm sạch sẵn.
> Lần chạy UTC: {manifest["analyzed_at_utc"]}. Chưa huấn luyện mô hình và chưa gọi Supabase.

## 1. Dữ liệu này có giống dữ liệu đang thu thập không?

**Giống một phần metadata, khác đơn vị quan sát và mục đích sử dụng.**
Adapter iTunes/Jamendo hiện trả một record bài hát. Last.fm trả một lượt nghe
gắn user, bài và thời điểm; cùng một bài có thể xuất hiện nhiều lần.

| Last.fm TSV | Model provider hiện tại | Nhận xét |
|---|---|---|
| `track_name` | `title` | Cùng ý nghĩa, có thể khác cách viết |
| `artist_name` | `artist_name` | Cùng ý nghĩa |
| `track_id` | `external_id` | Khác hệ ID: MusicBrainz và provider; không join trực tiếp |
| `artist_id` | `artist_external_id` | Khác hệ ID, nhiều giá trị có thể thiếu |
| `user_id` | Không có | Lịch sử hành vi, cần cho lọc cộng tác |
| `timestamp` | Không có | Thời điểm nghe; KHÔNG phải ngày phát hành |
| Không có | album, duration, release_date, cover | Chưa đủ đặc trưng cho content model phong phú |
| Không có | preview/audio URL, license | Không phục vụ playback như catalog provider |
| Không có | explicit | Không suy ra từ lượt nghe |

Kết luận: dùng Last.fm cho **EDA hành vi, ALS và mô phỏng xu hướng theo thời gian**;
giữ iTunes/Jamendo cho **catalog và demo playback**. Chưa đo giao bài hát giữa các
nguồn vì repository chưa có tập dữ liệu provider thật được lưu để đối chiếu.
Không khẳng định cùng tên là cùng bản thu, không tự ghép ID và không nhập benchmark
vào database ứng dụng trong bước này.

## 2. Nguồn, định dạng và tính toàn vẹn

- Tác giả gốc: Òscar Celma, MTG/UPF; dữ liệu lịch sử Last.fm.
- [Trang nguồn gốc](https://ocelma.net/MusicRecommendationDataset/lastfm-1K.html).
- [Mirror công khai và README gốc](https://github.com/eifuentes/lastfm-dataset-1K).
- [File ZIP đã tải]({SOURCE}).
- README đi kèm: cho phép sử dụng phi thương mại, yêu cầu dẫn nguồn Last.fm.
- ZIP được tải từ mirror vì trang tác giả không truy cập ổn định trong phiên này.
- MD5 TSV khớp README gốc: **{manifest["matches_original_md5"]}**.
- MD5: `{manifest["tsv"]["md5"]}`.
- SHA-256: `{manifest["tsv"]["sha256"]}`.
- TSV: {fmt(manifest["tsv"]["bytes"])} bytes, {fmt(manifest["tsv"]["physical_lines"])} dòng vật lý.
- Không tải audio. Không thu thập profile nhân khẩu học vì chưa cần cho bài toán.

Định dạng TSV không có header, 6 cột phân cách bằng tab:

```text
user_id  timestamp  artist_id  artist_name  track_id  track_name
```

File được đọc như chuỗi, không coi dấu ngoặc kép trong tên bài là dấu quote CSV.
Các dòng không đủ/đúng 6 cột được ghi nhận là lỗi, không bỏ qua âm thầm.

## 3. Chất lượng dữ liệu gốc

| Chỉ tiêu | Kết quả |
|---|---:|
| Dòng đọc thành công | {fmt(m["parsed_rows"])} |
| User khác nhau trong dữ liệu parse được | {fmt(m["raw_users"])} |
| Track ID không rỗng, khác nhau trước lọc | {fmt(m["raw_nonempty_track_ids"])} |
| Dòng lỗi cấu trúc | {fmt(m["malformed_lines"])} |
| Timestamp thiếu/không parse được | {fmt(m["invalid_timestamps"])} |
| Timestamp trước năm 1970 | {fmt(m["before_1970"])} |
| Timestamp sau ngày cutoff {manifest["cutoff"]} | {fmt(m["after_source_cutoff"])} |
| Track ID có giá trị nhưng sai cấu trúc UUID | {fmt(m["invalid_nonempty_track_ids"])} |

Khoảng thời gian parse được trước lọc: `{m["raw_time_range"][0]}` → `{m["raw_time_range"][1]}`.
Các ngày bất thường phải được phân tích trước khi dùng để tạo split và xu hướng.
Cutoff lấy theo phạm vi nguồn công bố (đến hết 05/05/2009 UTC), không tự dịch dữ liệu
sang năm hiện tại. Các nhóm lỗi có thể chồng nhau, không cộng chúng thành số dòng loại.

| Field | Số giá trị thiếu sau trim | Tỷ lệ trên dòng parse thành công |
|---|---:|---:|
{missing}

![Tỷ lệ thiếu field](missing_fields.png)

Thiếu MBID không đồng nghĩa thiếu tên bài. Baseline dưới đây chọn strict track MBID
để tránh gộp nhầm các bài trùng tên; đây là quyết định tiền xử lý có mất dữ liệu.
Một biến thể sau có thể dùng khóa tên artist/title đã chuẩn hóa, nhưng phải đánh giá
rủi ro đồng danh và báo kết quả riêng.

## 4. Quy tắc tạo tập sạch cho EDA

1. Trim chuỗi, rỗng thành null, parse timestamp UTC.
2. Giữ user ID, tên artist, tên bài đầy đủ; yêu cầu track MBID đúng cấu trúc UUID.
3. Giữ event từ 01/01/1970 đến hết {manifest["cutoff"]} UTC.
4. Artist MBID được phép thiếu; không dùng tên artist để tự bịa MBID.
5. Loại các bản ghi trùng toàn bộ 6 field sau chuẩn hóa; giữ lượt nghe cùng bài ở timestamp khác.
6. Tổng hợp user–track thành `plays` khi tính ma trận; không xem từng event lặp là một cặp mới.

| Bước | Số event |
|---|---:|
| Parse được | {fmt(m["parsed_rows"])} |
| Đủ điều kiện trước dedup | {fmt(m["eligible_before_dedup"])} |
| Trùng hoàn toàn được loại trong tập đủ điều kiện | {fmt(m["exact_duplicates_removed"])} |
| Sau lọc và dedup | {fmt(m["clean_events"])} |
| Tỷ lệ giữ so với dòng parse được | {pct(m["retention"])} |

Chưa lọc k-core hoặc chỉ lấy top user/item. Chưa phân phối train/test chính thức.
Tập này phản ánh quyết định strict-ID, không đại diện nguyên vẹn cho mọi record gốc.

## 5. Quy mô và hành vi sau làm sạch

| Chỉ tiêu | Giá trị |
|---|---:|
| Người dùng | {fmt(m["users"])} |
| Track MBID khác nhau | {fmt(m["tracks"])} |
| Artist MBID có giá trị, khác nhau | {fmt(m["artists_with_mbid"])} |
| Cặp user–song khác nhau | {fmt(m["unique_user_song_pairs"])} |
| Độ thưa ma trận user–song | {pct(m["sparsity"])} |
| Tỷ lệ event vượt lượt đầu của mỗi cặp user–song | {pct(m["repeat_event_fraction"])} |
| Tỷ trọng lượt nghe của top 1% bài theo lượt nghe | {pct(m["top_one_percent_track_share"])} |
| Bài chỉ có một lượt nghe trong tập sạch | {fmt(m["singleton_track_count"])} |
| Track MBID có nhiều cách viết tên bài | {fmt(m["track_ids_with_multiple_names"])} |

Độ thưa = `1 - số cặp user–song / (số user × số song)`.
Tỷ lệ nghe lại = `(event - cặp user–song) / event`; không phải tỷ lệ user nghe lại.
Số artist chỉ tính ID có giá trị, không phải tổng nghệ sĩ thật.
Sự phổ biến ở đây là số scrobble của nhóm người dùng trong dataset, chưa đại diện
cho xu hướng thị trường hoặc sở thích người dùng Việt Nam hiện tại.

| Phân bố | Min | Median | Mean | P90 | P99 | Max |
|---|---:|---:|---:|---:|---:|---:|
{distributions}

![Tổng quan hoạt động, thời gian và đuôi dài](overview.png)

Trục thời gian dùng UTC. Lượt nghe theo tháng chịu ảnh hưởng số user hoạt động và
độ phủ thu thập; tăng theo tháng không tự chứng minh thị trường âm nhạc tăng trưởng.
Tháng đầu và cuối chỉ có độ phủ một phần; tháng 05/2009 kết thúc ở cutoff ngày 05,
nên mức giảm ở điểm cuối không chứng minh nhu cầu nghe nhạc giảm.
Chênh lệch mean/median và đồ thị đuôi dài cần được xét khi chọn baseline, trọng số
confidence và biện pháp tăng catalog coverage.

### Top 10 bài theo lượt nghe trong tập sạch

Tên hiển thị lấy biến thể xuất hiện nhiều nhất của mỗi track MBID; không gộp theo tên.

| Bài | Nghệ sĩ | Lượt nghe |
|---|---|---:|
{top}

## 6. Thử phân chia thời gian để xem rủi ro đánh giá

Đây là **split preview**, chưa phải đánh giá mô hình: chọn mốc phân vị 80% và 90%
timestamp trên tập sạch. Các event cùng timestamp nằm chung phía mốc để tránh
chia tùy tiện cùng một thời điểm. Khi làm thí nghiệm thật phải chốt protocol và
xây vocabulary/aggregate chỉ bằng train; EDA toàn tập không phải feature cho model.

- Mốc train/validation: `{split["train_validation_boundary"]}`.
- Mốc validation/test: `{split["validation_test_boundary"]}`.

| Split | Event |
|---|---:|
{split_rows}

- Event test có bài chưa xuất hiện trong train: {fmt(split["cold_test_events"])}.
- Track cold trong test so với train: {fmt(split["cold_test_tracks"])}.
- User trong test chưa có trong train: {fmt(split["cold_test_users"])}.
- Event test có cặp user–song đã xuất hiện trong train: {fmt(split["test_events_previously_seen_user_song"])}.

Không loại vĩnh viễn mọi bài đã nghe: nhiều event test chính là hành vi nghe lại.
Nếu so sánh phương pháp chỉ gợi ý bài chưa nghe, cần định nghĩa target và candidate
universe riêng. Bài chưa xuất hiện trong train là *cold item theo interaction*,
không chứng minh vừa phát hành vì dataset không có release date.

## 7. Ý nghĩa đối với hệ thống của nhóm

- **ALS/CF:** có thể tạo ma trận user–song từ play count; ma trận thưa nên lưu sparse.
  Confidence cần giảm ảnh hưởng user nghe cực nhiều, thử log/cap trên train.
- **Sở thích và phiên:** có lịch sử theo thời gian, nhưng muốn session phải đặt
  quy tắc chia khoảng cách event và báo đó là suy diễn, không phải session gốc.
- **Xu hướng:** tính rolling popularity tại từng mốc lịch sử; không gọi đó là trend năm 2026.
- **Content-based:** artist và title có thể dùng baseline yếu; thiếu genre, album,
  mood/audio features nên chưa đánh giá được mô hình hiểu phong cách đầy đủ.
- **Skip/like/search:** không có trong TSV; không được suy ra mọi khoảng cách ngắn
  là skip hoặc bịa event để báo cáo như dữ liệu thật.
- **Thời lượng:** không có duration/listened_ms nên không tính completion rate đáng tin cậy.
- **Ứng dụng:** metadata provider phục vụ catalog; interaction benchmark không tự
  gắn với user/item của ứng dụng. Cần mapping có kiểm chứng hoặc train lại bằng event nội bộ.

## 8. Bước tiếp theo đề xuất

1. Dùng tập sạch làm đầu vào cho popularity và ALS baseline, chưa cần tải audio.
2. Chốt temporal protocol và báo riêng warm/cold item, warm/cold user.
3. Thử sensitivity theo cách xử lý missing MBID và mức lọc user/item; báo tỷ lệ mất dữ liệu.
4. Đánh giá NDCG/Recall và coverage; không đưa kết quả model khi mới hoàn thành EDA.
5. Duy trì importer iTunes/Jamendo như nhánh ứng dụng riêng. Sau khi có file metadata
   thật, đo giao catalog bằng mapping candidate + kiểm tra bản thu, không join theo tên đơn lẻ.

## 9. Tái lập

```bash
cd recommender/eda
uv sync --locked
uv run python lastfm_eda.py
```

File raw/duckdb/CSV tổng hợp lớn nằm trong `data/` được Git ignore. Báo cáo, metric
JSON, manifest và PNG nằm trong `docs/eda/lastfm-1k/`. Script không tự tải mạng;
lệnh tải và giải thích chi tiết nằm ở README cạnh script.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=RAW_DIR / "events.tsv.zip")
    parser.add_argument("--cutoff", default="2009-05-05")
    parser.add_argument("--output", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    cutoff = date.fromisoformat(args.cutoff).isoformat()
    print("Extracting and verifying original TSV...", flush=True)
    path = prepare_input(args.archive)
    info = fingerprint(path)
    if info["md5"] != EXPECTED_MD5:
        raise ValueError("TSV checksum does not match the original dataset README")
    manifest = {
        "dataset": "Last.fm 1K original events, full dataset",
        "source": SOURCE,
        "cutoff": cutoff,
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sampled": False,
        "tsv": info,
        "matches_original_md5": info["md5"] == EXPECTED_MD5,
        "duckdb_version": duckdb.__version__,
        "matplotlib_version": matplotlib.__version__,
    }
    processed = ROOT / "data/processed/lastfm-1k"
    processed.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(processed / "eda.duckdb"))
    con.execute("SET memory_limit='2GB'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET TimeZone='UTC'")
    print("Loading original events, recording malformed lines...", flush=True)
    load_events(con, path, cutoff)
    parsed = one(con, "SELECT count(*) FROM raw")
    rejected = one(con, "SELECT count(DISTINCT line) FROM csv_rejects")
    if parsed + rejected != info["physical_lines"]:
        raise ValueError("Line accounting failed: parsed + rejected != original lines")
    print("Computing exact full-dataset statistics...", flush=True)
    metrics = analyze(con, cutoff)
    print("Writing aggregates and charts...", flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in (("metrics.json", metrics), ("manifest.json", manifest)):
        (args.output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    make_outputs(con, processed)
    for name in ("overview.png", "missing_fields.png"):
        shutil.copyfile(processed / name, args.output / name)
    (args.output / "REPORT.md").write_text(
        markdown_report(metrics, manifest), encoding="utf-8"
    )
    con.close()
    print(
        json.dumps(
            {
                k: metrics[k]
                for k in (
                    "parsed_rows",
                    "malformed_lines",
                    "clean_events",
                    "users",
                    "tracks",
                    "sparsity",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
