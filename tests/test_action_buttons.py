"""IconButton: draws every icon kind, flashes a 'Copied!' confirmation and then returns to normal.

Run: python tests/test_action_buttons.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from src.ui.action_buttons import IconButton  # noqa: E402


def main() -> None:
    for kind in ("star", "pin", "copy", "edit", "trash", "retry", "book-plus"):
        b = IconButton(kind, kind)
        b.set_active(True)
        assert not b.grab().isNull()
    b = IconButton("copy", "Copy")
    assert b.width() == 34
    b.flash("Copied!")
    assert b.width() > 60 and b._flash_text == "Copied!"
    assert not b.grab().isNull()
    b._end_flash()
    assert b.width() == 34 and b._flash_text == ""
    print("PASS: icons draw, 'Copied!' flashes and the button returns to its small size.")


if __name__ == "__main__":
    main()
