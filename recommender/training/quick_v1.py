"""Bounded first-result experiment; source-order sampling is explicit, not full training."""

import argparse
import bz2
import csv
import json
from pathlib import Path

from data_utils import sha256, write_json
from prepare import prepare
from train import train


def sample_counts(source, destination, max_rows, max_users, max_pairs):
    histories = {}
    scanned = 0
    if min(max_rows, max_users, max_pairs) < 1:
        raise ValueError("Sampling limits must be positive")
    with bz2.open(source, "rt", encoding="utf-8") as stream:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        if next(reader) != ["user_id", "track_id", "count"]:
            raise ValueError("Unexpected count header")
        for row in reader:
            scanned += 1
            if len(row) != 3 or not row[0].strip() or not row[1].strip():
                raise ValueError("Malformed source row in V1 prefix")
            user, item, raw_count = row
            if (
                not raw_count.isascii()
                or not raw_count.isdigit()
                or int(raw_count) <= 0
            ):
                raise ValueError("Invalid count in V1 prefix")
            if user in histories or len(histories) < max_users:
                history = histories.setdefault(user, {})
                if item in history or len(history) < max_pairs:
                    history[item] = history.get(item, 0) + int(raw_count)
            if scanned >= max_rows:
                break
    histories = {
        user: history for user, history in histories.items() if len(history) >= 5
    }
    if not histories:
        raise ValueError(
            "No user with >=5 sampled pairs; increase prefix/user/pair limits"
        )
    with bz2.open(destination, "wt", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["user_id", "track_id", "count"])
        for user, history in histories.items():
            for item, count in history.items():
                writer.writerow([user, item, count])
    return {
        "source_rows_scanned": scanned,
        "sample_users": len(histories),
        "sample_pairs": sum(len(history) for history in histories.values()),
        "selection": "First source-order users in a bounded source prefix; first pairs per user; not random or representative",
        "limits": {"rows": max_rows, "users": max_users, "pairs_per_user": max_pairs},
        "scope": "V1 bounded experiment, non-temporal; not full dataset training or current trends",
    }


def run_v1(onion, output, scratch, settings):
    if output.exists() or scratch.exists():
        raise ValueError("Use new output AND sample scratch directories for V1")
    for name in ("userid_trackid_count.tsv.bz2", "id_genres_tf-idf.tsv.bz2"):
        if not (onion / name).is_file():
            raise ValueError(f"Attach required Onion file: {name}")
    scratch.mkdir(parents=True)
    sample = scratch / "onion-sample"
    sample.mkdir()
    report = sample_counts(
        onion / "userid_trackid_count.tsv.bz2",
        sample / "userid_trackid_count.tsv.bz2",
        settings["max_source_rows"],
        settings["sample_users"],
        settings["max_pairs_per_user"],
    )
    (sample / "id_genres_tf-idf.tsv.bz2").symlink_to(
        (onion / "id_genres_tf-idf.tsv.bz2").resolve()
    )
    config = {
        **settings,
        "onion_root": str(sample),
        "output_root": str(output),
        "scratch_root": str(scratch / "duckdb"),
    }
    # Save provenance before preparation/training; included in artifact hashes.
    output.mkdir(parents=True)
    write_json(output / "v1_sampling.json", report)
    print(json.dumps(report, indent=2), flush=True)
    prepare(config)
    train(config)
    results = json.loads((output / "metrics.json").read_text())
    if any(
        results["evaluation"][name]["evaluated_users"] == 0
        for name in ("validation", "test")
    ):
        raise ValueError(
            "V1 has no eligible evaluation users; do not report empty metrics"
        )
    # A small summary is convenient to send without sharing model/history files.
    with (output / "metrics_summary.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "split",
                "method",
                "evaluated_users",
                "recall_at_10",
                "ndcg_at_10",
                "mrr_at_10",
                "precision_at_10",
                "catalog_coverage",
            ]
        )
        for split, evaluation in results["evaluation"].items():
            for method, metrics in evaluation["methods"].items():
                writer.writerow(
                    [
                        split,
                        method,
                        evaluation["evaluated_users"],
                        *[
                            metrics.get(key)
                            for key in (
                                "recall_at_10",
                                "ndcg_at_10",
                                "mrr_at_10",
                                "precision_at_10",
                                "catalog_coverage",
                            )
                        ],
                    ]
                )
    manifest_path = output / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["metrics_summary.csv"] = sha256(output / "metrics_summary.csv")
    write_json(manifest_path, manifest)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onion-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).parent / "configs/v1.json"
    )
    args = parser.parse_args()
    run_v1(
        args.onion_root, args.output, args.scratch, json.loads(args.config.read_text())
    )
