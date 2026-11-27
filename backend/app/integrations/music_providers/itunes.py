"""iTunes Search API adapter."""

from typing import Any

import httpx

from .base import (
    clean_required,
    non_negative_int,
    payload_dict,
    safe_limit,
    valid_http_url,
)
from .errors import ProviderHTTPError, ProviderResponseError
from .models import NormalizedTrack

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


class ITunesProvider:
    source_provider = "apple_itunes"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def search(
        self, query: str, *, country: str = "VN", limit: int = 25
    ) -> list[NormalizedTrack]:
        safe_limit(limit)
        response = await self._get(
            params={
                "term": query.strip(),
                "country": country,
                "media": "music",
                "entity": "song",
                "limit": limit,
            }
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("iTunes returned an invalid response") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), list
        ):
            raise ProviderResponseError("iTunes returned an invalid result shape")
        return [track for item in payload["results"] if (track := self.normalize(item))]

    async def _get(self, *, params: dict[str, Any]) -> httpx.Response:
        try:
            response = await self.client.get(ITUNES_SEARCH_URL, params=params)
        except httpx.HTTPError as exc:
            raise ProviderResponseError("iTunes request failed") from exc
        if response.is_error:
            raise ProviderHTTPError(self.source_provider, response.status_code)
        return response

    @classmethod
    def normalize(cls, item: Any) -> NormalizedTrack | None:
        raw = payload_dict(item)
        if raw is None:
            return None
        external_id = clean_required(raw.get("trackId"))
        title = clean_required(raw.get("trackName"))
        artist_name = clean_required(raw.get("artistName"))
        if not external_id or not title or not artist_name:
            return None
        preview_url = valid_http_url(raw.get("previewUrl"))
        explicitness = str(raw.get("trackExplicitness", "")).casefold()
        return NormalizedTrack(
            source_provider=cls.source_provider,
            external_id=external_id,
            title=title,
            artist_name=artist_name,
            artist_external_id=clean_required(raw.get("artistId")),
            album_name=clean_required(raw.get("collectionName")),
            album_external_id=clean_required(raw.get("collectionId")),
            duration_ms=non_negative_int(raw.get("trackTimeMillis")),
            release_date=clean_required(raw.get("releaseDate")),
            explicit=explicitness == "explicit",
            cover_url=valid_http_url(raw.get("artworkUrl100")),
            external_url=valid_http_url(raw.get("trackViewUrl")),
            preview_url=preview_url,
            playback_type="preview" if preview_url else "external_only",
            playback_duration_ms=30_000 if preview_url else None,
            can_stream=preview_url is not None,
            raw_provider_payload=raw,
        )
