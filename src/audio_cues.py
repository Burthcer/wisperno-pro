"""
Start/stop sounds for dictation (Settings -> Sounds). Windows-only like the rest of the app.

You choose one sound for "starts listening" and one for "stops", from:
  - built-in presets, synthesized in memory with the stdlib (no asset files), or
  - your own short .wav files, dropped into Settings -> Sounds and copied to
    %APPDATA%\\WispernoPro\\sounds.

A sound id is a preset name ("soft_pop"), "none" (silence for that event) or
"custom:<file name>". Each preset has a rising variant (start) and a falling one (stop).
"""

import io
import math
import shutil
import struct
import sys
import threading
import wave
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger

from src.config import get_app_data_dir

SAMPLE_RATE = 44100
DEFAULT_SOUND = "soft_pop"
NONE_ID = "none"
CUSTOM_PREFIX = "custom:"

# Limits for a sound you add yourself (so it can never be slow, huge or jarring).
MAX_CUSTOM_BYTES = 1_000_000      # 1 MB
MAX_CUSTOM_SECONDS = 3.0
MAX_CUSTOM_SOUNDS = 12


# ---------------------------------------------------------------- synthesis helpers

def _env_fade(samples: List[float], fade_ms: float = 12.0) -> List[float]:
    """Fade the very end to silence so a sound never ends on a click."""
    n = len(samples)
    fade = max(1, int(SAMPLE_RATE * fade_ms / 1000))
    for i in range(min(fade, n)):
        samples[n - 1 - i] *= i / fade
    return samples


def _mix(parts: List[Tuple[int, List[float]]], total_ms: int) -> List[float]:
    n = int(SAMPLE_RATE * total_ms / 1000)
    out = [0.0] * n
    for start_ms, samples in parts:
        first = int(SAMPLE_RATE * start_ms / 1000)
        for i, v in enumerate(samples):
            if first + i < n:
                out[first + i] += v
    return out


def _tone(f0: float, f1: float, ms: int, decay_ms: float, harmonics: Tuple[float, ...] = (1.0,), attack_ms: float = 3.0, amp: float = 1.0) -> List[float]:
    """A sine that glides from f0 to f1 (exponentially) while fading out. `harmonics` are the
    relative levels of the fundamental, 2nd, 3rd ... partials."""
    n = int(SAMPLE_RATE * ms / 1000)
    attack = max(1, int(SAMPLE_RATE * attack_ms / 1000))
    out, phase = [], 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        glide = i / max(n - 1, 1)
        freq = f0 * (f1 / f0) ** glide
        phase += 2 * math.pi * freq / SAMPLE_RATE
        env = min(1.0, i / attack) * math.exp(-t * 1000.0 / decay_ms)
        out.append(amp * env * sum(h * math.sin(phase * (k + 1)) for k, h in enumerate(harmonics)))
    return out


def _noise_tap(ms: int, centre_hz: float, q: float, decay_ms: float, seed: int = 7) -> List[float]:
    """A short burst of noise through a resonant band-pass: a wooden 'tap' or soft 'click'."""
    n = int(SAMPLE_RATE * ms / 1000)
    w0 = 2 * math.pi * centre_hz / SAMPLE_RATE
    alpha = math.sin(w0) / (2 * q)
    b0, b2, a0, a1, a2 = alpha, -alpha, 1 + alpha, -2 * math.cos(w0), 1 - alpha
    x1 = x2 = y1 = y2 = 0.0
    state, out = seed, []
    for i in range(n):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF  # deterministic noise: the same sound every time
        x0 = (state / 0x3FFFFFFF) - 1.0
        y0 = (b0 * x0 + b2 * x2 - a1 * y1 - a2 * y2) / a0
        x2, x1, y2, y1 = x1, x0, y1, y0
        out.append(y0 * math.exp(-(i / SAMPLE_RATE) * 1000.0 / decay_ms))
    return out


def _to_wav(samples: List[float], gain: float) -> bytes:
    samples = _env_fade(samples)
    peak = max((abs(v) for v in samples), default=0.0) or 1.0
    pcm = bytearray()
    for v in samples:
        pcm += struct.pack("<h", int(32767 * gain * v / peak))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(pcm))
    return out.getvalue()


