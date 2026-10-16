"""
Where the NVIDIA CUDA runtime libraries (cuBLAS, cuBLASLt, cudart) live, and making them findable.

The speech engine (CTranslate2) and the language model engine (llama.cpp) both need three NVIDIA DLLs and
neither ships them. In the installed app they are bundled in `_internal\\cuda` - just those three (about
550 MB). The app used to bundle all of PyTorch (3.6 GB) only to borrow them; nothing here imports PyTorch.

In a development checkout the same DLLs are found next to a PyTorch install (as before), or in the
`nvidia-*-cu12` pip packages. Stdlib only, so it can run before anything else is imported.
"""

import importlib.util
import os
import sys
from pathlib import Path
from typing import List

# The only CUDA libraries the engines import (checked from their DLL import tables, and by running a real
# GPU transcription with just these visible).
REQUIRED_DLLS = ("cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll")

_added: List[str] = []


def _package_dir(name: str):
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0])
    return None


def cuda_dll_dirs() -> List[Path]:
    """Folders that may hold the CUDA DLLs, most specific first (only ones that exist)."""
    candidates: List[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent / "_internal"))
        candidates.append(base / "cuda")
    else:
        torch_dir = _package_dir("torch")  # found without importing it (importing loads ~3 GB of DLLs)
        if torch_dir:
            candidates.append(torch_dir / "lib")
        for sub in ("nvidia.cublas", "nvidia.cuda_runtime"):
            pkg = _package_dir(sub)
            if pkg:
                candidates.append(pkg / "bin")
    return [d for d in candidates if d.is_dir()]


def add_cuda_dll_dirs() -> List[str]:
    """Make the CUDA DLL folders visible to the Windows loader. Safe to call repeatedly."""
    if sys.platform != "win32":
        return []
    for folder in cuda_dll_dirs():
        path = str(folder)
        if path in _added:
            continue
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(path)
        except OSError:
            continue
        os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
        _added.append(path)
    return list(_added)


def missing_dlls() -> List[str]:
    """Required DLLs not found in any known folder (empty when the GPU runtime is complete)."""
    folders = cuda_dll_dirs()
    return [name for name in REQUIRED_DLLS if not any((folder / name).exists() for folder in folders)]
