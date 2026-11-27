"""Synthetic full-path tests: no real audio, credentials or cloud access."""

import bz2
import csv
import json
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from data_utils import ORIGINAL_TABLES, inventory, load_features, normalize_rows
from package_original import package
from predict import Recommender
from prepare import prepare
from train import train
from train_genre_classifier import train_classifier


def make_data(tmp_path, tracks=40):
    original = tmp_path / "original"
    onion = tmp_path / "onion"
    original.mkdir()
    onion.mkdir()
    for folder in ("audios", "lyrics"):
        (original / folder).mkdir()
    ids = [f"track{i:03d}" for i in range(tracks)]
    with (original / "id_information.csv").open("w") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["id", "song", "artist", "album"])
        for i, item in enumerate(ids):
            writer.writerow(
                [item, f"Synthetic song {i}", "Synthetic artist", "Synthetic album"]
            )
            # Inventory fixture only, explicitly NOT decodable or real audio.
            (original / "audios" / f"{item}.mp3").write_bytes(
                b"synthetic-inventory-fixture"
            )
            (original / "lyrics" / f"{item}.txt").write_text("Synthetic lyrics")
    for name in ORIGINAL_TABLES:
        if name != "id_information.csv":
            (original / name).write_text("id\tfixture\n")
    with bz2.open(onion / "id_genres_tf-idf.tsv.bz2", "wt") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["id", "rock", "pop"])
        for i, item in enumerate(ids):
            writer.writerow([item, int(i % 2 == 0), int(i % 2 == 1)])
    with bz2.open(onion / "userid_trackid_count.tsv.bz2", "wt") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["user_id", "track_id", "count"])
        for user in range(12):
            for i in range(15):
                writer.writerow([str(user), ids[(i + user) % tracks], 1 + i % 4])
    with bz2.open(onion / "userid_trackid_timestamp.tsv.bz2", "wt") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["user_id", "track_id", "timestamp"])
        for day in range(30):
            for user in range(12):
                writer.writerow(
                    [
                        str(user),
                        ids[(day + user) % tracks],
                        f"2020-01-{day + 1:02d}T12:00:00Z",
                    ]
                )
    return original, onion, ids


def configuration(tmp_path, original, onion, split):
    return {
        "original_root": str(original),
        "onion_root": str(onion),
        "output_root": str(tmp_path / f"run-{split}"),
        "scratch_root": str(tmp_path / "scratch"),
        "expected_tracks": 40,
        "require_full_original": True,
        "split": split,
        "train_quantile": 0.6,
        "validation_quantile": 0.8,
        "max_users": None,
        "seed": 42,
        "factors": 8,
        "iterations": 2,
        "regularization": 0.05,
        "alpha": 10,
        "threads": 1,
        "use_gpu": False,
        "eval_users": 12,
        "k": 5,
        "hybrid_weights": {"als": 0.5, "content": 0.4, "popularity": 0.1},
    }


@pytest.mark.parametrize("split", ["hash", "temporal"])
def test_train_reload_and_recommend_end_to_end(tmp_path, split):
    original, onion, ids = make_data(tmp_path)
    config = configuration(tmp_path, original, onion, split)
    prepare(config)
    run = Path(config["output_root"])
    matrices = [
        sparse.load_npz(run / "prepared" / f"{name}.npz")
        for name in ("train", "validation", "test")
    ]
    assert matrices[0].shape == (12, 40)
    assert all(matrix.nnz for matrix in matrices)
    assert (matrices[0].multiply(matrices[1])).nnz == 0
    assert (matrices[0].multiply(matrices[2])).nnz == 0
    assert (matrices[1].multiply(matrices[2])).nnz == 0
    if split == "hash":
        assert matrices[1].nnz == matrices[2].nnz == 12
    else:
        manifest = json.loads((run / "prepared/manifest.json").read_text())
        assert manifest["split"]["kind"] == "global_temporal"
        # Earliest days only: user 0's training cannot contain the final-day item.
        users = json.loads((run / "prepared/user_ids.json").read_text())
        items = json.loads((run / "prepared/item_ids.json").read_text())
        assert matrices[0][users.index("0"), items.index(ids[29])] == 0
    train(config)
    rec = Recommender(run)
    rows = rec.recommend(user_id="0", k=5)
    assert len(rows) == 5
    known = set(matrices[0][rec.users.index("0")].indices)
    assert all(rec.items.index(row["track_id"]) not in known for row in rows)
    assert all(
        np.isfinite(row["score"]) and 0 <= row["score"] <= 1.00001 for row in rows
    )
    assert rows == rec.recommend(user_id="0", k=5)
    assert len(rec.recommend(genres=["rock"], recent=[ids[0]], k=5)) == 5
    assert all(row["track_id"] != ids[0] for row in rec.recommend(recent=[ids[0]], k=5))
    assert all(
        "title" in row and not row["playback_permission_verified"] for row in rows
    )
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["evaluation"]["test"]["evaluated_users"] > 0
    assert set(metrics["evaluation"]["test"]["methods"]) == {
        "popularity",
        "content",
        "als",
        "hybrid",
    }
    assert (run / "artifact_manifest.json").is_file()


