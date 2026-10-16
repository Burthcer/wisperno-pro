"""
Automatic paragraphs for long dictation.

Whisper only starts a new paragraph where you paused. Someone who talks for a minute without a
break gets one wall of text. This splits such a wall at the points where the topic changes - no
AI model involved (fast, and it can't rewrite or drop a word): it compares the vocabulary of the
sentences before and after each possible break, adds a bonus where a sentence opens with a
transition ("Also,", "Another thing", "Finally") and picks the strongest break points, keeping
paragraphs a readable size.

Short text, lists and anything already broken into lines are left exactly as they are.
"""

import re
from typing import List, Optional

MIN_WORDS_TO_SPLIT = 70      # a paragraph shorter than this is never touched
MIN_PARAGRAPH_WORDS = 30
TARGET_WORDS = 60            # start looking for a break once a paragraph is about this long
MAX_PARAGRAPH_WORDS = 130    # ...and force one before it gets longer than this
BREAK_THRESHOLD = 0.55       # how strong a topic change must be to split a not-yet-too-long paragraph
MARKER_BONUS = 0.4

_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.", "dr.", "no.", "approx.", "inc.", "st.")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)

# A sentence that opens with one of these usually starts a new thought.
_MARKERS = (
    "also", "furthermore", "moreover", "additionally", "in addition", "another thing", "another point",
    "another issue", "one more", "next", "second", "secondly", "third", "thirdly", "finally", "lastly",
    "anyway", "anyways", "moving on", "on another note", "by the way", "separately", "meanwhile",
    "however", "on the other hand", "in conclusion", "to sum up", "as for", "regarding", "speaking of",
    "now", "okay", "ok so", "so now", "besides",
)

_STOPWORDS = frozenset(
    "the a an and or but if then than that this these those there here with from into onto over under about "
    "have has had having is are was were be been being do does did doing done will would could should can may "
    "might must shall just also very really quite some any many much more most other such only own same "
    "what which who whom whose when where why how all each every both few not nor too its it's i'm you're "
    "they're we're i've you've we've they've i'll you'll we'll they'll i'd you'd we'd they'd don't doesn't "
    "didn't isn't aren't wasn't weren't can't couldn't won't wouldn't shouldn't your yours mine ours their "
    "theirs them they you your yourself myself himself herself itself ourselves themselves like get got "
    "make made going want need know think say said thing things kind sort lot bit yeah okay well right "
    "actually basically literally honestly".split()
)


def _words(text: str) -> int:
    return len(text.split())


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _content(sentence: str) -> set:
    tokens = re.findall(r"[a-z][a-z']+", sentence.lower())
    return {_stem(t) for t in tokens if len(t) >= 4 and t not in _STOPWORDS}


def _split_sentences(text: str) -> List[str]:
    pieces = _SENTENCE_END.split(text.strip())
    sentences: List[str] = []
    for piece in pieces:
        if sentences and sentences[-1].lower().endswith(_ABBREVIATIONS):
            sentences[-1] += " " + piece  # "e.g." / "Dr." doesn't end a sentence
        else:
            sentences.append(piece)
    return [s for s in sentences if s]


def _similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _opens_with_marker(sentence: str) -> bool:
    head = re.sub(r"^[^a-z]+", "", sentence.lower())
    return any(head == m or head.startswith(m + " ") or head.startswith(m + ",") for m in _MARKERS)


def _break_scores(sentences: List[str]) -> List[float]:
    """scores[i] = how good a place it is to start a new paragraph at sentences[i] (i >= 1)."""
    sets = [_content(s) for s in sentences]
    scores = [0.0] * len(sentences)
    for i in range(1, len(sentences)):
        left = set().union(*sets[max(0, i - 3):i])
        right = set().union(*sets[i:i + 3])
        scores[i] = (1.0 - _similarity(left, right)) + (MARKER_BONUS if _opens_with_marker(sentences[i]) else 0.0)
    return scores


def _choose_breaks(sentences: List[str]) -> List[int]:
    """Indices (into `sentences`) where a new paragraph starts."""
    scores = _break_scores(sentences)
    counts = [_words(s) for s in sentences]
    breaks: List[int] = []
    start = 0
    n = len(sentences)
    while start < n:
        remaining = sum(counts[start:])
        if remaining < 2 * MIN_PARAGRAPH_WORDS:
            break  # too little left to make two paragraphs
        best: Optional[int] = None
        best_score = 0.0
        running = 0
        for i in range(start, n - 1):
            running += counts[i]
            nxt = i + 1  # candidate: a paragraph starts at sentence nxt
            tail = sum(counts[nxt:])
            if running < MIN_PARAGRAPH_WORDS or tail < MIN_PARAGRAPH_WORDS or nxt - start < 2:
                continue
            if running > MAX_PARAGRAPH_WORDS:
                break
            # Breaking early costs a little: a break has to be clearly worth it before the paragraph is "full".
            score = scores[nxt] - (0.35 if running < TARGET_WORDS else 0.0)
            if best is None or score > best_score:
                best, best_score = nxt, score
        if best is None:
            break
        forced = remaining > MAX_PARAGRAPH_WORDS  # a wall this long gets cut even at a weak spot
        if best_score < BREAK_THRESHOLD and not forced:
            break
        breaks.append(best)
        start = best
    return breaks


def split_paragraph(paragraph: str) -> List[str]:
    """One block of text -> one or more paragraphs. Returns the block unchanged if it should stay whole."""
    if _words(paragraph) < MIN_WORDS_TO_SPLIT or "\n" in paragraph or _LIST_LINE.search(paragraph):
        return [paragraph]
    sentences = _split_sentences(paragraph)
    if len(sentences) < 4:
        return [paragraph]
    breaks = _choose_breaks(sentences)
    if not breaks:
        return [paragraph]
    bounds = [0] + breaks + [len(sentences)]
    return [" ".join(sentences[a:b]) for a, b in zip(bounds, bounds[1:])]


def split_into_paragraphs(text: str) -> str:
    """Add paragraph breaks to long blocks of `text`; paragraphs that already exist are kept."""
    if not text or _words(text) < MIN_WORDS_TO_SPLIT:
        return text
    blocks = re.split(r"(\n{2,})", text)
    out: List[str] = []
    for block in blocks:
        if block.strip() and not block.startswith("\n"):
            out.append("\n\n".join(split_paragraph(block)))
        else:
            out.append(block)
    return "".join(out)
