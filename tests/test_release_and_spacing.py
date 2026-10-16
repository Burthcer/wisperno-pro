"""
End-of-dictation behavior (src/engine.py, src/workers.py), with a real Qt
event loop and stand-in audio/models:
  - the mic stays open config.audio.post_roll_ms after key release (the last
    word isn't cut off) without blocking the UI thread
  - a second release or a new press inside that window is ignored
  - the stop beep plays after the mic has closed, so it isn't recorded
  - a dictated sentence is typed with a trailing space; lists are not

Run: python tests/test_release_and_spacing.py
"""

import sys
import time
import types
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))

from PySide6.QtCore import QCoreApplication, QObject  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])


def _engine(post_roll_ms: int):
    from src.config import AppConfig
    from src.engine import WispernoEngine

    engine = WispernoEngine.__new__(WispernoEngine)
    QObject.__init__(engine)
    engine.config = AppConfig()
    engine.config.audio.post_roll_ms = post_roll_ms
    engine.config.audio_cues_enabled = True
    engine._engines_ready, engine._processing, engine._live_worker = True, False, None
    engine._active_transform_id = None
    engine.audio_worker = mock.Mock()
    engine.audio_worker.recorder.is_recording = True
    engine.audio_worker.recorder.last_duration_seconds = 0.0
    engine.audio_worker.stop_recording.return_value = None  # "nothing usable" -> engine goes idle
    engine.hotkey_worker = None
    return engine


def _pump(ms: int) -> None:
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.005)


def test_post_roll_keeps_recording_then_stops() -> None:
    logger.info("--- Testing post-roll: mic stays open briefly after release, UI not blocked ---")
    engine = _engine(200)
    order = mock.Mock()
    engine.audio_worker.stop_recording.side_effect = lambda: (order.stop(), None)[1]  # records the call, returns "no audio"
    with mock.patch("src.engine.audio_cues") as cues:
        cues.play_stop_cue.side_effect = lambda *args: order.beep()
        t0 = time.perf_counter()
        engine._on_ptt_release()
        returned_after_ms = (time.perf_counter() - t0) * 1000
        assert returned_after_ms < 50, f"release blocked the UI thread for {returned_after_ms:.0f}ms"
        assert not engine.audio_worker.stop_recording.called, "stopped before the post-roll"

        engine._on_ptt_release()          # second release (e.g. auto-silence) inside the window
        engine._on_ptt_press()            # new press inside the window
        assert not engine.audio_worker.start_recording.called

        _pump(120)
        assert not engine.audio_worker.stop_recording.called, "stopped too early"
        _pump(200)
    assert engine.audio_worker.stop_recording.call_count == 1, "double release ran the stop twice"
    assert [c[0] for c in order.mock_calls] == ["stop", "beep"], order.mock_calls
    assert not engine._is_releasing()
    logger.success(f"PASS: returned in {returned_after_ms:.0f}ms, stopped once after ~200ms, beep after mic closed.")


def test_post_roll_zero_stops_immediately() -> None:
    logger.info("--- Testing post_roll_ms=0 stops synchronously ---")
    engine = _engine(0)
    with mock.patch("src.engine.audio_cues"):
        engine._on_ptt_release()
    assert engine.audio_worker.stop_recording.call_count == 1
    logger.success("PASS: post-roll disabled -> immediate stop.")


def test_transform_release_uses_post_roll_too() -> None:
    logger.info("--- Testing transform hotkeys (Alt+C, ...) get the same post-roll ---")
    engine = _engine(150)
    engine.db = mock.Mock()
    engine.db.get_transform.return_value = None  # transform deleted -> engine just goes idle
    with mock.patch("src.engine.audio_cues"):
        engine._on_transform_release("polish")
        assert not engine.audio_worker.stop_recording.called
        _pump(250)
    assert engine.audio_worker.stop_recording.call_count == 1
    logger.success("PASS: transform release also waits for the post-roll.")


def test_trailing_space() -> None:
    from src.workers import InferenceWorker, with_trailing_space

    logger.info("--- Testing the trailing space after a dictated sentence ---")
    assert with_trailing_space("Sounds good.") == "Sounds good. "
    assert with_trailing_space("Really?") == "Really? "
    assert with_trailing_space("1. Buy milk.\n2. Get eggs.") == "1. Buy milk.\n2. Get eggs."
    assert with_trailing_space("/compact") == "/compact"

    transcriber = mock.Mock(); transcriber.transcribe.return_value = "sounds good"
    injector = mock.Mock(); injector.inject_text.return_value = True
    db = mock.Mock()
    worker = InferenceWorker([0.0], transcriber, mock.Mock(profanity_filter="allow"), injector, db, {}, "polish",
                             500.0, use_direct_formatter=True, trailing_space=True)
    worker.run()
    assert injector.inject_text.call_args[0][0] == "Sounds good. "
    assert db.add_history.call_args.kwargs["polished_transcript"] == "Sounds good.", "history keeps the clean text"
    logger.success("PASS: sentences typed with a trailing space; lists/commands untouched; history unchanged.")


def run_all_tests() -> None:
    test_post_roll_keeps_recording_then_stops()
    test_post_roll_zero_stops_immediately()
    test_transform_release_uses_post_roll_too()
    test_trailing_space()
    logger.success("ALL RELEASE / SPACING TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
