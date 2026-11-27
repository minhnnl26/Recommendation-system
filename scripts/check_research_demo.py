"""Run local checks in copies that exclude every .env file (including existing ones)."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-only", action="store_true")
    args = parser.parse_args()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("SUPABASE_", "NEXT_PUBLIC_")):
            del env[key]
    env.update(
        NEXT_TELEMETRY_DISABLED="1",
        NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8001",
        NEXT_PUBLIC_RESEARCH_API_BASE_URL="http://127.0.0.1:8001",
    )
    results = []

    def run(label, command, cwd):
        print(f"\n[{label}] {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=cwd, env=env, check=False)
        results.append((label, result.returncode))

    with tempfile.TemporaryDirectory(prefix="music4all-gate-") as temporary:
        sandbox = Path(temporary)
        ignore = shutil.ignore_patterns(
            ".env",
            ".env.*",
            ".venv",
            "node_modules",
            ".next",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "*.tsbuildinfo",
        )
        backend = sandbox / "backend"
        shutil.copytree(ROOT / "backend", backend, ignore=ignore)
        # Read-only artifact consumers; no copying the multi-GB raw dataset.
        (sandbox / "data").symlink_to(ROOT / "data", target_is_directory=True)
        run(
            "backend unit tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-m",
                "not integration and not research_integration",
            ],
            backend,
        )
        run(
            "real Music4All artifact integration",
            [sys.executable, "-m", "pytest", "-q", "-m", "research_integration"],
            backend,
        )
        run("Ruff check", [sys.executable, "-m", "ruff", "check", "."], backend)
        run(
            "Ruff format",
            [sys.executable, "-m", "ruff", "format", "--check", "."],
            backend,
        )
        run(
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "app", "tests"],
            backend,
        )
        if not args.backend_only:
            frontend = sandbox / "frontend"
            shutil.copytree(ROOT / "frontend", frontend, ignore=ignore)
            (frontend / "node_modules").symlink_to(
                ROOT / "frontend/node_modules", target_is_directory=True
            )
            run("frontend lint", ["npm", "run", "lint"], frontend)
            run("frontend build", ["npm", "run", "build"], frontend)
    run("git diff check", ["git", "diff", "--check"], ROOT)
    print("\nGate results:", flush=True)
    for label, code in results:
        print(f"  {label}: {'PASS' if code == 0 else 'FAIL'}", flush=True)
    return int(any(code != 0 for _, code in results))


if __name__ == "__main__":
    raise SystemExit(main())
