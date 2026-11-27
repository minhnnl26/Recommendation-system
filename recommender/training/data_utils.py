"""Local, streaming dataset utilities. No cloud credentials or environment files."""

import bz2
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy import sparse

ORIGINAL_TABLES = (
    "id_information.csv",
    "id_metadata.csv",
    "id_genres.csv",
    "id_tags.csv",
    "id_lang.csv",
    "listening_history.csv",
)


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def read_catalog(root):
    path = Path(root) / "id_information.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.read(16384)
        stream.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
        rows = csv.DictReader(stream, dialect=dialect)
        fields = rows.fieldnames or []
        aliases = {
            "id": ("id", "track_id"),
            "title": ("song", "name", "track_name", "title"),
            "artist": ("artist", "artist_name"),
            "album": ("album", "album_name"),
        }
        columns = {
            key: next((name for name in names if name in fields), None)
            for key, names in aliases.items()
        }
        if any(value is None for value in columns.values()):
            raise ValueError(
                "id_information.csv must contain ID, song/title, artist and album columns"
            )
        catalog = {}
        for row in rows:
            item = row[columns["id"]]
            if not item or item != item.strip() or item in catalog:
                raise ValueError("Empty, padded or duplicate original track ID")
            if Path(item).name != item or item in {".", ".."} or "\\" in item:
                raise ValueError("Unsafe original track ID")
            catalog[item] = {
                key: row[column] for key, column in columns.items() if key != "id"
            }
    return catalog


def inventory(root, expected=109269, full=True):
    root = Path(root)
    catalog = read_catalog(root)
    missing_tables = [
        name
        for name in ORIGINAL_TABLES
        if not (root / name).is_file() or (root / name).stat().st_size == 0
    ]
    ids = set(catalog)
    result = {
        "catalog_tracks": len(ids),
        "expected_tracks": expected,
        "missing_tables": missing_tables,
    }
    for folder, extension in (("audios", ".mp3"), ("lyrics", ".txt")):
        files = list((root / folder).rglob(f"*{extension}"))
        files = [p for p in files if p.stem in ids]
        present = {p.stem for p in files if p.stat().st_size > 0}
        result[folder] = {
            "nonempty_matching_ids": len(present),
            "missing_ids": len(ids - present),
            "duplicate_ids": len(files) - len({p.stem for p in files}),
            "bytes": sum(p.stat().st_size for p in files),
        }
    result["complete"] = (
        len(ids) == expected
        and not missing_tables
        and all(
            result[key]["missing_ids"] == 0 and result[key]["duplicate_ids"] == 0
            for key in ("audios", "lyrics")
        )
    )
    result["verification"] = (
        "Nonempty file/ID inventory; does not decode MP3 or establish playback permissions"
    )
    if full and not result["complete"]:
        raise ValueError(
            "Full original Music4All inventory failed: " + json.dumps(result)
        )
    return catalog, result


def load_features(path, item_ids):
    """Read an ID + numerical TSV without materializing a dense catalog matrix."""
    lookup = {item: index for index, item in enumerate(item_ids)}
    row_indices, columns, values = [], [], []
    seen = set()
    opener = bz2.open if str(path).endswith(".bz2") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        if header[0] != "id" or len(header) < 2 or len(set(header)) != len(header):
            raise ValueError(
                "Expected numerical feature header: id + unique feature columns"
            )
        for row in reader:
            if row[0] not in lookup:
                continue
            if row[0] in seen or len(row) != len(header):
                raise ValueError("Duplicate or malformed feature row")
            seen.add(row[0])
            for column, raw in enumerate(row[1:]):
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("Nonfinite feature value")
                if value != 0:
                    row_indices.append(lookup[row[0]])
                    columns.append(column)
                    values.append(value)
    matrix = sparse.csr_matrix(
        (np.asarray(values, dtype=np.float32), (row_indices, columns)),
        shape=(len(item_ids), len(header) - 1),
    )
    return matrix, header[1:]


def normalize_rows(matrix):
    norms = np.sqrt(matrix.multiply(matrix).sum(axis=1)).A1
    return sparse.diags(1 / np.where(norms > 0, norms, 1)).dot(matrix).tocsr()


def export_sparse(db, query, shape, output):
    """Bounded result streaming; disk-backed buffers avoid 50M Python tuples."""
    count = db.execute(f"SELECT count(*) FROM ({query}) q").fetchone()[0]
    if not count:
        matrix = sparse.csr_matrix(shape, dtype=np.float32)
        sparse.save_npz(output, matrix)
        return matrix
    paths = [
        Path(str(output) + suffix)
        for suffix in (".rows.tmp", ".cols.tmp", ".values.tmp")
    ]
    buffers = [
        np.memmap(path, dtype=dtype, mode="w+", shape=(count,))
        for path, dtype in zip(paths, (np.int32, np.int32, np.float32))
    ]
    cursor = db.execute(query)
    position = 0
    while rows := cursor.fetchmany(100000):
        batch = np.asarray(rows)
        end = position + len(batch)
        for column, target in enumerate(buffers):
            target[position:end] = batch[:, column]
        position = end
    matrix = sparse.coo_matrix(
        (buffers[2], (buffers[0], buffers[1])), shape=shape
    ).tocsr()
    sparse.save_npz(output, matrix)
    for buffer in buffers:
        buffer.flush()
    del buffers
    for path in paths:
        path.unlink()
    return matrix
