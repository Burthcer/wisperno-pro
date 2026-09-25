"""
Custom dictionary (src/vocabulary.py, src/ui/dictionary_tab.py):
  - a word can be added on its own (no "heard as" needed)
  - dictionary words are packed into Whisper's prompt first, then its
    separate hotwords slot, newest first, with the style sentence kept last
  - near-miss spellings Whisper writes as names are snapped to the
    dictionary spelling, and nothing else is touched

The sound-alike cases below are real Whisper large-v3-turbo outputs from
tests/fixtures/vocab_cases.json.

Run: python tests/test_dictionary.py
"""

import json
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

VOCAB = json.loads((BASE_DIR / "tests" / "fixtures" / "vocab_cases.json").read_text(encoding="utf-8"))


def _vocabulary(terms):
    from src.database import WispernoDB
    from src.vocabulary import Vocabulary

    db = WispernoDB(str(Path(tempfile.mkdtemp()) / "d.db"))
    with db._cursor() as cur:
        cur.execute("DELETE FROM dictionary")
    for t in terms:
        db.add_dictionary_entry(t, t)
    return Vocabulary(db=db)


def test_sound_alike_correction_real_whisper_misses() -> None:
    logger.info("--- Testing sound-alike correction on real Whisper near-misses ---")
    vocab = _vocabulary(VOCAB["dictionary"])
    fixes = {
        "Saw the user profiles in Superbase for now.": "Saw the user profiles in Supabase for now.",
        "Whisper Note transcribes everything locally on my laptop.": "Wisperno transcribes everything locally on my laptop.",
        "WhisperNo transcribes everything locally on my laptop.": "Wisperno transcribes everything locally on my laptop.",
        "The dashboard is written in Svelte and deployed on Versil.": "The dashboard is written in Svelte and deployed on Vercel.",
        "NuYen will set up Kubernetes for the staging cluster.": "Nguyen will set up Kubernetes for the staging cluster.",
    }
    for heard, want in fixes.items():
        assert vocab.correct_sound_alikes(heard) == want, (heard, vocab.correct_sound_alikes(heard))
    untouched = [
        "The model was trained in PyTorch on a single GPU.",       # a correct term's neighbor is never swallowed
        "Our GraphQL server talks to Postgres through a connection pool.",
        "The desktop app is built with Tori instead of Electron.",  # too short to judge safely - left alone
        "I think we should go with the super base plan.",           # not written as a name
    ]
    for text in untouched:
        assert vocab.correct_sound_alikes(text) == text, (text, vocab.correct_sound_alikes(text))
    logger.success("PASS: 5 real near-misses corrected; correct/uncertain/ordinary text untouched.")


def test_sound_alike_has_no_false_positives_on_other_text() -> None:
    logger.info("--- Testing sound-alike correction leaves every other fixture text alone ---")
    extra = ("React Angular Django Flask FastAPI Redis Kafka Terraform Docker Nginx Grafana Pandas NumPy TensorFlow "
             "Keras TypeScript JavaScript Rust Golang Kotlin Swift Xcode Jenkins GitLab Notion Slack Zoom Figma "
             "Linear Stripe Twilio Azure").split()
    vocab = _vocabulary(VOCAB["dictionary"] + extra)
    texts = []
    for name in ("llm_cases.json", "formatting_cases.json", "speech_cases.json"):
        for case in json.loads((BASE_DIR / "tests" / "fixtures" / name).read_text(encoding="utf-8")):
            texts += [case.get("raw") or case.get("say") or "", case.get("expected", "")]
    changed = [t for t in texts if t and vocab.correct_sound_alikes(t) != t]
    assert not changed, changed
    logger.success(f"PASS: {len(texts)} unrelated texts unchanged with a {len(vocab.canonical_terms())}-word dictionary.")


