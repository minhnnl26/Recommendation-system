"""Offline API and ranking checks; synthetic inputs contain no real credentials."""

import math
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.repositories.research_repository import ResearchStore
from app.research_demo import app, get_store
from app.services.research_recommender import rank_tracks, train_neighbors


@pytest.fixture
def store():
    tracks = {
        "A": {"features": {"rock": 1.0}, "tags": ["guitar"], "plays": 20},
        "B": {"features": {"rock": 1.0}, "tags": [], "plays": 8},
        "C": {"features": {"pop": 1.0}, "tags": ["dance"], "plays": 3},
        "D": {"features": {"pop": 1.0}, "tags": [], "plays": 0},
    }
    for item, track in tracks.items():
        track.update(id=item, display_name=f"Track {item}")
    histories = {"one": {"A": 2}, "two": {"A": 5, "B": 2}}
    result = SimpleNamespace(
        tracks=tracks,
        histories=histories,
        neighbors=train_neighbors(histories),
        genres=["pop", "rock"],
        metadata={"tracks": 4, "users": 2, "train_pairs": 3},
    )
    result.public_track = lambda item: ResearchStore.public_track(result, item)
    return result


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_knn_uses_shared_training_users():
    neighbors = train_neighbors({"one": {"A": 2, "B": 1}, "two": {"A": 3}})
    assert neighbors["A"][0][0] == "B"
    assert neighbors["A"][0][1] == pytest.approx(1 / math.sqrt(2) / 11)
    assert "C" not in neighbors


def test_catalog_search_genre_pagination_and_detail(client):
    assert (
        client.get("/api/v1/research/tracks?query=%20GuItAr%20").json()["items"][0][
            "id"
        ]
        == "A"
    )
    assert client.get("/api/v1/research/tracks?query=%20%20").json()["total"] == 4
    page = client.get("/api/v1/research/tracks?genre=rock&limit=1&offset=1").json()
    assert page["total"] == 2
    assert [t["id"] for t in page["items"]] == ["B"]
    assert client.get("/api/v1/research/tracks/A").json()["can_stream"] is False
    assert client.get("/api/v1/research/tracks/absent").status_code == 404
    assert client.get("/api/v1/research/tracks?limit=101").status_code == 422
    assert client.get("/api/v1/research/tracks?offset=-1").status_code == 422


def test_cold_start_genre_and_popularity(client):
    popular = client.post("/api/v1/research/recommendations", json={}).json()["items"]
    assert popular[0]["track_id"] == "A"
    assert popular[0]["reason"] == "popularity"
    content = client.post(
        "/api/v1/research/recommendations", json={"genres": ["pop"]}
    ).json()["items"]
    assert content[0]["track_id"] == "C"
    assert content[0]["reason"] == "content"


def test_history_collaborative_exclusions_and_session(client):
    rows = client.post(
        "/api/v1/research/recommendations", json={"user_id": "one"}
    ).json()["items"]
    assert rows[0]["track_id"] == "B"
    assert all(row["track_id"] != "A" for row in rows)
    assert rows[0]["components"]["collaborative"] > 0
    recent = client.post(
        "/api/v1/research/recommendations", json={"recent_track_ids": ["C"]}
    ).json()["items"]
    assert recent[0]["track_id"] == "D"
    assert all(row["track_id"] != "C" for row in recent)
    assert len(client.get("/api/v1/research/users/one/history").json()) == 1


@pytest.mark.parametrize(
    "body,code",
    [
        ({"user_id": "missing"}, 404),
        ({"genres": ["missing"]}, 422),
        ({"recent_track_ids": ["missing"]}, 404),
        ({"limit": 0}, 422),
        ({"limit": 51}, 422),
        ({"recent_track_ids": ["A"] * 6}, 422),
    ],
)
def test_invalid_recommendation_input(client, body, code):
    assert (
        client.post("/api/v1/research/recommendations", json=body).status_code == code
    )


def test_scores_are_finite_and_deterministic(store):
    args = (store.tracks, store.neighbors, {"A": 3}, [], [], 10)
    first = rank_tracks(*args)
    assert first == rank_tracks(*args)
    assert len({row["track_id"] for row in first}) == len(first)
    assert all(0 <= row["score"] <= 1 for row in first)


def test_missing_artifact_is_safe_and_does_not_create_database(tmp_path, monkeypatch):
    path = tmp_path / "missing.sqlite3"
    monkeypatch.setenv("MUSIC4ALL_ARTIFACT", str(path))
    with TestClient(app) as client:
        response = client.get("/api/v1/research/info")
        assert response.status_code == 503
        assert str(path) not in response.text
        assert client.get("/health").status_code == 200
    assert not path.exists()
