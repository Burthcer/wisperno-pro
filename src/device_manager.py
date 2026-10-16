"""
Hardware capability detection for Wisperno: decides whether Whisper/the local
LLM should run on GPU or fall back to CPU, checked ONCE at startup before
either model is loaded - proactive, not a post-hoc exception handler racing
whatever failure mode a native library happens to throw on integrated
graphics or a VRAM-starved GPU. Keeps that reactive fallback in transcriber.py
(a real CUDA init exception is still caught there) as a second line of
defense, not a replacement for this one.
"""

from typing import Tuple, TypedDict
from loguru import logger

# Below this, treat the GPU as unusable for this app's models even though
# CUDA itself is technically available (e.g. an old/integrated GPU that
# reports a CUDA device but doesn't have room for Whisper + a 3B-parameter LLM).
MIN_VRAM_GB = 2.0


class GpuCapability(TypedDict):
    has_cuda: bool
    vram_gb: float
    use_gpu: bool
    reason: str


def _probe_gpu() -> Tuple[int, float]:
    """(number of usable CUDA devices, VRAM in GB of the first one). Asks the speech engine itself whether it can
    see a CUDA device - the same check that decides whether it can actually use the GPU - and NVIDIA's NVML for the
    memory size. No PyTorch needed."""
    import ctranslate2

    count = int(ctranslate2.get_cuda_device_count())
    vram_gb = 0.0
    if count > 0:
        try:
            import pynvml

            pynvml.nvmlInit()
            vram_gb = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0)).total / (1024 ** 3)
        except Exception:
            vram_gb = MIN_VRAM_GB  # the device exists but its size can't be read: give it the benefit of the doubt
    return count, vram_gb


def detect_gpu_capability() -> GpuCapability:
    """Best-effort, exception-safe GPU probe. Never raises - a probe failure
    itself is treated as "no usable GPU", the same as a genuine absence."""
    has_cuda = False
    vram_gb = 0.0
    reason = ""
    try:
        count, vram_gb = _probe_gpu()
        has_cuda = count > 0
    except Exception as e:
        reason = f"GPU probe failed ({e})"
        has_cuda = False

    if not has_cuda and not reason:
        reason = "No CUDA-capable GPU detected"
    elif has_cuda and vram_gb < MIN_VRAM_GB:
        reason = f"GPU has only {vram_gb:.1f}GB VRAM (below the {MIN_VRAM_GB:.0f}GB this app needs)"

    use_gpu = has_cuda and vram_gb >= MIN_VRAM_GB
    if not use_gpu:
        logger.warning(
            f"Running in CPU Compatibility Mode: {reason}. "
            f"Whisper -> CPU/int8, local LLM -> 0 GPU layers (CPU/AVX2)."
        )
    return {"has_cuda": has_cuda, "vram_gb": vram_gb, "use_gpu": use_gpu, "reason": reason}
