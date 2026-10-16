"""
Automatic topic paragraphs for long dictation: only long text is touched, breaks land where the
topic changes, no word is ever changed or lost, lists/short text/other apps are left alone.

Run: python tests/test_paragraphing.py
"""

import os
import re
import sys
import types
from pathlib import Path
from unittest import mock

from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

# A real-style wall of text: sound settings, then GPU memory, then disk space.
WALL = (
    "The startup sound is still not right for me. The chime sounds harsh and the old beep was worse. "
    "I would like a softer sound for starting and stopping, and I want to pick it myself in the settings. "
    "It should also let me drop in my own short sound file so I am not stuck with the built in ones. "
    "Also, the graphics memory number does not match what task manager shows for the graphics card. "
    "Task manager says three point three gigabytes while the app says three point five gigabytes. "
    "That mismatch makes me distrust the memory gauge, so it should show the same number as task manager. "
    "Finally, the disk space card should say which files can be deleted and which cannot. "
    "The application files and the model files are part of the installation and should not be deletable. "
    "The history and the saved recordings can be deleted, so those should have a delete button."
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_splits_a_wall_at_topic_changes_without_changing_a_word() -> None:
    logger.info("--- Testing the splitter on a long single-block dictation ---")
    from src.paragraphing import MAX_PARAGRAPH_WORDS, split_into_paragraphs

    out = split_into_paragraphs(WALL)
    paragraphs = out.split("\n\n")
    assert len(paragraphs) >= 2, "a long block with several topics should be split"
    assert _norm(out) == _norm(WALL), "not a single word may be added, dropped or changed"
    assert all(len(p.split()) <= MAX_PARAGRAPH_WORDS for p in paragraphs)
    assert any(p.startswith("Also, the graphics memory") for p in paragraphs), "a transition word starts a new paragraph"
    assert any(p.startswith("Finally,") for p in paragraphs)
    logger.success(f"PASS: {len(paragraphs)} paragraphs, text identical apart from the breaks.")


def test_leaves_short_text_lists_and_existing_paragraphs_alone() -> None:
    from src.paragraphing import split_into_paragraphs

    logger.info("--- Testing what must NOT be touched ---")
    short = "This is a short note. It has two sentences."
    assert split_into_paragraphs(short) == short and split_into_paragraphs("") == ""
    listed = "Here is the plan:\n\n1. Build the app.\n2. Test the app.\n3. Ship the app.\n" + WALL
    assert "1. Build the app." in split_into_paragraphs(listed)
    assert split_into_paragraphs(listed).count("1. Build") == 1
    already = "First paragraph of normal length here.\n\n" + "Second paragraph is also fairly short and sweet."
    assert split_into_paragraphs(already) == already
    abbreviations = ("We met Dr. Patel, i.e. the new lead, at ten. " * 3 + "Then we reviewed the numbers together. ") * 2
    for paragraph in split_into_paragraphs(abbreviations).split("\n\n"):
        assert not paragraph.endswith(("Dr.", "i.e.")), "an abbreviation must not end a paragraph"
    logger.success("PASS: short text, lists, existing paragraphs and abbreviations are respected.")


def test_a_single_topic_still_gets_broken_before_it_becomes_a_wall() -> None:
    from src.paragraphing import MAX_PARAGRAPH_WORDS, split_into_paragraphs

    one_topic = " ".join(f"The report covers the quarterly numbers for team {i} and the budget plan." for i in range(30))
    out = split_into_paragraphs(one_topic)
    assert _norm(out) == _norm(one_topic)
    assert all(len(p.split()) <= MAX_PARAGRAPH_WORDS + 20 for p in out.split("\n\n"))
    assert len(out.split("\n\n")) >= 3
    logger.success("PASS: even one long topic is cut into readable chunks.")


def _run_worker(raw: str, app: str, mode: str, *, auto: bool, system_prompt=None, app_styles=None) -> str:
    from src.workers import InferenceWorker

    transcriber = mock.Mock(); transcriber.transcribe.return_value = raw
    injector = mock.Mock(); injector.inject_text.return_value = True
    transformer = mock.Mock(profanity_filter="allow")
    transformer.transform.side_effect = lambda text, mode="polish": text
    transformer.transform_with_prompt.side_effect = lambda text, prompt, label=None: text
    worker = InferenceWorker([0.0], transcriber, transformer, injector, mock.Mock(), {}, mode, 500.0,
                             system_prompt=system_prompt, use_direct_formatter=True, app_styles=app_styles, auto_paragraphs=auto)
    with mock.patch("src.workers.foreground_app", return_value=app):
        worker.run()
    return injector.inject_text.call_args[0][0]


def test_worker_only_splits_for_plain_dictation_in_normal_apps() -> None:
    from src.app_context import DEFAULT_APP_STYLES

    logger.info("--- Testing where the worker applies it ---")
    raw = WALL.lower()
    styles = dict(DEFAULT_APP_STYLES)
    assert "\n\n" in _run_worker(raw, "winword.exe", "polish", auto=True, app_styles=styles), "normal app: split"
    assert "\n\n" not in _run_worker(raw, "winword.exe", "polish", auto=False, app_styles=styles), "setting off: untouched"
    assert "\n\n" not in _run_worker(raw, "slack.exe", "polish", auto=True, app_styles=styles), "chat app: untouched"
    assert "\n\n" not in _run_worker(raw, "windowsterminal.exe", "polish", auto=True, app_styles=styles), "terminal: untouched"
    assert "\n\n" not in _run_worker(raw, "winword.exe", "prompt_engineer", auto=True, app_styles=styles), "other modes: untouched"
    assert "\n\n" not in _run_worker(raw, "winword.exe", "polish", auto=True, system_prompt="x", app_styles=styles), "custom transform: untouched"
    logger.success("PASS: split only for plain Polish dictation into a normal writing app, and only when enabled.")


def run_all_tests() -> None:
    test_splits_a_wall_at_topic_changes_without_changing_a_word()
    test_leaves_short_text_lists_and_existing_paragraphs_alone()
    test_a_single_topic_still_gets_broken_before_it_becomes_a_wall()
    test_worker_only_splits_for_plain_dictation_in_normal_apps()
    logger.success("ALL PARAGRAPHING TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
