"""Run with uvicorn app.research_demo:app. Independent of Supabase and .env."""

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.health import router as health_router
from app.repositories.research_repository import DEFAULT_ARTIFACT, ResearchStore
from app.services.research_recommender import rank_tracks


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = Path(os.environ.get("MUSIC4ALL_ARTIFACT", str(DEFAULT_ARTIFACT)))
    try:
        app.state.research_store = await run_in_threadpool(ResearchStore, path)
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError):
        # Fail closed; no fallback to the production app or any cloud database.
        app.state.research_store = None
    yield


app = FastAPI(title="Music4All local research demo", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)


def get_store(request: Request) -> ResearchStore:
    store = getattr(request.app.state, "research_store", None)
    if store is None:
        raise HTTPException(
            503, "Local artifact unavailable; run the Music4All preparation command"
        )
    return store


Store = Annotated[ResearchStore, Depends(get_store)]


@app.get("/api/v1/research/info")
def info(store: Store):
    return {**store.metadata, "genres": store.genres}


@app.get("/api/v1/research/tracks")
def tracks(
    store: Store,
    query: str = "",
    genre: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = query.strip().casefold()
    items = [
        item
        for item, track in store.tracks.items()
        if (genre is None or genre in track["features"])
        and (
            not query
            or query in item.casefold()
            or any(query in tag.casefold() for tag in track["tags"])
            or any(query in g.casefold() for g in track["features"])
        )
    ]
    items.sort(key=lambda item: (-store.tracks[item]["plays"], item))
    return {
        "total": len(items),
        "items": [store.public_track(item) for item in items[offset : offset + limit]],
    }


@app.get("/api/v1/research/tracks/{track_id}")
def detail(track_id: str, store: Store):
    if track_id not in store.tracks:
        raise HTTPException(404, "Track not found")
    return store.public_track(track_id)


@app.get("/api/v1/research/users")
def users(
    store: Store,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    ids = sorted(store.histories)
    return {
        "total": len(ids),
        "items": [
            {"id": user, "history_size": len(store.histories[user])}
            for user in ids[offset : offset + limit]
        ],
    }


@app.get("/api/v1/research/users/{user_id}/history")
def history(user_id: str, store: Store):
    if user_id not in store.histories:
        raise HTTPException(404, "Research user not found")
    return [
        {"track": store.public_track(item), "plays": plays}
        for item, plays in sorted(
            store.histories[user_id].items(), key=lambda pair: (-pair[1], pair[0])
        )
    ]


class RecommendationRequest(BaseModel):
    user_id: str | None = None
    genres: list[str] = Field(default_factory=list, max_length=10)
    recent_track_ids: list[str] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=10, ge=1, le=50)


@app.post("/api/v1/research/recommendations")
def recommendations(body: RecommendationRequest, store: Store):
    if body.user_id is not None and body.user_id not in store.histories:
        raise HTTPException(404, "Research user not found")
    if any(item not in store.tracks for item in body.recent_track_ids):
        raise HTTPException(404, "Recent track not found")
    if any(genre not in store.genres for genre in body.genres):
        raise HTTPException(422, "Unknown genre")
    recent = list(dict.fromkeys(body.recent_track_ids))
    rows = rank_tracks(
        store.tracks,
        store.neighbors,
        store.histories.get(body.user_id, {}),
        list(dict.fromkeys(body.genres)),
        recent,
        body.limit,
    )
    return {
        "model": "item-knn-genre-popularity-v1",
        "items": [
            {**row, "track": store.public_track(row["track_id"])} for row in rows
        ],
    }
