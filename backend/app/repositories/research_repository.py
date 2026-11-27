"""Read a prepared, local-only SQLite artifact. No env files or network clients."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT = ROOT / "data/processed/music4all-demo/catalog.sqlite3"


class ResearchStore:
    def __init__(self, path: Path = DEFAULT_ARTIFACT):
        # mode=ro prevents accidental empty database creation at API startup.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            self.tracks = {
                item: {
                    "id": item,
                    "display_name": f"Track {item}",
                    "features": json.loads(features),
                    "tags": json.loads(tags),
                    "plays": plays,
                }
                for item, features, tags, plays in db.execute(
                    "SELECT id, features, tags, plays FROM tracks ORDER BY id"
                )
            }
            self.histories = {}
            for user, item, plays in db.execute(
                "SELECT user_id, track_id, plays FROM interactions ORDER BY user_id, track_id"
            ):
                self.histories.setdefault(user, {})[item] = plays
            self.neighbors = {}
            for item, neighbor, similarity in db.execute(
                "SELECT track_id, neighbor_id, similarity FROM neighbors "
                "ORDER BY track_id, similarity DESC, neighbor_id"
            ):
                self.neighbors.setdefault(item, []).append((neighbor, similarity))
            self.metadata = json.loads(
                db.execute(
                    "SELECT value FROM metadata WHERE key = 'manifest'"
                ).fetchone()[0]
            )
        self.genres = sorted({g for t in self.tracks.values() for g in t["features"]})

    def public_track(self, item: str) -> dict:
        track = self.tracks[item]
        return {
            "id": item,
            "display_name": track["display_name"],
            "genres": [
                {"name": genre, "weight": value}
                for genre, value in sorted(
                    track["features"].items(), key=lambda pair: (-pair[1], pair[0])
                )
            ],
            "tags": track["tags"],
            "training_plays": track["plays"],
            "can_stream": False,
        }
