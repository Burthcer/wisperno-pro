"""
Custom Vocabulary & Word-Replacement Engine for Wisperno.
Boosts transcription accuracy two ways:
  1. Whisper keyword biasing: canonical dictionary terms are appended to the
     `initial_prompt` so Whisper is more likely to transcribe them correctly.
  2. Phonetic/custom post-processing: raw transcripts are regex-corrected
     against a user dictionary (e.g. "pie torch" -> "PyTorch") before being
     handed to the LLM.

Backed by src/database.py (SQLite) rather than a flat file, so the Dictionary
tab's add/edit/remove is immediately durable and immediately reflected here.
"""

import difflib
import re
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple
from loguru import logger

if TYPE_CHECKING:
    from src.database import WispernoDB


# Whisper's prompt window (max_length // 2 - 1 in faster-whisper), minus a
# little headroom; hotwords get their own window of the same size.
WHISPER_PROMPT_TOKENS = 215
WHISPER_HOTWORDS_TOKENS = 215
TERMS_LEAD_IN = "Technical terms:"


# --- Sound-alike correction -------------------------------------------------
# Whisper often gets a dictionary word *almost* right - "Superbase" for
# Supabase, "Versil" for Vercel, "NuYen" for Nguyen, "Whisper Note" for
# Wisperno - and typically capitalizes it mid-sentence because it guessed a
# name. Only such name-like words are compared against the dictionary, which
# is what keeps ordinary words safe: measured on tests/fixtures/vocab_cases.json
# this recovered 4 more terms with no Whisper biasing, with zero changes to
# ~200 other transcripts checked against a 50-word dictionary.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
SOUND_ALIKE_MIN_RATIO = 0.8        # plain spelling similarity that counts as a match
SOUND_ALIKE_KEY_MIN_RATIO = 0.6    # ...or this, if they also sound the same (sound_key)


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def sound_key(text: str) -> str:
    """Crude English sound signature: first letter + consonant skeleton with
    common spelling variants merged (c/k/s, ph/f, z/s, y/i). "Versil" and
    "Vercel" both give "vrsl"."""
    s = _letters(text)
    if not s:
        return ""
    for a, b in (("ph", "f"), ("ck", "k"), ("qu", "kw"), ("x", "ks"), ("z", "s"), ("gh", "g"), ("wh", "w")):
        s = s.replace(a, b)
    s = re.sub(r"c(?=[eiy])", "s", s).replace("c", "k").replace("y", "i")
    key = s[0] + re.sub(r"[aeiouhw]", "", s[1:])
    return re.sub(r"(.)\1+", r"\1", key)


def _sounds_like(candidate: str, term: str) -> bool:
    a, b = _letters(candidate), _letters(term)
    if len(a) < 4 or len(b) < 4:
        return False  # too short to judge safely ("Tori"/"Tauri" is left alone)
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    if ratio >= SOUND_ALIKE_MIN_RATIO:
        return True
    key = sound_key(term)
    return ratio >= SOUND_ALIKE_KEY_MIN_RATIO and len(key) >= 3 and sound_key(candidate) == key


def _name_like(text: str, start: int, span: str) -> bool:
    """Capitalized mid-sentence, internal capitals ("WhisperNo"), or a pair of
    capitalized words ("Whisper Note") - how Whisper writes a name it guessed."""
    words = span.split()
    if any(re.search(r"[a-z][A-Z]", w) for w in words):
        return True
    if not all(w[0].isupper() for w in words):
        return False
    before = text[:start].rstrip()
    sentence_start = not before or before[-1] in ".!?\n:"
    return not sentence_start or len(words) == 2


