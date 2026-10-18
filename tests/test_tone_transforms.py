"""Tone transforms (Polite / Professional / Casual / Concise): seeded once, deletable, list-safe.

Run: python tests/test_tone_transforms.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

from src.database import WispernoDB  # noqa: E402

TONES = ("tone_polite", "tone_professional", "tone_casual", "tone_concise")


def test_seed_once_and_respect_choices() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = WispernoDB(os.path.join(d, "t.db"))
        assert all(db.get_transform(t) for t in TONES), "a fresh database ships the tones"
        db.update_transform("tone_casual", is_active=0)
        assert db.seed_tone_transforms() is False, "a fresh database is already flagged as seeded"
        assert db.get_transform("tone_casual")["is_active"] == 0, "a tone you switched off stays off"
        # an existing install (no flag, no tones) gets all four exactly once
        with db._cursor() as cur:
            cur.execute("DELETE FROM transforms WHERE id LIKE 'tone_%'")
            cur.execute("DELETE FROM settings WHERE key = 'seeded_tone_transforms_v1'")
        assert db.seed_tone_transforms() is True
        assert all(db.get_transform(t) for t in TONES)
        db.close()
    print("PASS: tones are seeded once and a switched-off tone stays off.")


def test_tone_rewrites_list_items_one_by_one() -> None:
    from src.transformer import Transformer

    t = Transformer.__new__(Transformer)  # no model needed: _run is replaced
    seen = []
    t._run = lambda body, label, prompt, sep: (seen.append(body) or body.upper())
    out = t._run_tone("question one what is the budget question two who owns it", "tone_concise", "p")
    assert out == "1. WHAT IS THE BUDGET?\n2. WHO OWNS IT?", out
    assert seen == ["What is the budget?", "Who owns it?"], seen
    print("PASS: a spoken list is laid out and each item rewritten separately, markers kept.")


if __name__ == "__main__":
    test_seed_once_and_respect_choices()
    test_tone_rewrites_list_items_one_by_one()
