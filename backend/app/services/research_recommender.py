"""Small, deterministic research baseline; never contacts a provider or database cloud."""

import math
from collections import Counter, defaultdict
from itertools import combinations


def train_neighbors(histories: dict, top_k: int = 40) -> dict:
    """Binary item cosine with support shrinkage, fitted on training pairs only."""
    frequency = Counter()
    pairs = Counter()
    for history in histories.values():
        items = sorted(history)
        frequency.update(items)
        pairs.update(combinations(items, 2))
    neighbors = defaultdict(list)
    for (left, right), support in pairs.items():
        score = support / math.sqrt(frequency[left] * frequency[right])
        score *= support / (support + 10)
        neighbors[left].append((right, score))
        neighbors[right].append((left, score))
    return {
        item: sorted(rows, key=lambda row: (-row[1], row[0]))[:top_k]
        for item, rows in neighbors.items()
    }


def rank_tracks(
    tracks: dict,
    neighbors: dict,
    history: dict,
    genres: list[str],
    recent: list[str],
    limit: int,
    mode: str = "hybrid",
) -> list[dict]:
    profile = Counter()
    collaborative = Counter()
    # Recent selections carry extra weight; the order is supplied by the demo UI.
    signals = {item: math.log1p(plays) for item, plays in history.items()}
    for position, item in enumerate(recent):
        signals[item] = signals.get(item, 0) + 3 / (position + 1)
    for item, weight in signals.items():
        for genre, value in tracks[item]["features"].items():
            profile[genre] += weight * value
        for candidate, similarity in neighbors.get(item, []):
            collaborative[candidate] += weight * similarity
    for genre in genres:
        profile[genre] += 3
    norm = math.sqrt(sum(value * value for value in profile.values())) or 1
    max_cf = max(collaborative.values(), default=0) or 1
    max_plays = math.log1p(max((t["plays"] for t in tracks.values()), default=0)) or 1
    has_cf = bool(collaborative)
    has_content = bool(profile)
    weights = {"collaborative": 0.5, "content": 0.4, "popularity": 0.1}
    if not has_cf:
        weights["collaborative"] = 0
    if not has_content:
        weights["content"] = 0
    if mode == "popularity":
        weights = {"collaborative": 0, "content": 0, "popularity": 1}
    total = sum(weights.values())
    weights = {key: value / total for key, value in weights.items()}
    excluded = set(history) | set(recent)
    ranked = []
    for item, track in tracks.items():
        if item in excluded:
            continue
        components = {
            "collaborative": collaborative[item] / max_cf,
            "content": sum(profile[g] * v for g, v in track["features"].items()) / norm,
            "popularity": math.log1p(track["plays"]) / max_plays,
        }
        score = sum(components[key] * weight for key, weight in weights.items())
        reason = max(components, key=lambda key: components[key] * weights[key])
        ranked.append(
            {
                "track_id": item,
                "score": score,
                "components": components,
                "reason": reason,
            }
        )
    return sorted(ranked, key=lambda row: (-row["score"], row["track_id"]))[:limit]
