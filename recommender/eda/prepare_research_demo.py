"""Prepare a bounded research artifact from downloaded Music4All-Onion files."""

import argparse
import ast
import bz2
import csv
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.research_recommender import rank_tracks, train_neighbors


def read_features(path: Path, selected: set) -> dict:
    tracks = {}
    with bz2.open(path / "id_genres_tf-idf.tsv.bz2", "rt") as stream:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        if header[0] != "id":
            raise ValueError("Unexpected genre header")
        for row in reader:
            if row[0] not in selected:
                continue
            if len(row) != len(header):
                raise ValueError("Invalid genre row")
            values = [float(v) for v in row[1:]]
            if any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError("Invalid genre weight")
            norm = math.sqrt(sum(v * v for v in values))
            tracks[row[0]] = {
                "features": {g: v / norm for g, v in zip(header[1:], values) if v > 0},
                "tags": [],
                "plays": 0,
            }
    tags = {}
    with bz2.open(path / "id_tags_dict.tsv.bz2", "rt") as stream:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        if next(reader) != ["id", "(tag, weight)"]:
            raise ValueError("Unexpected tag header")
        for item, literal in reader:
            if item not in tracks:
                continue
            parsed = ast.literal_eval(literal)
            if not isinstance(parsed, dict):
                raise TypeError("Invalid tag dictionary")
            merged = tags.setdefault(item, {})
            for tag, weight in parsed.items():
                if (
                    not isinstance(tag, str)
                    or not isinstance(weight, (int, float))
                    or isinstance(weight, bool)
                    or not math.isfinite(weight)
                    or weight < 0
                ):
                    raise ValueError("Invalid tag weight")
                tag = tag.strip().casefold()
                if weight > 0 and tag:
                    merged[tag] = max(weight, merged.get(tag, 0))
    for item, values in tags.items():
        tracks[item]["tags"] = sorted(values, key=lambda tag: (-values[tag], tag))[:20]
    return tracks


def evaluate(tracks, neighbors, histories, holdouts, limit=100):
    results = {}
    users = sorted(holdouts)[:limit]
    for mode in ("popularity", "hybrid"):
        hits = 0
        ndcg = 0
        for user in users:
            rows = rank_tracks(tracks, neighbors, histories[user], [], [], 10, mode)
            ids = [row["track_id"] for row in rows]
            if holdouts[user] in ids:
                hits += 1
                ndcg += 1 / math.log2(ids.index(holdouts[user]) + 2)
        results[mode] = {
            "recall_at_10": hits / len(users) if users else 0,
            "ndcg_at_10": ndcg / len(users) if users else 0,
        }
    return {"evaluated_users": len(users), "results": results}


