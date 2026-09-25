"""
LLM cleanup path (item 3 of the improvement plan), exercised with a stand-in
model so it runs anywhere:
  - when the LLM's output is rejected (or the call fails), the fallback is the
    instant formatter's cleanup, not the raw transcript with its "um"s
  - short, already-clean Polish dictations skip the LLM entirely
  - the user's dictionary spellings are given to the model and restored after

Run: python tests/test_llm_cleanup.py
"""

import sys
import tempfile
import types
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))


def _transformer(model_output=None, raises=None, vocabulary=None):
    from src.config import load_config
    from src.transformer import Transformer

    config = load_config()
    t = Transformer.__new__(Transformer)
    t.config, t.prompts, t.profanity_filter = config.llm, config.prompts, "allow"
    t.vocabulary, t.last_fallback_applied = vocabulary, False
    t.llm = mock.Mock()
    if raises:
        t.llm.create_chat_completion.side_effect = raises
    else:
        t.llm.create_chat_completion.return_value = {"choices": [{"message": {"content": model_output}}]}
    return t


def _vocabulary(pairs):
    from src.database import WispernoDB
    from src.vocabulary import Vocabulary

    tmp = tempfile.mkdtemp()
    db = WispernoDB(str(Path(tmp) / "v.db"))
    with db._cursor() as cur:
        cur.execute("DELETE FROM dictionary")
    for word, replacement in pairs:
        db.add_dictionary_entry(word, replacement)
    return Vocabulary(db=db)


def test_rejected_output_falls_back_to_instant_cleanup() -> None:
    logger.info("--- Testing a rejected LLM output falls back to the instant formatter ---")
    raw = "um so uh can you explain how python decorators work"
    # The model answered the question instead of cleaning it - a guardrail trip.
    t = _transformer("Sure, here is how decorators work: they wrap a function in another function.")
    out = t.transform(raw, mode="polish")
    assert t.last_fallback_applied
    assert out == "So can you explain how python decorators work?", out  # fillers gone, still a question
    logger.success(f"PASS: guardrail fallback -> {out!r}")


def test_llm_error_falls_back_to_instant_cleanup() -> None:
    logger.info("--- Testing an LLM exception falls back to the instant formatter ---")
    t = _transformer(raises=RuntimeError("CUDA out of memory"))
    out = t.transform("um first we fix the bug uh second we ship it", mode="polish")
    assert t.last_fallback_applied
    assert out == "1. We fix the bug.\n2. We ship it.", out
    logger.success("PASS: LLM error -> fillers removed and list formatted anyway.")


def test_short_clean_detection() -> None:
    from src.direct_formatter import is_short_and_clean

    logger.info("--- Testing which utterances are clean enough to skip the LLM ---")
    for text in ("Sounds good, see you at 3.", "Can you send me the file?", "I'm running late today",
                 "Thanks for the update."):
        assert is_short_and_clean(text), text
    for text in ("um sounds good", "see you at 3 wait no 4", "I mean, it's fine", "the the file is here",
                 "call him at 3 actually 4 pm", "can you like, send it",
                 "this is a much longer dictation that goes on for well more than twelve words in total"):
        assert not is_short_and_clean(text), text
    logger.success("PASS: short/clean vs filler, corrections, stutters and long dictation.")


def _run_worker(raw, mode, system_prompt=None, use_direct=False):
    """Runs the real InferenceWorker.run() synchronously with stand-ins around it."""
    sys.modules.setdefault("src.hotkey_manager", types.SimpleNamespace(HotkeyManager=object))
    from src.workers import InferenceWorker

    transcriber = mock.Mock(); transcriber.transcribe.return_value = raw
    transformer = mock.Mock(); transformer.profanity_filter = "allow"
    transformer.transform.return_value = "LLM OUTPUT"
    transformer.transform_with_prompt.return_value = "LLM OUTPUT"
    injector = mock.Mock(); injector.inject_text.return_value = True
    worker = InferenceWorker(
        [0.0], transcriber, transformer, injector, None, {}, mode, 1000.0,
        system_prompt=system_prompt, use_direct_formatter=use_direct,
    )
    worker.run()
    return injector.inject_text.call_args[0][0], transformer


def test_worker_skips_llm_for_short_clean_polish() -> None:
    logger.info("--- Testing the dictation worker skips the LLM only when it can't help ---")
    pasted, t = _run_worker("sounds good, see you at 3", "polish")
    assert pasted == "Sounds good, see you at 3." and not t.transform.called, pasted

    pasted, t = _run_worker("sounds good, see you at 3", "polish", system_prompt="(Alt+C prompt)")
    assert pasted == "Sounds good, see you at 3." and not t.transform_with_prompt.called, pasted

    pasted, t = _run_worker("um so see you at 3 wait no 4", "polish")
    assert pasted == "LLM OUTPUT" and t.transform.called

    pasted, t = _run_worker("fix the login bug", "prompt_engineer")  # other modes always use their prompt
    assert pasted == "LLM OUTPUT" and t.transform.called
    logger.success("PASS: short clean Polish -> instant; filler/corrections or other modes -> LLM.")


def test_dictionary_spellings_reach_and_survive_the_llm() -> None:
    logger.info("--- Testing dictionary spellings in the prompt and restored in the output ---")
    vocab = _vocabulary([("git hub", "GitHub"), ("cloud code", "Claude Code"), ("screen shot", "screenshot")])
    t = _transformer("I pushed it to Github and ran it in claude code, then took a Screenshot.", vocabulary=vocab)
    out = t.transform("i pushed it to github and ran it in claude code then took a screenshot", mode="polish")
    assert out == "I pushed it to GitHub and ran it in Claude Code, then took a Screenshot.", out

    sent_prompt = t.llm.create_chat_completion.call_args.kwargs["messages"][0]["content"]
    base_prompt = t.prompts["polish"]
    assert sent_prompt.startswith(base_prompt), "dictionary must be appended so the cached prompt prefix survives"
    assert "GitHub, Claude Code, screenshot" in sent_prompt or all(
        term in sent_prompt for term in ("GitHub", "Claude Code", "screenshot")
    )

    plain = _transformer("Fine.", vocabulary=_vocabulary([]))
    plain.transform("fine", mode="polish")
    assert plain.llm.create_chat_completion.call_args.kwargs["messages"][0]["content"] == base_prompt
    logger.success("PASS: terms appended to the prompt, casing restored ('Github' -> 'GitHub'), "
                   "lowercase terms never force a lowercase sentence start.")


def run_all_tests() -> None:
    test_rejected_output_falls_back_to_instant_cleanup()
    test_llm_error_falls_back_to_instant_cleanup()
    test_short_clean_detection()
    test_worker_skips_llm_for_short_clean_polish()
    test_dictionary_spellings_reach_and_survive_the_llm()
    logger.success("ALL LLM CLEANUP TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
