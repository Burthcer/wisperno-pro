"""
Profanity filter edge cases, "scratch that" self-correction, and the kept
last-N recordings + careful Re-transcribe.

Run: python tests/test_recovery_features.py
"""

import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

import numpy as np
from loguru import logger

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))


def test_profanity_filter_misses_and_false_hits() -> None:
    logger.info("--- Testing the profanity filter: slips, Whisper-masked words, names ---")
    from src.swear_filter import apply_profanity_filter as f, profanity_was_censored

    # Words that used to slip through every mode.
    for word in ("bullshit", "motherfucking", "dumbass", "dammit", "wtf", "fuckin'"):
        assert f(f"that is {word} here", "censor") != f"that is {word} here", word
        assert word not in f(f"that is {word} here", "remove"), word
        assert f(f"that is {word} here", "allow") == f"that is {word} here", "allow never edits a plain word"

    # Whisper's own masking: Allow restores the spoken word, Censor/Remove still catch it.
    assert f("this f**king works", "allow") == "this fucking works"
    assert f("what the f*ck", "allow") == "what the fuck"
    assert f("a s**tty b*tch", "allow") == "a shitty bitch"
    assert f("this f**king works", "censor") == "this f****** works"
    assert f("this f**king works", "remove") == "this works"
    assert f("Fuck this", "allow") == "Fuck this"
    assert f("2*3 and a*b stay", "allow") == "2*3 and a*b stay", "maths is not a swear word"

    # Remove mode leaves clean text.
    assert f("Fuck, I forgot the keys.", "remove") == "I forgot the keys."
    assert f("Yes, damn, I agree.", "remove") == "Yes, I agree."

    # Innocent words and names are left alone.
    assert f("the class will assess hello Scunthorpe", "remove") == "the class will assess hello Scunthorpe"
    assert f("I met Dick Cheney", "remove") == "I met Dick Cheney"
    assert f("he is a dick", "remove") == "he is a"

    # The model-censoring backstop still sees asterisks in the OUTPUT as censoring.
    assert profanity_was_censored("this is fucking great", "This is f***ing great.")
    assert not profanity_was_censored("this is f**king great", "This is fucking great.")
    logger.success("PASS: no slips, masked words handled, names/innocent words untouched.")


def test_profanity_masks_variants_and_false_hits() -> None:
    logger.info("--- Testing more masking styles, and that code/maths/emails are safe ---")
    from src.swear_filter import apply_profanity_filter as f, unmask_profanity as u

    assert u("that's f#cking great") == "that's fucking great" and u("what the f@ck") == "what the fuck"
    assert u("this sh$t is b*llsh*t") == "this shit is bullshit" and u("a$$hole") == "asshole"
    assert u("f*****") == "fucked" and u("motherf*****") == "motherfucker", "a different number of symbols is still understood"
    for safe in ("I use C# and pay$ off", "A$AP Rocky", "email me at a@b.com", "Call me @ noon", "Wow! amazing", "2*3 and x*y*z", "C##"):
        assert u(safe) == safe, safe
    assert f("f*ck!", "remove") == "!" and f("you f*****", "remove") == "you"
    logger.success("PASS: more mask styles caught; C#, emails, maths and punctuation left alone.")


def test_cleanup_never_drops_a_phrase_like_letting_you_know() -> None:
    logger.info("--- Testing the 'you know' idiom guard ---")
    from src.direct_formatter import format_direct
    from src.transformer import sanity_check

    assert format_direct("also, just letting you know, the chime is bad") == "Also, just letting you know, the chime is bad."
    assert format_direct("as you know, it works") == "As you know, it works."
    assert format_direct("it was, you know, kind of slow") == "It was kind of slow.", "a real filler is still removed"
    assert format_direct("do you know the answer") == "Do you know the answer?"
    raw = "Also, just letting you know, the chime is absolute ass."
    assert "letting you know" in sanity_check(raw, "Also, just letting the chime is absolute ass.")
    assert sanity_check(raw, "Also, just letting you know, the chime is absolute ass.") is None
    logger.success("PASS: idioms survive both the rule-based formatter and the AI cleanup check.")


def test_self_correction() -> None:
    logger.info("--- Testing spoken retractions ---")
    from src.self_correction import apply_self_correction as f

    assert f("Let's meet on Monday. No, no, let's meet on Tuesday.") == "Let's meet on Tuesday."
    assert f("Send it to Sam. Scratch that. Send it to Priya.") == "Send it to Priya."
    assert f("First point.\n\nSecond point. No wait, third point.") == "First point.\n\nThird point."
    assert f("I will go. Never mind, I'll stay.") == "I'll stay."
    assert f("Send it to Sam. Scratch that.") == ""
    # Ordinary speech must never be cut.
    for safe in ("No, no problem at all.", "Actually no one came.", "Nothing to retract. It's fine.", "I never mind waiting."):
        assert f(safe) == safe, safe
    logger.success("PASS: cues remove the previous sentence only; normal sentences untouched.")


