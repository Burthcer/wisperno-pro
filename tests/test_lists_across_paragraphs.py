"""
Lists spoken across pauses. src/transcriber.py starts a new paragraph at
every pause of 1.3s+, and people pause before each point when answering in
points - so "I will answer both of your questions.\\n\\nFirst, ...\\n\\n
Second, ..." must still become one introduced list, on every path:

  - the instant formatter (format_direct) - the fixture cases
  - the LLM path's pre-format (what the model is handed)
  - the LLM path's backstop (what the model returned)
  - long dictations split into several LLM chunks

Real model output isn't needed to prove the plumbing: the stand-in models
below either echo what they were given or flatten it back into paragraphs.

Run: python tests/test_lists_across_paragraphs.py
"""

import json
import re
import sys
import types
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

SPOKEN = ("I will answer both of your questions.\n\nFirst, I don't speak in English.\n\n"
          "Second, I only want the app to be in English.")
LISTED = ("I will answer both of your questions:\n1. I don't speak in English.\n"
          "2. I only want the app to be in English.")
CASES = json.loads((BASE_DIR / "tests" / "fixtures" / "formatting_cases.json").read_text(encoding="utf-8"))


def _fenced(messages) -> str:
    content = messages[-1]["content"]
    m = re.search(r'"""\n(.*)\n"""', content, re.DOTALL)
    return m.group(1) if m else content


def _transformer(reply):
    """reply(handed_text) -> what the stand-in model answers."""
    from src.config import load_config
    from src.transformer import Transformer

    config = load_config()
    t = Transformer.__new__(Transformer)
    t.config, t.prompts, t.profanity_filter = config.llm, config.prompts, "allow"
    t.vocabulary, t.last_fallback_applied, t.wrap_transcript = None, False, True
    t.handed = []

    def complete(messages, **kwargs):
        handed = _fenced(messages)
        t.handed.append(handed)
        return {"choices": [{"message": {"content": reply(handed)}}]}

    t.llm = mock.Mock()
    t.llm.create_chat_completion.side_effect = complete
    return t


def test_instant_formatter_fixture_cases() -> None:
    from src.direct_formatter import format_direct

    logger.info("--- Testing every across-pauses fixture through the instant formatter ---")
    across = [c for c in CASES if "across pauses" in c["name"] or c["name"].startswith("implicit")]
    assert len(across) >= 15, len(across)
    failures = [(c["name"], format_direct(c["raw"])) for c in across if format_direct(c["raw"]) != c["expected"]]
    assert not failures, failures
    logger.success(f"PASS: {len(across)} across-pauses fixtures (lists and must-stay-prose) exact.")


def test_llm_is_handed_the_list() -> None:
    logger.info("--- Testing the LLM path lays the list out before the model sees it ---")
    t = _transformer(lambda handed: handed)  # a model that changes nothing
    out = t.transform(SPOKEN, mode="polish")
    assert t.handed[0] == LISTED, t.handed[0]
    assert out == LISTED, out
    logger.success("PASS: the model is handed one introduced list, not three paragraphs.")


def test_llm_backstop_rebuilds_a_flattened_list() -> None:
    logger.info("--- Testing the backstop when the model returns the points as paragraphs ---")
    t = _transformer(lambda handed: SPOKEN)  # a model that undoes the list
    out = t.transform(SPOKEN, mode="polish")
    assert out == LISTED, out
    logger.success("PASS: paragraphs from the model are joined back into the list.")


def test_llm_path_keeps_prose_paragraphs() -> None:
    logger.info("--- Testing ordinary paragraphs keep their breaks on the LLM path ---")
    prose = "At first I thought it was broken.\n\nThen I tried it for the second time and it worked."
    t = _transformer(lambda handed: handed)
    assert t.transform(prose, mode="polish") == prose
    logger.success("PASS: prose mentioning first/second stays two paragraphs.")


def test_long_dictation_never_splits_a_list() -> None:
    from src.transformer import CHUNK_WORD_TARGET, Transformer

    logger.info("--- Testing long-dictation chunking with a list spoken across pauses ---")
    # Neutral filler - no list cue words ("number 3" would rightly continue a list).
    filler = " ".join(f"The team reviewed the report in detail on day {n} of the quarter." for n in range(1, 40))
    text = f"{filler}\n\n{SPOKEN}\n\n{filler}"
    assert len(text.split()) > CHUNK_WORD_TARGET

    chunks = Transformer._split_into_chunks(text)
    assert len(chunks) >= 2
    assert all(len(c.split()) <= CHUNK_WORD_TARGET or "\n" in c for c, _ in chunks)

    t = _transformer(lambda handed: handed)
    out = t.transform(text, mode="polish")
    assert LISTED in out, out
    assert "\n\n" + LISTED + "\n\n" in out, "the list must stay its own block between the prose paragraphs"
    assert len(t.handed) >= 2 and sum(LISTED in h for h in t.handed) == 1, "the list must reach one chunk, whole"
    logger.success(f"PASS: {len(t.handed)} LLM chunks, list intact in one of them, paragraph breaks kept.")


def test_long_prose_paragraph_still_splits_at_sentences() -> None:
    from src.transformer import CHUNK_WORD_TARGET, Transformer

    logger.info("--- Testing a single over-long paragraph is still cut at sentence ends ---")
    para = " ".join(f"The team reviewed the long report again on day {n}." for n in range(1, 120))
    chunks = Transformer._split_into_chunks(para)
    assert len(chunks) >= 2 and all(len(c.split()) <= CHUNK_WORD_TARGET for c, _ in chunks)
    assert [j for _, j in chunks][1:] == [" "] * (len(chunks) - 1), "pieces of one paragraph rejoin with a space"
    assert " ".join(c for c, _ in chunks) == para
    logger.success(f"PASS: {len(chunks)} sentence-aligned pieces, nothing lost.")


def run_all_tests() -> None:
    test_instant_formatter_fixture_cases()
    test_llm_is_handed_the_list()
    test_llm_backstop_rebuilds_a_flattened_list()
    test_llm_path_keeps_prose_paragraphs()
    test_long_dictation_never_splits_a_list()
    test_long_prose_paragraph_still_splits_at_sentences()
    logger.success("ALL LISTS-ACROSS-PARAGRAPHS TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
