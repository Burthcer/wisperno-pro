"""
The "no text box found" card and the worker rule that raises it.

Run: python tests/test_paste_card.py
"""

import os
import sys
from pathlib import Path
from unittest import mock

from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


def test_card_copies_and_shows() -> None:
    from src.ui.paste_card import PasteCard

    card = PasteCard()
    card.show_for("Hello there, this is the dictated text.", QPoint(600, 700))
    assert card.isVisible() and not card._copied, "showing the card copies nothing by itself"
    APP.clipboard().setText("something else")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card._copy_rect.center().toPoint())
    assert card._copied and APP.clipboard().text() == "Hello there, this is the dictated text."
    card.grab()  # paints once without error
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=card._close_rect.center().toPoint())
    assert not card.isVisible(), "the close button just closes it"
    logger.success("PASS: Copy copies, close closes, nothing is copied until you choose.")


def test_focus_check_fails_open() -> None:
    from src import focus_check

    with mock.patch.object(focus_check, "_inspect_focus", side_effect=RuntimeError("no UIA")):
        assert focus_check.has_text_target() is True, "any doubt = assume a text box (no card)"
    with mock.patch.object(focus_check, "_inspect_focus", return_value=False):
        assert focus_check.has_text_target() is False
    logger.success("PASS: the check only says 'no text box' when it is sure.")


def test_detection_rules() -> None:
    from src.focus_check import is_text_target

    assert is_text_target(50004, False, False) is True, "Edit"
    assert is_text_target(50030, False, False) is True, "Document"
    assert is_text_target(50026, False, False) is True, "Group (web chat box): unknown means text box"
    assert is_text_target(50033, False, False, "chrome.exe") is True, "a pane in a normal program may be an editor"
    assert is_text_target(50033, False, False, "terminal.exe") is True
    assert is_text_target(50000, True, False) is True, "anything with a text/value pattern is a text box"
    assert is_text_target(50000, False, False) is False, "Button"
    assert is_text_target(50008, False, False) is False, "List"
    assert is_text_target(50033, False, False, "explorer.exe") is False, "the desktop / taskbar"
    # measured in Edge: a focused <input> vs a page body (read-only value = the address)
    assert is_text_target(50004, True, True, "msedge.exe", value_read_only=False) is True, "web input"
    assert is_text_target(50030, True, True, "msedge.exe", value_read_only=True) is False, "page with nothing focused"
    assert is_text_target(50030, True, False, "winword.exe") is True, "a Word document (no value pattern)"
    logger.success("PASS: only definite non-text elements raise the card.")


def test_worker_raises_card_only_without_target() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.modules.setdefault("llama_cpp", __import__("types").SimpleNamespace(Llama=object))
    from src.workers import InferenceWorker

    def run(has_target: bool):
        transcriber = mock.Mock()
        transcriber.transcribe.return_value = "send the report to the team today"
        worker = InferenceWorker([0.0], transcriber, mock.Mock(profanity_filter="allow"), mock.Mock(inject_text=lambda t: True),
                                 mock.Mock(), {}, "polish", 500.0, use_direct_formatter=True)
        missed = []
        worker.paste_missed.connect(missed.append)
        with mock.patch("src.workers.foreground_app", return_value="winword.exe"),                 mock.patch("src.workers.has_text_target", return_value=has_target):
            worker.run()
        return missed

    assert run(True) == [], "a text box had focus: no card"
    assert run(False) == ["Send the report to the team today."], "no text box: the card gets the text"
    logger.success("PASS: the card is raised only when there was no text box.")


if __name__ == "__main__":
    test_card_copies_and_shows()
    test_focus_check_fails_open()
    test_detection_rules()
    test_worker_raises_card_only_without_target()
    logger.success("ALL PASTE CARD TESTS PASSED")
