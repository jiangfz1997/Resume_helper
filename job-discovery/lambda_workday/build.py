"""Build the deployment zip for the Workday-only pipeline Lambda.

Only runtime dependency is pydantic -- no numpy/pandas/tls-client, so this
stays small and avoids everything lambda_probe/build.py had to work around
(the tls-client platform-binary pruning, the NUMPY==1.26.3 pin bypass).

job_discovery itself is not published anywhere to pip install; this copies
src/job_discovery straight into the package.

    python build.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
JOB_DISCOVERY_SRC = HERE.parent / "src" / "job_discovery"
BUILD_DIR = HERE / "build" / "pkg"
DIST = HERE / "dist" / "lambda-workday.zip"

PYTHON_VERSION = "3.13"
PIP_PLATFORM = "manylinux2014_x86_64"
DEPENDENCIES = ["pydantic>=2.7.0"]


def run(args: list[str]) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, check=True)


def main() -> int:
    if not JOB_DISCOVERY_SRC.is_dir():
        raise SystemExit(f"job_discovery package not found at {JOB_DISCOVERY_SRC}")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"installing dependencies for python{PYTHON_VERSION} / {PIP_PLATFORM}")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--target",
            str(BUILD_DIR),
            "--platform",
            PIP_PLATFORM,
            "--python-version",
            PYTHON_VERSION,
            "--only-binary=:all:",
            "--upgrade",
            *DEPENDENCIES,
        ]
    )

    print(f"copying job_discovery package from {JOB_DISCOVERY_SRC}")
    shutil.copytree(
        JOB_DISCOVERY_SRC,
        BUILD_DIR / "job_discovery",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    DIST.parent.mkdir(parents=True, exist_ok=True)
    DIST.unlink(missing_ok=True)
    with zipfile.ZipFile(DIST, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in BUILD_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(BUILD_DIR).as_posix())
        archive.write(HERE / "lambda_function.py", "lambda_function.py")

    zipped = DIST.stat().st_size
    print(f"\noutput: {DIST}")
    print(f"zipped: {zipped / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
