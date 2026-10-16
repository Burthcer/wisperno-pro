"""
The app logo can never be blank: if the .ico is missing or corrupt, it is drawn in code instead.

Run: python tests/test_icon_fallback.py
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _is_orange(icon) -> bool:
    image = icon.pixmap(64, 64).toImage()
    r, g, b, _ = image.pixelColor(32, 8).getRgb()  # top-middle of the tile, above the waveform
    return r > 200 and 40 < g < 160 and b < 90


def test_logo_never_blank() -> None:
    from PySide6.QtWidgets import QApplication

    from src.ui import theme

    app = QApplication.instance() or QApplication([])  # noqa: F841
    real = theme.get_app_icon()
    assert not real.isNull() and _is_orange(real), "the shipped icon is the orange logo"

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        with mock.patch("src.ui.theme.get_base_dir", return_value=tmp):  # no icon file at all
            missing = theme.get_app_icon()
            assert not missing.isNull() and _is_orange(missing), "missing file -> drawn logo"
        (tmp / "assets" / "icons").mkdir(parents=True)
        (tmp / "assets" / "icons" / "wisperno.ico").write_bytes(b"not an icon at all")
        with mock.patch("src.ui.theme.get_base_dir", return_value=tmp):  # corrupt file
            corrupt = theme.get_app_icon()
            assert not corrupt.isNull() and _is_orange(corrupt), "corrupt file -> drawn logo"
    for size in (16, 32, 48, 256):
        assert not theme.fallback_icon().pixmap(size, size).isNull()
    logger.success("PASS: the logo is the orange tile whether the file loads, is missing or is corrupt.")


if __name__ == "__main__":
    test_logo_never_blank()
    logger.success("ALL ICON TESTS PASSED")
