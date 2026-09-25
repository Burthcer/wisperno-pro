"""
Engine preset lineup (src/presets.py): only Turbo Flagship and Standard ship,
both under the 4GB VRAM target, and a config saved with a retired preset
(Flagship / Eco / Gemma Beta) is moved to a supported one.

Run: python tests/test_presets.py
"""

import sys
import tempfile
from pathlib import Path

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def test_only_supported_presets_ship() -> None:
    from src.presets import BENCHMARK_MATRIX, DEFAULT_PRESET, MODEL_PRESETS

    logger.info("--- Testing the shipped preset lineup ---")
    assert set(MODEL_PRESETS) == {"turbo", "standard"}, sorted(MODEL_PRESETS)
    assert DEFAULT_PRESET in MODEL_PRESETS
    assert {row["key"] for row in BENCHMARK_MATRIX} == set(MODEL_PRESETS)
    assert all(row["gpu_total_mb"] < 4096 for row in BENCHMARK_MATRIX), "every preset must stay under 4GB"
    logger.success("PASS: Turbo Flagship + Standard only, both under 4GB.")


def test_shipped_config_uses_a_supported_preset() -> None:
    from src.config import load_config
    from src.presets import MODEL_PRESETS

    logger.info("--- Testing config/config.yaml points at a supported preset ---")
    config = load_config()
    assert config.model_preset in MODEL_PRESETS, config.model_preset
    assert config.llm.model_path == MODEL_PRESETS[config.model_preset]["model_path"]
    logger.success(f"PASS: shipped config uses '{config.model_preset}'.")


def test_retired_presets_migrate() -> None:
    from src.config import load_config, save_config
    from src.presets import MODEL_PRESETS, migrate_removed_preset

    logger.info("--- Testing retired presets migrate to a supported one ---")
    cases = {
        "flagship": ("standard", "models/Qwen2.5-3B-Instruct-Q8_0.gguf"),
        "eco": ("standard", "models/wisperno-custom-v1.gguf"),
        "gemma_beta": ("turbo", "models/gemma-2-2b-it-Q4_K_M.gguf"),
        "something_unknown": ("turbo", "models/whatever.gguf"),
    }
    for old_key, (expected, old_path) in cases.items():
        config = load_config()
        config.model_preset = old_key
        config.llm.model_path = old_path
        config.llm.flash_attn = False
        config.llm.chat_style = "gemma"
        assert migrate_removed_preset(config) == expected, old_key
        preset = MODEL_PRESETS[expected]
        assert config.model_preset == expected
        assert config.llm.model_path == preset["model_path"]
        assert config.llm.filename == preset["filename"]
        assert config.llm.flash_attn == preset["flash_attn"]
        assert config.llm.chat_style == preset["chat_style"]
        assert config.llm.kv_cache_quantization == preset["kv_cache_quantization"]

        # Survives a save/load round-trip, and a second pass is a no-op.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config(config, str(path))
            reloaded = load_config(str(path))
        assert reloaded.model_preset == expected
        assert migrate_removed_preset(reloaded) is None

    for key in MODEL_PRESETS:
        config = load_config()
        config.model_preset = key
        assert migrate_removed_preset(config) is None, f"'{key}' is supported and must not be migrated"
    logger.success("PASS: Flagship/Eco -> Standard, Gemma Beta/unknown -> Turbo Flagship; supported presets untouched.")


def run_all_tests() -> None:
    test_only_supported_presets_ship()
    test_shipped_config_uses_a_supported_preset()
    test_retired_presets_migrate()
    logger.success("ALL PRESET TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
