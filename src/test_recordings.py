"""
Opt-in capture of real dictations for building a personal test set (see
scripts/eval_dictation.py). Off by default: when enabled in Settings, each
dictation's audio is written to %APPDATA%\\Wisperno\\recordings as a WAV,
alongside what Whisper heard and what was pasted. Nothing is written while
the setting is off, and nothing ever leaves the machine.

Per clip:
  <stamp>.wav          16kHz mono audio, exactly what Whisper received
  <stamp>.heard.txt    Whisper's raw transcript
  <stamp>.pasted.txt   the final text that was pasted
You add, by hand:
  <stamp>.txt          what you actually said (the reference for WER)
  <stamp>.expected.txt optional: the ideal final output (e.g. with a list)
"""

import time
import wave
from pathlib import Path

import numpy as np
from loguru import logger

from src.config import get_app_data_dir

SAMPLE_RATE = 16000


def recordings_dir() -> Path:
    path = get_app_data_dir() / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_wav(path: Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def read_wav(path: Path) -> np.ndarray:
    """Float32 mono samples in [-1, 1]; the file must be 16kHz mono 16-bit (as write_wav makes them)."""
    with wave.open(str(path), "rb") as wav:
        if wav.getframerate() != SAMPLE_RATE or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(f"{path.name}: expected 16kHz mono 16-bit PCM")
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    return pcm.astype(np.float32) / 32767.0


def save_recording(audio: np.ndarray, heard: str, pasted: str) -> Path:
    """Write one dictation's clip + transcripts; returns the .wav path."""
    folder = recordings_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    wav_path = folder / f"{stamp}.wav"
    write_wav(wav_path, audio)
    (folder / f"{stamp}.heard.txt").write_text(heard, encoding="utf-8")
    (folder / f"{stamp}.pasted.txt").write_text(pasted, encoding="utf-8")
    logger.info(f"[TEST SET] Saved recording {wav_path.name} ({len(audio) / SAMPLE_RATE:.1f}s).")
    return wav_path
