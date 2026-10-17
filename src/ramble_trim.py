"""
Trim spoken padding: "...so yeah, I guess yeah this will be version 1.4 and yeah accordingly do so" ->
"...this will be version 1.4 accordingly do so".

Rule-based and deliberately narrow, like self_correction.py: it only removes a small list of phrases that carry
no meaning when they stand as an aside, trail off a sentence, or glue two thoughts ("and yeah", "so yeah"). It
never touches a word that could be an answer or an opinion ("yeah, I can do that", "I guess it works" stay), and
if a pass would delete more than 40% of the words it gives the text back unchanged.
The untouched transcript is still stored in History's raw transcript. Off via AppConfig.trim_rambling.
"""

import re

# Aside fenced in commas: "it works, I mean, mostly". Both commas go with it.
_FENCED = re.compile(
    r",\s*(?:i guess(?: yeah)?|i mean|basically|sort of|kind of|or whatever|you know what i mean)\s*,\s*", re.IGNORECASE
)
# Trails off the end of a sentence: "...done, or whatever." / "...fine, yeah." / "...fine, I guess."
_TRAILING = re.compile(
    r",?\s*\b(?:or whatever|and stuff|and yeah|so yeah|you know what i mean|if that makes sense)\b(?=\s*(?:[.!?]|$))"
    r"|,\s*(?:yeah|i guess(?: yeah)?)(?=\s*(?:[.!?]|$))",
    re.IGNORECASE,
)
# Glue between thoughts: "and yeah accordingly", "so yeah, then", "I guess yeah this".
_GLUE = re.compile(r"\b(?:(?:and|so) yeah|i guess,? yeah|yeah,? i guess)\b,?\s*", re.IGNORECASE)
# A sentence that opens with an aside: "I mean, the build is slow." / "Basically, we ship Friday."
_LEADING = re.compile(r"(^|(?<=[.!?]\s))(?:i mean|basically),\s*", re.IGNORECASE)

MAX_REMOVED_FRACTION = 0.4


def trim_rambling(text: str) -> str:
    if not text:
        return text
    out = _FENCED.sub(" ", text)
    out = _TRAILING.sub("", out)
    out = _GLUE.sub("", out)
    out = _LEADING.sub(r"\1", out)
    if out == text:
        return text
    out = re.sub(r"[ \t]+([,.!?])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = out.strip(" ,")
    out = out[:1].upper() + out[1:]
    before, after = len(text.split()), len(out.split())
    if after < 3 or (before - after) / before > MAX_REMOVED_FRACTION:
        return text  # ponytail: a blunt size guard; if real speech is ever eaten, tighten the patterns instead
    return out
