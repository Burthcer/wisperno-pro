"""
Instant, zero-LLM formatter for Wisperno's default dictation hotkey (Mode 1).

Pure regex/string cleanup - no llama.cpp call, no model, <5ms. Dictionary/
jargon replacement is NOT duplicated here: Vocabulary.apply_replacements()
already runs inside Transcriber.transcribe() before this ever sees the text
(see src/transcriber.py), and Whisper's own punctuation is left as-is except
for the capitalization/terminal-punctuation pass at the end.
"""

import re

from src.list_formatter import format_lists_across_paragraphs, format_spoken_list

# A period/!/?/:/, immediately followed by a letter with NO space at all
# ("Hello.How are you?") - restricted to letters, never digits, so real
# numeric text (decimals like "3.14", thousands separators like "1,234") is
# never touched by this.
_MISSING_SPACE_RE = re.compile(r"([.!?:,])(?=[A-Za-z])")

# "like" is only a filler when it trails off as a verbal pause (Whisper tends
# to punctuate that with a comma) - stripping every "like" would also eat the
# verb ("I like pizza"), so it's matched separately and only with a comma.
# "um"/"uh" are never words. "er"/"ah" and "you know" only count as filler
# when punctuated as an aside ("Ah, I see", "it was, you know, bad") - bare,
# they're content: "Do you know the answer?", "the ER diagram".
_FILLER_RE = re.compile(
    r"\b(?:u+h+|u+m+)\b,?\s*|\b(?:ah|er|you know)\b(?:\s*,\s*|(?=[.!?]))", re.IGNORECASE
)
_FILLER_LIKE_RE = re.compile(r"\blike,\s*", re.IGNORECASE)

# Stutter: a word immediately repeating itself one or more times ("the the",
# "I I I"), or a sentence-final abbreviation repeated by an STT quirk ("etc.
# etc."). The optional trailing "\.?" is deliberately period-only, not comma -
# a comma before the repeat ("great, great job") is intentional spoken
# emphasis, not a stutter, and must survive untouched.
_STUTTER_RE = re.compile(r"\b(?!no\b)(\w+)(\.?)(?:\s+\1\b\.?)+", re.IGNORECASE)
# A restarted phrase of 2-4 words ("we should we should go", "can you, can you
# check") - kept once. Single repeated words are _STUTTER_RE's job.
_PHRASE_REPEAT_RE = re.compile(r"\b((?:\w+[ \t]+){1,3}\w+)(?:,?[ \t]+\1\b)+", re.IGNORECASE)
# "no no other languages" is an answer followed by a sentence, not a stutter -
# collapsing it loses the answer. Keep both, separated.
_NO_NO_RE = re.compile(r"\b(no)\s+(?=no\b)", re.IGNORECASE)

# Spoken developer/terminal shorthand -> the literal symbol.
_SLASH_COMMAND_RE = re.compile(r"\b(?:slash|forward slash)\s*([a-zA-Z0-9_\-]+)\b", re.IGNORECASE)
# Lookaround-guarded (word on both sides) so an isolated "dash" used as a
# spoken bullet-list cue (see src/list_formatter.py) isn't eaten by this pass.
_DASH_WORD_RE = re.compile(r"(?<=\w)\s+(?:dash|hyphen)\s+(?=\w)", re.IGNORECASE)
_UNDERSCORE_WORD_RE = re.compile(r"(?<=\w)\s+underscore\s+(?=\w)", re.IGNORECASE)
_BACKTICK_RE = re.compile(r"\bbacktick\b", re.IGNORECASE)
# A bare command ("/compact") shouldn't get a terminal "." appended by the
# normal sentence-punctuation pass.
_BARE_COMMAND_RE = re.compile(r"^/[\w\-]+$")

