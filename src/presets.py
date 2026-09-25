"""
Engine presets (the local LLM behind Polish/Transforms), shared by the
engine and the Settings UI - kept out of src/ui so the engine can use it
without importing any widget code.

Two tiers, both under 4 GB of combined GPU memory with Whisper loaded, so
the app runs on common 6-8 GB laptop GPUs:

- Turbo Flagship (default): Qwen2.5-1.5B-Instruct Q8_0 - fastest.
- Standard: Qwen2.5-3B-Instruct Q4_K_M - more reliable cleanup, a bit slower.

Retired presets and why (full history in git before this module existed):
- Flagship (Qwen2.5-3B Q8_0): ~5.1 GB, above the VRAM target, and only
  matched Standard's measured fidelity (98.8%) while decoding ~30% slower.
- Eco (Qwen2.5-3B IQ4_XS, renamed wisperno-custom-v1.gguf): same model as
  Standard at a lower quant, no measured advantage over it, and needed a
  manually renamed download.
- Gemma 2 2B (Beta): measured slower than Turbo Flagship (no flash
  attention for Gemma-2) with no quality win.

A config still pointing at a retired preset is moved to a supported one on
the next launch (see migrate_removed_preset()).
"""

from typing import Dict, List, Optional

DEFAULT_PRESET = "turbo"

MODEL_PRESETS: Dict[str, dict] = {
    "turbo": {
        "label": "Turbo Flagship (Instant Speed)",
        "description": "Compact, speed-tuned engine for near-instant text replacement - the fastest tier "
        "(~114 tok/s). A lightweight safety net protects against rare edge cases so output stays reliable.",
        "badge": "Fastest  |  Instant Text Replacement",
        "tooltip": "The fastest tier - best when speed matters most.",
        "repo_id": "bartowski/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "Qwen2.5-1.5B-Instruct-Q8_0.gguf",
        "model_path": "models/Qwen2.5-1.5B-Instruct-Q8_0.gguf",
        "kv_cache_quantization": False,
        "n_ctx": 8192, "flash_attn": True, "chat_style": "standard",
    },
    "standard": {
        "label": "Standard (Balanced)",
        "description": "Larger 3B model: more reliable cleanup on long or tricky dictation, at ~92 tok/s. "
        "Pick this if Turbo Flagship ever leaves text unpolished.",
        "badge": "Balanced  |  Most Reliable Cleanup",
        "tooltip": "The reliable daily driver - a bit slower than Turbo Flagship, more consistent output.",
        "repo_id": "bartowski/Qwen2.5-3B-Instruct-GGUF",
        "filename": "Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        "model_path": "models/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
        "kv_cache_quantization": True,
        "n_ctx": 8192, "flash_attn": True, "chat_style": "standard",
    },
}

# Measured by tests/benchmark_models.py against llama-cpp-python 0.3.26 (see
# BENCHMARKS.md). "gpu_total_mb" is whole-GPU memory in use during the run
# (pynvml), so it includes Windows and any other app on the GPU, not just
# Wisperno - the System Usage tab's "Wisperno" figure is the per-process one.
BENCHMARK_MATRIX: List[dict] = [
    {"key": "turbo", "gpu_total_mb": 3491, "ram_mb": 2311, "tok_s": 113.8, "latency_100w_s": 0.82, "fidelity_pct": 97.6},
    {"key": "standard", "gpu_total_mb": 3691, "ram_mb": 2559, "tok_s": 91.7, "latency_100w_s": 1.04, "fidelity_pct": 98.8},
]

# Where a config saved with a retired preset lands: the 3B-based ones move to
# Standard (same model family), Gemma to the default.
REMOVED_PRESET_FALLBACKS = {"flagship": "standard", "eco": "standard", "gemma_beta": DEFAULT_PRESET}


def apply_preset(llm_config, key: str) -> None:
    """Copy one preset's model settings onto an LLMConfig in place."""
    preset = MODEL_PRESETS[key]
    llm_config.repo_id = preset["repo_id"]
    llm_config.filename = preset["filename"]
    llm_config.model_path = preset["model_path"]
    llm_config.kv_cache_quantization = preset["kv_cache_quantization"]
    llm_config.n_ctx = preset["n_ctx"]
    llm_config.flash_attn = preset["flash_attn"]
    llm_config.chat_style = preset["chat_style"]


def migrate_removed_preset(app_config) -> Optional[str]:
    """If app_config names a preset that no longer exists, switch it to its
    replacement in place and return the new key; otherwise return None.
    The caller persists the change."""
    old = app_config.model_preset
    if old in MODEL_PRESETS:
        return None
    new = REMOVED_PRESET_FALLBACKS.get(old, DEFAULT_PRESET)
    app_config.model_preset = new
    apply_preset(app_config.llm, new)
    return new
