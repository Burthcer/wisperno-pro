"""
Spoken-padding trimmer: removes empty phrases, never answers or opinions.

Run: python tests/test_ramble_trim.py
"""

import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ramble_trim import trim_rambling  # noqa: E402


def test_removes_padding() -> None:
    cases = {
        "I guess yeah this will be version 1.4 and yeah accordingly do so":
            "This will be version 1.4 accordingly do so",
        "We ship the fix on Friday and then update the docs for everyone, so yeah, it is basically done":
            "We ship the fix on Friday and then update the docs for everyone, it is basically done",
        "The report is finished and sent to the whole team, or whatever.":
            "The report is finished and sent to the whole team.",
        "The build is slow, I mean, really slow on my laptop today.":
            "The build is slow really slow on my laptop today.",
        "I mean, the new layout works well for the whole team.":
            "The new layout works well for the whole team.",
    }
    for src, want in cases.items():
        got = trim_rambling(src)
        assert got == want, (src, got)
    logger.success("PASS: padding phrases are removed.")


def test_keeps_real_content() -> None:
    keep = [
        "Yeah, I can do that tomorrow morning.",
        "I guess it works for the demo next week.",
        "Do you know what I mean by that?",
        "Yes, of course, I will send it today.",
        "I mean it, the deadline is Friday.",
        "It is kind of blue and sort of green.",
        "so yeah",  # all padding: guard returns it rather than leaving nothing
        "",
    ]
    for t in keep:
        assert trim_rambling(t) == t, (t, trim_rambling(t))
    # Most of the words would go: the original comes back untouched.
    heavy = "so yeah and yeah and yeah I guess yeah"
    assert trim_rambling(heavy) == heavy
    logger.success("PASS: answers, opinions and content are untouched.")


if __name__ == "__main__":
    test_removes_padding()
    test_keeps_real_content()
    logger.success("ALL RAMBLE TRIM TESTS PASSED")