# Whisper frequently leaves the first-person pronoun lowercase mid-utterance
# ("i think", "i'm not sure"). \b matches on BOTH sides of a bare "i" even
# right before an apostrophe (the apostrophe is a non-word char), so this one
# pattern already covers "i"/"i'm"/"i've"/"i'll"/"i'd" - no separate
# contraction regex needed. Case-sensitive on purpose: an already-correct "I"
# is left untouched rather than needlessly rewritten.
LOWERCASE_I_RE = re.compile(r"\bi\b")


# What the LLM polish is actually for: filler, self-corrections, hedges and
# restarts. A short utterance with none of these ("sounds good, see you at
# 3") gains nothing from a ~0.3-1s LLM round trip.
LLM_SKIP_MAX_WORDS = 12
_NEEDS_LLM_RE = re.compile(
    r"\b(?:um+|uh+|er|ah+|hmm+|mm+|you know|i mean|sort of|kind of|wait|actually|scratch that|"
    r"no no|sorry|or rather|let me rephrase|never mind|rather)\b|\blike,",
    re.IGNORECASE,
)


def is_short_and_clean(text: str) -> bool:
    """True if `text` is short and has nothing the LLM polish would fix beyond
    what format_direct() already does - so dictation can skip the LLM."""
    words = text.split()
    if not words or len(words) > LLM_SKIP_MAX_WORDS:
        return False
    return not _NEEDS_LLM_RE.search(text) and not _STUTTER_RE.search(text)


def capitalize_pronoun_i(text: str) -> str:
    return LOWERCASE_I_RE.sub("I", text)


# --- Domains, file names and e-mail addresses --------------------------------
# "dev.to", "google.com", "main.py" and "me@site.org" are one token: the
# missing-space rule above must not turn them into "dev. to", and a spoken
# "dev dot to" should come out as "dev.to".
_TLDS_SURE = (
    "com|org|net|io|dev|app|ai|edu|gov|xyz|info|tech|tv|uk|ly|gg|sh|fm|biz|online|site|blog|page|cloud|club|"
    "store|shop|ca|de|fr|jp|au|nz|eu|ch|nl|ru|cc"
)
# Real endings that are also everyday words ("dot to", "dot in the middle"):
# only taken after a label that isn't itself a plain word (see _DOT_STOPWORDS).
_TLDS_AMBIGUOUS = "to|in|me|so|us|co|it|is|my|at|be|by|no|do|go|we|he|am"
_FILE_EXTS = (
    "py|js|ts|tsx|jsx|json|md|txt|csv|yaml|yml|html|htm|css|java|cpp|cs|go|rs|rb|php|bat|exe|dll|pdf|docx|xlsx|"
    "pptx|png|jpg|jpeg|gif|svg|zip|mp3|mp4|wav|ini|cfg|toml|log|sql|env|gguf|iss|spec"
)
_DOTTED_TOKEN_RE = re.compile(
    rf"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                                   # e-mail address
    rf"|\b(?:[\w-]+\.)+(?:{_TLDS_SURE}|{_TLDS_AMBIGUOUS}|{_FILE_EXTS})\b(?:/[\w\-./?=&%#~]*)?",  # domain / file name (+ path)
    re.IGNORECASE,
)
_DOT_STOPWORDS = frozenset(
    "a an the this that these those one two my your his her our their its any each every no some another same "
    "first last next per and or but of with from for on at by as if when then than so not just only very "
    "polka decimal red green blue black white full single double small big little tiny period "
    "i you he she it we they there here what which who whom whose".split()
)
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_SPOKEN_DOMAIN_RE = re.compile(
    rf"\b({_LABEL}(?:\s+dot\s+{_LABEL})*)\s+dot\s+({_TLDS_SURE}|{_TLDS_AMBIGUOUS})\b(?![\w-])", re.IGNORECASE,
)
_DOMAIN_SLASH_RE = re.compile(
    rf"(\b(?:[\w-]+\.)+(?:{_TLDS_SURE}|{_TLDS_AMBIGUOUS})(?:/[\w\-.]+)*)\s+(?:forward\s+)?slash\s+(?=[\w])",
    re.IGNORECASE,
)


