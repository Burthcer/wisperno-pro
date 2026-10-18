# Installing Wisperno Pro

Wisperno Pro is a separate app from the original Wisperno: it has its own
installer identity, install folder (`%LOCALAPPDATA%\Programs\Wisperno Pro`),
settings/history folder (`%APPDATA%\WispernoPro`) and icon, so it installs
alongside Wisperno without changing or replacing it. Don't run both at the
same time with the same hotkeys - Wisperno Pro warns you at startup if the
original is running.

## Why no `.exe` here

This repository is source only. Wisperno's packaged portable build bundles
PyTorch, CUDA/cuDNN, and CTranslate2's runtime - about 4.7GB, with several
individual DLLs near or over 1GB each. GitHub hard-rejects any file over
100MB without Git LFS, and the full runtime would exceed GitHub's free LFS
quota outright, so it's excluded via `.gitignore` rather than committed.
Build it yourself with `build_exe.py`/`wisperno.spec` (see below) if you
want a standalone portable folder like the one this project ships day-to-day.

## 1. Prerequisites

- **Windows 11** (64-bit). Windows 10 64-bit likely works but isn't the
  primary tested target.
- **Python 3.12** (64-bit).
- **NVIDIA GPU + driver** with CUDA support, 4GB+ VRAM recommended (2GB is
  the hard minimum before Wisperno automatically falls back to a slower
  CPU-only mode - see SYSTEM_REQUIREMENTS.md). Install the latest driver from
  https://www.nvidia.com/Download/index.aspx - `pip install -r requirements.txt`
  pulls in the CUDA runtime itself (PyTorch/CTranslate2 wheels), you only
  need the driver on the system.

## 2. Run from source

```
git clone https://github.com/<your-account>/wisperno-pro.git
cd wisperno-pro
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python download_models.py
python main.py
```

`download_models.py` fetches the STT model (auto, via `faster-whisper`/
Hugging Face) and the LLM preset your `config/config.yaml`'s `model_preset`
points at - see `models/MODELS.md` for the manual-download alternative and
the full per-preset file list. Skip it and Wisperno still runs, just without
LLM polish (a warning is logged).

A small pill indicator appears near the bottom of your screen once ready
(a few seconds after Whisper/LLM load). Hold/tap `Ctrl+Alt` to dictate.

## 3. Building a standalone portable build (optional)

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python build_exe.py
```

Produces a `dist/`/`build/` output per `wisperno.spec` - the same kind of
self-contained, no-Python-required folder described above, for distributing
to a machine without a Python install. `scripts/package_portable.py` and
`scripts/package_git_release.py` handle staging that output for distribution;
`installer/setup.iss` builds a Windows installer via Inno Setup.

To build the installer (`Final App\WispernoPro-Setup-v<version>.exe` plus
its numbered `.bin` volumes - keep them together in one folder, Setup reads
the volumes from beside the exe):

```
.venv\Scripts\python download_models.py
.venv\Scripts\python build_exe.py
.venv\Scripts\python scripts\build_installer.py
```

`build_installer.py` installs Inno Setup 6 via winget if it's missing.

## 4. CPU-only fallback (no compatible GPU)

If Wisperno detects no CUDA-capable GPU (or under ~2GB VRAM), it
automatically switches to CPU inference for that launch - slower, but still
functional, and never silently corrupts your saved GPU preset for later.
A toast on the floating pill confirms when this happens.

## Uninstalling

Delete the folder and your `.venv`. Your dictation history/dictionary/
settings live in `%APPDATA%\WispernoPro\` - delete that too for a full removal.
An installed Wisperno Pro uninstalls from Settings -> Apps like any other app.
