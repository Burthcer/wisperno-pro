"""
Website names, file names and e-mail addresses in dictation.

  - saying "dev dot to" must type dev.to (and "dot" stays a word in prose)
  - a literal "dev.to" / "main.py" from Whisper must NOT be split into
    "dev. To" / "main. Py" by the missing-space-after-period rule
  - both on the instant formatter and on the LLM path (what the model is handed)

Run: python tests/test_spoken_domains.py
"""

import sys
import types
from pathlib import Path
from unittest import mock

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

SPOKEN = [
    ("visit dev dot to", "Visit dev.to."),
    ("dev dot to is a great site", "dev.to is a great site."),
    ("I posted it on dev dot to.", "I posted it on dev.to."),
    ("www dot google dot com is huge", "www.google.com is huge."),
    ("open dev dot io and then go to settings", "Open dev.io and then go to settings."),
    ("visit dev dot to slash burthcer", "Visit dev.to/burthcer."),
    ("visit dev dot to slash burthcer slash posts", "Visit dev.to/burthcer/posts."),
    ("my site is devbhamaria dot com and github dot com slash burthcer",
     "My site is devbhamaria.com and github.com/burthcer."),
    ("Dev dot to and Hacker News", "Dev.to and Hacker News."),
    ("my-site dot org", "my-site.org."),
]
PROSE_STAYS = [  # "dot" is a word here - nothing may turn into a domain
    ("put a dot in the middle", "Put a dot in the middle."),
    ("the polka dot to the left", "The polka dot to the left."),
    ("we use a dot product here", "We use a dot product here."),
    ("I like it dot so", "I like it dot so."),
    ("add a decimal dot in the price", "Add a decimal dot in the price."),
    ("press the dot key", "Press the dot key."),
    ("slash compact", "/compact"),
    ("run slash help to see options", "Run /help to see options."),
]
LITERAL = [  # what Whisper writes when it already got it right
    ("check out dev.to and google.com", "Check out dev.to and google.com."),
    ("I posted it on dev.to.", "I posted it on dev.to."),
    ("go to www.example.co.uk/page now", "Go to www.example.co.uk/page now."),
    ("the file is main.py and README.md", "The file is main.py and README.md."),
    ("email me at dev.bhamaria@gmail.com", "Email me at dev.bhamaria@gmail.com."),
    ("this is one sentence.here comes another", "This is one sentence. Here comes another."),
    ("hello.how are you?wait,really", "Hello. How are you? Wait, really."),
    ("the value is 3.14 and there were 1,234 attendees", "The value is 3.14 and there were 1,234 attendees."),
]


def _check(cases, label):
    from src.direct_formatter import format_direct

    failures = [(raw, format_direct(raw), want) for raw, want in cases if format_direct(raw) != want]
    assert not failures, failures
    logger.success(f"PASS: {len(cases)} {label}.")


def test_spoken_dot_becomes_a_domain() -> None:
    logger.info("--- Testing 'dev dot to' -> dev.to ---")
    _check(SPOKEN, "spoken-domain cases")


def test_dot_stays_a_word_in_prose() -> None:
    logger.info("--- Testing 'dot' in ordinary sentences is left alone ---")
    _check(PROSE_STAYS, "prose cases")


def test_literal_domains_are_not_split() -> None:
    logger.info("--- Testing a literal domain/file/e-mail is not split after its period ---")
    _check(LITERAL, "literal-domain cases")


def test_llm_is_handed_the_domain() -> None:
    from src.config import load_config
    from src.transformer import Transformer

    logger.info("--- Testing the LLM path converts the domain before the model sees it ---")
    config = load_config()
    t = Transformer.__new__(Transformer)
    t.config, t.prompts, t.profanity_filter = config.llm, config.prompts, "allow"
    t.vocabulary, t.last_fallback_applied, t.wrap_transcript = None, False, True
    handed = []

    def complete(messages, **kwargs):
        import re

        content = messages[-1]["content"]
        m = re.search(r'"""\n(.*)\n"""', content, re.DOTALL)
        handed.append(m.group(1) if m else content)
        return {"choices": [{"message": {"content": handed[-1]}}]}

    t.llm = mock.Mock()
    t.llm.create_chat_completion.side_effect = complete
    out = t.transform("so I posted the write up on dev dot to slash burthcer yesterday", mode="polish")
    assert "dev.to/burthcer" in handed[0], handed
    assert "dev.to/burthcer" in out and " dot " not in out, out
    logger.success(f"PASS: model handed {handed[0]!r}")


def run_all_tests() -> None:
    test_spoken_dot_becomes_a_domain()
    test_dot_stays_a_word_in_prose()
    test_literal_domains_are_not_split()
    test_llm_is_handed_the_domain()
    logger.success("ALL SPOKEN-DOMAIN TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
