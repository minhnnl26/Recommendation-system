"""Split a complete original dataset into ZIP shards for private storage/upload."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from data_utils import inventory, sha256, write_json


def package(root, output, shard_gib=2.0, expected=109269):
    if output.exists():
        raise ValueError(
            "Use a new output directory; existing shards are never overwritten"
        )
    _, report = inventory(root, expected, full=True)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in files):
        raise ValueError("Symlinked input files are not supported for packaging")
    if any(
        path.name.startswith(".env")
        or path.name in {"kaggle.json", "credentials.json", "token.json"}
        or path.suffix in {".pem", ".key"}
        for path in files
    ):
        raise ValueError(
            "Credential-like filename found in dataset root; packaging stopped"
        )
    output.mkdir(parents=True)
    budget = int(shard_gib * 1024**3)
    if budget < 1:
        raise ValueError("shard-gib must be positive")
    manifest = []
    archive = None
    current_bytes = 0
    try:
        for path in files:
            size = path.stat().st_size
            if archive is None or (current_bytes and current_bytes + size > budget):
                if archive is not None:
                    archive.close()
                shard = output / f"music4all-{len(manifest):03d}.zip"
                archive = ZipFile(shard, "x", compression=ZIP_STORED, allowZip64=True)
                manifest.append({"file": shard.name, "source_bytes": 0, "files": 0})
                current_bytes = 0
            archive.write(
                path, arcname="music4all/" + path.relative_to(root).as_posix()
            )
            current_bytes += size
            manifest[-1]["source_bytes"] += size
            manifest[-1]["files"] += 1
    finally:
        if archive is not None:
            archive.close()
    for entry in manifest:
        entry["sha256"] = sha256(output / entry["file"])
    write_json(
        output / "shards_manifest.json", {"inventory": report, "shards": manifest}
    )
    print(json.dumps({"shards": len(manifest), "tracks": report["catalog_tracks"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shard-gib", type=float, default=2.0)
    parser.add_argument("--expected-tracks", type=int, default=109269)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.root.resolve()):
        parser.error("Output must be outside the source dataset root")
    package(args.root, args.output, args.shard_gib, args.expected_tracks)
