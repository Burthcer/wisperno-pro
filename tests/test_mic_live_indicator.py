"""
"Mic is live" indicator: the pill shows "Opening mic..." on key press and
only switches to "Listening..." once real audio arrives from the device; a
mic that fails to open or never delivers audio cancels the dictation with a
visible "Microphone didn't start". The mic is only open while recording.

Runs with a real Qt event loop and a stand-in audio device.

Run: python tests/test_mic_live_indicator.py
"""

import sys
import time
import types
from pathlib import Path
from unittest import mock

import numpy as np
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QObject  # noqa: E402

APP = QApplication.instance() or QApplication([])
SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


class FakeStream:
    """Stands in for sounddevice.InputStream; the test decides when audio 'arrives'."""
    last = None

    def __init__(self, callback=None, **kwargs):
        self.callback, self.started, self.closed = callback, False, False
        FakeStream.last = self

    def start(self):
        self.started = True

    def stop(self):
        pass

    def close(self):
        self.closed = True

    def deliver(self, n=1024):
        self.callback(np.zeros((n, 1), dtype=np.float32), n, None, None)


def _recorder(started_callback):
    import src.audio_recorder as ar

    fake_sd = types.SimpleNamespace(
        default=types.SimpleNamespace(device=[0, 0]),
        query_devices=lambda *a, **k: {"max_input_channels": 1, "default_samplerate": 16000, "name": "Fake mic"},
        InputStream=FakeStream, CallbackFlags=object,
    )
    with mock.patch.object(ar, "sd", fake_sd):
        return ar.AudioRecorder(started_callback=started_callback), fake_sd


def test_recorder_reports_first_audio_once_per_recording() -> None:
    import src.audio_recorder as ar

    logger.info("--- Testing AudioRecorder fires 'mic live' on the first audio block only ---")
    fired = []
    recorder, fake_sd = _recorder(lambda: fired.append(time.perf_counter()))
    with mock.patch.object(ar, "sd", fake_sd):
        recorder.start_recording()
        assert not recorder.mic_live and fired == []   # stream open, no audio yet
        FakeStream.last.deliver()
        FakeStream.last.deliver()
        assert recorder.mic_live and len(fired) == 1
        recorder.stop_recording()
        assert FakeStream.last.closed, "mic must be released when recording stops"
        recorder.start_recording()                      # next dictation starts "not live" again
        assert not recorder.mic_live
        FakeStream.last.deliver()
        assert len(fired) == 2
        recorder.stop_recording()
    logger.success("PASS: one 'live' event per recording; stream closed on stop.")


def _engine():
    from src.config import AppConfig
    from src.engine import WispernoEngine

    engine = WispernoEngine.__new__(WispernoEngine)
    QObject.__init__(engine)
    engine.config = AppConfig()
    engine.config.audio_cues_enabled = False
    engine._engines_ready, engine._processing, engine._live_worker = True, False, None
    engine._active_transform_id = None
    engine.active_mode = "polish"
    engine.audio_worker = mock.Mock()
    engine.audio_worker.start_recording.return_value = True
    engine.audio_worker.recorder.is_recording = True
    engine.audio_worker.recorder.mic_live = False
    engine.hotkey_worker = mock.Mock()
    states = []
    engine.state_changed.connect(states.append)
    return engine, states


def _pump(ms):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        APP.processEvents()
        time.sleep(0.005)


def test_pill_goes_live_only_when_audio_arrives() -> None:
    logger.info("--- Testing 'Opening mic...' -> 'Listening...' on first audio ---")
    engine, states = _engine()
    engine._on_ptt_press()
    assert states == ["mic_starting:DIRECT"], states
    engine.audio_worker.recorder.mic_live = True
    engine._on_mic_live()
    assert states[-1] == "recording:DIRECT", states
    _pump(50)
    logger.success(f"PASS: states {states}")


def test_transform_hotkey_uses_the_same_indicator() -> None:
    logger.info("--- Testing transform hotkeys (Alt+C...) show the same cue ---")
    engine, states = _engine()
    engine._on_transform_press("polish")
    engine._on_mic_live()
    assert states == ["mic_starting", "recording"], states
    logger.success(f"PASS: states {states}")


def test_late_audio_after_release_does_not_reopen_listening() -> None:
    logger.info("--- Testing a quick tap: no 'Listening...' after the key is already up ---")
    engine, states = _engine()
    engine._on_ptt_press()
    engine.audio_worker.recorder.is_recording = False  # released and stopped before any audio arrived
    engine._on_mic_live()
    assert "recording:DIRECT" not in states, states
    logger.success("PASS: a late 'live' signal after stop is ignored.")


def test_mic_that_never_delivers_audio_is_cancelled_visibly() -> None:
    import src.engine as engine_mod

    logger.info("--- Testing a silent/broken mic is cancelled with 'Microphone didn't start' ---")
    engine, states = _engine()
    with mock.patch.object(engine_mod, "MIC_START_TIMEOUT_MS", 100):
        engine._on_ptt_press()
        _pump(250)
    assert states[-1] == "mic_error", states
    engine.audio_worker.stop_recording.assert_called_once()
    engine.hotkey_worker.manager.force_stop_active_recording.assert_called_once()

    engine, states = _engine()
    with mock.patch.object(engine_mod, "MIC_START_TIMEOUT_MS", 100):
        engine._on_ptt_press()
        engine.audio_worker.recorder.mic_live = True       # audio arrived in time
        engine._on_mic_live()
        _pump(250)
    assert states[-1] == "recording:DIRECT" and not engine.audio_worker.stop_recording.called, states

    engine, states = _engine()
    engine.audio_worker.start_recording.return_value = False  # device missing / in use
    engine._on_ptt_press()
    assert states == ["mic_starting:DIRECT", "mic_error"], states
    logger.success("PASS: watchdog cancels only a mic that never went live; open failure shown at once.")


def test_pill_renders_every_mic_state() -> None:
    from src.ui.floating_pill import FloatingPill

    logger.info("--- Rendering the pill in each mic state ---")
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    pill = FloatingPill()
    pill.hotkey_label = "CTRL+ALT"
    for state in ("mic_starting:DIRECT", "recording:DIRECT", "mic_error"):
        pill.set_state(state)
        for _ in range(30):  # let the width animation settle
            pill._tick()
        out = SCREENSHOT_DIR / f"pill_{state.split(':')[0]}.png"
        assert pill.grab().save(str(out)), out
    pill.close()
    logger.success(f"PASS: rendered to {SCREENSHOT_DIR}")


def run_all_tests() -> None:
    test_recorder_reports_first_audio_once_per_recording()
    test_pill_goes_live_only_when_audio_arrives()
    test_transform_hotkey_uses_the_same_indicator()
    test_late_audio_after_release_does_not_reopen_listening()
    test_mic_that_never_delivers_audio_is_cancelled_visibly()
    test_pill_renders_every_mic_state()
    logger.success("ALL MIC-LIVE INDICATOR TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
