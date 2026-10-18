"""If Windows' volume mixer has Wisperno at 0/muted, the cue code puts it back (the 'no sound at all' bug).

Run: python tests/test_audio_mixer.py   (Windows with an audio device; skips quietly otherwise)
"""
import os
import sys
import threading
import time
import winsound
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import audio_cues  # noqa: E402


def _our_volume():
    from pycaw.pycaw import AudioUtilities

    for s in AudioUtilities.GetAllSessions():
        if s.Process is not None and s.Process.pid == os.getpid():
            return s.SimpleAudioVolume
    return None


def main() -> None:
    threading.Thread(target=winsound.PlaySound, args=(audio_cues._silent_wav(400), winsound.SND_MEMORY), daemon=True).start()
    vol = None
    for _ in range(40):
        vol = _our_volume()
        if vol is not None:
            break
        time.sleep(0.05)
    if vol is None:
        print("SKIP: no audio session (no output device?)")
        return
    vol.SetMasterVolume(0.0, None)
    vol.SetMute(1, None)
    assert audio_cues.ensure_audible() is True, "should report it had to fix the volume"
    vol = _our_volume()
    assert vol.GetMasterVolume() == 1.0 and not vol.GetMute()
    assert audio_cues.ensure_audible() is False, "nothing to fix the second time"
    print("PASS: a muted / zero-volume Wisperno mixer entry is restored to full volume.")


if __name__ == "__main__":
    main()
