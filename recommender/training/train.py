"""Train CPU/GPU ALS and evaluate popularity/content/ALS/hybrid on held-out pairs."""

import argparse
import importlib.metadata
import json
import math
import time
from pathlib import Path

import numpy as np
from scipy import sparse
from threadpoolctl import threadpool_limits

from data_utils import sha256, write_json
from predict import rank, score_components


def evaluate(model, train, validation, test, genre, config):
    popularity = np.asarray(train.sum(axis=0)).ravel()
    variants = {
        "popularity": {"als": 0, "content": 0, "popularity": 1},
        "content": {"als": 0, "content": 1, "popularity": 0},
        "als": {"als": 1, "content": 0, "popularity": 0},
        "hybrid": config["hybrid_weights"],
    }
    results = {}
    for name, truth in (("validation", validation), ("test", test)):
        eligible = np.flatnonzero(truth.getnnz(axis=1) > 0)
        # Fixed seed subset, not just first IDs; same users for each method.
        users = np.random.default_rng(config["seed"]).permutation(eligible)[
            : config["eval_users"]
        ]
        accum = {
            variant: {"recall": 0, "ndcg": 0, "mrr": 0, "precision": 0, "items": set()}
            for variant in variants
        }
        started = time.monotonic()
        for user in users:
            components, excluded = score_components(
                model, train, genre, popularity, int(user)
            )
            if name == "test":
                # Frozen train-only model; mask validation observations when testing.
                excluded.update(validation[user].indices.tolist())
            relevant = set(truth[user].indices.tolist())
            for variant, weights in variants.items():
                ids, _, _ = rank(components, excluded, weights, config["k"])
                hit = [int(item in relevant) for item in ids]
                metrics = accum[variant]
                metrics["recall"] += sum(hit) / len(relevant)
                metrics["precision"] += sum(hit) / config["k"]
                dcg = sum(
                    value / math.log2(position + 2)
                    for position, value in enumerate(hit)
                )
                ideal = sum(
                    1 / math.log2(position + 2)
                    for position in range(min(config["k"], len(relevant)))
                )
                metrics["ndcg"] += dcg / ideal
                metrics["mrr"] += next(
                    (1 / (position + 1) for position, value in enumerate(hit) if value),
                    0,
                )
                metrics["items"].update(ids.tolist())
        results[name] = {
            "eligible_users": len(eligible),
            "evaluated_users": len(users),
            "seconds": round(time.monotonic() - started, 3),
            "methods": {
                variant: {
                    **{
                        f"{metric}_at_{config['k']}": value / len(users)
                        if len(users)
                        else None
                        for metric, value in metrics.items()
                        if metric != "items"
                    },
                    "catalog_coverage": len(metrics["items"]) / train.shape[1],
                }
                for variant, metrics in accum.items()
            },
        }
    return results


def train(config):
    from implicit.als import AlternatingLeastSquares

    output = Path(config["output_root"])
    if json.loads((output / "config.json").read_text()) != config:
        raise ValueError("Training config differs from prepared data; create a new run")
    model_dir = output / "model"
    if model_dir.exists():
        raise ValueError("Model output already exists; use a new output_root")
    model_dir.mkdir(parents=True)
    train_matrix = sparse.load_npz(output / "prepared/train.npz").astype(np.float32)
    validation = sparse.load_npz(output / "prepared/validation.npz")
    test = sparse.load_npz(output / "prepared/test.npz")
    genre = sparse.load_npz(output / "prepared/genre.npz")
    confidence = train_matrix.copy()
    confidence.data = 1 + config["alpha"] * np.log1p(confidence.data)
    model = AlternatingLeastSquares(
        factors=config["factors"],
        regularization=config["regularization"],
        iterations=config["iterations"],
        alpha=1.0,
        use_gpu=config["use_gpu"],
        num_threads=config["threads"],
        random_state=config["seed"],
    )
    started = time.monotonic()
    with threadpool_limits(limits=1, user_api="blas"):
        model.fit(confidence)
        fit_seconds = time.monotonic() - started
        if config["use_gpu"]:
            model = model.to_cpu()
        if (
            not np.isfinite(model.user_factors).all()
            or not np.isfinite(model.item_factors).all()
        ):
            raise ValueError("Nonfinite ALS factors")
        # Checkpoint before evaluation so a long evaluation does not lose the fit.
        model.save(model_dir / "als.npz")
        metrics = evaluate(model, train_matrix, validation, test, genre, config)
    versions = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "duckdb", "implicit", "scikit-learn")
    }
    write_json(
        output / "metrics.json", {"fit_seconds": fit_seconds, "evaluation": metrics}
    )
    manifest = {
        "model": "implicit-als-genre-hybrid-v1",
        "versions": versions,
        "confidence": "1 + alpha * log1p(train_count), implicit model alpha=1",
        "config": config,
        "files": {
            str(path.relative_to(output)): sha256(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and path.name != "artifact_manifest.json"
        },
        "scope": "Recommender, not a genre classifier; no audio binary in output; not wired into FastAPI yet",
        "evaluation": "Frozen train model; no validation/test refit or test-based tuning; unseen pairs only",
    }
    write_json(output / "artifact_manifest.json", manifest)
    print(json.dumps({"fit_seconds": fit_seconds, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    train(json.loads(args.config.read_text()))
