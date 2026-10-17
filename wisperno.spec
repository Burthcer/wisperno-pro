# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build spec for Wisperno Pro.

Produces a --onedir bundle (WispernoPro.exe + a dist folder of DLLs/assets) rather
than --onefile: --onefile re-extracts its entire payload to a temp dir on every
launch, which is a poor fit for a multi-GB CUDA/torch/ctranslate2 dependency tree.

Build with:
    pyinstaller wisperno.spec --noconfirm --clean
or:
    python build_exe.py

Model weights (Whisper + .gguf LLMs) are intentionally NOT bundled - the app
resolves them from a `models/` folder next to the executable at runtime (see
src/config.py:get_base_dir(), which is frozen-aware via sys.frozen/sys.executable).
"""

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

block_cipher = None

# Native CUDA/ML shared libraries these packages load via ctypes/dlopen at
# runtime, which PyInstaller's static import analysis can't discover on its own.
binaries = []
binaries += collect_dynamic_libs("llama_cpp")
binaries += collect_dynamic_libs("ctranslate2")

# The engines need three NVIDIA DLLs (cuBLAS, cuBLASLt, cudart) and nothing else from CUDA. They used to arrive by
# bundling ALL of PyTorch (3.6 GB, ~3 GB of it unused). Now only these three (~550 MB) are copied into _internal/cuda
# (found at run time by src/cuda_runtime.py). Their source on the build machine is PyTorch's lib folder (installed
# for this purpose only) or the nvidia-*-cu12 pip packages.
import importlib.util
import os


def _cuda_runtime_binaries():
    wanted = ("cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll")
    folders = []
    for name, sub in (("torch", "lib"), ("nvidia.cublas", "bin"), ("nvidia.cuda_runtime", "bin")):
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        if spec and spec.submodule_search_locations:
            folders.append(os.path.join(list(spec.submodule_search_locations)[0], sub))
    found = {}
    for folder in folders:
        for dll in wanted:
            path = os.path.join(folder, dll)
            if dll not in found and os.path.exists(path):
                found[dll] = path
    missing = [dll for dll in wanted if dll not in found]
    if missing:
        raise SystemExit(f"Build needs {missing} (install the pinned torch from requirements.txt, or nvidia-cublas-cu12 + nvidia-cuda-runtime-cu12).")
    return [(path, "cuda") for path in found.values()]


binaries += _cuda_runtime_binaries()

datas = []
datas += collect_data_files("faster_whisper")
datas += [("config/config.yaml", "config"), ("config/dictionary.json", "config")]
datas += [("assets/icons/wisperno.ico", "assets/icons"), ("assets/icons/wisperno.png", "assets/icons")]
datas += [("assets/fonts", "assets/fonts")]  # Inter Tight + JetBrains Mono (SIL OFL) - see src/ui/theme.py:load_fonts

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "comtypes", "comtypes.client",  # focus_check.py: UI Automation for the paste-missed card
        "src.config",
        "src.audio_recorder",
        "src.transcriber",
        "src.transformer",
        "src.injector",
        "src.hotkey_manager",
        "src.vocabulary",
        "src.autostart",
        "src.single_instance",
        "src.database",
        "src.workers",
        "src.engine",
        "src.system_monitor",
        "src.branding",
        "src.presets",
        "src.app_context",
        "src.direct_formatter",
        "src.list_formatter",
        "src.swear_filter",
        "src.test_recordings",
        "src.live_transcriber",
        "src.writing_styles",
        "src.audio_cues",
        "src.device_manager",
        "psutil",
        "pynvml",
        "src.ui.theme",
        "src.ui.floating_pill",
        "src.ui.main_window",
        "src.ui.settings_tab",
        "src.ui.shortcut_recorder",
        "src.ui.history_tab",
        "src.ui.transforms_tab",
        "src.ui.dictionary_tab",
        "src.ui.snippets_tab",
        "src.ui.icons",
        "src.ui.tray",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "sqlite3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # torch/torchaudio are installed only as a source of the three CUDA DLLs above; never ship them.
    excludes=["tkinter", "PyQt5", "PyQt6", "torch", "torchaudio", "torchvision"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# PyInstaller also finds those same three DLLs as dependencies of the engines (it searches PATH) and would copy
# them a second time under torch/lib. They are already in cuda/, so drop the duplicate (547 MB).
a.binaries = [b for b in a.binaries if not b[0].replace("\\", "/").lower().startswith("torch/")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WispernoPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # --noconsole: no terminal window for the daemon
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icons/wisperno.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WispernoPro",
)