def _spoken_domain(match: "re.Match") -> str:
    labels = re.split(r"\s+dot\s+", match.group(1), flags=re.IGNORECASE) + [match.group(2)]
    tld = match.group(2).lower()
    if tld in _TLDS_AMBIGUOUS.split("|") and tld not in _TLDS_SURE.split("|"):
        # "polka dot to", "a dot in the middle": a plain word before "dot" means it's prose.
        if labels[-2].lower() in _DOT_STOPWORDS:
            return match.group(0)
    return ".".join(labels)


def apply_spoken_domains(text: str) -> str:
    """"dev dot to" -> "dev.to", "www dot google dot com" -> "www.google.com",
    "dev dot to slash burthcer" -> "dev.to/burthcer". Only when the last part is
    a real top-level domain, so "polka dot" and "dot product" stay words."""
    text = _SPOKEN_DOMAIN_RE.sub(_spoken_domain, text)
    previous = None
    while previous != text:  # one "slash <segment>" at a time, for deep paths
        previous = text
        text = _DOMAIN_SLASH_RE.sub(r"\1/", text)
    return text


def _starts_with_dotted_token(text: str) -> bool:
    m = _DOTTED_TOKEN_RE.match(text)
    return bool(m) and m.start() == 0


def normalize_punctuation_spacing(text: str) -> str:
    """Insert a missing space after sentence/clause punctuation that's fused
    directly to the next word ('Hello.How' -> 'Hello. How') - a real defect
    both here and in transformer.py's LLM path (fixed content can still be
    typographically fused if the raw input was), so both call this. Safe
    against decimals/thousands-separators since it only fires before a
    letter, never a digit - and against domains, file names and e-mail
    addresses ('dev.to', 'main.py'), which are left whole."""
    spans = [m.span() for m in _DOTTED_TOKEN_RE.finditer(text)]
    if not spans:
        return _MISSING_SPACE_RE.sub(r"\1 ", text)
    return _MISSING_SPACE_RE.sub(
        lambda m: m.group(0) if any(a <= m.start() < b for a, b in spans) else m.group(0) + " ", text
    )


def _apply_spoken_commands(text: str) -> str:
    """Spoken developer/terminal shorthand -> literal symbols ("slash compact"
    -> "/compact", "my dash file" -> "my-file", "backtick" -> "`")."""
    text = apply_spoken_domains(text)
    text = _SLASH_COMMAND_RE.sub(r"/\1", text)
    text = _DASH_WORD_RE.sub("-", text)
    text = _UNDERSCORE_WORD_RE.sub("_", text)
    text = _BACKTICK_RE.sub("`", text)
    return text


# A filler Whisper fenced in commas ("we should, uh, go", "Can you, like,
# send") - drop the filler AND both commas, or "we should, go" is left behind.
_COMMA_FENCED_FILLER_RE = re.compile(r",\s*\b(?:uh|um|ah|er|like|you know)\b\s*,\s*", re.IGNORECASE)


# A filler that ends a sentence takes its leading comma with it ("bad, you know." -> "bad.").
_TRAILING_FILLER_RE = re.compile(r",\s*\b(?:you know|ah|er|u+h+|u+m+)\b(?=\s*(?:[.!?]|$))", re.IGNORECASE)


def _strip_fillers(text: str) -> str:
    text = _COMMA_FENCED_FILLER_RE.sub(" ", text)
    text = _TRAILING_FILLER_RE.sub("", text)
    text = _FILLER_RE.sub("", text)
    text = _FILLER_LIKE_RE.sub("", text)
    text = _PHRASE_REPEAT_RE.sub(r"\1", text)
    text = _STUTTER_RE.sub(r"\1\2", text)
    text = _NO_NO_RE.sub(r"\1, ", text)
    text = re.sub(r"[ \t]+([,.!?])", r"\1", text)
    # Collapse runs of plain spaces/tabs only - a "\n\n" paragraph break
    # (src/transcriber.py's pause-based split) must survive this pass, so
    # newlines are deliberately excluded from what counts as collapsible
    # whitespace here.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]*\n\n[ \t]*", "\n\n", text)
    return re.sub(r"^[,\s]+", "", text).strip()


