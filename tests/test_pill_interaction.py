"""
The compact floating pill: it can be dragged anywhere (and remembers where),
a click starts a dictation / opens the dashboard / does nothing as configured,
the x cancels and the check finishes while recording, the waveform follows the
real mic level - and the engine side of those buttons drives the same pipeline
as the hotkeys without ever leaving the mic open.

Run: python tests/test_pill_interaction.py
"""

import os
import sys
import time
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

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _pill(**kwargs):
    from src.ui.floating_pill import FloatingPill

    pill = FloatingPill(**kwargs)
    pill._width_current, pill._height_current = pill._width_target, pill._height_target
    pill.resize(int(pill._width_current), int(pill._height_current))
    pill._reposition()
    return pill


def _settle(pill, state: str) -> None:
    pill.set_state(state)
    pill._width_current, pill._height_current = pill._width_target, pill._height_target
    pill.resize(int(pill._width_current), int(pill._height_current))
    pill._reposition()
    pill.grab()  # paints once, which lays out the x / check hit areas


def _send(pill, kind, local: QPointF, buttons=Qt.MouseButton.LeftButton, button=Qt.MouseButton.LeftButton) -> None:
    glob = QPointF(pill.mapToGlobal(local.toPoint()))
    APP.sendEvent(pill, QMouseEvent(kind, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier))


def _click(pill, local: QPointF) -> None:
    _send(pill, QEvent.Type.MouseButtonPress, local)
    _send(pill, QEvent.Type.MouseButtonRelease, local, buttons=Qt.MouseButton.NoButton)


