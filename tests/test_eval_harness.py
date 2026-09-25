"""
The personal test-set harness: WER/similarity scoring (src/eval_metrics.py),
WAV save/load (src/test_recordings.py), and scripts/eval_dictation.py run end
to end against a stand-in transcriber - no GPU or microphone needed.

Run: python tests/test_eval_harness.py
"""

import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

import numpy as np
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def test_word_error_rate() -> None:
    from src.eval_metrics import normalize_words, word_error_rate

    logger.info("--- Testing word error rate ---")
    assert word_error_rate("Let's meet at 4 PM.", "lets meet at four pm") == 0.2  # "let's" vs "lets": 1 of 5 words
    assert word_error_rate("let's meet at four pm", "Let's meet at 4 PM.") == 0.0  # casing/punct/digits don't count
    assert word_error_rate("the cat sat", "the cat sat down") == 1 / 3  # one insertion
    assert word_error_rate("the cat sat", "the sat") == 1 / 3  # one deletion
    assert word_error_rate("the cat sat", "a dog sat") == 2 / 3  # two substitutions
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("four PM, up twenty percent", "4pm, up 20%") == 0.0
    assert normalize_words("It's GitHub-based, isn't it?") == ["it's", "github", "based", "isn't", "it"]
    logger.success("PASS: WER counts word errors only, ignoring casing, punctuation and 0-20 digit/word forms.")


def test_text_similarity() -> None:
    from src.eval_metrics import exact_match, text_similarity

    logger.info("--- Testing formatted-text similarity ---")
    assert exact_match("1. Buy milk.\n2. Get eggs.", " 1. Buy  milk.\n\n2. Get eggs. ")
    assert not exact_match("1. Buy milk.\n2. Get eggs.", "Buy milk. Get eggs.")
    assert 0 < text_similarity("1. Buy milk.\n2. Get eggs.", "Buy milk. Get eggs.") < 1
    logger.success("PASS: similarity ignores stray whitespace but not line structure.")


def test_wav_round_trip_and_save() -> None:
    from src import test_recordings

    logger.info("--- Testing WAV save/load ---")
    audio = (0.5 * np.sin(np.linspace(0, 200 * np.pi, 16000))).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(test_recordings, "get_app_data_dir", lambda: Path(tmp)):
            wav = test_recordings.save_recording(audio, "um hello", "Hello.")
        assert wav.parent == Path(tmp) / "recordings"
        back = test_recordings.read_wav(wav)
        assert back.shape == audio.shape and np.max(np.abs(back - audio)) < 1e-3
        assert wav.with_name(wav.stem + ".heard.txt").read_text(encoding="utf-8") == "um hello"
        assert wav.with_name(wav.stem + ".pasted.txt").read_text(encoding="utf-8") == "Hello."
    logger.success("PASS: recordings round-trip as 16kHz mono WAV with their transcripts.")


def test_eval_script_end_to_end() -> None:
    from src.test_recordings import write_wav

    logger.info("--- Testing scripts/eval_dictation.py end to end (stand-in transcriber) ---")
    heard_by_length = {16000: "um let's meet at 3 pm", 32000: "first buy milk second get eggs"}

    class FakeTranscriber:
        def __init__(self, config=None, vocabulary=None):
            pass

        def transcribe(self, audio):
            return heard_by_length.get(len(audio), "")

    fake_module = types.ModuleType("src.transcriber")
    fake_module.Transcriber = FakeTranscriber

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        silence = np.zeros(16000, dtype=np.float32)
        write_wav(folder / "a.wav", silence)
        (folder / "a.txt").write_text("let's meet at four pm", encoding="utf-8")
        write_wav(folder / "b.wav", np.zeros(32000, dtype=np.float32))
        (folder / "b.txt").write_text("first buy milk second get eggs", encoding="utf-8")
        write_wav(folder / "unscored.wav", silence)  # no .txt -> skipped

        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import eval_dictation

        with mock.patch.dict(sys.modules, {"src.transcriber": fake_module}), \
                mock.patch.dict(os.environ, {"APPDATA": tmp}):
            args = types.SimpleNamespace(folder=str(folder), llm=False, save="base", compare=None, verbose=False)
            from src.config import load_config
            result = eval_dictation.run_recordings(args, load_config())
            heard_by_length[16000] = "let's meet at four pm"
            args.save, args.compare = None, "base"
            improved = eval_dictation.run_recordings(args, load_config())

        saved = json.loads((folder / "results" / "base.json").read_text(encoding="utf-8"))
    assert result["summary"]["clips"] == 2
    # Clip a: "um" inserted + "3" heard for "four" = 2 errors; clip b: 0. Over 5 + 6 reference words.
    assert abs(result["summary"]["wer"] - 2 / 11) < 1e-9, result["summary"]["wer"]
    assert improved["summary"]["wer"] == 0.0
    assert saved["summary"]["clips"] == 2
    logger.success("PASS: eval script scores clips, skips unreferenced ones, saves and compares runs.")


def run_all_tests() -> None:
    test_word_error_rate()
    test_text_similarity()
    test_wav_round_trip_and_save()
    test_eval_script_end_to_end()
    logger.success("ALL EVAL HARNESS TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
