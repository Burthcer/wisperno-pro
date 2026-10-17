"""
Run every tests/test_*.py in its own process against a THROWAWAY %APPDATA%.

Several tests open the real wisperno.db (src.config.get_db_path follows %APPDATA%). Run against your real folder
while the app is open and they can corrupt your history, so always use this runner for the whole suite.

Run: python tests/run_all.py [name_substring]
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    sandbox = Path(tempfile.mkdtemp(prefix="wisperno-test-")) / "AppData"  # path keeps "AppData" for tests that check it
    sandbox.mkdir(parents=True)
    env = {**os.environ, "APPDATA": str(sandbox)}
    failed = []
    files = sorted(p for p in HERE.glob("test_*.py") if only in p.name)
    for path in files:
        result = subprocess.run([sys.executable, str(path)], env=env, capture_output=True, text=True)
        if result.returncode != 0:
            failed.append(path.stem)
            print(f"FAIL {path.stem}")
    print(f"files: {len(files)} failures: {len(failed)} {' '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
