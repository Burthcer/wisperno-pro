"""Whisper's dash-bleeped swear words are restored; the GPU gauge never reads 0 with models loaded.

Run: python tests/test_dash_and_vram.py
"""
import sys
import types
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.swear_filter import unmask_profanity  # noqa: E402


def test_dashes() -> None:
    cases = {
        "the f- is the issue": "the fuck is the issue",
        "not using any f-ing RAM": "not using any fucking RAM",
        "F-ing hell": "Fucking hell",
        "f--king awful": "fucking awful",
        "sh-t happens": "shit happens",
        "the F-16 and the f-stop and a well-known thing": "the F-16 and the f-stop and a well-known thing",
    }
    for src, want in cases.items():
        assert unmask_profanity(src) == want, (src, unmask_profanity(src))
    print("PASS: dash-bleeped swear words are restored, ordinary hyphens are untouched.")


def test_vram_floor() -> None:
    from src import system_monitor as sm

    monitor = sm.SystemMonitor.__new__(sm.SystemMonitor)
    import os
    monitor._pid = os.getpid()
    monitor._gpu_handle = object()
    monitor._mismatch_logged = monitor._first_reading_logged = monitor._low_used_logged = False
    monitor._ram_read_at, monitor._ram_cached_mb = 0.0, None
    monitor._proc_vram = types.SimpleNamespace(read=lambda pid: (3200.0, 90.0, []))
    # NVML claims the whole GPU uses 0 MB, although this app alone holds 3.2 GB
    monitor._read_gpu_memory = lambda: (8188.0, 0.0)
    with mock.patch.object(sm.pynvml, "nvmlDeviceGetUtilizationRates", side_effect=RuntimeError("Unknown Error")), \
            mock.patch.object(sm.pynvml, "nvmlDeviceGetTemperature", side_effect=RuntimeError("Unknown Error")):
        snap = monitor.snapshot()
    assert snap["gpu_used_mb"] >= 3200.0, snap["gpu_used_mb"]
    assert snap["app_vram_mb"] <= snap["gpu_used_mb"]
    print("PASS: the GPU gauge falls back to the app's own figure instead of 0.")


if __name__ == "__main__":
    test_dashes()
    test_vram_floor()
