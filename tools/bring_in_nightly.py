"""Start a nightly run from main's code with the data collected so far on data/nightly.

Up to main's pin, main's bronze is the record, so a reading added or removed by hand on main stays that way.
After the pin, the branch's bronze is the record. Everything else in data/ comes from the branch, so crawls
resume where they stopped. Standard library only, because this runs before `make setup`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "origin/data/nightly"
_DATED = re.compile(r"dt=(\d{4}-\d{2}-\d{2})")


def drop_up_to(bronze: Path, pin: str) -> int:
    """Delete the bronze folders, manifests and run reports dated on or before the pin."""
    dropped = 0
    for path in [*bronze.glob("*/*/dt=*"), *bronze.glob("_manifest/dt=*"), *bronze.glob("_runs/dt=*")]:
        if _DATED.search(path.name).group(1) <= pin:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            dropped += 1
    return dropped


def main() -> None:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()

    if subprocess.run(["git", "rev-parse", "-q", "--verify", BRANCH], cwd=ROOT, capture_output=True).returncode != 0:
        print("No data/nightly branch yet, so this run starts from main's data")
        return
    pin = git("show", "HEAD:data/PINNED")
    git("checkout", BRANCH, "--", "data")
    drop_up_to(ROOT / "data" / "bronze", pin)
    git("checkout", "HEAD", "--", "data/bronze")
    print(f"Brought in {BRANCH}; main's bronze is the record up to {pin}")


if __name__ == "__main__":
    main()
