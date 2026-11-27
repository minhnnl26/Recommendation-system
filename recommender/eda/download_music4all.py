"""Download only the selected official Music4All-Onion v2 metadata files."""

import argparse
import hashlib
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data/raw/music4all-onion"
RECORD_URL = "https://zenodo.org/records/15394646"
FILES = {
    "README.md": "df379ed27dcefe5652b8db4e6783e304",
    "id_genres_tf-idf.tsv.bz2": "a742b5fa1d2e2ce780101773e57bb7f5",
    "id_tags_dict.tsv.bz2": "9c1ca4a3e04a9696b9449ec54ac40cd5",
    "userid_trackid_count.tsv.bz2": "314b51196a9c8f333c7fefc0711760a1",
}


def file_hash(path, algorithm="md5"):
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def download(name):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / name
    if target.exists():
        if file_hash(target) == FILES[name]:
            print(f"Verified existing {name}", flush=True)
            return
        raise ValueError(f"Existing {name} has an unexpected checksum; not overwriting")
    partial = target.with_name(target.name + ".partial")
    request = Request(
        f"{RECORD_URL}/files/{name}?download=1",
        headers={"User-Agent": "MusicRecommendationAcademicEDA/1.0"},
    )
    for attempt in range(3):
        try:
            print(f"Downloading {name}", flush=True)
            with urlopen(request, timeout=90) as source, partial.open("wb") as dest:
                received = 0
                next_progress = 32 * 1024 * 1024
                while block := source.read(1024 * 1024):
                    dest.write(block)
                    received += len(block)
                    if received >= next_progress:
                        print(f"{name}: {received // (1024 * 1024)} MiB", flush=True)
                        next_progress += 32 * 1024 * 1024
            if file_hash(partial) != FILES[name]:
                raise ValueError(f"Checksum mismatch for {name}")
            partial.replace(target)
            print(f"Verified {name}", flush=True)
            return
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError(f"Public download failed for {name}") from None
            time.sleep(attempt + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-interactions", action="store_true")
    args = parser.parse_args()
    for name in FILES:
        if name.startswith("userid_") and not args.include_interactions:
            continue
        download(name)


if __name__ == "__main__":
    main()
