"""Offline-safe CLI entry point for manually probing a provider."""

import argparse
import asyncio
import sys

from app.integrations.music_providers.errors import ProviderError
from app.integrations.music_providers.service import MusicProviderService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe a music provider without database writes"
    )
    parser.add_argument("--provider", choices=("itunes", "jamendo"), required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    return parser


async def run(args: argparse.Namespace) -> int:
    try:
        tracks = await MusicProviderService().search(
            args.provider, args.query, limit=args.limit
        )
    except (ProviderError, ValueError) as exc:
        print(f"{args.provider}: {exc}", file=sys.stderr)
        return 2
    for track in tracks:
        print(
            {
                "provider": track.source_provider,
                "external_id": track.external_id,
                "title": track.title,
                "artist": track.artist_name,
                "playback_type": track.playback_type,
                "can_stream": track.can_stream,
                "has_preview_url": track.preview_url is not None,
                "has_license": track.license_url is not None,
            }
        )
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