# "Scratch that" as a spoken edit command (as in Dragon): only when it
# stands alone as its own phrase - "I need to scratch that itch" is content.
_SCRATCH_THAT_RE = re.compile(
    r"(?:\b(?:actually|no|oh|wait)\b[,\s]*)*\bscratch that\b(?=\s*(?:[.,!?;]|$))[.,!?;]*\s*", re.IGNORECASE
)


def apply_scratch_that(text: str) -> str:
    """Delete what "scratch that" retracts: the words before it in the same
    sentence, or - if it starts its own sentence - the previous sentence.
    "Use the red one. Actually, scratch that. Use the blue one." -> "Use the blue one." """
    while True:
        m = _SCRATCH_THAT_RE.search(text)
        if not m:
            return text
        before, after = text[:m.start()], text[m.end():]
        sentence_start = max(before.rfind(". "), before.rfind("! "), before.rfind("? "), before.rfind("\n"))
        own_sentence = before[sentence_start + 1:].strip(" ,")
        if own_sentence:  # "..., scratch that, ..." -> drop this sentence's words so far
            before = before[:sentence_start + 1]
        else:             # "... . Scratch that. ..." -> drop the previous sentence
            prev = before.rstrip()
            prev_start = max(prev[:-1].rfind(". "), prev[:-1].rfind("! "), prev[:-1].rfind("? "), prev[:-1].rfind("\n"))
            before = prev[:prev_start + 1]
        text = (before.rstrip() + " " + after.lstrip()).strip()


def strip_fillers(text: str) -> str:
    """Public: remove hesitations/stutters only (no capitalization or list
    formatting) - used to pre-clean text before the LLM polish sees it."""
    return _strip_fillers(text)


# When Whisper left a sentence without end punctuation, a question still gets
# "?": an auxiliary + subject ("can you ...", "is it ...") or a question word.
# "do it ..." (imperative) and "when you get home ..." (a clause) aren't.
_QUESTION_START_RE = re.compile(
    r"^(?:(?:can|could|would|will|should|shall|may|is|are|was|were|am|have|has|had)\s+"
    r"(?:you|i|we|they|he|she|it|this|that|there|the|my|your|our|anyone|someone|everyone)\b"
    r"|(?:do|does|did)\s+(?:you|i|we|they|he|she|the|my|your|our|anyone|someone|everyone)\b"
    r"|(?:what|why|how|where|who|which)\b"
    r"|when\s+(?:is|are|was|were|will|do|does|did|can|should)\b)",
    re.IGNORECASE,
)


def _cap_punct(item: str) -> str:
    item = item.strip(" ,")
    if not item:
        return item
    if not _starts_with_dotted_token(item):
        item = item[0].upper() + item[1:]
    if item[-1] not in ".!?":
        last_sentence = re.split(r"(?<=[.!?])\s+", item)[-1]
        item += "?" if _QUESTION_START_RE.match(last_sentence) else "."
    return item


def _cap_sentences(text: str) -> str:
    """Capitalize the first letter of the text and of every sentence following
    a '.'/'!'/'?' - independent of src.transformer so this module never pulls
    in the (heavy, CUDA-touching) llama.cpp import chain."""
    sentences = re.split(r"([.!?]\s+)", text)
    capitalized = "".join(
        (s[0].upper() + s[1:] if s and s[0].isalpha() and not _starts_with_dotted_token(s) else s) for s in sentences
    )
    if not capitalized or _starts_with_dotted_token(capitalized):
        return capitalized
    return capitalized[0].upper() + capitalized[1:]


