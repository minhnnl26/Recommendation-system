"""Prepare the complete catalog and bounded-memory sparse splits for Kaggle."""

import argparse
import bz2
import csv
import json
import shutil
from pathlib import Path

import duckdb
from scipy import sparse

from data_utils import (
    export_sparse,
    inventory,
    load_features,
    normalize_rows,
    read_onion_catalog,
    sha256,
    write_json,
)


def decompress(source, target):
    with bz2.open(source, "rb") as reader, target.open("wb") as writer:
        shutil.copyfileobj(reader, writer, length=8 * 1024 * 1024)


def prepare(config):
    onion = Path(config["onion_root"])
    feature_path = onion / "id_genres_tf-idf.tsv.bz2"
    catalog_source = config.get("catalog_source", "original")
    if catalog_source == "original":
        catalog, report = inventory(
            config["original_root"],
            config.get("expected_tracks", 109269),
            full=config.get("require_full_original", True),
        )
    elif catalog_source == "onion":
        if config.get("require_full_original", False):
            raise ValueError(
                "Onion-only training cannot require the original audio inventory"
            )
        catalog = read_onion_catalog(feature_path)
        report = {
            "complete": False,
            "checked": False,
            "reason": "Onion-only training; original metadata/audio/lyrics not required or inspected",
        }
    else:
        raise ValueError("catalog_source must be original or onion")
    output = Path(config["output_root"])
    prepared = output / "prepared"
    if prepared.exists():
        raise ValueError("Prepared output already exists; select a new output_root")
    prepared.mkdir(parents=True)
    scratch = Path(config["scratch_root"])
    scratch.mkdir(parents=True, exist_ok=True)
    # Unique scratch directory; never remove user-owned existing directories.
    import tempfile

    temporary = Path(tempfile.mkdtemp(prefix="prepare-", dir=scratch))
    item_ids = sorted(catalog)
    write_json(prepared / "catalog.json", catalog)
    write_json(prepared / "item_ids.json", item_ids)
    write_json(prepared / "original_inventory.json", report)
    genre, names = load_features(feature_path, item_ids)
    if genre.data.size and (genre.data < 0).any():
        raise ValueError("Genre weights must be nonnegative")
    sparse.save_npz(prepared / "genre.npz", normalize_rows(genre))
    write_json(prepared / "genre_names.json", names)
    split = config.get("split", "temporal")
    if split not in {"temporal", "hash"}:
        raise ValueError("split must be temporal or hash")
    source_name = (
        "userid_trackid_timestamp.tsv.bz2"
        if split == "temporal"
        else "userid_trackid_count.tsv.bz2"
    )
    source = onion / source_name
    if not source.is_file():
        raise ValueError(
            f"Required source missing: {source_name}; no silent split fallback"
        )
    raw = temporary / "source.tsv"
    print(
        "Decompressing interaction file into scratch (not notebook output)", flush=True
    )
    decompress(source, raw)
    with raw.open(encoding="utf-8") as stream:
        header = next(csv.reader(stream, delimiter="\t"))
    expected = ["user_id", "track_id", "timestamp" if split == "temporal" else "count"]
    if header != expected:
        raise ValueError(f"Unexpected interaction header; expected {expected}")
    db = duckdb.connect(str(temporary / "prepare.duckdb"))
    try:
        db.execute("SET memory_limit = '4GB'")
        db.execute("SET threads = ?", [config.get("threads", 4)])
        db.execute("SET preserve_insertion_order = false")
        db.execute("SET TimeZone = 'UTC'")
        db.execute(
            "CREATE TABLE catalog (track_id VARCHAR PRIMARY KEY, item_index INTEGER)"
        )
        # Bulk-load ID mapping instead of issuing 109k individual Python inserts.
        catalog_rows = temporary / "catalog.tsv"
        with catalog_rows.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t")
            writer.writerow(["track_id", "item_index"])
            writer.writerows((item, i) for i, item in enumerate(item_ids))
        db.execute(
            "INSERT INTO catalog SELECT track_id, item_index FROM read_csv(?, "
            "delim='\t', header=true, columns={'track_id':'VARCHAR','item_index':'INTEGER'})",
            [str(catalog_rows)],
        )
        db.execute(
            "CREATE VIEW source AS SELECT user_id, track_id, "
            + ("timestamp" if split == "temporal" else "count")
            + " AS value FROM read_csv('"
            + str(raw).replace("'", "''")
            + "', delim='\t', header=true, all_varchar=true, quote='', escape='')"
        )
        if split == "temporal":
            # Accept Unix seconds or ISO timestamps. Numeric timestamps are seconds,
            # not milliseconds; out-of-range years are rejected below.
            db.execute("""CREATE TABLE events AS
                SELECT s.user_id, c.item_index,
                  coalesce(try_cast(s.value AS TIMESTAMPTZ),
                    to_timestamp(try_cast(s.value AS DOUBLE))) AS occurred_at
                FROM source s JOIN catalog c USING(track_id)""")
            bad = db.execute("""SELECT count(*) FROM events WHERE
                user_id IS NULL OR trim(user_id) = '' OR occurred_at IS NULL
                OR year(occurred_at) NOT BETWEEN 1970 AND 2100""").fetchone()[0]
            if bad:
                raise ValueError(f"Invalid in-catalog event rows: {bad}")
            q1, q2 = (
                config.get("train_quantile", 0.8),
                config.get("validation_quantile", 0.9),
            )
            if not 0 < q1 < q2 < 1:
                raise ValueError("Require 0 < train_quantile < validation_quantile < 1")
            cuts = db.execute(
                "SELECT quantile_disc(occurred_at, ?), quantile_disc(occurred_at, ?) FROM events",
                [q1, q2],
            ).fetchone()
            if cuts[0] is None or cuts[0] >= cuts[1]:
                raise ValueError(
                    "Not enough distinct event timestamps for temporal splits"
                )
            db.execute(
                """CREATE TABLE pairs AS SELECT user_id, item_index,
                count(*) FILTER (WHERE occurred_at < ?)::FLOAT AS train_plays,
                count(*) FILTER (WHERE occurred_at >= ? AND occurred_at < ?)::FLOAT AS val_plays,
                count(*) FILTER (WHERE occurred_at >= ?)::FLOAT AS test_plays
                FROM events GROUP BY user_id, item_index""",
                [cuts[0], cuts[0], cuts[1], cuts[1]],
            )
            split_detail = {
                "kind": "global_temporal",
                "validation_start": str(cuts[0]),
                "test_start": str(cuts[1]),
                "duplicates": "identical source events retained as listens",
            }
        else:
            db.execute("""CREATE TABLE raw_counts AS SELECT s.user_id, c.item_index,
                try_cast(s.value AS BIGINT) AS plays, s.value
                FROM source s JOIN catalog c USING(track_id)""")
            bad = db.execute("""SELECT count(*) FROM raw_counts WHERE
                user_id IS NULL OR trim(user_id) = '' OR plays IS NULL OR plays <= 0
                OR NOT regexp_full_match(value, '[0-9]+')""").fetchone()[0]
            if bad:
                raise ValueError(f"Invalid in-catalog count rows: {bad}")
            db.execute(
                """CREATE TABLE ordered AS SELECT user_id, item_index, sum(plays) AS plays,
                row_number() OVER (PARTITION BY user_id
                    ORDER BY md5(user_id || ':' || item_index::VARCHAR || ':' || ?), item_index) AS position,
                count(*) OVER (PARTITION BY user_id) AS total
                FROM raw_counts GROUP BY user_id, item_index""",
                [str(config.get("seed", 42))],
            )
            db.execute("""CREATE TABLE pairs AS SELECT user_id, item_index,
                CASE WHEN position > 2 OR total < 3 THEN plays ELSE 0 END::FLOAT train_plays,
                CASE WHEN position = 2 AND total >= 3 THEN plays ELSE 0 END::FLOAT val_plays,
                CASE WHEN position = 1 AND total >= 3 THEN plays ELSE 0 END::FLOAT test_plays
                FROM ordered""")
            split_detail = {
                "kind": "hash_leave_two_out",
                "warning": "Non-temporal experiment; cannot measure forecasting or recent trends",
            }
        db.execute("""CREATE TABLE users AS SELECT user_id,
            (row_number() OVER (ORDER BY user_id) - 1)::INTEGER AS user_index
            FROM pairs GROUP BY user_id HAVING sum(train_plays) > 0""")
        max_users = config.get("max_users")
        if max_users is not None:
            if not isinstance(max_users, int) or max_users < 1:
                raise ValueError("max_users must be null or a positive integer")
            db.execute("DELETE FROM users WHERE user_index >= ?", [max_users])
        user_ids = [
            row[0]
            for row in db.execute(
                "SELECT user_id FROM users ORDER BY user_index"
            ).fetchall()
        ]
        if not user_ids:
            raise ValueError("No training users")
        write_json(prepared / "user_ids.json", user_ids)
        shape = (len(user_ids), len(item_ids))
        nnz = {}
        for name, column, condition in (
            ("train", "train_plays", "train_plays > 0"),
            ("validation", "val_plays", "val_plays > 0 AND train_plays = 0"),
            (
                "test",
                "test_plays",
                "test_plays > 0 AND train_plays = 0 AND val_plays = 0",
            ),
        ):
            query = f"SELECT u.user_index, p.item_index, p.{column} FROM pairs p JOIN users u USING(user_id) WHERE {condition}"
            matrix = export_sparse(db, query, shape, prepared / f"{name}.npz")
            nnz[name] = matrix.nnz
            del matrix
        source_rows = db.execute("SELECT count(*) FROM source").fetchone()[0]
        retained_rows = db.execute(
            "SELECT count(*) FROM source s JOIN catalog c USING(track_id)"
        ).fetchone()[0]
        all_users = db.execute("SELECT count(DISTINCT user_id) FROM pairs").fetchone()[
            0
        ]
        manifest = {
            "schema_version": 1,
            "catalog_tracks": len(item_ids),
            "training_users": len(user_ids),
            "source_rows": source_rows,
            "in_catalog_rows": retained_rows,
            "users_without_train_or_limited": all_users - len(user_ids),
            "pairs": nnz,
            "split": split_detail,
            "catalog_source": catalog_source,
            "catalog_selection": f"All {catalog_source} catalog IDs; no popularity-based item selection",
            "evaluation_target": "Unseen user-item discovery; validation excludes train, test excludes train + validation",
            "genre_coverage": int((genre.getnnz(axis=1) > 0).sum()),
            "source_sha256": {
                source.name: sha256(source),
                feature_path.name: sha256(feature_path),
                **(
                    {
                        "id_information.csv": sha256(
                            Path(config["original_root"]) / "id_information.csv"
                        )
                    }
                    if catalog_source == "original"
                    else {}
                ),
            },
            "full_original_verified": report["complete"],
        }
        write_json(prepared / "manifest.json", manifest)
        write_json(output / "config.json", config)
        print(
            json.dumps(
                {
                    "tracks": len(item_ids),
                    "users": len(user_ids),
                    "pairs": nnz,
                    "split": split_detail,
                },
                indent=2,
            )
        )
    finally:
        db.close()
        shutil.rmtree(temporary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    prepare(json.loads(args.config.read_text()))