class Vocabulary:
    """Loads dictionary entries from the database and applies keyword biasing + replacements."""

    def __init__(self, db: Optional["WispernoDB"] = None):
        self.db = db
        self.entries: List[Dict] = []  # rows: id, word, replacement, case_sensitive, category
        self.reload()

    def reload(self) -> None:
        """(Re)load dictionary entries from the database."""
        if not self.db:
            self.entries = []
            return
        rows = self.db.list_dictionary()
        # Longest phrase first, so multi-word entries match before shorter overlapping ones.
        rows.sort(key=lambda r: len(r["word"]), reverse=True)
        self.entries = rows
        logger.info(f"Vocabulary: loaded {len(self.entries)} dictionary entries from the database.")

    def add_entry(self, word: str, replacement: str, case_sensitive: bool = False, category: str = "Jargon") -> None:
        word, replacement = word.strip(), replacement.strip()
        if not self.db or not word or not replacement:
            return
        self.db.add_dictionary_entry(word, replacement, case_sensitive, category)
        self.reload()

    def remove_entry(self, entry_id: int) -> None:
        if not self.db:
            return
        self.db.delete_dictionary_entry(entry_id)
        self.reload()

    def apply_replacements(self, text: str) -> str:
        """Whole-word replacement of dictionary phrases in `text` (case-insensitive unless flagged)."""
        if not text or not self.entries:
            return text
        for entry in self.entries:
            flags = 0 if entry["case_sensitive"] else re.IGNORECASE
            pattern = r"(?<!\w)" + re.escape(entry["word"]) + r"(?!\w)"
            text = re.sub(pattern, entry["replacement"], text, flags=flags)
        return text

    def canonical_terms(self) -> List[str]:
        """Unique dictionary spellings (the replacement side), in load order."""
        terms: List[str] = []
        for entry in self.entries:
            if entry["replacement"] not in terms:
                terms.append(entry["replacement"])
        return terms

    def correct_sound_alikes(self, text: str) -> str:
        """Snap near-miss spellings of dictionary words to the dictionary
        spelling ("Superbase" -> "Supabase"). One- and two-word windows; a
        window containing a word that already is a dictionary term is never
        touched, so a correct neighbor can't be swallowed ("in PyTorch")."""
        terms = self.canonical_terms()
        if not text or not terms:
            return text
        known = {_letters(t) for t in terms}
        tokens = list(_TOKEN_RE.finditer(text))
        pieces, last, i = [], 0, 0
        while i < len(tokens):
            replaced = False
            for n in (2, 1):
                if i + n > len(tokens):
                    continue
                start, end = tokens[i].start(), tokens[i + n - 1].end()
                span = text[start:end]
                if n == 2 and not re.fullmatch(r"[A-Za-z'\-]+\s+[A-Za-z'\-]+", span):
                    continue
                if any(_letters(w) in known for w in span.split()) or not _name_like(text, start, span):
                    continue
                match = next((t for t in terms if _sounds_like(span, t)), None)
                if match:
                    logger.info(f"Dictionary: '{span}' -> '{match}' (sounds alike).")
                    pieces += [text[last:start], match]
                    last, i, replaced = end, i + n, True
                    break
            if not replaced:
                i += 1
        pieces.append(text[last:])
        return "".join(pieces)

    def restore_term_casing(self, text: str) -> str:
        """Put dictionary terms back in their exact spelling when a later step
        (the LLM polish, usually) re-cased them - "Github" -> "GitHub",
        "claude code" -> "Claude Code". All-lowercase terms are skipped, so
        this never lowercases a sentence-initial capital."""
        for term in self.canonical_terms():
            if term == term.lower():
                continue
            pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
            text = re.sub(pattern, lambda m: term, text, flags=re.IGNORECASE)
        return text

    def build_whisper_bias(
        self, base_prompt: str, count_tokens: Callable[[str], int], reserve_tokens: int = 0,
    ) -> Tuple[str, Optional[str]]:
        """(initial_prompt, hotwords) that tell Whisper which spellings to expect.

        Whisper only looks at ~223 tokens of initial_prompt (faster-whisper keeps
        the LAST ones) and separately ~223 tokens of hotwords (keeps the FIRST).
        Measured on 16 clips of names/jargon (tests/fixtures/vocab_cases.json):
        terms in the prompt got 21/22 right vs 13/22 with no dictionary - but
        with an 86-word dictionary the prompt overflowed and fell to 16/22. So:
        terms fill the prompt first (newest-added first, since those are the
        likeliest to matter now), then spill into hotwords, and the base style
        sentence goes LAST in the prompt so truncation can never cut it.
        `reserve_tokens` leaves room for context appended after the prompt."""
        terms = self._terms_newest_first()
        if not terms:
            return base_prompt, None
        prompt_budget = WHISPER_PROMPT_TOKENS - count_tokens(base_prompt) - reserve_tokens - count_tokens(TERMS_LEAD_IN + ".")
        in_prompt: List[str] = []
        in_hotwords: List[str] = []
        used_prompt = used_hotwords = 0
        for term in terms:
            cost = count_tokens(term) + 1  # + the ", " separator
            if used_prompt + cost <= prompt_budget:
                in_prompt.append(term)
                used_prompt += cost
            elif used_hotwords + cost <= WHISPER_HOTWORDS_TOKENS:
                in_hotwords.append(term)
                used_hotwords += cost
        prompt = f"{TERMS_LEAD_IN} {', '.join(in_prompt)}. {base_prompt}" if in_prompt else base_prompt
        return prompt, (", ".join(in_hotwords) if in_hotwords else None)

    def _terms_newest_first(self) -> List[str]:
        terms: List[str] = []
        for entry in sorted(self.entries, key=lambda e: e.get("id", 0), reverse=True):
            if entry["replacement"] not in terms:
                terms.append(entry["replacement"])
        return terms

    def build_initial_prompt(self, base_prompt: str) -> str:
        """Append canonical dictionary terms to Whisper's initial_prompt for keyword biasing."""
        if not self.entries:
            return base_prompt
        terms = []
        for entry in self.entries:
            if entry["replacement"] not in terms:
                terms.append(entry["replacement"])
        return f"{base_prompt} Technical terms: {', '.join(terms)}."


def _demo() -> None:
    """Self-check against a throwaway temp database - no JSON file involved."""
    import os
    import tempfile
    from src.database import WispernoDB

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    try:
        db = WispernoDB(path)
        db.add_dictionary_entry("pie torch", "PyTorch")
        db.add_dictionary_entry("git hub", "GitHub")
        db.add_dictionary_entry("json", "JSON")

        vocab = Vocabulary(db=db)
        text = "I was using pie torch and git hub to parse some json data"
        result = vocab.apply_replacements(text)
        assert result == "I was using PyTorch and GitHub to parse some JSON data", result

        # Word-boundary safety: "json" inside "jsonify" must NOT be replaced.
        assert vocab.apply_replacements("jsonify this") == "jsonify this"

        prompt = vocab.build_initial_prompt("Clean transcription.")
        assert "PyTorch" in prompt and "GitHub" in prompt and "JSON" in prompt

        vocab.add_entry("cuda", "CUDA")
        assert any(e["word"] == "cuda" for e in vocab.entries)
        cuda_id = next(e["id"] for e in vocab.entries if e["word"] == "cuda")
        vocab.remove_entry(cuda_id)
        assert all(e["word"] != "cuda" for e in vocab.entries)

        db.close()
        print("PASS: vocabulary replacement, word-boundary safety, biasing prompt, and add/remove all verified.")
    finally:
        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    _demo()