def format_direct(text: str, detect_lists: bool = True) -> str:
    """Zero-LLM dictation cleanup: fillers/stutters out, spoken lists formatted
    (src/list_formatter.py), capitalization/terminal punctuation applied. Runs
    in well under 10ms. detect_lists=False for continuous transcripts (Live
    Transcription), where "first ... second" is conversation, not dictation."""
    text = text.strip()
    if not text:
        return ""

    text = normalize_punctuation_spacing(text)
    text = apply_scratch_that(text)
    text = _strip_fillers(text)
    if not text:
        return ""
    text = capitalize_pronoun_i(text)
    text = _apply_spoken_commands(text)

    if _BARE_COMMAND_RE.match(text.strip()):
        return text.strip()

    # Paragraph breaks (src/transcriber.py's pause-based split) are kept and
    # each prose paragraph formatted on its own - but a spoken list can run
    # across them (people pause before each point), so list detection looks
    # across paragraphs: see list_formatter.format_lists_across_paragraphs.
    prose = lambda para: _cap_punct(_cap_sentences(para))  # noqa: E731
    if detect_lists:
        return format_lists_across_paragraphs(text, prose=prose)
    return "\n\n".join(prose(p.strip()) for p in text.split("\n\n") if p.strip())


def _demo() -> None:
    import time

    r1 = format_direct("um I think we should uh go with option A")
    assert r1 == "I think we should go with option A.", r1

    r2 = format_direct("we need three things first buy milk second get eggs third go home")
    lines = r2.split("\n")
    assert lines == ["We need three things:", "1. Buy milk.", "2. Get eggs.", "3. Go home."], r2

    r3 = format_direct("the the client wants changes")
    assert r3 == "The client wants changes.", r3

    r4 = format_direct("bullet point buy milk bullet point get eggs")
    assert r4.split("\n") == ["• Buy milk.", "• Get eggs."], r4

    r5 = format_direct("I first went to the store")
    assert "\n" not in r5 and r5 == "I first went to the store.", r5

    r6 = format_direct("i think i'm going to head out, i've already told them i'll be late")
    assert r6 == "I think I'm going to head out, I've already told them I'll be late.", r6

    r7 = format_direct("slash compact")
    assert r7 == "/compact", r7

    r8 = format_direct("run slash help to see options")
    assert r8 == "Run /help to see options.", r8

    r9 = format_direct("we're all done here etc. etc.")
    assert "etc. etc." not in r9 and r9.rstrip(".").endswith("etc"), r9

    r10 = format_direct("great, great job team")
    assert r10 == "Great, great job team.", r10  # comma-separated emphasis preserved

    r11 = format_direct("my project dash file underscore name")
    assert r11 == "My project-file_name.", r11

    r12 = format_direct("this is the opening thought\n\nhere is another one after a pause")
    assert r12 == "This is the opening thought.\n\nHere is another one after a pause.", r12

    r13 = format_direct("um so uh this is one thought\n\n  the the other thought here")
    assert r13 == "So this is one thought.\n\nThe other thought here.", r13

    r14 = format_direct("this is one sentence.here comes another")
    assert r14 == "This is one sentence. Here comes another.", r14

    r15 = format_direct("hello.how are you?wait,really")
    assert r15 == "Hello. How are you? Wait, really.", r15

    r16 = format_direct("the value is 3.14 and there were 1,234 attendees")
    assert r16 == "The value is 3.14 and there were 1,234 attendees.", r16  # numeric punctuation untouched

    t0 = time.perf_counter()
    for _ in range(100):
        format_direct("um so uh I was thinking we could uh go with the the second option")
    elapsed_ms = (time.perf_counter() - t0) * 1000 / 100
    assert elapsed_ms < 10, f"format_direct averaged {elapsed_ms:.3f}ms/call, expected <10ms"

    print(f"PASS: filler/stutter stripping, numbered + bullet list detection, capitalization all verified "
          f"({elapsed_ms:.3f}ms/call avg).")


if __name__ == "__main__":
    _demo()
