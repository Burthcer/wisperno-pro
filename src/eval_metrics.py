"""
Scoring helpers for scripts/eval_dictation.py: word error rate (WER) for
what Whisper heard, and a similarity score for the final formatted text.
Pure Python, no model imports, so it's cheap to unit-test.
"""

import difflib
import re
from typing import List

_NUMBER_WORDS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty",
]
_DIGIT_TO_WORD = {str(i): w for i, w in enumerate(_NUMBER_WORDS)}


def normalize_words(text: str) -> List[str]:
    """Lowercase, drop punctuation (keeping in-word apostrophes), and spell out
    0-20 so "4 PM" and "four pm" count as the same words. Casing and
    punctuation are the formatter's job, so they don't count against Whisper."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"[-_/]", " ", text)
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"(?<!\w)'|'(?!\w)", " ", text)
    return [_DIGIT_TO_WORD.get(w, w) for w in text.split()]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """(substitutions + deletions + insertions) / reference word count.
    0.0 is perfect; can exceed 1.0 if the hypothesis adds lots of words."""
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def text_similarity(expected: str, actual: str) -> float:
    """0-1 character-level similarity of the final text, whitespace-normalized
    per line but keeping line breaks (list formatting is part of what's scored)."""
    def norm(s: str) -> str:
        return "\n".join(" ".join(line.split()) for line in s.strip().splitlines() if line.strip())
    return difflib.SequenceMatcher(None, norm(expected), norm(actual)).ratio()


def exact_match(expected: str, actual: str) -> bool:
    return text_similarity(expected, actual) == 1.0
