"""
The CUDA runtime helper: finds the three NVIDIA DLLs the engines need, never imports PyTorch to do it,
and is safe to call repeatedly.

Run: python tests/test_cuda_runtime.py
"""

import subprocess
import sys
from pathlib import Path

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def test_required_dlls_are_found() -> None:
    from src import cuda_runtime

    assert cuda_runtime.REQUIRED_DLLS == ("cublas64_12.dll", "cublasLt64_12.dll", "cudart64_12.dll")
    assert cuda_runtime.missing_dlls() == [], f"CUDA runtime incomplete: {cuda_runtime.missing_dlls()}"
    first = cuda_runtime.add_cuda_dll_dirs()
    assert first and cuda_runtime.add_cuda_dll_dirs() == first, "calling it twice adds nothing new"
    logger.success(f"PASS: found {len(first)} CUDA folder(s); nothing missing; idempotent.")


def test_never_imports_pytorch() -> None:
    code = (
        "import sys; import src, src.cuda_runtime, src.device_manager; src.cuda_runtime.add_cuda_dll_dirs(); "
        "src.device_manager.detect_gpu_capability(); print('torch' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=BASE_DIR, timeout=120)
    assert out.stdout.strip().splitlines()[-1] == "False", out.stdout + out.stderr
    logger.success("PASS: starting up and probing the GPU never imports PyTorch.")


def test_frozen_layout_points_at_the_bundled_folder() -> None:
    from unittest import mock

    from src import cuda_runtime

    with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "_MEIPASS", str(BASE_DIR), create=True):
        assert cuda_runtime.cuda_dll_dirs() == [], "no cuda folder next to this fake install -> nothing to add, no crash"
    logger.success("PASS: an install without the folder degrades quietly.")


def run_all_tests() -> None:
    test_required_dlls_are_found()
    test_never_imports_pytorch()
    test_frozen_layout_points_at_the_bundled_folder()
    logger.success("ALL CUDA RUNTIME TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
