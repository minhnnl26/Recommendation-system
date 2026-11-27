"""Create an allowlisted code-only archive; never traverses app env/data folders."""

import argparse
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package(output):
    code = ROOT / "recommender/training"
    paths = sorted(code.glob("*.py")) + [
        code / "requirements-kaggle.txt",
        code / "pyproject.toml",
        code / "uv.lock",
        code / "configs/full.json",
    ]
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValueError("Missing training source/lock or symlink detected")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x") as archive:
        for path in paths:
            archive.write(path, "training/" + path.relative_to(code).as_posix())
    print("Created code-only archive:", output.name, "files:", len(paths))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "artifacts/kaggle/training-code.zip"
    )
    args = parser.parse_args()
    package(args.output)
