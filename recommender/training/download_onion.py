"""Download verified official Onion files, optionally the whole release."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

RECORD = "https://zenodo.org/records/15394646"
CORE = {
    "README.md",
    "id_genres_tf-idf.tsv.bz2",
    "id_tags_dict.tsv.bz2",
    "userid_trackid_count.tsv.bz2",
    "userid_trackid_timestamp.tsv.bz2",
}


def md5(path):
    digest = hashlib.md5()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download(output, all_files=False):
    output.mkdir(parents=True, exist_ok=True)
    with urlopen("https://zenodo.org/api/records/15394646", timeout=60) as response:
        record = json.load(response)
    selected = [row for row in record["files"] if all_files or row["key"] in CORE]
    if not all_files and {row["key"] for row in selected} != CORE:
        raise ValueError("Official core file inventory changed; review release")
    manifest = []
    for entry in selected:
        name = entry["key"]
        if Path(name).name != name or "\\" in name:
            raise ValueError("Unsafe release filename")
        algorithm, expected = entry["checksum"].split(":", 1)
        if algorithm != "md5":
            raise ValueError("Unexpected release checksum algorithm")
        target = output / name
        if target.exists():
            if md5(target) != expected:
                raise ValueError(
                    f"Existing checksum mismatch for {name}; not overwriting"
                )
        else:
            partial = output / (name + ".partial")
            print("Downloading", name, "bytes:", entry["size"], flush=True)
            with (
                urlopen(
                    f"{RECORD}/files/{quote(name)}?download=1", timeout=120
                ) as response,
                partial.open("wb") as dest,
            ):
                while block := response.read(8 * 1024 * 1024):
                    dest.write(block)
            if partial.stat().st_size != entry["size"] or md5(partial) != expected:
                raise ValueError(f"Download integrity failure for {name}")
            partial.replace(target)
        manifest.append({"name": name, "bytes": target.stat().st_size, "md5": expected})
        print("Verified", name, flush=True)
    (output / "download_manifest.json").write_text(
        json.dumps({"record": RECORD, "files": manifest}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download the entire Onion release (~19.9 GB compressed)",
    )
    args = parser.parse_args()
    download(args.output, args.all)
