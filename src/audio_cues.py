"""
Optional audio feedback for dictation start/stop (Settings -> Dictation ->
Sounds). A soft two-note chime, synthesized in memory with the stdlib -
no audio asset files and no new dependency, Windows-only like the rest of the app.

Start is a gentle rising pair ("I'm listening"); stop is a quieter falling pair
("done"). Each note is a sine with a little 2nd/3rd harmonic (a bell-like tone)
and a quick exponential decay, so it is pleasant rather than a raw beep.
"""

import io
import math
import struct
import sys
import threading
import wave
from functools import lru_cache
from typing import Sequence, Tuple

from loguru import logger

SAMPLE_RATE = 44100
# (frequency Hz, start ms) - E5 -> B5 rising, B5 -> E5 falling: a perfect fifth either way.
START_NOTES: Sequence[Tuple[float, int]] = ((659.25, 0), (987.77, 85))
STOP_NOTES: Sequence[Tuple[float, int]] = ((987.77, 0), (659.25, 85))
START_GAIN, STOP_GAIN = 0.34, 0.26
NOTE_DECAY_MS = 75          # exponential decay time constant of each note
TOTAL_MS = 330


def synth_chime(notes: Sequence[Tuple[float, int]], gain: float, total_ms: int = TOTAL_MS) -> bytes:
    """A mono 16-bit WAV (as bytes) of the given notes, peak amplitude `gain` (0-1)."""
    n = int(SAMPLE_RATE * total_ms / 1000)
    mix = [0.0] * n
    attack = int(SAMPLE_RATE * 0.006)
    for freq, start_ms in notes:
        first = int(SAMPLE_RATE * start_ms / 1000)
        for i in range(first, n):
            t = (i - first) / SAMPLE_RATE
            env = min(1.0, (i - first) / attack) * math.exp(-t * 1000.0 / NOTE_DECAY_MS)
            tone = math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(4 * math.pi * freq * t) + 0.08 * math.sin(6 * math.pi * freq * t)
            mix[i] += tone * env
    peak = max(abs(v) for v in mix) or 1.0
    fade = int(SAMPLE_RATE * 0.02)
    pcm = bytearray()
    for i, v in enumerate(mix):
        tail = min(1.0, (n - 1 - i) / fade)  # fade to silence so there is no click at the end
        pcm += struct.pack("<h", int(32767 * gain * (v / peak) * tail))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(pcm))
    return out.getvalue()


@lru_cache(maxsize=None)
def _start_wav() -> bytes:
    return synth_chime(START_NOTES, START_GAIN)


@lru_cache(maxsize=None)
def _stop_wav() -> bytes:
    return synth_chime(STOP_NOTES, STOP_GAIN)


def _play(get_wav) -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound

        # SND_MEMORY can't be combined with SND_ASYNC, so this blocks - which is why it runs on its own thread.
        winsound.PlaySound(get_wav(), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except Exception as e:
        logger.debug(f"Audio cue playback failed: {e}")


def play_start_cue() -> None:
    """Fire-and-forget; never call blocking on the hotkey callback thread."""
    threading.Thread(target=_play, args=(_start_wav,), daemon=True).start()


def play_stop_cue() -> None:
    threading.Thread(target=_play, args=(_stop_wav,), daemon=True).start()
