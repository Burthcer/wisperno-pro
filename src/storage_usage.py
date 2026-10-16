"""
How much disk space Wisperno Pro takes on this PC, split into the parts a user
can reason about: the application itself, the AI models, saved history, and kept
recordings. Shown in the System Usage tab.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional

from src.config import get_app_data_dir, get_base_dir


def dir_size(path: Path) -> int:
    """Total bytes of every file under `path` (0 if it doesn't exist). Symlinks and
    junctions below the top are not followed, so nothing is counted twice."""
    total = 0
    stack = [str(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if not entry.is_junction():
                                stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def format_bytes(n: float) -> str:
    """1536 -> '1.5 KB', 3.2e9 -> '3.0 GB' (binary units, one decimal)."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def storage_breakdown(base_dir: Optional[Path] = None, data_dir: Optional[Path] = None) -> Dict[str, Optional[int]]:
    """Bytes used by each part, plus the free space on the drive the app lives on.
    `app` is None when running from source (the folder is a whole dev checkout, not an install)."""
    base_dir = Path(base_dir) if base_dir is not None else get_base_dir()
    data_dir = Path(data_dir) if data_dir is not None else get_app_data_dir()

    models_dir = base_dir / "models"
    # In a dev checkout `models` is often a junction to a shared folder - follow the top-level link.
    models = dir_size(models_dir.resolve()) if models_dir.exists() else 0

    app: Optional[int] = None
    if getattr(sys, "frozen", False):
        app = max(dir_size(base_dir) - (models if not models_dir.is_junction() else 0), 0)

    history = 0
    for name in ("wisperno.db", "wisperno.db-wal", "wisperno.db-shm"):
        try:
            history += (data_dir / name).stat().st_size
        except OSError:
            pass
    recordings = dir_size(data_dir / "recent_audio") + dir_size(data_dir / "recordings")

    try:
        free = shutil.disk_usage(base_dir).free
    except OSError:
        free = None
    return {"app": app, "models": models, "history": history, "recordings": recordings, "free": free}


def delete_recordings(data_dir: Optional[Path] = None) -> int:
    """Delete every kept recording (the recent clips History can re-transcribe, and any test
    recordings). Returns the bytes freed. Only files inside those two folders are touched."""
    data_dir = Path(data_dir) if data_dir is not None else get_app_data_dir()
    freed = 0
    for folder in (data_dir / "recent_audio", data_dir / "recordings"):
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            try:
                if entry.is_file():
                    size = entry.stat().st_size
                    entry.unlink()
                    freed += size
            except OSError:
                continue
    return freed


def total_bytes(breakdown: Dict[str, Optional[int]]) -> int:
    return sum(int(breakdown[k] or 0) for k in ("app", "models", "history", "recordings"))
