"""
Keep `Final App` small: only the newest KEEP versions of Wisperno Pro stay on disk (app folder v<ver>, installer
.exe and its .bin volumes); every older one is deleted. Called at the end of scripts/build_installer.py, or run by hand:

    python scripts/prune_builds.py            # delete older versions
    python scripts/prune_builds.py --dry-run  # only list what would go

Only names that look like v<major>.<minor>.<patch> / WispernoPro-Setup-v<...> are ever touched.
"""

import re
import shutil
import sys
from pathlib import Path

KEEP = 2
BASE_DIR = Path(__file__).resolve().parent.parent
_VERSION = re.compile(r"^(?:WispernoPro-Setup-)?v(\d+)\.(\d+)\.(\d+)(?:$|\.exe$|-\d+\.bin$)")


def prune(final_app: Path = BASE_DIR / "Final App", keep: int = KEEP, dry_run: bool = False) -> list:
    found = {}
    for item in final_app.iterdir():
        m = _VERSION.match(item.name)
        if m:
            found.setdefault(tuple(int(g) for g in m.groups()), []).append(item)
    removed = []
    for version in sorted(found, reverse=True)[keep:]:
        for item in found[version]:
            removed.append(item)
            if not dry_run:
                shutil.rmtree(item) if item.is_dir() else item.unlink()
    return removed


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    gone = prune(dry_run=dry)
    for p in gone:
        print(("would delete " if dry else "deleted ") + str(p))
    print(f"{len(gone)} old item(s) {'found' if dry else 'removed'}; newest {KEEP} versions kept.")
