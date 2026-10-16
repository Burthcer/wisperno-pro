"""
The last few dictations' audio, kept on this PC so History can re-transcribe a
bad one with a different (slower, more careful) method.

One 16 kHz mono WAV per History row, named by its id, in %APPDATA%\\WispernoPro\\recent_audio.
Only the newest `keep` clips are kept - saving a new one deletes the oldest -
and nothing here ever leaves the machine.
"""

from pathlib import Path
from typing import Optional

import numpy as np
from loguru import logger

from src.config import get_app_data_dir
from src.test_recordings import read_wav, write_wav


def audio_dir() -> Path:
    path = get_app_data_dir() / "recent_audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def path_for(history_id: int) -> Path:
    return audio_dir() / f"{int(history_id)}.wav"


def has_audio(history_id: int) -> bool:
    return path_for(history_id).exists()


def load(history_id: int) -> Optional[np.ndarray]:
    path = path_for(history_id)
    return read_wav(path) if path.exists() else None


def save(history_id: int, audio: np.ndarray, keep: int) -> None:
    """Store this dictation's audio, then delete everything but the newest `keep` clips."""
    if keep <= 0 or audio is None or len(audio) == 0:
        return
    write_wav(path_for(history_id), audio)
    prune(keep)


def prune(keep: int) -> None:
    clips = sorted((p for p in audio_dir().glob("*.wav") if p.stem.isdigit()), key=lambda p: int(p.stem), reverse=True)
    for old in clips[max(keep, 0):]:
        try:
            old.unlink()
        except OSError as e:
            logger.warning(f"Could not delete old recording {old.name}: {e}")