def test_whisper_bias_packing() -> None:
    logger.info("--- Testing dictionary packing into Whisper's prompt + hotwords ---")
    count = lambda text: max(1, len(text) // 3)  # noqa: E731 - same fallback the app uses without a tokenizer
    base = "Hello, welcome. Please transcribe with clear punctuation."

    small = _vocabulary(["PyTorch", "Supabase"])
    prompt, hotwords = small.build_whisper_bias(base, count)
    assert prompt.startswith("Technical terms: ") and prompt.endswith(base), prompt  # style sentence last
    assert "Supabase, PyTorch" in prompt and hotwords is None  # newest first; all fit in the prompt

    many = [f"Term{i:03d}" for i in range(200)]
    big = _vocabulary(many)
    prompt, hotwords = big.build_whisper_bias(base, count)
    assert prompt.endswith(base) and hotwords, "an overflowing dictionary must spill into hotwords"
    assert "Term199" in prompt, "the newest words get the prompt"
    in_prompt = prompt.count("Term")
    in_hot = hotwords.count("Term")
    assert in_prompt + in_hot < len(many), "more than fits: the oldest are left out, not truncated mid-word"
    assert count(prompt) <= 223 and count(hotwords) <= 223, (count(prompt), count(hotwords))

    reserved, _ = big.build_whisper_bias(base, count, reserve_tokens=30)
    assert reserved.count("Term") < in_prompt, "reserve_tokens must leave room for chunk context"
    logger.success(f"PASS: small dictionary all in prompt; 200 words -> {in_prompt} prompt + {in_hot} hotwords, newest first.")


def test_transcriber_sends_hotwords_to_whisper() -> None:
    import numpy as np

    sys.modules.setdefault("faster_whisper", types.SimpleNamespace(WhisperModel=object))
    from src.config import WhisperConfig
    from src.transcriber import Transcriber

    logger.info("--- Testing the transcriber passes prompt + hotwords and applies sound-alike fixes ---")
    seen = []

    class FakeWhisper:
        def transcribe(self, audio, **kwargs):
            seen.append(kwargs)
            words = [types.SimpleNamespace(word=" " + w, start=i * 0.3, end=i * 0.3 + 0.2)
                     for i, w in enumerate("Store it in Superbase please.".split())]
            return iter([types.SimpleNamespace(words=words)]), types.SimpleNamespace(duration_after_vad=2.0)

    t = Transcriber.__new__(Transcriber)
    t.config = WhisperConfig()
    t.vocabulary = _vocabulary([f"Term{i:03d}" for i in range(120)] + ["Supabase"])
    t.model = FakeWhisper()
    out = t.transcribe(np.zeros(16000, dtype=np.float32))
    assert out == "Store it in Supabase please.", out
    assert seen[0]["hotwords"] and "Technical terms:" in seen[0]["initial_prompt"], seen[0]
    logger.success("PASS: hotwords reach Whisper; 'Superbase' -> 'Supabase' after transcription.")


def test_dictionary_tab_accepts_a_word_on_its_own() -> None:
    sys.modules.setdefault("winreg", mock.MagicMock())
    from PySide6.QtWidgets import QApplication
    from src.ui.dictionary_tab import DictionaryTab

    logger.info("--- Testing the Dictionary tab: a word alone, and a word with 'heard as' ---")
    app = QApplication.instance() or QApplication([])  # noqa: F841
    vocab = _vocabulary([])
    engine = mock.Mock(vocabulary=vocab, db=vocab.db)
    tab = DictionaryTab(engine)
    tab.repl_in.setText("Supabase")
    tab._add()
    tab.repl_in.setText("PyTorch")
    tab.word_in.setText("pie torch")
    tab._add()
    rows = {(e["word"], e["replacement"]) for e in vocab.db.list_dictionary()}
    assert rows == {("Supabase", "Supabase"), ("pie torch", "PyTorch")}, rows
    cells = {tab.table.item(r, 0).text(): tab.table.item(r, 1).text() for r in range(tab.table.rowCount())}
    assert cells == {"Supabase": "—", "PyTorch": '"pie torch" → PyTorch'}, cells
    assert vocab.apply_replacements("i use supabase and pie torch") == "i use Supabase and PyTorch"
    logger.success("PASS: word-only entries work and also fix casing; 'heard as' still rewrites.")


def run_all_tests() -> None:
    test_sound_alike_correction_real_whisper_misses()
    test_sound_alike_has_no_false_positives_on_other_text()
    test_whisper_bias_packing()
    test_transcriber_sends_hotwords_to_whisper()
    test_dictionary_tab_accepts_a_word_on_its_own()
    logger.success("ALL DICTIONARY TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
