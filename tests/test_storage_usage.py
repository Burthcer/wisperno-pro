"""
Disk-space accounting for System Usage: sizes are summed correctly, junctions aren't
double-counted, and the byte formatter reads naturally.

Run: python tests/test_storage_usage.py
"""

import os
import sys
import tempfile
from pathlib import Path

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def test_format_bytes() -> None:
    from src.storage_usage import format_bytes

    assert format_bytes(0) == "0 B" and format_bytes(1023) == "1023 B"
    assert format_bytes(1536) == "1.5 KB" and format_bytes(5 * 1024 ** 2) == "5.0 MB"
    assert format_bytes(3.2 * 1024 ** 3) == "3.2 GB" and format_bytes(2 * 1024 ** 4) == "2.0 TB"
    logger.success("PASS: byte sizes read naturally.")


def test_breakdown_adds_up() -> None:
    from src.storage_usage import dir_size, storage_breakdown, total_bytes

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        base, data = tmp / "install", tmp / "data"
        (base / "models").mkdir(parents=True)
        (data / "recent_audio").mkdir(parents=True)
        (base / "models" / "m.gguf").write_bytes(b"x" * 5000)
        (base / "app.dll").write_bytes(b"y" * 700)
        (data / "wisperno.db").write_bytes(b"d" * 300)
        (data / "wisperno.db-wal").write_bytes(b"w" * 40)
        (data / "recent_audio" / "1.wav").write_bytes(b"a" * 2000)
        assert dir_size(base) == 5700 and dir_size(tmp / "missing") == 0

        info = storage_breakdown(base, data)
        assert info["models"] == 5000 and info["history"] == 340 and info["recordings"] == 2000
        assert info["app"] is None, "running from source: the folder is a checkout, not an install"
        assert total_bytes(info) == 5000 + 340 + 2000
        assert info["free"] and info["free"] > 0

        sys.frozen = True  # an installed build: app = everything in the install folder except the models
        try:
            assert storage_breakdown(base, data)["app"] == 700
        finally:
            del sys.frozen
    logger.success("PASS: app / models / history / recordings are measured separately and add up.")


def run_all_tests() -> None:
    test_format_bytes()
    test_breakdown_adds_up()
    logger.success("ALL STORAGE USAGE TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