# ---------------------------------------------------------------- presets: id -> (label, build(kind))

def _soft_pop(kind: str) -> bytes:
    # A soft bubble: the pitch slides up to say "listening", down to say "done".
    f0, f1 = (520.0, 900.0) if kind == "start" else (780.0, 430.0)
    return _to_wav(_mix([(0, _tone(f0, f1, 120, 36, (1.0, 0.14)))], 140), 0.30)


def _droplet(kind: str) -> bytes:
    f0, f1 = (650.0, 1450.0) if kind == "start" else (1350.0, 700.0)
    main = _tone(f0, f1, 90, 30, (1.0, 0.10))
    echo = _tone(f0, f1, 90, 30, (1.0, 0.10), amp=0.32)
    return _to_wav(_mix([(0, main), (105, echo)], 240), 0.28)


def _wood_tap(kind: str) -> bytes:
    centre, thump = (980.0, 430.0) if kind == "start" else (640.0, 300.0)
    tap = _noise_tap(40, centre, 9.0, 11.0)
    body = _tone(thump, thump * 0.9, 60, 18, (1.0, 0.2), amp=0.8)
    return _to_wav(_mix([(0, tap), (0, body)], 70), 0.32)


def _marimba(kind: str) -> bytes:
    f = 659.25 if kind == "start" else 440.0
    return _to_wav(_mix([(0, _tone(f, f, 300, 95, (1.0, 0.0, 0.0, 0.32, 0.0, 0.0, 0.0, 0.0, 0.0, 0.08)))], 320), 0.30)


def _glass_tick(kind: str) -> bytes:
    f = 2600.0 if kind == "start" else 1900.0
    return _to_wav(_mix([(0, _tone(f, f, 50, 9, (1.0, 0.18), attack_ms=1.0))], 60), 0.22)


def _soft_click(kind: str) -> bytes:
    centre = 1800.0 if kind == "start" else 1100.0
    click = _noise_tap(18, centre, 2.5, 4.5, seed=11)
    thump = _tone(170, 140, 30, 9, amp=0.6)
    return _to_wav(_mix([(0, click), (0, thump)], 40), 0.26)


def _chime(kind: str) -> bytes:
    notes = ((659.25, 0), (987.77, 85)) if kind == "start" else ((987.77, 0), (659.25, 85))
    parts = [(start, _tone(f, f, 260, 75, (1.0, 0.25, 0.08))) for f, start in notes]
    return _to_wav(_mix(parts, 330), 0.34 if kind == "start" else 0.26)


PRESETS: Dict[str, Tuple[str, Callable[[str], bytes]]] = {
    "soft_pop": ("Soft pop", _soft_pop),
    "droplet": ("Droplet", _droplet),
    "wood_tap": ("Wood tap", _wood_tap),
    "marimba": ("Marimba", _marimba),
    "glass_tick": ("Glass tick", _glass_tick),
    "soft_click": ("Soft click", _soft_click),
    "chime": ("Chime", _chime),
}


# ---------------------------------------------------------------- your own sounds

def custom_dir() -> Path:
    path = get_app_data_dir() / "sounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_custom() -> List[str]:
    return sorted(p.name for p in custom_dir().glob("*.wav"))


def custom_id(file_name: str) -> str:
    return CUSTOM_PREFIX + file_name


def describe_limits() -> str:
    return f"WAV file, up to {MAX_CUSTOM_SECONDS:g} seconds and {MAX_CUSTOM_BYTES // 1000} KB"


