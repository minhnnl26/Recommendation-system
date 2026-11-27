import httpx
import pytest

from app.integrations.music_providers.errors import (
    ProviderConfigurationError,
    ProviderHTTPError,
)
from app.integrations.music_providers.itunes import ITunesProvider
from app.integrations.music_providers.jamendo import JamendoProvider
from app.integrations.music_providers.models import NormalizedTrack
from app.integrations.music_providers.mood import normalize_mood_query
from app.integrations.music_providers.service import MusicProviderService


def make_client(payload, *, status_code=200):
    def handler(request: httpx.Request):
        return httpx.Response(status_code, json=payload, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_itunes_maps_preview_and_optional_fields():
    client = make_client(
        {
            "results": [
                {
                    "trackId": 123,
                    "trackName": "Example",
                    "artistName": "Artist",
                    "artistId": 456,
                    "collectionName": "Album",
                    "collectionId": 789,
                    "trackTimeMillis": 201000,
                    "releaseDate": "2026-01-01T00:00:00Z",
                    "trackExplicitness": "explicit",
                    "artworkUrl100": "https://example.test/cover.jpg",
                    "trackViewUrl": "https://example.test/song",
                    "previewUrl": "https://example.test/preview.m4a",
                },
                {"trackId": 456, "trackName": "Missing artist"},
            ]
        }
    )
    try:
        results = await ITunesProvider(client).search("Example", limit=1)
    finally:
        await client.aclose()

    assert len(results) == 1
    track = results[0]
    assert track.source_provider == "apple_itunes"
    assert track.playback_type == "preview"
    assert track.playback_duration_ms == 30_000
    assert track.can_stream is True
    assert track.explicit is True
    assert track.duration_ms == 201000


@pytest.mark.asyncio
async def test_itunes_without_preview_is_external_only():
    client = make_client(
        {"results": [{"trackId": 1, "trackName": "No preview", "artistName": "Artist"}]}
    )
    try:
        track = (await ITunesProvider(client).search("No preview"))[0]
    finally:
        await client.aclose()
    assert track.playback_type == "external_only"
    assert track.can_stream is False
    assert track.playback_duration_ms is None


@pytest.mark.asyncio
async def test_itunes_http_error_is_sanitized():
    client = make_client({"error": "not exposed"}, status_code=503)
    try:
        with pytest.raises(
            ProviderHTTPError, match="apple_itunes provider request failed"
        ):
            await ITunesProvider(client).search("Artist")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_jamendo_maps_full_audio_seconds_and_license():
    client = make_client(
        {
            "results": [
                {
                    "id": "jam-1",
                    "name": "Licensed track",
                    "artist_name": "Jam Artist",
                    "artist_id": "artist-1",
                    "album_name": "Jam Album",
                    "album_id": "album-1",
                    "duration": 215,
                    "releasedate": "2026-02-01",
                    "image": "https://example.test/image.jpg",
                    "shareurl": "https://example.test/share",
                    "audio": "https://example.test/audio.mp3",
                    "audiodownload": "https://example.test/do-not-use",
                    "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                }
            ]
        }
    )
    try:
        track = (await JamendoProvider(client, "test-client-id").search("track"))[0]
    finally:
        await client.aclose()
    assert track.playback_type == "full"
    assert track.can_stream is True
    assert track.duration_ms == 215000
    assert track.playback_duration_ms == 215000
    assert track.license_name == "Creative Commons"
    assert track.preview_url == "https://example.test/audio.mp3"


@pytest.mark.asyncio
async def test_jamendo_without_audio_is_external_only():
    client = make_client(
        {"results": [{"id": "jam-2", "name": "No audio", "artist_name": "Artist"}]}
    )
    try:
        track = (await JamendoProvider(client, "test-client-id").search("track"))[0]
    finally:
        await client.aclose()
    assert track.playback_type == "external_only"
    assert track.can_stream is False
    assert track.playback_duration_ms is None


@pytest.mark.asyncio
async def test_jamendo_missing_client_id_does_not_make_request():
    client = make_client({"results": []})
    try:
        with pytest.raises(
            ProviderConfigurationError, match="configuration is missing"
        ):
            await JamendoProvider(client, None).search("track")
    finally:
        await client.aclose()


def test_mood_query_normalization_and_plain_text():
    sad = normalize_mood_query("  Nhạc   buồn piano ")
    assert sad.normalized_query == "nhạc buồn piano"
    assert sad.text_query == "piano"
    assert sad.mood == "sad"
    assert sad.provider_tags == ["sad", "melancholic", "emotional"]

    plain = normalize_mood_query("Taylor Swift")
    assert plain.text_query == "taylor swift"
    assert plain.mood is None
    assert plain.provider_tags == []


@pytest.mark.asyncio
async def test_service_selects_one_provider_and_preserves_order(monkeypatch):
    payload = {
        "results": [
            {"trackId": 1, "trackName": "First", "artistName": "Artist"},
            {"trackId": 2, "trackName": "Second", "artistName": "Artist"},
        ]
    }

    def factory():
        return make_client(payload)

    monkeypatch.delenv("JAMENDO_CLIENT_ID", raising=False)
    results = await MusicProviderService(client_factory=factory).search(
        "itunes", "Artist"
    )
    assert [item.external_id for item in results] == ["1", "2"]
    assert all(isinstance(item, NormalizedTrack) for item in results)
