"""
Start/stop sounds: every preset is valid, soft and short; your own .wav files are accepted only
within the limits, copied into the app's sounds folder, and can be dropped onto Settings -> Sounds.

Run: python tests/test_sounds.py
"""

import io
import os
import struct
import sys
import tempfile
import types
import wave
from pathlib import Path
from unittest import mock

from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))


def _write_wav(path: Path, seconds: float, rate: int = 22050, channels: int = 1) -> Path:
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<h", 800) * frames * channels)
    return path


def test_every_preset_is_valid_soft_and_short() -> None:
    logger.info("--- Testing the built-in sounds ---")
    from src import audio_cues

    assert audio_cues.DEFAULT_SOUND in audio_cues.PRESETS and len(audio_cues.PRESETS) >= 6
    for sound_id in audio_cues.PRESETS:
        starts, stops = audio_cues.wav_for(sound_id, "start"), audio_cues.wav_for(sound_id, "stop")
        assert starts != stops, f"{sound_id}: start and stop must sound different"
        for kind, data in (("start", starts), ("stop", stops)):
            with wave.open(io.BytesIO(data)) as wav:
                assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
                n = wav.getnframes()
                samples = struct.unpack("<%dh" % n, wav.readframes(n))
            peak = max(abs(x) for x in samples) / 32767
            ms = 1000 * n / audio_cues.SAMPLE_RATE
            assert 0.12 < peak <= 0.40, f"{sound_id}/{kind}: peak {peak:.2f} should be audible but gentle"
            assert 30 <= ms <= 450, f"{sound_id}/{kind}: {ms:.0f} ms - short enough never to feel like lag"
            assert abs(samples[-1]) < 50, f"{sound_id}/{kind}: must end at silence (no click)"
    assert audio_cues.wav_for("none", "start") is None
    assert audio_cues.wav_for("bogus-id", "start") == audio_cues.wav_for(audio_cues.DEFAULT_SOUND, "start"), "unknown id falls back to the default"
    logger.success("PASS: all presets are gentle, short, click-free, and start differs from stop.")


def test_custom_sound_rules() -> None:
    logger.info("--- Testing the rules for your own sound ---")
    from src import audio_cues

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, \
            mock.patch("src.audio_cues.get_app_data_dir", return_value=Path(tmp) / "data"):
        src = Path(tmp) / "in"
        src.mkdir()
        good = _write_wav(src / "My Ping!.wav", 0.5)
        sound_id = audio_cues.import_custom(good)
        assert sound_id == "custom:My Ping.wav" and (audio_cues.custom_dir() / "My Ping.wav").exists()
        assert audio_cues.wav_for(sound_id, "start") == good.read_bytes()

        def rejected(path):
            try:
                audio_cues.import_custom(path)
            except ValueError as e:
                return str(e)
            raise AssertionError(f"{path.name} should have been rejected")

        assert "too long" in rejected(_write_wav(src / "long.wav", 4.0))
        assert "too big" in rejected(_write_wav(src / "big.wav", 2.9, rate=96000, channels=2))  # 2.9 s but ~1.1 MB
        (src / "notes.mp3").write_bytes(b"x" * 100)
        assert ".wav" in rejected(src / "notes.mp3")
        (src / "fake.wav").write_bytes(b"this is not audio")
        assert "PCM WAV" in rejected(src / "fake.wav")
        assert "empty" in rejected(_write_wav(src / "empty.wav", 0.0))

        audio_cues.remove_custom(sound_id)
        assert not (audio_cues.custom_dir() / "My Ping.wav").exists()
        assert audio_cues.wav_for(sound_id, "start") == audio_cues.wav_for(audio_cues.DEFAULT_SOUND, "start"), "a removed sound falls back"

        for i in range(audio_cues.MAX_CUSTOM_SOUNDS):
            audio_cues.import_custom(_write_wav(src / f"s{i}.wav", 0.1))
        assert "12 custom sounds" in rejected(_write_wav(src / "one-too-many.wav", 0.1))
    logger.success("PASS: only short, small, standard .wav files are accepted; bad ones say why.")


def test_drop_zone_and_settings_tab() -> None:
    logger.info("--- Testing drag and drop onto Settings -> Sounds ---")
    from PySide6.QtCore import QMimeData, QPoint, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import QApplication, QMessageBox

    from src import audio_cues
    from src.config import AppConfig
    from src.ui.settings_tab import SettingsTab, _SoundDropZone

    app = QApplication.instance() or QApplication([])  # noqa: F841
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, \
            mock.patch("src.audio_cues.get_app_data_dir", return_value=Path(tmp) / "data"):
        engine = mock.MagicMock()
        engine.config = AppConfig()
        engine.transcriber = engine.transformer = None
        saved = {}
        engine.set_cue_sounds.side_effect = lambda start=None, stop=None: saved.update({k: v for k, v in (("start", start), ("stop", stop)) if v})
        tab = SettingsTab(engine, mock.MagicMock())
        general = tab.general_tab
        assert "Sounds" in [tab.sub_tabs.tabText(i) for i in range(tab.sub_tabs.count())]
        assert general.start_sound_cb.count() == len(audio_cues.PRESETS) + 1  # presets + "No sound"
        assert general.start_sound_cb.currentData() == "soft_pop"

        def drop(zone, path):
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path))])
            event = QDropEvent(QPoint(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            zone.dropEvent(event)

        good = _write_wav(Path(tmp) / "ding.wav", 0.4)
        warnings = []
        with mock.patch.object(QMessageBox, "exec", lambda self: 0), mock.patch.object(QMessageBox, "clickedButton", lambda self: None), \
                mock.patch.object(QMessageBox, "warning", lambda *a, **k: warnings.append(a[2])), mock.patch("src.audio_cues.play"):
            drop(general.sound_drop_zone, good)
            assert not warnings and general.start_sound_cb.findData("custom:ding.wav") >= 0 and general.stop_sound_cb.findData("custom:ding.wav") >= 0
            assert general.custom_sounds_box.count() == 1

            drop(general.sound_drop_zone, _write_wav(Path(tmp) / "huge.wav", 5.0))
            assert warnings and "too long" in warnings[-1], warnings
            assert general.custom_sounds_box.count() == 1, "a refused file is not added"

            general.start_sound_cb.setCurrentIndex(general.start_sound_cb.findData("custom:ding.wav"))
            assert saved["start"] == "custom:ding.wav"
            general._remove_custom_sound("custom:ding.wav")
            assert saved["start"] == "soft_pop", "removing a sound that's in use falls back to the default"
            assert general.start_sound_cb.findData("custom:ding.wav") < 0
        tab.close()
    logger.success("PASS: dropping a .wav adds it, refuses bad files with a reason, and removal falls back safely.")


def run_all_tests() -> None:
    test_every_preset_is_valid_soft_and_short()
    test_custom_sound_rules()
    test_drop_zone_and_settings_tab()
    logger.success("ALL SOUND TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
