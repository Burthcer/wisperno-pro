"""
The hovered pill's two buttons (mic, wand) and the transform menu behind the wand, plus the engine applying
the picked transform to dictation.

Run: python tests/test_pill_menu.py
"""

import os
import sys
import types
from pathlib import Path
from unittest import mock

from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
for p in (BASE_DIR, BASE_DIR / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _hovered_pill(**kwargs):
    from test_pill_interaction import _click, _pill  # noqa: F401  (reuse the existing helpers)

    pill = _pill(**kwargs)
    pill.set_state("idle")
    pill._hover = True
    pill._apply_size_targets()
    pill._width_current, pill._height_current = pill._width_target, pill._height_target
    pill.resize(int(pill._width_current), int(pill._height_current))
    pill.grab()  # paints once, which lays out the two buttons' hit areas
    return pill


def test_hover_shows_mic_and_wand_and_they_work() -> None:
    from test_pill_interaction import _click, _collect
    from src.ui import floating_pill as fp

    logger.info("--- Testing the hovered pill's mic and wand buttons ---")
    resting = _hovered_pill()
    resting._hover = False
    resting._apply_size_targets()
    assert resting._width_target == fp.IDLE_W, "not hovered: the small resting strip"

    pill = _hovered_pill(click_action="none")  # even with "click does nothing" the explicit buttons work
    assert pill.width() == fp.HOVER_W and pill.height() == fp.HOVER_H
    assert not pill._mic_rect.isEmpty() and not pill._wand_rect.isEmpty()
    assert pill._mic_rect.right() < pill._wand_rect.left() and pill._wand_rect.right() <= pill.width()
    got = _collect(pill)
    menu_requests = []
    pill.transform_menu_requested.connect(lambda: menu_requests.append(1))

    _click(pill, pill._mic_rect.center())
    assert got["toggle"] == 1 and not menu_requests, "mic = start dictating"
    _click(pill, pill._wand_rect.center())
    assert menu_requests == [1] and got["toggle"] == 1, "wand = open the transform menu"
    _click(pill, QPointF(pill.width() - 1.0, 1.0))  # a gap: falls back to the 'click does nothing' setting
    assert got["toggle"] == 1 and menu_requests == [1]
    pill.close()
    logger.success("PASS: hover grows the pill to mic + wand; mic dictates, wand opens the menu, gaps obey the click setting.")


def test_menu_rows_do_what_they_say() -> None:
    from PySide6.QtWidgets import QWidgetAction

    from src.ui.pill_menu import _Row, _SwitchRow, build_transform_menu

    logger.info("--- Testing the transform menu ---")
    picked, toggles, configured = [], [], []
    items = [("polish", "Polish"), ("prompt_engineer", "Prompt Engineer"), ("code_fix", "Detailed Code Fix Prompt")]
    menu = build_transform_menu(None, items, "prompt_engineer", False, picked.append, toggles.append, lambda: configured.append(1))
    widgets = [a.defaultWidget() for a in menu.actions() if isinstance(a, QWidgetAction)]
    switch = next(w for w in widgets if isinstance(w, _SwitchRow))
    rows = [w for w in widgets if isinstance(w, _Row)]
    assert [r._text for r in rows] == ["Polish", "Prompt Engineer", "Detailed Code Fix Prompt", "Configure transforms"]
    assert [r._checked for r in rows[:3]] == [False, True, False], "the current transform has the tick"
    assert switch.isChecked() is False

    menu.popup(menu.pos())
    APP.processEvents()
    QTest.mouseClick(switch, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)
    assert toggles == [True] and switch.isChecked() and menu.isVisible(), "the switch flips and the menu stays open"
    QTest.mouseClick(rows[2], __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)
    assert picked == ["code_fix"] and not menu.isVisible(), "picking a transform selects it and closes the menu"

    menu2 = build_transform_menu(None, items, "polish", True, picked.append, toggles.append, lambda: configured.append(1))
    cfg = [a.defaultWidget() for a in menu2.actions() if isinstance(a, QWidgetAction) and isinstance(a.defaultWidget(), _Row)][-1]
    menu2.popup(menu2.pos())
    QTest.mouseClick(cfg, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)
    assert configured == [1] and not menu2.isVisible()
    logger.success("PASS: tick on the current transform; switch stays open; picking and Configure close the menu.")


def test_pill_popup_keeps_itself_expanded_and_collapses_after() -> None:
    logger.info("--- Testing the pill while its menu is open ---")
    pill = _hovered_pill()
    pill.popup_transform_menu([("polish", "Polish")], "polish", True, lambda t: None, lambda b: None, lambda: None)
    assert pill._menu_open
    pill._hover = False  # the mouse moved onto the menu
    pill._apply_size_targets()
    from src.ui import floating_pill as fp
    assert pill._width_target == fp.HOVER_W + fp.WAND_EXTRA, "stays expanded (wand open) under its own menu"
    pill._on_menu_closed()
    assert not pill._menu_open and pill._width_target == fp.IDLE_W
    pill.close()
    logger.success("PASS: expanded while the menu is open, back to the small strip after.")


def _engine_with_transforms():
    from test_pill_interaction import _engine

    engine, states, _ = _engine()
    engine.config.active_transform, engine.config.auto_apply_transform = "polish", True
    engine.db = mock.Mock()
    rows = {"prompt_engineer": {"id": "prompt_engineer", "title": "Prompt Engineer", "system_prompt": "PROMPT!", "is_active": 1},
            "off": {"id": "off", "title": "Off", "system_prompt": "x", "is_active": 0}}
    engine.db.get_transform.side_effect = lambda tid: rows.get(tid)
    engine.db.list_snippets.return_value = []
    engine.transcriber = engine.transformer = engine.injector = object()
    engine._llm_dictation_enabled = lambda: False
    engine.save_config = mock.Mock()
    return engine


def test_engine_applies_the_picked_transform() -> None:
    logger.info("--- Testing the engine applies the transform picked in the menu ---")
    engine = _engine_with_transforms()
    assert engine._auto_apply_transform() is None, "Polish is ordinary dictation"
    engine.set_active_transform("prompt_engineer")
    assert engine.config.active_transform == "prompt_engineer" and engine.save_config.called
    assert engine._auto_apply_transform()["title"] == "Prompt Engineer"
    engine.set_auto_apply_transform(False)
    assert engine._auto_apply_transform() is None, "Auto Apply off: dictation gets the normal cleanup"
    engine.set_auto_apply_transform(True)
    engine.set_active_transform("off")
    assert engine._auto_apply_transform() is None, "a transform you switched off is never applied"
    engine.set_active_transform("deleted-long-ago")
    assert engine._auto_apply_transform() is None, "a transform that no longer exists falls back safely"

    engine.set_active_transform("prompt_engineer")
    captured = {}

    class FakeWorker:
        def __init__(self, *args, **kwargs):
            captured["args"], captured["kwargs"] = args, kwargs
            for name in ("state_changed", "result_ready", "recording_saved", "finished"):
                setattr(self, name, mock.MagicMock())

        def start(self):
            pass

    with mock.patch("src.engine.InferenceWorker", FakeWorker):
        engine._start_dictation_worker([0.1] * 10, 1000.0)
        assert captured["args"][6] == "prompt_engineer"
        assert captured["kwargs"]["system_prompt"] == "PROMPT!" and captured["kwargs"]["status_label"] == "Prompt Engineer"
        assert captured["kwargs"]["use_direct_formatter"] is False, "a transform always goes through the AI"

        engine.set_active_transform("polish")
        engine._start_dictation_worker([0.1] * 10, 1000.0)
        assert captured["args"][6] == "polish" and captured["kwargs"]["system_prompt"] is None
        assert captured["kwargs"]["status_label"] is None
    logger.success("PASS: the picked transform runs on dictation with its own prompt; Polish / Auto Apply off stay ordinary.")


def run_all_tests() -> None:
    test_hover_shows_mic_and_wand_and_they_work()
    test_menu_rows_do_what_they_say()
    test_pill_popup_keeps_itself_expanded_and_collapses_after()
    test_engine_applies_the_picked_transform()
    logger.success("ALL PILL MENU TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
