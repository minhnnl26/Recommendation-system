"""Jamendo API v3 tracks adapter."""

from typing import Any

import httpx

from .base import (
    clean_required,
    non_negative_int,
    payload_dict,
    safe_limit,
    valid_http_url,
)
from .errors import ProviderConfigurationError, ProviderHTTPError, ProviderResponseError
from .models import NormalizedTrack

JAMENDO_TRACKS_URL = "https://api.jamendo.com/v3.0/tracks/"


class JamendoProvider:
    source_provider = "jamendo"

    def __init__(self, client: httpx.AsyncClient, client_id: str | None):
        self.client = client
        self.client_id = client_id.strip() if client_id and client_id.strip() else None

    async def search(
        self,
        query: str | None,
        *,
        tags: list[str] | None = None,
        limit: int = 25,
    ) -> list[NormalizedTrack]:
        safe_limit(limit)
        if not self.client_id:
            raise ProviderConfigurationError("Jamendo client configuration is missing")
        params: dict[str, Any] = {
            "client_id": self.client_id,
            "format": "json",
            "limit": limit,
            "include": "musicinfo+licenses",
        }
        if query and query.strip():
            params["namesearch"] = query.strip()
        if tags:
            params["tags"] = "+".join(tag.strip() for tag in tags if tag.strip())
        response = await self._get(params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("Jamendo returned an invalid response") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), list
        ):
            raise ProviderResponseError("Jamendo returned an invalid result shape")
        return [track for item in payload["results"] if (track := self.normalize(item))]

    async def _get(self, *, params: dict[str, Any]) -> httpx.Response:
        try:
            response = await self.client.get(JAMENDO_TRACKS_URL, params=params)
        except httpx.HTTPError as exc:
            raise ProviderResponseError("Jamendo request failed") from exc
        if response.is_error:
            raise ProviderHTTPError(self.source_provider, response.status_code)
        return response

    @classmethod
    def normalize(cls, item: Any) -> NormalizedTrack | None:
        raw = payload_dict(item)
        if raw is None:
            return None
        external_id = clean_required(raw.get("id"))
        title = clean_required(raw.get("name"))
        artist_name = clean_required(raw.get("artist_name"))
        if not external_id or not title or not artist_name:
            return None
        duration_ms = _seconds_to_ms(raw.get("duration"))
        audio_url = valid_http_url(raw.get("audio"))
        license_url = valid_http_url(raw.get("license_ccurl"))
        return NormalizedTrack(
            source_provider=cls.source_provider,
            external_id=external_id,
            title=title,
            artist_name=artist_name,
            artist_external_id=clean_required(raw.get("artist_id")),
            album_name=clean_required(raw.get("album_name")),
            album_external_id=clean_required(raw.get("album_id")),
            duration_ms=duration_ms,
            release_date=clean_required(raw.get("releasedate")),
            explicit=False,
            cover_url=valid_http_url(raw.get("image")),
            external_url=valid_http_url(raw.get("shareurl")),
            preview_url=audio_url,
            playback_type="full" if audio_url else "external_only",
            playback_duration_ms=duration_ms if audio_url else None,
            license_name="Creative Commons" if license_url else None,
            license_url=license_url,
            can_stream=audio_url is not None,
            raw_provider_payload=raw,
        )


def _seconds_to_ms(value: Any) -> int | None:
    seconds = non_negative_int(value)
    return seconds * 1000 if seconds is not None else None