def test_recent_audio_keeps_only_the_newest() -> None:
    logger.info("--- Testing the last-N recordings buffer ---")
    from src import recent_audio

    with tempfile.TemporaryDirectory() as tmp, mock.patch("src.recent_audio.get_app_data_dir", return_value=Path(tmp)):
        tone = (0.3 * np.sin(np.linspace(0, 440, 16000))).astype(np.float32)
        for history_id in range(1, 6):
            recent_audio.save(history_id, tone, keep=3)
        assert [recent_audio.has_audio(i) for i in range(1, 6)] == [False, False, True, True, True]
        loaded = recent_audio.load(5)
        assert loaded is not None and len(loaded) == 16000 and abs(float(loaded.max()) - 0.3) < 0.01
        recent_audio.save(9, tone, keep=0)
        assert not recent_audio.has_audio(9), "keep=0 stores nothing"
        recent_audio.prune(1)
        assert [recent_audio.has_audio(i) for i in (3, 4, 5)] == [False, False, True]
    logger.success("PASS: only the newest 3 clips survive; prune and keep=0 behave.")


def test_retranscribe_worker_replaces_the_row() -> None:
    logger.info("--- Testing History -> Re-transcribe uses the careful method and updates the row ---")
    from src.database import WispernoDB
    from src.workers import RetranscribeWorker

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows keeps the sqlite file open
        db = WispernoDB(Path(tmp) / "t.db")
        row_id = db.add_history("2026-01-01T00:00:00", 3.0, "garbled text", "Garbled text.", "polish", 100.0)

        calls = {}
        transcriber = types.SimpleNamespace(transcribe=lambda audio, careful=False: calls.setdefault("careful", careful) and "the real words said here")
        transformer = types.SimpleNamespace(profanity_filter="allow", transform=lambda text, mode="polish": "The real words said here.")
        results, errors = [], []
        worker = RetranscribeWorker(row_id, np.zeros(16000, dtype=np.float32), transcriber, transformer, db)
        worker.result_ready.connect(results.append)
        worker.error.connect(errors.append)
        worker.run()

        assert calls["careful"] is True, "must use the careful method, not the normal one"
        assert not errors and results[0]["polished_transcript"] == "The real words said here."
        saved = [r for r in db.list_history() if r["id"] == row_id][0]
        assert saved["raw_transcript"] == "the real words said here" and saved["polished_transcript"] == "The real words said here."
        assert saved["word_count"] == 5

        empty = RetranscribeWorker(row_id, np.zeros(16000, dtype=np.float32),
                                   types.SimpleNamespace(transcribe=lambda a, careful=False: ""), transformer, db)
        failures = []
        empty.error.connect(failures.append)
        empty.run()
        assert failures and [r for r in db.list_history() if r["id"] == row_id][0]["polished_transcript"] == "The real words said here.", \
            "a failed re-run must leave the old text alone"
    logger.success("PASS: careful pass used, row overwritten, a failed re-run changes nothing.")


def test_careful_transcription_loosens_the_gates() -> None:
    logger.info("--- Testing the careful Whisper settings ---")
    from src.config import WhisperConfig
    from src.transcriber import Transcriber

    seen = []

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            seen.append(kwargs)
            return iter([]), types.SimpleNamespace(duration_after_vad=1.0)

    t = Transcriber.__new__(Transcriber)
    t.config = WhisperConfig()
    t.model = FakeModel()
    t._run_transcription(np.zeros(16000, dtype=np.float32), "prompt", vad_filter=True, vad_params={}, careful=False)
    t._run_transcription(np.zeros(16000, dtype=np.float32), "", vad_filter=False, vad_params=None, careful=True)
    normal, careful = seen
    assert normal["no_speech_threshold"] == 0.6 and normal["log_prob_threshold"] == -1.0 and normal["temperature"] == 0.0
    assert careful["no_speech_threshold"] is None and careful["log_prob_threshold"] is None
    assert careful["compression_ratio_threshold"] is None and careful["beam_size"] >= 8
    assert isinstance(careful["temperature"], tuple) and len(careful["temperature"]) > 1
    logger.success("PASS: careful mode drops the rejection gates, widens the beam, allows temperature retries.")


def run_all_tests() -> None:
    test_profanity_filter_misses_and_false_hits()
    test_profanity_masks_variants_and_false_hits()
    test_cleanup_never_drops_a_phrase_like_letting_you_know()
    test_self_correction()
    test_recent_audio_keeps_only_the_newest()
    test_retranscribe_worker_replaces_the_row()
    test_careful_transcription_loosens_the_gates()
    logger.success("ALL RECOVERY FEATURE TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
