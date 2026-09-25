"""
Dictating in points (src/list_formatter.py): spoken enumerations become real
lists on both the instant formatter and the LLM polish path, ordinary prose
that happens to use ordinal words stays prose, and the Polish prompt carries
the new LISTS rule (with a safe upgrade for existing databases).

Run: python tests/test_list_formatting.py
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

CASES = json.loads((BASE_DIR / "tests" / "fixtures" / "formatting_cases.json").read_text(encoding="utf-8"))


def test_fixture_cases_through_instant_formatter() -> None:
    from src.direct_formatter import format_direct

    logger.info("--- Testing every formatting fixture through format_direct() ---")
    failures = []
    for case in CASES:
        got = format_direct(case["raw"])
        if got != case["expected"]:
            failures.append(f"{case['name']}: expected {case['expected']!r}, got {got!r}")
    assert not failures, "\n".join(failures)
    lists = sum(1 for c in CASES if c["name"].startswith(("list", "bullets")))
    prose = sum(1 for c in CASES if c["name"].startswith("prose"))
    logger.success(f"PASS: {len(CASES)} fixtures ({lists} lists, {prose} must-stay-prose).")


def _fake_transformer(model_output: str):
    """A Transformer whose 'LLM' just returns model_output - exercises the real
    post-processing (clean_output, sanity_check, list backstop) with no GPU."""
    sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))
    from src.config import load_config
    from src.transformer import Transformer

    config = load_config()
    transformer = Transformer.__new__(Transformer)
    transformer.config = config.llm
    transformer.prompts = config.prompts
    transformer.profanity_filter = "allow"
    transformer.last_fallback_applied = False
    transformer.llm = mock.Mock()
    transformer.llm.create_chat_completion.return_value = {"choices": [{"message": {"content": model_output}}]}
    return transformer


def test_llm_path_backstop_formats_prose_lists() -> None:
    logger.info("--- Testing the LLM path turns a prose enumeration into a list ---")
    raw = "so there are two problems first the build is slow second the tests are flaky"
    transformer = _fake_transformer("There are two problems. First, the build is slow. Second, the tests are flaky.")
    out = transformer.transform(raw, mode="polish")
    assert out == "There are two problems:\n1. The build is slow.\n2. The tests are flaky.", out
    logger.success("PASS: LLM prose enumeration -> numbered list.")


def test_llm_path_keeps_a_list_the_model_already_made() -> None:
    logger.info("--- Testing an LLM-formatted list passes through unchanged ---")
    already = "There are two problems:\n1. The build is slow.\n2. The tests are flaky."
    transformer = _fake_transformer(already)
    out = transformer.transform("so there are two problems first the build is slow second the tests are flaky", mode="polish")
    assert out == already, out
    logger.success("PASS: model-made list left as is.")


def test_llm_path_leaves_other_modes_alone() -> None:
    logger.info("--- Testing non-polish modes are not list-formatted ---")
    prose = "First, the build is slow. Second, the tests are flaky."
    transformer = _fake_transformer(prose)
    out = transformer.transform("first the build is slow second the tests are flaky", mode="prompt_engineer")
    assert out == prose, out
    logger.success("PASS: only Polish gets the list backstop.")


def test_live_transcripts_are_not_turned_into_lists() -> None:
    from src.direct_formatter import format_direct

    logger.info("--- Testing Live Transcription cleanup skips list detection ---")
    meeting = "first we looked at the numbers second we argued about the budget"
    assert "\n" not in format_direct(meeting, detect_lists=False)
    assert format_direct(meeting).startswith("1. ")
    logger.success("PASS: detect_lists=False keeps conversation as prose.")


def test_polish_prompts_carry_the_list_rule() -> None:
    from src.config import load_config
    from src.database import DEFAULT_TRANSFORMS

    logger.info("--- Testing both Polish prompts include the LISTS rule ---")
    assert "LISTS" in load_config().prompts["polish"]
    assert "LISTS" in next(t for t in DEFAULT_TRANSFORMS if t["id"] == "polish")["system_prompt"]
    logger.success("PASS: config.yaml and the Alt+C transform both describe list formatting.")


def test_existing_database_polish_prompt_upgrade() -> None:
    from src.database import _POLISH_LIST_RULES, _POLISH_PROMPT_BEFORE_LISTS, WispernoDB

    logger.info("--- Testing the Polish transform prompt upgrade for existing databases ---")
    with tempfile.TemporaryDirectory() as tmp:
        db = WispernoDB(str(Path(tmp) / "untouched.db"))
        db.update_transform("polish", system_prompt=_POLISH_PROMPT_BEFORE_LISTS)  # an install from before this change
        assert db.update_polish_prompt_with_list_rules() is True
        assert db.get_transform("polish")["system_prompt"] == _POLISH_PROMPT_BEFORE_LISTS + _POLISH_LIST_RULES
        assert db.update_polish_prompt_with_list_rules() is False  # one-time
        db.close()

        db = WispernoDB(str(Path(tmp) / "customized.db"))
        db.update_transform("polish", system_prompt="My own polish prompt.")
        assert db.update_polish_prompt_with_list_rules() is False
        assert db.get_transform("polish")["system_prompt"] == "My own polish prompt."
        db.close()
    logger.success("PASS: untouched default prompt upgraded once; a customized prompt is left alone.")


def run_all_tests() -> None:
    test_fixture_cases_through_instant_formatter()
    test_llm_path_backstop_formats_prose_lists()
    test_llm_path_keeps_a_list_the_model_already_made()
    test_llm_path_leaves_other_modes_alone()
    test_live_transcripts_are_not_turned_into_lists()
    test_polish_prompts_carry_the_list_rule()
    test_existing_database_polish_prompt_upgrade()
    logger.success("ALL LIST FORMATTING TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
