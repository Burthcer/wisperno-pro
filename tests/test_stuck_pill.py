"""
The pill must never be left on "processing": every way a dictation can end tells it so, a dictation
finished while the previous one is still being typed is queued rather than dropped, and an ignored tick
resyncs the pill with the truth.

Run: python tests/test_stuck_pill.py
"""

import os
import sys
import types
from pathlib import Path
from unittest import mock

import numpy as np
from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
for p in (BASE_DIR, BASE_DIR / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _run_worker(transcribe, inject=None):
    """Run an InferenceWorker synchronously; returns the ordered list of everything it announced."""
    from src.workers import InferenceWorker

    transcriber = mock.Mock()
    transcriber.transcribe.side_effect = transcribe
    injector = mock.Mock()
    injector.inject_text.side_effect = inject or (lambda text: True)
    worker = InferenceWorker([0.0], transcriber, mock.Mock(profanity_filter="allow"), injector, mock.Mock(), {}, "polish", 500.0,
                             use_direct_formatter=True)
    events = []
    worker.state_changed.connect(lambda s: events.append(("state", s)))
    worker.result_ready.connect(lambda r: events.append(("result", None)))
    with mock.patch("src.workers.foreground_app", return_value="winword.exe"):
        worker.run()
    return events


def test_every_way_out_ends_with_a_final_state() -> None:
    logger.info("--- Testing the worker always sends a final state ---")
    ok = _run_worker(lambda audio: "hello world this is fine")
    assert [e for e in ok if e[0] == "state"][-1] == ("state", "success")
    assert ok.index(("state", "success")) < ok.index(("result", None)), "pill is told 'done' BEFORE the History redraw"

    silent = _run_worker(lambda audio: "")
    assert silent[-1] == ("state", "idle")

    def boom(audio):
        raise RuntimeError("the speech engine blew up")

    crashed = _run_worker(boom)
    assert crashed[-1] == ("state", "idle"), crashed

    not_typed = _run_worker(lambda audio: "hello there friend", inject=lambda text: False)
    assert [e for e in not_typed if e[0] == "state"][-1] == ("state", "idle")

    def inject_explodes(text):
        raise OSError("target window vanished")

    exploded = _run_worker(lambda audio: "hello there friend", inject=inject_explodes)
    assert exploded[-1] == ("state", "idle"), exploded
    logger.success("PASS: success, silence, a crash, a failed paste and an exploding paste all clear the pill.")


def test_a_dictation_finished_while_busy_is_queued_not_dropped() -> None:
    from test_pill_interaction import _engine

    logger.info("--- Testing the dictation queue ---")
    engine, states, _ = _engine()
    started = []
    engine._start_dictation_worker = lambda audio, ms: (started.append((len(audio), ms)), setattr(engine, "_processing", True))
    audio = np.ones(16000, dtype=np.float32)
    engine.audio_worker.stop_recording.side_effect = lambda: audio
    engine.audio_worker.recorder.last_duration_seconds = 1.0

    engine._processing = True  # the previous dictation is still being typed
    engine._finish_ptt_release()
    assert started == [] and len(engine._dictation_queue()) == 1, "queued, not dropped"
    assert states[-1] == "processing", "and the pill shows busy, not a stranded waveform"

    engine._on_inference_finished()  # previous one done -> the queued one starts by itself
    assert started == [(16000, 1000.0)] and engine._dictation_queue() == []

    engine._on_inference_finished()  # nothing left: just frees the pipeline
    assert engine._processing is False
    logger.success("PASS: the second dictation waits its turn instead of being thrown away.")


def test_an_ignored_tick_resyncs_the_pill() -> None:
    from test_pill_interaction import _engine

    logger.info("--- Testing a tick the engine can't act on ---")
    engine, states, _ = _engine()
    engine.audio_worker.recorder.is_recording = False  # the pill thinks it's recording; nothing is
    engine.pill_finish_dictation()
    assert states[-1] == "idle", states
    engine._processing = True
    engine.pill_finish_dictation()
    assert states[-1] == "processing", "still working on a previous one: say so"
    logger.success("PASS: an ignored tick tells the pill the truth instead of leaving it on screen.")


def test_history_redraw_is_deferred_while_hidden() -> None:
    from PySide6.QtCore import QObject, Signal

    logger.info("--- Testing the History tab doesn't redraw while hidden ---")

    class FakeEngine(QObject):
        retranscribed = Signal(dict)
        retranscribe_failed = Signal(str)

    from src.ui.history_tab import HistoryTab

    engine = FakeEngine()
    engine.db = mock.Mock()
    engine.db.get_stats.return_value = {"total_words": 0, "hours_saved": 0.0, "avg_wpm": 0.0, "total_dictations": 0}
    engine.db.list_history.return_value = []
    tab = HistoryTab(engine)
    calls = engine.db.list_history.call_count
    tab.refresh_when_visible()  # hidden: only marks dirty
    assert engine.db.list_history.call_count == calls and tab._dirty
    tab.show()  # becoming visible does the redraw
    APP.processEvents()
    assert engine.db.list_history.call_count == calls + 1 and not tab._dirty
    tab.refresh_when_visible()  # visible: redraws immediately
    assert engine.db.list_history.call_count == calls + 2
    tab.close()
    logger.success("PASS: no GUI-thread redraw while the dashboard is closed; it catches up when opened.")


def run_all_tests() -> None:
    test_every_way_out_ends_with_a_final_state()
    test_a_dictation_finished_while_busy_is_queued_not_dropped()
    test_an_ignored_tick_resyncs_the_pill()
    test_history_redraw_is_deferred_while_hidden()
    logger.success("ALL STUCK-PILL TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
