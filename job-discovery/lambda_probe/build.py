"""Build a Linux-targeted deployment zip for the Lambda probe.

Runs on any host: pip resolves manylinux wheels explicitly rather than using
the build machine's platform, so a Windows box produces a valid Lambda package.

    python build.py

Output: dist/lambda-probe.zip
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
BUILD_DIR = HERE / "build" / "pkg"
DIST = HERE / "dist" / "lambda-probe.zip"

PYTHON_VERSION = "3.13"

PIP_PLATFORM = {"x86_64": "manylinux2014_x86_64", "arm64": "manylinux2014_aarch64"}

# tls-client ships as py3-none-any and bundles the Go shared library for every
# platform: 93 MB of binaries where one is used. Which one is not obvious --
# tls_client/cffi.py branches on platform.machine(), and on x86_64 Linux the
# check "x86" in machine() matches "x86_64" first, so it loads tls-client-x86.so
# and never reaches the -amd64.so branch. Pruning to -amd64.so builds a package
# that fails at import with a ctypes error.
TLS_CLIENT_KEEP = {"x86_64": "tls-client-x86.so", "arm64": "tls-client-arm64.so"}

# boto3 ships with the Lambda runtime and is excluded deliberately.
# numpy is the one deviation from jobspy's declared pins: it requires
# NUMPY==1.26.3, which has no cp313 wheel.
DEPENDENCIES: list[str] = [
    "pydantic>=2.7.0",
    "numpy>=2.1",
    "pandas>=2.2.3,<3",
    "beautifulsoup4>=4.12.2,<5",
    "markdownify>=0.13.1,<0.14",
    "regex>=2024.4.28,<2025",
    "requests>=2.31,<3",
    "tls-client>=1.0.1,<2",
]

JOBSPY = "python-jobspy>=1.1.82"

# Test and build artifacts that inflate the zip without being imported.
PRUNE_DIRS = {"__pycache__", "tests", "test", "testing", ".dist-info-ignore"}
PRUNE_SUFFIXES = (".pyc", ".pyo", ".c", ".h", ".pyx")


def run(args: list[str]) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, check=True)


def pip_install(packages: list[str], no_deps: bool, arch: str) -> None:
    args = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--target",
        str(BUILD_DIR),
        "--platform",
        PIP_PLATFORM[arch],
        "--python-version",
        PYTHON_VERSION,
        "--only-binary=:all:",
        "--upgrade",
    ]
    if no_deps:
        args.append("--no-deps")
    run(args + packages)


def prune_tls_client(arch: str) -> int:
    """Drop the bundled binaries for every platform except the target."""
    dependencies = BUILD_DIR / "tls_client" / "dependencies"
    if not dependencies.is_dir():
        return 0
    keep = TLS_CLIENT_KEEP[arch]
    freed = 0
    for path in dependencies.iterdir():
        if path.is_file() and path.name != keep:
            freed += path.stat().st_size
            path.unlink()
    kept = dependencies / keep
    if not kept.exists():
        raise SystemExit(f"expected {keep} in {dependencies}; tls-client layout changed")
    return freed


def prune(root: Path) -> int:
    removed = 0
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and path.name in PRUNE_DIRS:
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
        elif path.is_file() and path.suffix in PRUNE_SUFFIXES:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def build_zip() -> None:
    DIST.parent.mkdir(parents=True, exist_ok=True)
    DIST.unlink(missing_ok=True)
    with zipfile.ZipFile(DIST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in BUILD_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(BUILD_DIR).as_posix())
        archive.write(HERE / "lambda_function.py", "lambda_function.py")


def directory_size(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Lambda probe zip")
    parser.add_argument("--arch", choices=["x86_64", "arm64"], default="x86_64")
    parser.add_argument("--keep-build", action="store_true", help="do not delete build/ first")
    args = parser.parse_args()

    if not args.keep_build and BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"installing dependencies for python{PYTHON_VERSION} / {PIP_PLATFORM[args.arch]}")
    pip_install(DEPENDENCIES, no_deps=False, arch=args.arch)
    print("installing jobspy without dependencies (bypasses its NUMPY==1.26.3 pin)")
    pip_install([JOBSPY], no_deps=True, arch=args.arch)

    freed = prune_tls_client(args.arch)
    print(f"tls-client: kept {TLS_CLIENT_KEEP[args.arch]}, freed {freed / 1e6:.1f} MB")
    pruned = prune(BUILD_DIR)
    unpacked = directory_size(BUILD_DIR)
    build_zip()
    zipped = DIST.stat().st_size

    print()
    print(f"pruned entries : {pruned}")
    print(f"unpacked       : {unpacked / 1e6:8.1f} MB  (Lambda limit 250 MB)")
    print(f"zipped         : {zipped / 1e6:8.1f} MB  (direct console upload limit 50 MB)")
    print(f"output         : {DIST}")
    if zipped > 50e6:
        print("\nzip exceeds the console upload limit; upload via S3 or use a container image")
    if unpacked > 250e6:
        print("\nunpacked size exceeds the Lambda limit; a container image is required")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
