"""Verify that the complete original catalog, metadata, audio and lyrics exist."""

import argparse
from pathlib import Path

from data_utils import inventory, write_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-tracks", type=int, default=109269)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    _, report = inventory(args.root, args.expected_tracks)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, report)
    print("Full Music4All inventory passed:", report["catalog_tracks"], "tracks")
