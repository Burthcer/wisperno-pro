"""
Spoken-list detection: turns dictation said "in points" into a real list.

    "there are three reasons first the price second the timeline and finally the team"
 -> "There are three reasons:\n1. The price.\n2. The timeline.\n3. The team."

Used by src/direct_formatter.py (the instant, zero-LLM path) and, as a
deterministic backstop, on the LLM polish output (src/transformer.py) so a
list is formatted no matter which preset is loaded.

Recognized cues, which must count up from 1 in order (a stray "second" in
"wait a second" can't start or break a list):
  - ordinals: first / firstly / first of all, second(ly), third(ly) ... tenth
  - labelled numbers: number one, step two, point three, item 4
  - bare numbers at the start of a clause, followed by punctuation:
    "One, fix the bug. Two, ship it." (not "one apple, two oranges")
  - digits the way Whisper writes them: "1. Open the app 2. Click save"
  - after the list has started: next / lastly / finally / last but not least
Plus bullet cues ("bullet point", "next point", "new bullet", "dash").

Deliberately conservative - explicit cues only. Prose that merely mentions
ordinals ("the first time", "at first", "on second thought") stays prose.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_ORDINAL_VALUES = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_NUM = r"(?:" + "|".join(_NUMBER_WORDS) + r"|\d{1,2})"

_ORDINAL_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)(?:ly)?(?:\s+of\s+all)?\b",
    re.IGNORECASE,
)
_LABELLED_RE = re.compile(rf"\b(?:number|step|point|item)\s+({_NUM})\b", re.IGNORECASE)
_CARDINAL_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b(?=\s*[,.:)])", re.IGNORECASE)
_DIGIT_RE = re.compile(r"(?<![\w.,])(\d{1,2})[.)](?=\s|$)")
_CONTINUATION_RE = re.compile(
    r"\b(?:and\s+)?(finally|lastly|last but not least|last of all|next)\b(?!\s+(?:week|month|year|day|"
    r"time|step|one|few|thing|morning|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b)",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"\b(?:bullet point|next bullet|new bullet|next point|dash)\b", re.IGNORECASE)

# "the first time", "at first", "a second", "on second thought" - an ordinal
# after one of these words is part of the sentence, not a list cue.
_ORDINAL_BLOCKED_BEFORE = frozenset(
    "a an the at my your his her our their its this that every each per whose in on".split()
)
_ORDINAL_BLOCKED_AFTER = frozenset(
    "time times place half hand class person floor grade name day days week month year round version "
    "draft attempt try look glance quarter thought nature rate one ones thing things".split()
)
# Only words that can never legitimately end an item ("...too short. And"
# before "and third"); "then"/"so" alone can ("back then", "I think so").
_ENDING_CONNECTORS = re.compile(r"(?:[\s,;:]+|\b(?:and then|and also|and)\b)+$", re.IGNORECASE)
# Right before the next cue, "then"/"also"/"so" are connectors too ("coffee then second ...").
_CONNECTORS_BEFORE_CUE = re.compile(r"(?:[\s,;:]+|\b(?:and then|and also|and|then|also|so)\b)+$", re.IGNORECASE)
# A lead-in made only of these ("okay so first ...") is dropped, not turned into a header line.
_FILLER_INTRO_WORDS = frozenset("okay ok so alright right well and um uh now".split())
_LEADING_JUNK = re.compile(r"^[\s,;:.)\-]+")

MIN_ITEMS = 2


@dataclass
class _Cue:
    start: int
    end: int
    value: Optional[int]  # None = continuation word (next / finally / ...)
    final: bool = False   # finally / lastly: nothing numbered can follow it


def _prev_word(text: str, idx: int) -> str:
    match = re.search(r"(\w+)\W*$", text[:idx])
    return match.group(1).lower() if match else ""


def _next_word(text: str, idx: int) -> str:
    match = re.match(r"\W*(\w+)", text[idx:])
    return match.group(1).lower() if match else ""


def _at_clause_start(text: str, idx: int) -> bool:
    before = text[:idx].rstrip()
    return not before or before[-1] in ".,;:!?\n"


def _find_numbered_cues(text: str) -> List[_Cue]:
    cues: List[_Cue] = []
    for m in _ORDINAL_RE.finditer(text):
        if _prev_word(text, m.start()) in _ORDINAL_BLOCKED_BEFORE:
            continue
        if _next_word(text, m.end()) in _ORDINAL_BLOCKED_AFTER:
            continue
        cues.append(_Cue(m.start(), m.end(), _ORDINAL_VALUES[m.group(1).lower()]))
    for m in _LABELLED_RE.finditer(text):
        num = m.group(1).lower()
        cues.append(_Cue(m.start(), m.end(), int(num) if num.isdigit() else _NUMBER_WORDS[num]))
    for m in _CARDINAL_RE.finditer(text):
        if _at_clause_start(text, m.start()):
            cues.append(_Cue(m.start(), m.end(), _NUMBER_WORDS[m.group(1).lower()]))
    for m in _DIGIT_RE.finditer(text):
        cues.append(_Cue(m.start(), m.end(), int(m.group(1))))
    for m in _CONTINUATION_RE.finditer(text):
        if m.group(0).lower().startswith("and") or _at_clause_start(text, m.start()):
            cues.append(_Cue(m.start(), m.end(), None, final=m.group(1).lower() != "next"))

    # Overlaps ("point one," matches both the labelled and bare-number
    # patterns): keep the earliest-starting, longest match.
    cues.sort(key=lambda c: (c.start, -(c.end - c.start)))
    kept: List[_Cue] = []
    for cue in cues:
        if kept and cue.start < kept[-1].end:
            continue
        kept.append(cue)
    return kept


def _best_chain(cues: List[_Cue]) -> List[_Cue]:
    """Longest run of cues counting 1, 2, 3... in order (continuation words
    count as the next number). Cues that don't fit are left as plain text."""
    best: List[_Cue] = []
    for i, start in enumerate(cues):
        if start.value != 1:
            continue
        chain, expected = [start], 2
        for cue in cues[i + 1:]:
            if chain[-1].final:
                break
            if cue.value == expected or cue.value is None:
                chain.append(cue)
                expected += 1
        numbered = sum(1 for c in chain if c.value is not None)
        if numbered >= MIN_ITEMS and len(chain) > len(best):
            best = chain
    return best


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _cap_sentences(text: str) -> str:
    parts = re.split(r"([.!?]\s+)", text)
    return "".join(p[:1].upper() + p[1:] if p and p[0].isalpha() else p for p in parts)


