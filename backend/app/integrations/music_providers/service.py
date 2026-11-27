"""Provider selection and normalized search orchestration."""

import os
from collections.abc import Callable
from typing import Literal

import httpx

from .base import safe_limit
from .errors import ProviderConfigurationError
from .itunes import ITunesProvider
from .jamendo import JamendoProvider
from .models import NormalizedTrack
from .mood import normalize_mood_query

ProviderName = Literal["itunes", "jamendo"]


class MusicProviderService:
    def __init__(
        self, *, client_factory: Callable[[], httpx.AsyncClient] | None = None
    ):
        self.client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=10.0)
        )

    async def search(
        self,
        provider: ProviderName,
        query: str,
        *,
        limit: int = 25,
        country: str = "VN",
    ) -> list[NormalizedTrack]:
        safe_limit(limit)
        parsed = normalize_mood_query(query)
        async with self.client_factory() as client:
            if provider == "itunes":
                provider_client = ITunesProvider(client)
                return await provider_client.search(
                    parsed.text_query or parsed.normalized_query,
                    country=country,
                    limit=limit,
                )
            if provider == "jamendo":
                provider_client = JamendoProvider(
                    client, os.environ.get("JAMENDO_CLIENT_ID")
                )
                return await provider_client.search(
                    parsed.text_query,
                    tags=parsed.provider_tags,
                    limit=limit,
                )
        raise ProviderConfigurationError("Unknown music provider")
