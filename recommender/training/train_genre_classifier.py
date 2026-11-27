"""Optional multi-label genre classifier from an ID-aligned audio feature TSV."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import f1_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import StandardScaler

from data_utils import load_features, sha256, write_json


def train_classifier(prepared, features, output, seed=42, min_support=20):
    if output.exists():
        raise ValueError("Classifier output already exists; use a new directory")
    # Prevent the most direct form of target leakage. Caller must supply audio
    # features, never label-derived genre/tag/lyrics TF-IDF as classifier input.
    if any(word in features.name.lower() for word in ("genre", "tag", "lyrics")):
        raise ValueError(
            "Classifier requires audio features, not genre/tag/lyrics targets"
        )
    ids = json.loads((prepared / "item_ids.json").read_text())
    labels = json.loads((prepared / "genre_names.json").read_text())
    y = sparse.load_npz(prepared / "genre.npz").astype(bool).astype(np.int32)
    x, feature_names = load_features(features, ids)
    eligible = np.flatnonzero((x.getnnz(axis=1) > 0) & (y.getnnz(axis=1) > 0))
    indices = np.random.default_rng(seed).permutation(eligible)
    n = len(indices)
    if n < 30:
        raise ValueError(
            "Need at least 30 tracks with both audio features and genre labels"
        )
    train, val, test = np.split(indices, [int(n * 0.8), int(n * 0.9)])
    supports = np.asarray(y[train].sum(axis=0)).ravel()
    keep = np.flatnonzero(
        (supports >= min_support) & (supports <= len(train) - min_support)
    )
    if len(keep) < 2:
        raise ValueError(
            "At least two genres need enough positive/negative training examples"
        )
    y = y[:, keep]
    scaler = StandardScaler(with_mean=False)
    x_train = scaler.fit_transform(x[train])
    model = OneVsRestClassifier(
        SGDClassifier(
            loss="log_loss",
            max_iter=1000,
            tol=1e-3,
            random_state=seed,
            class_weight="balanced",
        ),
        n_jobs=1,
    )
    model.fit(x_train, y[train])
    val_probability = np.asarray(model.predict_proba(scaler.transform(x[val])))
    if val_probability.shape[1] != len(keep):
        # sklearn uses binary shape conventions with one output; require >=2.
        raise ValueError("Need at least two retained genre labels")
    candidates = [0.2, 0.35, 0.5, 0.65]
    threshold = max(
        candidates,
        key=lambda t: f1_score(
            y[val], val_probability >= t, average="micro", zero_division=0
        ),
    )
    probability = np.asarray(model.predict_proba(scaler.transform(x[test])))
    output.mkdir(parents=True)
    np.savez_compressed(
        output / "genre_classifier.npz",
        coefficients=np.vstack([m.coef_ for m in model.estimators_]),
        intercepts=np.concatenate([m.intercept_ for m in model.estimators_]),
        scale=scaler.scale_,
        threshold=np.array(threshold),
        labels=np.array([labels[i] for i in keep]),
        feature_names=np.array(feature_names),
    )
    write_json(
        output / "report.json",
        {
            "model": "OneVsRest SGD logistic multi-label classifier",
            "seed": seed,
            "split": "Random track-disjoint 80/10/10, not artist-disjoint; no recommender user split",
            "tracks": {"train": len(train), "validation": len(val), "test": len(test)},
            "retained_labels": len(keep),
            "excluded_labels": len(labels) - len(keep),
            "threshold_selected_on_validation": threshold,
            "test_micro_f1": f1_score(
                y[test], probability >= threshold, average="micro", zero_division=0
            ),
            "test_macro_f1": f1_score(
                y[test], probability >= threshold, average="macro", zero_division=0
            ),
            "source_sha256": sha256(features),
            "limitations": "Predicts dataset-derived genre labels, not user preference or human-verified mood; artist overlap can inflate results",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--audio-features", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-support", type=int, default=20)
    args = parser.parse_args()
    train_classifier(
        args.prepared, args.audio_features, args.output, args.seed, args.min_support
    )
