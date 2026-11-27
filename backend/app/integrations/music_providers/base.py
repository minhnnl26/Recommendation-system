"""Shared validation helpers for provider adapters."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

MAX_PROVIDER_LIMIT = 50


def safe_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_PROVIDER_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_PROVIDER_LIMIT}")
    return limit


def valid_http_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def clean_required(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def payload_dict(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, Mapping) else None
