"""
Per-app styles (src/app_context.py): chat apps drop a one-line message's
final period, editors/terminals also skip the trailing space, everything
else is unchanged - and the Settings table edits the mapping.

Run: python tests/test_app_styles.py
"""

import sys
import types
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def test_style_rules() -> None:
    from src.app_context import apply_app_style, style_for_app, wants_trailing_space, DEFAULT_APP_STYLES

    logger.info("--- Testing the style rules ---")
    cases = [
        ("messaging", "Sounds good, see you at 3.", "Sounds good, see you at 3"),
        ("messaging", "Can you send it over?", "Can you send it over?"),
        ("messaging", "Great work!", "Great work!"),
        ("messaging", "Done. Shipping it now.", "Done. Shipping it now."),               # two sentences: untouched
        ("messaging", "We need:\n1. Milk.\n2. Eggs.", "We need:\n1. Milk.\n2. Eggs."),   # list: untouched
        ("messaging", "I moved to the U.S.", "I moved to the U.S."),                     # abbreviation keeps its period
        ("messaging", "Well...", "Well..."),
        ("code", "Run git status.", "Run git status"),
        ("default", "Sounds good, see you at 3.", "Sounds good, see you at 3."),
    ]
    for style, text, want in cases:
        assert apply_app_style(text, style) == want, (style, text, apply_app_style(text, style))
    assert style_for_app("Slack.exe", DEFAULT_APP_STYLES) == "messaging"
    assert style_for_app("Code.exe", DEFAULT_APP_STYLES) == "code"
    assert style_for_app("winword.exe", DEFAULT_APP_STYLES) == "default"
    assert style_for_app(None, DEFAULT_APP_STYLES) == "default"
    assert not wants_trailing_space("code") and wants_trailing_space("messaging")
    logger.success("PASS: only a one-line sentence's final period changes; ?/!, lists, abbreviations kept.")


def _paste(raw, app, app_styles, snippets=None):
    from src.app_context import DEFAULT_APP_STYLES  # noqa: F401
    from src.workers import InferenceWorker

    transcriber = mock.Mock(); transcriber.transcribe.return_value = raw
    injector = mock.Mock(); injector.inject_text.return_value = True
    db = mock.Mock()
    worker = InferenceWorker([0.0], transcriber, mock.Mock(profanity_filter="allow"), injector, db, snippets or {},
                             "polish", 500.0, use_direct_formatter=True, trailing_space=True, app_styles=app_styles)
    with mock.patch("src.workers.foreground_app", return_value=app):
        worker.run()
    return injector.inject_text.call_args[0][0], db.add_history.call_args.kwargs["polished_transcript"]


def test_dictation_worker_applies_the_app_style() -> None:
    from src.app_context import DEFAULT_APP_STYLES

    logger.info("--- Testing the dictation worker per foreground app ---")
    styles = dict(DEFAULT_APP_STYLES)
    assert _paste("sounds good see you at 3", "slack.exe", styles) == ("Sounds good see you at 3", "Sounds good see you at 3")
    assert _paste("run the tests again", "code.exe", styles)[0] == "Run the tests again"
    assert _paste("sounds good see you at 3", "winword.exe", styles)[0] == "Sounds good see you at 3. "
    assert _paste("sounds good see you at 3", "slack.exe", None)[0] == "Sounds good see you at 3. "  # feature off
    pasted, _ = _paste("my email", "slack.exe", styles, snippets={"my email": "me@example.com."})
    assert pasted == "me@example.com. ", pasted  # snippets are pasted exactly as written
    logger.success("PASS: Slack -> no period; VS Code -> no period, no space; Word -> normal; off -> normal.")


def test_settings_table_edits_the_mapping() -> None:
    sys.modules.setdefault("winreg", mock.MagicMock())
    sys.modules.setdefault("src.autostart", mock.MagicMock())
    from PySide6.QtWidgets import QApplication
    from src.config import AppConfig
    from src.engine import WispernoEngine
    from src.ui.settings_tab import SettingsTab

    logger.info("--- Testing the Per-App Styles settings table ---")
    app = QApplication.instance() or QApplication([])  # noqa: F841
    engine = mock.MagicMock()
    engine.config = AppConfig()
    engine.transcriber = engine.transformer = None
    for name in ("set_app_style", "set_app_styles_enabled"):
        setattr(engine, name, types.MethodType(getattr(WispernoEngine, name), engine))
    tab = SettingsTab(engine, mock.MagicMock())
    general = tab.general_tab
    rows = general.app_styles_table.rowCount()
    assert rows == len(engine.config.app_styles) > 20

    general.app_name_in.setText("Obsidian")
    general.app_style_in.setCurrentIndex(1)  # messaging
    general._add_app_style()
    assert engine.config.app_styles["obsidian.exe"] == "messaging"
    assert general.app_styles_table.rowCount() == rows + 1

    general._remove_app_style("obsidian.exe")
    assert "obsidian.exe" not in engine.config.app_styles

    general.app_styles_cb.setChecked(False)
    assert engine.config.app_styles_enabled is False and not general.app_styles_table.isEnabled()
    general.app_styles_cb.setChecked(True)

    SCREENSHOT_DIR.mkdir(exist_ok=True)
    general.resize(760, 1900)
    general.grab().save(str(SCREENSHOT_DIR / "settings_general.png"))
    tab.close()
    logger.success("PASS: add / change / remove / disable all update the config.")


def run_all_tests() -> None:
    test_style_rules()
    test_dictation_worker_applies_the_app_style()
    test_settings_table_edits_the_mapping()
    logger.success("ALL APP STYLE TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
