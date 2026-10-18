"""
Configurable profanity handling for polished dictation output.
Three modes (see config.py's AppConfig.profanity_filter):
  "allow"  - leave verbatim, the default (a dictation tool should not
             silently alter what the user actually said). The only change is
             that a swear word the speech model itself masked ("f**king") is
             put back as the word that was said.
  "censor" - replace all but the first letter with asterisks (e.g. "fuck" -> "f***").
  "remove" - drop the word entirely (surrounding whitespace/punctuation collapsed).

A compiled-once regex over a common English profanity list - deliberately
whole-word-boundary matched so it never touches a word that merely contains one
as a substring (e.g. "class", "assess", "Scunthorpe").
"""

import re
from typing import Optional

# Common English profanity - not exhaustive (a determined user can always defeat
# a client-side word list), just the frequent, unambiguous cases and their usual
# inflections/compounds. Whole-word matched below, case-insensitive. Order matters
# only for un-masking (see unmask_profanity): earlier = more likely intended.
_PROFANITY_WORDS = (
    "fuck", "fucking", "fucked", "fucker", "fuckers", "fucks", "fuckin", "fuckup", "fuckups", "fuckwit", "fuckhead",
    "motherfucker", "motherfuckers", "motherfucking", "motherfuck",
    "shit", "shitty", "shitting", "shits", "shithead", "shitheads", "shitshow", "shite",
    "bullshit", "bullshitting", "horseshit",
    "bitch", "bitches", "bitching", "bitchy",
    "asshole", "assholes", "ass", "asses", "dumbass", "jackass", "badass", "smartass", "fatass", "kickass",
    "dick", "dicks", "dickhead", "dickheads",
    "damn", "damned", "dammit", "damnit", "goddamn", "goddamned", "goddammit", "goddamnit",
    "bastard", "bastards",
    "crap", "crappy",
    "piss", "pissed", "pissing",
    "cock", "cocks",
    "pussy", "pussies",
    "cunt", "cunts",
    "whore", "whores",
    "slut", "sluts",
    "hell",
    "wtf",
)