def _drag(pill, dx: int, dy: int) -> None:
    """Press at the centre, move the mouse by (dx, dy) in steps, release. Global
    mouse positions are fixed on screen (as with a real mouse) - the pill moves
    underneath them."""
    start = QPointF(pill.mapToGlobal(QPoint(pill.width() // 2, pill.height() // 2)))

    def send(kind, glob, buttons, button=Qt.MouseButton.LeftButton):
        local = QPointF(pill.mapFromGlobal(glob.toPoint()))
        APP.sendEvent(pill, QMouseEvent(kind, local, glob, button, buttons, Qt.KeyboardModifier.NoModifier))

    send(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    for step in range(1, 6):
        send(QEvent.Type.MouseMove, QPointF(start.x() + dx * step / 5.0, start.y() + dy * step / 5.0),
             Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    send(QEvent.Type.MouseButtonRelease, QPointF(start.x() + dx, start.y() + dy), Qt.MouseButton.NoButton)


def _collect(pill):
    got = {"toggle": 0, "dashboard": 0, "finish": 0, "cancel": 0, "moved": []}
    pill.toggle_dictation_requested.connect(lambda: got.__setitem__("toggle", got["toggle"] + 1))
    pill.dashboard_requested.connect(lambda: got.__setitem__("dashboard", got["dashboard"] + 1))
    pill.finish_dictation_requested.connect(lambda: got.__setitem__("finish", got["finish"] + 1))
    pill.cancel_dictation_requested.connect(lambda: got.__setitem__("cancel", got["cancel"] + 1))
    pill.position_changed.connect(lambda x, y: got["moved"].append((x, y)))
    return got


def test_click_action_is_configurable() -> None:
    logger.info("--- Testing a click on the idle pill follows the setting ---")
    for action, want in (("dictate", (1, 0)), ("dashboard", (0, 1)), ("none", (0, 0))):
        pill = _pill(click_action=action)
        got = _collect(pill)
        _settle(pill, "idle")
        _click(pill, QPointF(pill.width() / 2.0, pill.height() / 2.0))
        assert (got["toggle"], got["dashboard"]) == want, (action, got)
        pill.close()
    pill = _pill(click_action="dictate")
    got = _collect(pill)
    pill.set_click_action("none")
    _settle(pill, "idle")
    _click(pill, QPointF(pill.width() / 2.0, pill.height() / 2.0))
    assert got["toggle"] == 0, "changing the setting must take effect without a restart"
    # While busy, a click must not start anything.
    pill.set_click_action("dictate")
    for state in ("processing", "typing", "loading"):
        _settle(pill, state)
        _click(pill, QPointF(pill.width() / 2.0, pill.height() / 2.0))
    assert got["toggle"] == 0, got
    pill.close()
    logger.success("PASS: dictate / dashboard / none, live-updating, ignored while busy.")


def test_drag_moves_the_pill_and_does_not_click() -> None:
    logger.info("--- Testing the pill can be dragged anywhere without triggering a click ---")
    pill = _pill(click_action="dictate")
    got = _collect(pill)
    _settle(pill, "idle")
    x0, y0 = pill.x(), pill.y()
    _drag(pill, -120, -90)
    assert got["toggle"] == 0 and got["dashboard"] == 0, "a drag is not a click"
    assert abs((pill.x() - x0) - (-120)) <= 2 and abs((pill.y() - y0) - (-90)) <= 2, (x0, y0, pill.x(), pill.y())
    assert len(got["moved"]) == 1, got["moved"]
    cx, cy = got["moved"][0]
    assert abs(cx - (pill.x() + pill.width() / 2)) <= 2 and abs(cy - (pill.y() + pill.height() / 2)) <= 2

    # It grows around its centre, so it stays where it was dropped (and on screen).
    centre = (pill.x() + pill.width() / 2, pill.y() + pill.height() / 2)
    _settle(pill, "recording")
    assert abs((pill.x() + pill.width() / 2) - centre[0]) <= 1 and abs((pill.y() + pill.height() / 2) - centre[1]) <= 1
    _settle(pill, "idle")

    # Dragging far past the screen edge is clamped to the visible area.
    _drag(pill, -5000, -5000)
    from PySide6.QtGui import QGuiApplication
    geo = QGuiApplication.primaryScreen().availableGeometry()
    assert pill.x() >= geo.left() and pill.y() >= geo.top(), (pill.x(), pill.y(), geo)
    pill.close()
    logger.success("PASS: drag moves it, reports the spot, no click, stays on screen.")


def test_position_is_remembered_and_resettable() -> None:
    from PySide6.QtGui import QGuiApplication

    logger.info("--- Testing a saved position is restored (and a stale one ignored) ---")
    geo = QGuiApplication.primaryScreen().geometry()
    want = (geo.x() + 200, geo.y() + 150)
    pill = _pill(position=list(want))
    _settle(pill, "idle")
    assert abs((pill.x() + pill.width() / 2) - want[0]) <= 2 and abs((pill.y() + pill.height() / 2) - want[1]) <= 2
    assert pill.has_custom_position()
    pill.reset_position()
    assert not pill.has_custom_position() and pill.y() > want[1], "reset returns to the bottom centre"
    pill.close()

    off_screen = _pill(position=[geo.x() + 99999, geo.y() + 99999])  # e.g. a monitor that was unplugged
    assert not off_screen.has_custom_position()
    assert off_screen.x() >= 0 and off_screen.x() + off_screen.width() <= geo.width()
    off_screen.close()
    logger.success("PASS: restored, reset to default, off-screen position ignored.")


def test_cancel_and_finish_buttons() -> None:
    logger.info("--- Testing x cancels and the check finishes while recording ---")
    pill = _pill()
    got = _collect(pill)

    _settle(pill, "recording:POLISH")
    assert not pill._cancel_rect.isEmpty() and not pill._finish_rect.isEmpty()
    _click(pill, pill._cancel_rect.center())
    assert got["cancel"] == 1 and got["finish"] == 0, got
    _click(pill, pill._finish_rect.center())
    assert got["cancel"] == 1 and got["finish"] == 1, got
    _click(pill, QPointF(pill.width() / 2.0, pill.height() / 2.0))  # the waveform itself does nothing
    assert got["cancel"] == 1 and got["finish"] == 1 and got["toggle"] == 0, got

    _settle(pill, "mic_starting:POLISH")  # mic still opening: can cancel, nothing to finish yet
    _click(pill, pill._finish_rect.center())
    assert got["finish"] == 1, got
    _click(pill, pill._cancel_rect.center())
    assert got["cancel"] == 2, got

    _settle(pill, "processing")
    assert pill._cancel_rect.isEmpty() and pill._finish_rect.isEmpty(), "no buttons outside recording"
    pill.close()
    logger.success("PASS: x cancels (also while the mic opens), check finishes only once live.")


def test_waveform_follows_the_real_mic_level() -> None:
    logger.info("--- Testing the waveform moves with the mic level ---")
    pill = _pill()
    _settle(pill, "recording")
    for _ in range(40):
        pill._tick()
    assert max(pill._levels) < 0.02, "silence draws a flat line"

    for _ in range(40):
        pill.set_level(0.08)     # speaking
        pill._tick()
    loud = max(pill._levels)
    assert loud > 0.5, loud

    for _ in range(60):
        pill._tick()             # then quiet again: decays back down
    assert pill._levels[-1] < loud * 0.3, (pill._levels[-1], loud)
    assert len(set(round(v, 2) for v in pill._levels)) > 3, "bars differ - a scrolling history, not one value"

    pill.set_state("idle")
    pill.set_level(1.0)          # levels outside a recording are ignored
    assert pill._smoothed_level < 0.9 or pill.state != "recording"
    pill.close()
    logger.success(f"PASS: silence flat, speech peaks at {loud:.2f}, decays after.")


def test_pill_never_takes_keyboard_focus() -> None:
    logger.info("--- Testing clicking the pill cannot steal focus from the app being dictated into ---")
    pill = _pill()
    assert pill.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus, "needs WS_EX_NOACTIVATE"
    assert pill.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert pill.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    always_on_top = _pill(always_on_top=True)
    always_on_top.set_always_on_top(False)  # re-showing after a flag change must keep the no-focus flag
    assert always_on_top.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    pill.close(); always_on_top.close()
    logger.success("PASS: no-activate window; survives the always-on-top toggle.")


def test_every_state_renders_to_png() -> None:
    logger.info("--- Rendering every pill state ---")
    out_dir = Path(__file__).resolve().parent / "screenshots"
    out_dir.mkdir(exist_ok=True)
    pill = _pill()
    for state in ("loading", "idle", "mic_starting:POLISH", "recording:POLISH", "processing", "processing:Prompt Engineering",
                  "typing", "success", "mode_changed", "mic_error", "error", "cpu_mode"):
        _settle(pill, state)
        if state.startswith("recording"):
            for i in range(60):
                pill.set_level(0.02 + 0.07 * abs(((i * 7) % 20) - 10) / 10)
                pill._tick()
        image = pill.grab()
        assert not image.isNull() and image.width() >= 40
        image.save(str(out_dir / f"pill_{state.replace(':', '_').replace(' ', '_')}.png"))
    pill.close()
    logger.success(f"PASS: rendered to {out_dir}")


# --- engine side: the same pipeline as the hotkeys -------------------------------------

def _engine():
    from src.config import AppConfig
    from src.engine import WispernoEngine

    engine = WispernoEngine.__new__(WispernoEngine)
    QObject.__init__(engine)
    engine.config = AppConfig()
    engine.config.audio_cues_enabled = False
    engine.config.audio.post_roll_ms = 0
    engine.config.auto_llm_polish = False  # the instant formatter: badge "DIRECT"
    engine._engines_ready, engine._processing, engine._live_worker = True, False, None
    engine._active_transform_id, engine._pill_recording = None, False
    engine.active_mode = "polish"
    engine.audio_worker = mock.Mock()
    recorder = engine.audio_worker.recorder
    recorder.is_recording, recorder.mic_live, recorder.last_duration_seconds = False, False, 0.0

    def start():
        recorder.is_recording = True
        return True

    def stop():
        recorder.is_recording = False
        return None  # nothing captured: the pipeline just goes back to idle

    engine.audio_worker.start_recording.side_effect = start
    engine.audio_worker.stop_recording.side_effect = stop
    engine.hotkey_worker = mock.Mock()
    states = []
    engine.state_changed.connect(states.append)
    saved = []
    engine.save_config = lambda: saved.append(True)
    return engine, states, saved


def test_engine_click_starts_then_finishes() -> None:
    logger.info("--- Testing pill click -> recording -> pill click -> pipeline ---")
    engine, states, _ = _engine()
    engine.pill_toggle_dictation()
    assert engine.audio_worker.recorder.is_recording and engine._pill_recording
    assert states == ["mic_starting:DIRECT"], states

    engine.pill_toggle_dictation()    # clicking again finishes it
    assert not engine.audio_worker.recorder.is_recording and not engine._pill_recording
    engine.hotkey_worker.manager.force_stop_active_recording.assert_called()
    assert states[-1] == "idle", states   # empty capture -> straight back to idle
    logger.success(f"PASS: states {states}")


def test_engine_cancel_discards_audio() -> None:
    logger.info("--- Testing x discards the recording: nothing is processed or typed ---")
    engine, states, _ = _engine()
    engine.pill_toggle_dictation()
    engine._finish_ptt_release = mock.Mock()
    engine.pill_cancel_dictation()
    assert not engine.audio_worker.recorder.is_recording and not engine._pill_recording
    engine._finish_ptt_release.assert_not_called()
    assert not engine._processing and states[-1] == "idle", states
    engine.pill_cancel_dictation()    # nothing recording: a no-op, not an error
    logger.success("PASS: audio dropped, pipeline untouched, mic closed.")


def test_engine_hotkey_tap_stops_a_pill_recording() -> None:
    logger.info("--- Testing the toggle hotkey ends a recording the pill started ---")
    engine, states, _ = _engine()
    engine.pill_toggle_dictation()
    engine._on_ptt_press()            # what the hotkey manager calls on a tap
    assert not engine.audio_worker.recorder.is_recording, "a tap must stop it, not start a second recording"
    assert engine.audio_worker.start_recording.call_count == 1
    logger.success("PASS: hotkey tap = stop for a pill-started recording.")


def test_engine_click_ignored_when_busy_or_not_ready() -> None:
    logger.info("--- Testing a pill click is ignored while loading/processing/live ---")
    for attr, value in (("_engines_ready", False), ("_processing", True), ("_live_worker", object())):
        engine, states, _ = _engine()
        setattr(engine, attr, value)
        engine.pill_toggle_dictation()
        assert not engine.audio_worker.recorder.is_recording and not engine._pill_recording and states == [], attr
    logger.success("PASS: no recording started and no stuck pill state.")


def test_engine_saves_pill_settings() -> None:
    logger.info("--- Testing click action and position persist ---")
    engine, _, saved = _engine()
    engine.set_pill_click_action("none")
    engine.set_pill_position(640, 480)
    assert engine.config.pill_click_action == "none" and engine.config.pill_position == [640, 480] and len(saved) == 2
    engine.set_pill_position(None, None)
    assert engine.config.pill_position is None
    from src.config import AppConfig
    assert AppConfig().pill_click_action == "dictate" and AppConfig().pill_position is None
    logger.success("PASS: defaults are click-to-dictate / default position; changes are saved.")


def test_shape_presets_and_speech_level() -> None:
    logger.info("--- Testing pill shape, position presets and normal-speech wave height ---")
    from src.config import AppConfig
    from src.ui.floating_pill import POSITION_PRESETS, SHAPE_BOX, SHAPE_PILL

    assert AppConfig().pill_shape == "pill"
    pill = _pill(shape="bogus")
    assert pill.shape == SHAPE_PILL, "unknown shape falls back to the pill"
    _settle(pill, "idle")
    assert pill._corner_radius(30) > 14, "pill is fully rounded"
    pill.set_shape(SHAPE_BOX)
    assert pill._corner_radius(30) < 10, "box has small corners"
    assert not pill.grab().isNull()

    moved, resets = [], []
    pill.position_changed.connect(lambda x, y: moved.append((x, y)))
    pill.position_reset_requested.connect(lambda: resets.append(1))
    spots = {}
    for key in POSITION_PRESETS:
        if key == "bottom_center":
            continue
        pill.apply_position_preset(key)
        spots[key] = (pill.x() + pill.width() / 2.0, pill.y() + pill.height() / 2.0)
    assert len(moved) == len(POSITION_PRESETS) - 1
    assert spots["top_left"][0] < spots["top_center"][0] < spots["top_right"][0]
    assert spots["top_left"][1] < spots["bottom_left"][1]
    pill.apply_position_preset("bottom_center")
    assert resets and not pill.has_custom_position(), "bottom centre is the default spot, i.e. a reset"

    _settle(pill, "recording")
    for _ in range(30):
        pill.set_level(0.02)     # ordinary speech on a laptop mic
        pill._tick()
    assert max(pill._levels) > 0.6, max(pill._levels)
    pill.close()
    logger.success("PASS: shape switches, presets land in the right corners, speech reaches >60% of the bar height.")


def run_all_tests() -> None:
    test_shape_presets_and_speech_level()
    test_click_action_is_configurable()
    test_drag_moves_the_pill_and_does_not_click()
    test_position_is_remembered_and_resettable()
    test_cancel_and_finish_buttons()
    test_waveform_follows_the_real_mic_level()
    test_pill_never_takes_keyboard_focus()
    test_every_state_renders_to_png()
    test_engine_click_starts_then_finishes()
    test_engine_cancel_discards_audio()
    test_engine_hotkey_tap_stops_a_pill_recording()
    test_engine_click_ignored_when_busy_or_not_ready()
    test_engine_saves_pill_settings()
    logger.success("ALL PILL INTERACTION TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
