"""
Whisper output filters (src/transcriber.py) and startup warm-up
(src/engine.py), run against a stand-in Whisper model so they need no GPU:
  - stock hallucinations ("Thank you.", "Thanks for watching!") are dropped
    only when there was (almost) no speech - a real "thank you" survives
  - prompt text copied into the output is removed
  - the startup warm-up touches both models and never fails the load

Run: python tests/test_whisper_filters.py
"""

import sys
import types
from pathlib import Path
from unittest import mock

import numpy as np
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("faster_whisper", types.SimpleNamespace(WhisperModel=object))

PROMPT = "Hello, welcome. Please transcribe with clear punctuation, commas, and sentence structure."


class FakeWhisper:
    """Returns `with_vad` when called with vad_filter=True, else `without_vad`."""

    def __init__(self, with_vad: str, without_vad: str = "", speech_sec: float = 2.0):
        self.outputs = {True: with_vad, False: without_vad}
        self.speech_sec = speech_sec
        self.calls = []

    def transcribe(self, audio, vad_filter=False, **kwargs):
        self.calls.append(vad_filter)
        text = self.outputs[bool(vad_filter)]
        words = [types.SimpleNamespace(word=" " + w, start=i * 0.3, end=i * 0.3 + 0.2) for i, w in enumerate(text.split())]
        segments = [types.SimpleNamespace(words=words)] if words else []
        info = types.SimpleNamespace(duration_after_vad=self.speech_sec if vad_filter else 0.0)
        return iter(segments), info


def _transcriber(model: FakeWhisper):
    from src.config import WhisperConfig
    from src.transcriber import Transcriber
    from src.vocabulary import Vocabulary

    t = Transcriber.__new__(Transcriber)
    t.config = WhisperConfig(initial_prompt=PROMPT)
    t.vocabulary = Vocabulary(db=None)
    t.model = model
    return t


def _run(with_vad, without_vad="", speech_sec=2.0):
    model = FakeWhisper(with_vad, without_vad, speech_sec)
    return _transcriber(model).transcribe(np.zeros(16000, dtype=np.float32)), model


def test_hallucinations_dropped_only_without_speech() -> None:
    logger.info("--- Testing stock Whisper hallucinations on silence ---")
    out, model = _run("", without_vad="Thank you.")
    assert out == "" and model.calls == [True, False], out  # VAD found nothing -> retry -> invented "Thank you."
    out, _ = _run("Thanks for watching!", speech_sec=0.1)
    assert out == "", out  # VAD kept only 0.1s of "speech"
    out, _ = _run("", without_vad="Hello, welcome.")
    assert out == "", out  # the prompt's own opening copied back on silence

    out, _ = _run("Thank you.", speech_sec=1.2)
    assert out == "Thank you.", out  # a real, spoken thank-you
    out, _ = _run("", without_vad="yes")
    assert out == "yes", out  # quiet short answer VAD missed: the retry still rescues it
    out, _ = _run("Hello, welcome to the meeting.")
    assert out == "Hello, welcome to the meeting.", out
    logger.success("PASS: hallucinations dropped on near-silence; real short speech kept.")


def test_prompt_leak_removed() -> None:
    logger.info("--- Testing prompt text copied into the transcript is removed ---")
    out, _ = _run("Please transcribe with clear punctuation, commas, and sentence structure. Let's meet at noon.")
    assert out == "Let's meet at noon.", out
    out, _ = _run("Let's meet at noon. Technical terms: GitHub, PyTorch.")
    assert out == "Let's meet at noon.", out
    out, _ = _run("Technical terms are hard to remember.")
    assert out == "Technical terms are hard to remember.", out
    logger.success("PASS: leaked prompt sentences removed, ordinary sentences untouched.")


def test_warm_up_touches_both_models_and_never_raises() -> None:
    sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
    from src.engine import WispernoEngine

    logger.info("--- Testing the startup warm-up ---")
    engine = WispernoEngine.__new__(WispernoEngine)
    engine.transcriber, engine.transformer = mock.Mock(), mock.Mock()
    engine._warm_up_models()
    assert engine.transcriber.transcribe.call_count == 1
    engine.transformer.transform.assert_called_once()
    assert engine.transformer.transform.call_args.kwargs["mode"] == "polish"

    engine.transformer.llm = None  # no LLM weights on disk: only Whisper is warmed
    engine.transformer.transform.reset_mock()
    engine._warm_up_models()
    assert not engine.transformer.transform.called

    engine.transcriber.transcribe.side_effect = RuntimeError("cuDNN missing")
    engine._warm_up_models()  # must not raise - a failed warm-up never blocks startup
    logger.success("PASS: warm-up runs Whisper + LLM once, skips a missing LLM, and swallows failures.")


def run_all_tests() -> None:
    test_hallucinations_dropped_only_without_speech()
    test_prompt_leak_removed()
    test_warm_up_touches_both_models_and_never_raises()
    logger.success("ALL WHISPER FILTER / WARM-UP TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