def prepare(args):
    started = time.monotonic()
    source = ROOT / "data/processed/music4all-onion/audit.duckdb"
    if not source.is_file():
        raise SystemExit(
            "Run music4all_audit.py first to prepare the local source database"
        )
    with duckdb.connect(str(source), read_only=True) as db:
        db.execute("SET memory_limit = '512MB'")
        db.execute("SET threads = 1")
        selected = {
            row[0]
            for row in db.execute(
                "SELECT track_id FROM track_totals ORDER BY plays DESC, track_id LIMIT ?",
                [args.tracks],
            ).fetchall()
        }
        tracks = read_features(ROOT / "data/raw/music4all-onion", selected)
        db.execute("CREATE TEMP TABLE selected_tracks (track_id VARCHAR)")
        db.executemany("INSERT INTO selected_tracks VALUES (?)", [(i,) for i in tracks])
        # Hash sampling is stable; do not select only the most active users.
        db.execute(
            """CREATE TEMP TABLE selected_users AS
            SELECT i.user_id FROM interactions i JOIN selected_tracks t USING (track_id)
            GROUP BY i.user_id HAVING count(*) >= 5
            ORDER BY md5(i.user_id), i.user_id LIMIT ?""",
            [args.users],
        )
        rows = db.execute(
            """SELECT i.user_id, i.track_id, i.plays FROM interactions i
            JOIN selected_tracks t USING (track_id)
            JOIN selected_users u USING (user_id)
            QUALIFY row_number() OVER (
                PARTITION BY i.user_id ORDER BY md5(i.user_id || ':' || i.track_id), i.track_id
            ) <= 60
            ORDER BY i.user_id, md5(i.user_id || ':' || i.track_id), i.track_id"""
        ).fetchall()
    histories = {}
    for user, item, plays in rows:
        histories.setdefault(user, {})[item] = plays
    holdouts = {}
    for user, history in histories.items():
        # Hash-ordered leave-one-out, explicitly NOT a chronological evaluation.
        item = next(reversed(history))
        holdouts[user] = item
        del history[item]
    totals = Counter()
    for history in histories.values():
        totals.update(history)
    for item, track in tracks.items():
        track["plays"] = totals[item]
    print(
        f"Prepared {len(tracks)} tracks / {len(histories)} users; fitting Item-kNN",
        flush=True,
    )
    neighbors = train_neighbors(histories)
    metrics = evaluate(tracks, neighbors, histories, holdouts)
    manifest = {
        "dataset": "Music4All-Onion v2",
        "source_record": "https://zenodo.org/records/15394646",
        "model": "item-knn-genre-popularity-v1",
        "tracks": len(tracks),
        "users": len(histories),
        "train_pairs": sum(map(len, histories.values())),
        "holdout_pairs": len(holdouts),
        "neighbors": sum(map(len, neighbors.values())),
        "selection": "Top tracks by full-source plays; hash-sampled users with >=5 pairs; cap 60 pairs/user",
        "split": "Deterministic hash-ordered leave-one-out; not temporal; catalog selection sees full-source totals",
        "limitations": [
            "No song titles, artist names, albums, timestamps, audio or playable URLs",
            "Historical popularity, not current trends",
            "Bounded popularity-biased research subset; metrics are a smoke baseline, not unbiased production quality",
            "Holdout not used for fitting neighbors, profiles or scoring popularity",
        ],
        "weights": {"collaborative": 0.5, "content": 0.4, "popularity": 0.1},
        "evaluation": metrics,
        "preparation_seconds": round(time.monotonic() - started, 2),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".building.sqlite3")
    if temporary.exists():
        temporary.unlink()
    with sqlite3.connect(temporary) as db:
        db.executescript("""
            CREATE TABLE tracks (id TEXT PRIMARY KEY, features TEXT NOT NULL, tags TEXT NOT NULL, plays INTEGER NOT NULL);
            CREATE TABLE interactions (user_id TEXT, track_id TEXT REFERENCES tracks(id), plays INTEGER NOT NULL, PRIMARY KEY(user_id, track_id));
            CREATE TABLE neighbors (track_id TEXT REFERENCES tracks(id), neighbor_id TEXT REFERENCES tracks(id), similarity REAL NOT NULL, PRIMARY KEY(track_id, neighbor_id));
            CREATE TABLE holdouts (user_id TEXT PRIMARY KEY, track_id TEXT REFERENCES tracks(id));
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        db.execute("PRAGMA foreign_keys = ON")
        db.executemany(
            "INSERT INTO tracks VALUES (?, ?, ?, ?)",
            [
                (i, json.dumps(t["features"]), json.dumps(t["tags"]), t["plays"])
                for i, t in tracks.items()
            ],
        )
        db.executemany(
            "INSERT INTO interactions VALUES (?, ?, ?)",
            [(u, i, p) for u, history in histories.items() for i, p in history.items()],
        )
        db.executemany(
            "INSERT INTO neighbors VALUES (?, ?, ?)",
            [(i, n, s) for i, rows in neighbors.items() for n, s in rows],
        )
        db.executemany("INSERT INTO holdouts VALUES (?, ?)", sorted(holdouts.items()))
        db.execute(
            "INSERT INTO metadata VALUES ('manifest', ?)", [json.dumps(manifest)]
        )
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Artifact integrity check failed")
    os.replace(temporary, output)
    manifest["artifact_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=int, default=3000)
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data/processed/music4all-demo/catalog.sqlite3",
    )
    options = parser.parse_args()
    if not 10 <= options.tracks <= 10000 or not 10 <= options.users <= 5000:
        parser.error("Use 10–10000 tracks and 10–5000 users for this local baseline")
    prepare(options)