def test_full_original_gate_rejects_missing_audio(tmp_path):
    original, _, ids = make_data(tmp_path)
    (original / "audios" / f"{ids[0]}.mp3").unlink()
    with pytest.raises(ValueError, match="inventory failed"):
        inventory(original, 40, full=True)
    _, report = inventory(original, 40, full=False)
    assert report["audios"]["missing_ids"] == 1
    assert not report["complete"]


def test_missing_timestamp_never_falls_back_to_hash(tmp_path):
    original, onion, _ = make_data(tmp_path)
    (onion / "userid_trackid_timestamp.tsv.bz2").unlink()
    with pytest.raises(ValueError, match="no silent split fallback"):
        prepare(configuration(tmp_path, original, onion, "temporal"))


def test_genre_normalization_and_invalid_weights(tmp_path):
    path = tmp_path / "feature.tsv"
    path.write_text("id\ta\tb\nA\t3\t4\nB\t0\t0\n")
    values, labels = load_features(path, ["A", "B"])
    np.testing.assert_allclose(normalize_rows(values).toarray(), [[0.6, 0.8], [0, 0]])
    assert labels == ["a", "b"]
    path.write_text("id\ta\nA\tnan\n")
    with pytest.raises(ValueError, match="Nonfinite"):
        load_features(path, ["A"])


def test_packaging_preserves_all_original_files(tmp_path):
    from zipfile import ZipFile

    original, _, _ = make_data(tmp_path)
    output = tmp_path / "shards"
    package(original, output, shard_gib=0.000001, expected=40)
    manifest = json.loads((output / "shards_manifest.json").read_text())
    names = []
    for entry in manifest["shards"]:
        with ZipFile(output / entry["file"]) as archive:
            names.extend(archive.namelist())
    assert len(names) == len(set(names))
    assert len(names) == sum(1 for path in original.rglob("*") if path.is_file())
    assert all(name.startswith("music4all/") for name in names)


def test_separate_multilabel_classifier(tmp_path):
    original, onion, ids = make_data(tmp_path, tracks=80)
    config = configuration(tmp_path, original, onion, "hash")
    config["expected_tracks"] = 80
    prepare(config)
    prepared = Path(config["output_root"]) / "prepared"
    feature = tmp_path / "audio.tsv"
    with feature.open("w") as stream:
        stream.write("id\taudio1\taudio2\n")
        for i, item in enumerate(ids):
            stream.write(f"{item}\t{1 + i % 2}\t{2 - i % 2}\n")
    output = tmp_path / "classifier"
    train_classifier(prepared, feature, output, min_support=3)
    report = json.loads((output / "report.json").read_text())
    assert report["retained_labels"] == 2
    assert report["tracks"]["train"] == 64
    assert 0 <= report["test_micro_f1"] <= 1
    with pytest.raises(ValueError, match="not genre"):
        train_classifier(
            prepared, onion / "id_genres_tf-idf.tsv.bz2", tmp_path / "leaky"
        )