# Longest first so "motherfucking" wins over "fucking"; "fuckin'" owns its apostrophe.
_PROFANITY_RE = re.compile(
    r"\b("
    + "|".join(re.escape(w) + ("'?" if w == "fuckin" else "") for w in sorted(_PROFANITY_WORDS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Speech models often mask a swear word themselves ("f**king", "s**t", "b*tch",
# "f***"). Those must count as the word that was said: a filter that only knows
# the plain spelling lets every one of them through, and "Allow" would otherwise
# hand back the model's asterisks instead of the speaker's word.
_MASK_CHARS = "*#@$%"
_MASKED_RE = re.compile(
    r"(?<![\w*#@$%])([A-Za-z][A-Za-z*#@$%]*[*#@$%][A-Za-z*#@$%]*)'?(?![\w*#@$%])"
)

_START_MARK = "\x00"  # marks where a sentence lost its first word (remove mode)


def _unmask_token(token: str) -> Optional[str]:
    """The profanity word a masked token stands for, or None. First choice: same length with every
    visible letter in place ("f**king"). If the model masked with a different number of symbols
    ("f*****" for "fucked"), fall back to a word that starts with the same letter, contains the visible
    letters in order and is within two letters of the token's length. The most common word wins ties."""
    t = token.lower()
    for word in _PROFANITY_WORDS:
        if len(word) == len(t) and all(c in _MASK_CHARS or c == word[i] for i, c in enumerate(t)):
            return word
    visible = [c for c in t if c not in _MASK_CHARS]
    # The loose match is only for clearly masked words: "C#" or "A$AP" must never become a swear word.
    if not t[0].isalpha() or len(t) < 4 or len(t) - len(visible) < 2:
        return None
    best, best_gap = None, 3
    for word in _PROFANITY_WORDS:
        gap = abs(len(word) - len(t))
        if gap > 2 or word[0] != t[0] or gap >= best_gap:
            continue
        pos, ok = 0, True
        for c in visible:
            pos = word.find(c, pos)
            if pos < 0:
                ok = False
                break
            pos += 1
        if ok and (t[-1] in _MASK_CHARS or word[-1] == t[-1]):
            best, best_gap = word, gap
    return best


# Whisper often "bleeps" a swear word with a dash instead of asterisks: "f-ing", "f-" (cut off), "sh-t", "b-tch".
# Only these exact shapes are restored, so ordinary hyphenated words ("f-stop", "F-16", "well-known") never change.
_DASH = r"[-\u2010-\u2014]{1,3}"
_DASH_FORMS = (
    (rf"f{_DASH}(?:ing|in)\b", {"ing": "fucking", "in": "fuckin"}),
    (rf"f{_DASH}(?:cking|king)\b", "fucking"),
    (rf"f{_DASH}(?:cked|ked|ed)\b", "fucked"),
    (rf"f{_DASH}(?:cker|ker|er)\b", "fucker"),
    (rf"f{_DASH}(?:ck|k)\b", "fuck"),
    (rf"sh{_DASH}tty\b", "shitty"),
    (rf"sh{_DASH}t\b", "shit"),
    (rf"b{_DASH}tch\b", "bitch"),
    (rf"d{_DASH}mn\b", "damn"),
    (rf"a{_DASH}?{_DASH}hole\b", "asshole"),
    (rf"f{_DASH}(?=[\s.,!?;:)\"']|$)", "fuck"),  # a cut-off "f-" followed by a space or punctuation
)
_DASH_RES = [(re.compile(rf"(?<![\w-]){pattern}", re.IGNORECASE), word) for pattern, word in _DASH_FORMS]


def _unmask_dashes(text: str) -> str:
    def make(word):
        def sub(m):
            if isinstance(word, dict):
                tail = re.sub(rf"^f{_DASH}", "", m.group(0), flags=re.IGNORECASE).lower()
                out = word.get(tail, word["ing"])
            else:
                out = word
            if m.group(0).isupper() and len(m.group(0)) > 2:
                return out.upper()
            return out[0].upper() + out[1:] if m.group(0)[0].isupper() else out
        return sub

    for rx, word in _DASH_RES:
        text = rx.sub(make(word), text)
    return text


def unmask_profanity(text: str) -> str:
    """Replace masked swear words ("f**king", "f-ing") with the word itself ("fucking"),
    keeping the first letter's case. Tokens that match no known word are untouched."""
    text = _unmask_dashes(text or "")

    def restore(m):
        word = _unmask_token(m.group(1))
        if word is None:
            return m.group(0)
        if m.group(1).isupper():
            return word.upper()
        return word[0].upper() + word[1:] if m.group(1)[0].isupper() else word
    return _MASKED_RE.sub(restore, text)


def _is_name(m) -> bool:
    """"Dick Cheney" / "Dick Van Dyke": a capitalised Dick followed by another
    capitalised word is a person, not the slang."""
    return m.group(0) == "Dick" and re.match(r"\s+[A-Z]", m.string[m.end():]) is not None


def _matches(text: str):
    return [m for m in _PROFANITY_RE.finditer(text) if not _is_name(m)]


def _censor_word(word: str) -> str:
    """"fuck" -> "f***", "SHIT" -> "S***" - first letter kept (preserves the
    reader's ability to recognize what was said), case of the first letter
    preserved, rest replaced one-for-one with asterisks."""
    if len(word) <= 1:
        return word
    return word[0] + "*" * (len(word) - 1)


def find_profanity_words(text: str, unmask: bool = True) -> set:
    """Lowercase set of known profanity words present in `text` (whole-word
    matched; with `unmask`, masked spellings like "f**king" count too)."""
    return {m.group(0).lower() for m in _matches(unmask_profanity(text) if unmask else (text or ""))}


def profanity_was_censored(raw: str, output: str) -> bool:
    """True if `raw` contains a known profanity word that no longer appears
    anywhere in `output` (verbatim, case-insensitive) - catches the base
    model's own RLHF safety alignment silently dropping, euphemizing, or
    asterisking a swear word despite an explicit 'allow' (never censor)
    instruction in the prompt. Prompt instructions alone are not reliable
    here (verified directly: the same polish prompt's rule against censoring
    still lost words like "fucking" on some inputs) - this is the
    deterministic backstop, checked only when profanity_filter == "allow"
    (see transformer.py's sanity_check)."""
    raw_words = find_profanity_words(raw)
    if not raw_words:
        return False
    # The output is read as-is: an asterisked "f***ing" there IS the censoring we're catching.
    output_words = find_profanity_words(output, unmask=False)
    return not raw_words.issubset(output_words)


def apply_profanity_filter(text: str, mode: str) -> str:
    """Apply the configured profanity mode to already-polished text. `mode` is
    one of "allow" (words only restored from masks), "censor", "remove". An
    unrecognized mode is treated as "allow" - never silently censor without an
    explicit setting."""
    if not text:
        return text
    text = unmask_profanity(text)
    if mode not in ("censor", "remove"):
        return text

    found = _matches(text)
    if mode == "censor":
        out, last = [], 0
        for m in found:
            out += [text[last:m.start()], _censor_word(m.group(0))]
            last = m.end()
        return "".join(out) + text[last:]

    # mode == "remove": drop the word and tidy what's left - no double spaces,
    # no space before punctuation, no orphaned comma, and a sentence that lost
    # its first word starts with a capital again ("Fuck, I forgot" -> "I forgot").
    out, last = [], 0
    for m in found:
        out.append(text[last:m.start()])
        so_far = "".join(out)
        if not so_far.strip() or re.search(r"[.!?]\s*$", so_far):
            out.append(_START_MARK)
        last = m.end()
    s = "".join(out) + text[last:]
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r" +([.,!?;:])", r"\1", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(_START_MARK + r"[\s,;:]*([A-Za-z])", lambda m: m.group(1).upper(), s)
    return s.replace(_START_MARK, "").strip()
