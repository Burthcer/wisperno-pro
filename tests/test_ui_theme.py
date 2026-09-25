"""
Dark theme: every text/background pair the dashboard and overlays actually
use must stay readable (WCAG AA: 4.5:1 body text, 3:1 large text and
non-text accents), and the dashboard tabs/windows must take their colours
from src/ui/theme.py only - a hard-coded "#fff" or "white" in a tab is how a
light-on-light (or dark-on-dark) label slips in when the palette changes.

Run: python tests/test_ui_theme.py
"""

import re
import sys
from pathlib import Path

from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ui import theme  # noqa: E402

UI_DIR = BASE_DIR / "src" / "ui"
# The pill paints a translucent white sheen/close glyph over PILL_BG, and the
# tray/icon helpers draw the app mark - neither is a themed surface.
PAINTED_FILES = {"theme.py", "floating_pill.py", "tray.py", "icons.py"}
COLOUR_LITERAL_RE = re.compile(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\b|\brgba?\(|:\s*(?:white|black)\b")


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(fg: str, bg: str) -> float:
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def test_palette_is_dark() -> None:
    logger.info("--- Testing the dashboard palette is dark ---")
    for name in ("BG_APP", "BG_SIDEBAR", "BG_CARD", "BG_CARD_HOVER", "INPUT_BG", "PILL_BG"):
        assert _luminance(getattr(theme, name)) < 0.02, f"{name} {getattr(theme, name)} is not a dark surface"
    assert _luminance(theme.TEXT_PRIMARY) > 0.7, "primary text must be light on the dark surfaces"
    logger.success("PASS: surfaces dark, text light.")


def test_text_contrast() -> None:
    logger.info("--- Testing contrast of every text/background pair in use ---")
    body = [  # 4.5:1
        ("TEXT_PRIMARY", "BG_APP"), ("TEXT_PRIMARY", "BG_CARD"), ("TEXT_PRIMARY", "BG_CARD_HOVER"),
        ("TEXT_PRIMARY", "INPUT_BG"), ("TEXT_PRIMARY", "BG_SIDEBAR"), ("TEXT_PRIMARY", "TOOLTIP_BG"),
        ("TEXT_SECONDARY", "BG_APP"), ("TEXT_SECONDARY", "BG_CARD"), ("TEXT_SECONDARY", "BG_CARD_HOVER"),
        ("TEXT_SECONDARY", "INPUT_BG"), ("TEXT_SECONDARY", "BG_SIDEBAR"),
        ("ON_INK", "INK"), ("ON_INK", "INK_HOVER"),
        ("ACCENT_PRIMARY", "BG_CARD"), ("ACCENT_PRIMARY_ACTIVE", "BG_CARD"), ("ACCENT_SECONDARY", "BG_CARD"),
        ("BADGE_EMERALD", "BG_CARD"), ("DANGER", "BG_CARD"), ("SUCCESS", "BG_CARD"),
        ("PILL_TEXT", "PILL_BG"), ("PILL_TEXT_PRIMARY", "PILL_BG"), ("PILL_TEXT_PRIMARY", "PILL_SURFACE"),
        ("PILL_TEXT_PRIMARY", "PILL_BUTTON"), ("PILL_TEXT_PRIMARY", "PILL_BUTTON_HOVER"),
        ("PILL_ON_ACCENT", "PILL_ACCENT"), ("PILL_ON_ACCENT", "PILL_ACCENT_HOVER"),
        ("ACCENT_RECORDING", "PILL_BG"), ("ACCENT_PROCESSING", "PILL_BG"), ("ACCENT_SUCCESS", "PILL_BG"),
        ("ACCENT_ERROR", "PILL_BG"),
    ] + [("PILL_TEXT_PRIMARY", n) for n in ("PILL_BG_RECORDING", "PILL_BG_PROCESSING", "PILL_BG_TYPING",
                                            "PILL_BG_SUCCESS", "PILL_BG_WARNING")]
    low = [(fg, bg, round(contrast(getattr(theme, fg), getattr(theme, bg)), 2))
           for fg, bg in body if contrast(getattr(theme, fg), getattr(theme, bg)) < 4.5]
    assert not low, f"below 4.5:1: {low}"
    # Placeholder text is a hint, not content - AA large/non-text (3:1).
    assert contrast(theme.TEXT_PLACEHOLDER, theme.INPUT_BG) >= 3.0
    logger.success(f"PASS: {len(body)} text pairs at 4.5:1 or better, placeholder 3:1+.")


def test_no_hard_coded_colours_outside_theme() -> None:
    logger.info("--- Testing tabs/windows take colours from theme.py only ---")
    offenders = []
    for path in sorted(UI_DIR.glob("*.py")):
        if path.name in PAINTED_FILES:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
            if COLOUR_LITERAL_RE.search(code):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "hard-coded colours:\n" + "\n".join(offenders)
    logger.success("PASS: no colour literals in the dashboard tabs or overlay windows.")


def test_overlays_use_pill_tokens_only() -> None:
    logger.info("--- Testing the pill and Live window use the PILL_* palette ---")
    allowed = re.compile(r"theme\.(PILL_\w+|ACCENT_(RECORDING|PROCESSING|SUCCESS|ERROR)\w*|FONT_\w+|get_app_icon)\b")
    for name in ("floating_pill.py", "live_window.py"):
        uses = re.findall(r"theme\.\w+", (UI_DIR / name).read_text(encoding="utf-8"))
        stray = sorted({u for u in uses if not allowed.fullmatch(u)})
        assert not stray, f"{name} uses dashboard tokens: {stray}"
    logger.success("PASS: overlays independent of the dashboard palette.")


def test_bug_fix_rules_kept() -> None:
    logger.info("--- Testing the layout fixes survived the palette change ---")
    qss = theme.MAIN_WINDOW_QSS
    assert re.search(r"QLabel,\s*QCheckBox,\s*QRadioButton\s*\{\s*background-color:\s*transparent;", qss)
    assert "QFrame#" in qss or "#card" in qss.lower(), "card styles must be scoped by objectName"
    assert not re.search(r"^\s*QFrame\s*\{", qss, re.M), "an unscoped QFrame rule paints every frame as a card"
    logger.success("PASS: transparent labels and objectName-scoped cards kept.")


def run_all_tests() -> None:
    test_palette_is_dark()
    test_text_contrast()
    test_no_hard_coded_colours_outside_theme()
    test_overlays_use_pill_tokens_only()
    test_bug_fix_rules_kept()
    logger.success("ALL UI THEME TESTS PASSED")


if __name__ == "__main__":
    run_all_tests()
