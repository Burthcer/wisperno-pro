"""
Spoken retractions: "Let's meet Monday. No, no, let's meet Tuesday." -> "Let's meet Tuesday."

Deliberately rule-based and narrow, not a language model: a small local model
that decides what you "meant" can silently delete real content. This only acts
when a sentence STARTS with an explicit retraction phrase, and then only drops
the single sentence just before it. The untouched transcript is still stored in
History's raw transcript. Off unless Settings turns it on (AppConfig.self_correction).
"""

import re
from typing import List

# Phrases that are unambiguous on their own.
_CLEAR = r"scratch that|no wait|wait no|ignore that|ignore what i (?:just )?said|delete that|start over"
# Phrases that also begin ordinary sentences ("No, no problem", "Actually no one came"),
# so they only count when the speaker's punctuation ends them ("No, no, let's...").
_NEEDS_PUNCT = r"no[,.]? no|actually no|never ?mind(?: that)?"

_CUE = re.compile(
    rf"^(?:(?:{_CLEAR})\b|(?:{_NEEDS_PUNCT})(?=[,.!?;:]))[\s,.!?;:\-]*",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"((?<=[.!?])\s+)")


def apply_self_correction(text: str) -> str:
    """Drop each sentence a following retraction cancels, and the cue itself."""
    if not text:
        return text
    pieces = _SENTENCE_SPLIT.split(text)
    sentences: List[str] = pieces[0::2]
    seps: List[str] = pieces[1::2] + [""]  # seps[i] follows sentences[i]

    kept: List[tuple] = []  # (separator before it, sentence)
    prev_sep = ""
    changed = False
    for sentence, sep in zip(sentences, seps):
        m = _CUE.match(sentence)
        if m:
            changed = True
            # The retracted sentence goes; its replacement takes its place (and its paragraph break).
            before = kept.pop()[0] if kept else ""
            rest = sentence[m.end():].strip()
            if rest:
                kept.append((before, rest[0].upper() + rest[1:]))
        else:
            kept.append((prev_sep, sentence))
        prev_sep = sep
    if not changed:
        return text
    return "".join(before + sentence for before, sentence in kept).strip()