def validate_custom(path: Path) -> Tuple[bool, str]:
    """(ok, message). The message says exactly what is wrong, in plain words."""
    path = Path(path)
    if path.suffix.lower() != ".wav":
        return False, f"'{path.name}' isn't a .wav file. Only {describe_limits()} is accepted."
    try:
        size = path.stat().st_size
    except OSError:
        return False, f"Couldn't read '{path.name}'."
    if size > MAX_CUSTOM_BYTES:
        return False, f"'{path.name}' is {size / 1000:.0f} KB - too big. Sounds must be {describe_limits()}."
    try:
        with wave.open(str(path), "rb") as wav:
            frames, rate, channels = wav.getnframes(), wav.getframerate(), wav.getnchannels()
    except (wave.Error, EOFError):
        return False, f"'{path.name}' isn't a standard PCM WAV file. Re-export it as a normal 16-bit WAV."
    if frames == 0 or rate <= 0:
        return False, f"'{path.name}' is empty."
    if channels > 2:
        return False, f"'{path.name}' has {channels} channels - use mono or stereo."
    if not 8000 <= rate <= 96000:
        return False, f"'{path.name}' has an unusual sample rate ({rate} Hz)."
    seconds = frames / rate
    if seconds > MAX_CUSTOM_SECONDS:
        return False, f"'{path.name}' is {seconds:.1f} seconds long - too long. Sounds must be {describe_limits()}."
    if len(list_custom()) >= MAX_CUSTOM_SOUNDS and not (custom_dir() / path.name).exists():
        return False, f"You already have {MAX_CUSTOM_SOUNDS} custom sounds. Remove one first."
    return True, ""


def import_custom(path: Path) -> str:
    """Validate and copy a sound into the app's own sounds folder. Returns its id, or raises
    ValueError(<plain-words reason>) if it is rejected."""
    path = Path(path)
    ok, message = validate_custom(path)
    if not ok:
        raise ValueError(message)
    safe = "".join(c for c in path.stem if c.isalnum() or c in " -_()").strip() or "sound"
    target = custom_dir() / f"{safe[:40]}.wav"
    shutil.copyfile(path, target)
    _custom_wav.cache_clear()
    return custom_id(target.name)


def remove_custom(sound_id: str) -> None:
    if sound_id.startswith(CUSTOM_PREFIX):
        try:
            (custom_dir() / sound_id[len(CUSTOM_PREFIX):]).unlink()
        except OSError as e:
            logger.debug(f"Could not remove custom sound: {e}")
        _custom_wav.cache_clear()


def label_for(sound_id: str) -> str:
    if sound_id == NONE_ID:
        return "No sound"
    if sound_id.startswith(CUSTOM_PREFIX):
        return sound_id[len(CUSTOM_PREFIX):].removesuffix(".wav") + " (yours)"
    return PRESETS.get(sound_id, PRESETS[DEFAULT_SOUND])[0]


# ---------------------------------------------------------------- playback

@lru_cache(maxsize=None)
def _preset_wav(sound_id: str, kind: str) -> bytes:
    return PRESETS[sound_id][1](kind)


@lru_cache(maxsize=16)
def _custom_wav(file_name: str) -> Optional[bytes]:
    try:
        return (custom_dir() / file_name).read_bytes()
    except OSError:
        return None


def wav_for(sound_id: str, kind: str) -> Optional[bytes]:
    """The WAV bytes to play for `sound_id` ('start' or 'stop'), or None for silence / a missing file."""
    if sound_id == NONE_ID:
        return None
    if sound_id.startswith(CUSTOM_PREFIX):
        data = _custom_wav(sound_id[len(CUSTOM_PREFIX):])
        return data if data is not None else _preset_wav(DEFAULT_SOUND, kind)  # file deleted by hand: fall back
    return _preset_wav(sound_id if sound_id in PRESETS else DEFAULT_SOUND, kind)


def _play(sound_id: str, kind: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound

        data = wav_for(sound_id, kind)
        if data:
            # SND_MEMORY can't be combined with SND_ASYNC, so this blocks - which is why it runs on its own thread.
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except Exception as e:
        logger.debug(f"Audio cue playback failed: {e}")


def play(sound_id: str, kind: str) -> None:
    """Fire-and-forget; never call blocking on the hotkey callback thread."""
    threading.Thread(target=_play, args=(sound_id, kind), daemon=True).start()


def play_start_cue(sound_id: str = DEFAULT_SOUND) -> None:
    play(sound_id, "start")


def play_stop_cue(sound_id: str = DEFAULT_SOUND) -> None:
    play(sound_id, "stop")
