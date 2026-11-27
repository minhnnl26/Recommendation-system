"""Optional real-artifact smoke test. Local files only, no Docker/network/cloud."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.repositories.research_repository import DEFAULT_ARTIFACT
from app.research_demo import app


@pytest.mark.research_integration
def test_prepared_artifact_end_to_end(monkeypatch):
    if not DEFAULT_ARTIFACT.is_file():
        pytest.skip("Prepare the local Music4All artifact first")
    monkeypatch.setenv("MUSIC4ALL_ARTIFACT", str(DEFAULT_ARTIFACT))
    with TestClient(app) as client:
        info = client.get("/api/v1/research/info").json()
        assert info["tracks"] >= 10
        first = client.get("/api/v1/research/tracks?limit=2").json()
        second = client.get("/api/v1/research/tracks?limit=2&offset=2").json()
        assert len(first["items"]) == len(second["items"]) == 2
        assert not {t["id"] for t in first["items"]} & {
            t["id"] for t in second["items"]
        }
        track = first["items"][0]
        assert client.get(f"/api/v1/research/tracks/{track['id']}").status_code == 200
        assert (
            client.get(f"/api/v1/research/tracks?query={track['id']}").json()["total"]
            == 1
        )
        assert track["can_stream"] is False
        user = client.get("/api/v1/research/users?limit=1").json()["items"][0]["id"]
        history = client.get(f"/api/v1/research/users/{user}/history").json()
        known = {row["track"]["id"] for row in history}
        response = client.post(
            "/api/v1/research/recommendations", json={"user_id": user}
        )
        assert response.status_code == 200
        rows = response.json()["items"]
        assert len(rows) == 10
        assert not known & {row["track_id"] for row in rows}
        genre = rows[0]["track"]["genres"][0]["name"]
        assert (
            client.get("/api/v1/research/tracks", params={"genre": genre}).json()[
                "total"
            ]
            > 0
        )
        assert (
            client.post(
                "/api/v1/research/recommendations", json={"genres": [genre]}
            ).status_code
            == 200
        )
    with sqlite3.connect(DEFAULT_ARTIFACT.as_uri() + "?mode=ro", uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert (
            db.execute(
                "SELECT count(*) FROM holdouts h JOIN interactions i "
                "ON h.user_id=i.user_id AND h.track_id=i.track_id"
            ).fetchone()[0]
            == 0
        )