def _clean_item(text: str, before_cue: bool) -> str:
    text = _LEADING_JUNK.sub("", text).strip()
    text = (_CONNECTORS_BEFORE_CUE if before_cue else _ENDING_CONNECTORS).sub("", text).strip()
    if not re.search(r"[A-Za-z0-9]", text):
        return ""
    text = _cap_sentences(_capitalize(text))
    return text if text[-1] in ".!?" else text + "."


def _clean_intro(text: str) -> str:
    text = _CONNECTORS_BEFORE_CUE.sub("", text.strip()).strip()
    words = re.findall(r"[a-z']+", text.lower())
    if not words or all(w in _FILLER_INTRO_WORDS for w in words):
        return ""
    text = _cap_sentences(_capitalize(text))
    if text[-1] in "?!:":
        return text
    return (text[:-1] if text[-1] == "." else text) + ":"


def _render(text: str, cues: List[_Cue], marker) -> Optional[str]:
    intro = _clean_intro(text[:cues[0].start])
    items = []
    for i, cue in enumerate(cues):
        end = cues[i + 1].start if i + 1 < len(cues) else len(text)
        item = _clean_item(text[cue.end:end], before_cue=i + 1 < len(cues))
        if not item:
            return None  # a cue with nothing after it isn't a real list item
        items.append(f"{marker(i)} {item}")
    lines = ([intro] if intro else []) + items
    return "\n".join(lines)


def format_spoken_list(text: str) -> Optional[str]:
    """Return `text` formatted as an (optionally introduced) numbered or
    bullet list if it was dictated as one, else None. Expects one paragraph."""
    if not text or not text.strip() or "\n" in text.strip():
        return None
    chain = _best_chain(_find_numbered_cues(text))
    if chain:
        rendered = _render(text, chain, lambda i: f"{i + 1}.")
        if rendered:
            return rendered
    bullets = [_Cue(m.start(), m.end(), None) for m in _BULLET_RE.finditer(text)]
    if len(bullets) >= MIN_ITEMS:
        return _render(text, bullets, lambda i: "*")
    return None


def format_lists_in_text(text: str) -> str:
    """Apply format_spoken_list() paragraph by paragraph ("\\n\\n"-separated),
    leaving paragraphs that are already multi-line or already a list alone."""
    paragraphs = text.split("\n\n")
    out = []
    for para in paragraphs:
        stripped = para.strip()
        if not stripped or "\n" in stripped:
            out.append(para)
            continue
        out.append(format_spoken_list(stripped) or para)
    return "\n\n".join(out)
