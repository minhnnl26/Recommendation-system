"""Provider-neutral models used by the feasibility spike."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PlaybackType = Literal["full", "preview", "external_only"]


class NormalizedTrack(BaseModel):
    """A normalized provider result; this is not a database or API model."""

    model_config = ConfigDict(extra="forbid")

    source_provider: str
    external_id: str
    title: str
    artist_name: str
    artist_external_id: str | None = None
    album_name: str | None = None
    album_external_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    release_date: str | None = None
    explicit: bool = False
    cover_url: str | None = None
    external_url: str | None = None
    preview_url: str | None = None
    playback_type: PlaybackType
    playback_duration_ms: int | None = Field(default=None, ge=0)
    license_name: str | None = None
    license_url: str | None = None
    can_stream: bool
    raw_provider_payload: dict[str, Any] = Field(default_factory=dict)


class NormalizedMoodQuery(BaseModel):
    """Deterministic query interpretation shared by provider adapters."""

    original_query: str
    normalized_query: str
    text_query: str | None = None
    mood: str | None = None
    provider_tags: list[str] = Field(default_factory=list)
