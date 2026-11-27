"""Small deterministic Vietnamese mood query normalizer."""

import re
import unicodedata

from .models import NormalizedMoodQuery

_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("sad", ("nhạc buồn", "buồn"), ("sad", "melancholic", "emotional")),
    ("happy", ("nhạc vui", "vui"), ("happy", "upbeat", "cheerful")),
    ("relaxing", ("thư giãn", "chill"), ("relaxing", "chill", "calm")),
    ("focus", ("tập trung", "học bài"), ("focus", "concentration", "instrumental")),
    ("sleep", ("dễ ngủ", "ngủ"), ("sleep", "calm", "ambient")),
    ("workout", ("tập thể dục", "chạy bộ"), ("workout", "energetic", "high-energy")),
)


def normalize_mood_query(query: str) -> NormalizedMoodQuery:
    original = query
    normalized = " ".join(query.casefold().strip().split())
    if not normalized:
        return NormalizedMoodQuery(original_query=original, normalized_query="")

    comparable = _without_diacritics(normalized)
    for mood, aliases, tags in _RULES:
        for alias in aliases:
            alias_key = _without_diacritics(alias)
            match = re.search(rf"(?<!\w){re.escape(alias_key)}(?!\w)", comparable)
            if match:
                residual = f"{comparable[: match.start()]} {comparable[match.end() :]}"
                residual = " ".join(residual.split()) or None
                return NormalizedMoodQuery(
                    original_query=original,
                    normalized_query=normalized,
                    text_query=residual,
                    mood=mood,
                    provider_tags=list(tags),
                )
    return NormalizedMoodQuery(
        original_query=original,
        normalized_query=normalized,
        text_query=normalized,
    )


def _without_diacritics(value: str) -> str:
    value = value.replace("đ", "d").replace("Đ", "d")
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
