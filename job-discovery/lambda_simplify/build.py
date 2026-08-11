"""Build the lightweight Simplify crawler Lambda deployment zip."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
JOB_DISCOVERY_SRC = HERE.parent / "src" / "job_discovery"
BUILD_DIR = HERE / "build" / "pkg"
DIST = HERE / "dist" / "lambda-simplify.zip"


def main() -> int:
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--quiet", "--target", str(BUILD_DIR),
        "--platform", "manylinux2014_x86_64", "--python-version", "3.13",
        "--only-binary=:all:", "--upgrade", "pydantic>=2.7.0",
    ], check=True)
    shutil.copytree(
        JOB_DISCOVERY_SRC, BUILD_DIR / "job_discovery",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    DIST.parent.mkdir(parents=True, exist_ok=True)
    DIST.unlink(missing_ok=True)
    with zipfile.ZipFile(DIST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in BUILD_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(BUILD_DIR).as_posix())
        archive.write(HERE / "lambda_function.py", "lambda_function.py")
    print(f"output: {DIST} ({DIST.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
