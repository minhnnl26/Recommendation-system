"""Load Kaggle artifacts for offline recommendations, without a network service."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import sparse


def score_components(
    model,
    train,
    genre,
    popularity,
    user_index=None,
    genres=(),
    genre_names=(),
    recent=(),
    confidence_alpha=20.0,
):
    items = genre.shape[0]
    signal = sparse.csr_matrix((1, items), dtype=np.float32)
    excluded = set(recent)
    if user_index is not None:
        signal = train[user_index].copy()
        excluded.update(signal.indices.tolist())
        signal.data = np.log1p(signal.data)
    if recent:
        session = sparse.csr_matrix(
            (
                [3 / (i + 1) for i in range(len(recent))],
                ([0] * len(recent), list(recent)),
            ),
            shape=(1, items),
            dtype=np.float32,
        )
        signal = signal + session
    profile = np.asarray((signal @ genre).toarray()).ravel()
    lookup = {name: i for i, name in enumerate(genre_names)}
    for name in set(genres):
        if name not in lookup:
            raise ValueError("Unknown genre")
        profile[lookup[name]] += 3
    norm = np.linalg.norm(profile)
    content = (
        np.asarray(genre @ (profile / norm)).ravel() if norm > 0 else np.zeros(items)
    )
    collaborative = np.zeros(items, dtype=np.float32)
    # No signal => no inferred CF profile. Existing users use fitted factors;
    # recent item selections trigger fold-in using the same training confidence scale.
    if signal.nnz:
        if recent or user_index is None:
            confidence = signal.copy()
            confidence.data = 1 + confidence_alpha * confidence.data
            # Fitted model uses alpha=1; the artifact stores scale separately below.
            user = model.recalculate_user(0, confidence)
        else:
            user = model.user_factors[user_index]
        collaborative = model.item_factors @ user
        collaborative = np.maximum(collaborative, 0)
        collaborative /= max(float(collaborative.max()), 1e-12)
        # Items with no train observations have no trustworthy collaborative signal.
        collaborative[popularity <= 0] = 0
    popular = np.log1p(popularity)
    popular /= max(float(popular.max()), 1e-12)
    return {"als": collaborative, "content": content, "popularity": popular}, excluded


def rank(components, excluded, weights, k):
    active = {
        name: float(weight) if np.any(components[name] > 0) else 0.0
        for name, weight in weights.items()
    }
    total = sum(active.values())
    if total <= 0:
        active = {"als": 0.0, "content": 0.0, "popularity": 1.0}
        total = 1
    active = {name: value / total for name, value in active.items()}
    scores = sum(components[name] * value for name, value in active.items())
    valid = np.ones(len(scores), dtype=bool)
    if excluded:
        valid[list(excluded)] = False
    indices = np.flatnonzero(valid)
    # Partial top-k, followed by stable ordering. Boundary ties resolved by index.
    if len(indices) > k:
        threshold = np.partition(scores[indices], -k)[-k]
        higher = indices[scores[indices] > threshold]
        ties = indices[scores[indices] == threshold][: k - len(higher)]
        indices = np.concatenate((higher, ties))
    indices = indices[np.lexsort((indices, -scores[indices]))][:k]
    return indices, scores, active


class Recommender:
    def __init__(self, run):
        from implicit.cpu.als import AlternatingLeastSquares

        run = Path(run)
        self.config = json.loads((run / "config.json").read_text())
        self.users = json.loads((run / "prepared/user_ids.json").read_text())
        self.items = json.loads((run / "prepared/item_ids.json").read_text())
        self.catalog = json.loads((run / "prepared/catalog.json").read_text())
        self.genres = json.loads((run / "prepared/genre_names.json").read_text())
        self.train = sparse.load_npz(run / "prepared/train.npz")
        self.genre = sparse.load_npz(run / "prepared/genre.npz")
        self.popularity = np.asarray(self.train.sum(axis=0)).ravel()
        self.model = AlternatingLeastSquares.load(run / "model/als.npz")
        # Model fit receives explicit 1+alpha*log1p(count), so its alpha remains 1.
        self.confidence_alpha = self.config["alpha"]

    def recommend(self, user_id=None, genres=(), recent=(), k=10):
        if not 1 <= k <= 100:
            raise ValueError("k must be between 1 and 100")
        user = None if user_id is None else self.users.index(str(user_id))
        recent_indices = [self.items.index(item) for item in dict.fromkeys(recent)]
        if len(recent_indices) > 5:
            raise ValueError("At most five recent tracks")
        components, excluded = score_components(
            self.model,
            self.train,
            self.genre,
            self.popularity,
            user,
            genres,
            self.genres,
            recent_indices,
            self.confidence_alpha,
        )
        indices, scores, active = rank(
            components, excluded, self.config["hybrid_weights"], k
        )
        return [
            {
                "track_id": self.items[i],
                **self.catalog[self.items[i]],
                "score": float(scores[i]),
                "components": {
                    name: float(values[i]) for name, values in components.items()
                },
                "weights": active,
                "audio_relative_path": (
                    f"audios/{self.items[i]}.mp3"
                    if self.config.get("catalog_source", "original") == "original"
                    else None
                ),
                "playback_permission_verified": False,
            }
            for i in indices
        ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--user-id")
    parser.add_argument("--genre", action="append", default=[])
    parser.add_argument("--recent", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    print(
        json.dumps(
            Recommender(args.run).recommend(
                args.user_id, args.genre, args.recent, args.limit
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
