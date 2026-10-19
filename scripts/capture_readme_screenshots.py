"""
Renders the README's screenshots offscreen into docs/images/.

Uses a throw-away database seeded with made-up demo entries - never your real
history, dictionary or settings - so the images are safe to publish.

Run: python scripts/capture_readme_screenshots.py
"""

import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE_DIR = Path(__file__).resolve().parent.parent
for p in (BASE_DIR, BASE_DIR / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

OUT = BASE_DIR / "docs" / "images"

DEMO_HISTORY = [
    ("Send the quarterly numbers to Priya by Friday, and cc the finance team.", "send the quarterly numbers to priya by friday and cc the finance team", "polish", 2.4, 640),
    ("I will answer both of your questions:\n\n1. I don't speak in English.\n2. I only want the app to be in English.",
     "i will answer both of your questions first i don't speak in english second i only want the app to be in english", "polish", 9.8, 1120),
    ("Visit dev.to/janedoe for the write-up.", "visit dev dot to slash janedoe for the write up", "polish", 3.1, 520),
    ("Hey team, quick update: the build is green and the installer is ready for testing.", "hey team quick update the build is green and the installer is ready for testing", "polish", 4.6, 710),
    ("Refactor the settings page so each option explains what it does.", "refactor the settings page so each option explains what it does", "polish", 3.9, 690),
]
DEMO_WORDS = [("kubernetes", "Kubernetes", "Jargon"), ("pie torch", "PyTorch", "Jargon"), ("wisperno", "Wisperno", "Name"), ("g p u", "GPU", "Jargon")]
DEMO_SNIPPETS = [("my email", "hello@example.com"), ("sign off", "Best regards,\nJane"), ("standup", "Yesterday: shipped the installer. Today: testing. Blockers: none.")]


def _seed(engine) -> None:
    from src.recent_audio import has_audio  # noqa: F401  (imported so the patch target exists)
    for polished, raw, mode, dur, latency in DEMO_HISTORY:
        engine.db.add_history("2026-10-16T10:%02d:00" % (10 + len(polished) % 40), dur, raw, polished, mode, latency)
    for word, replacement, category in DEMO_WORDS:
        engine.db.add_dictionary_entry(word, replacement, category=category)
    for trigger, expansion in DEMO_SNIPPETS:
        try:
            engine.db.add_snippet(trigger, expansion)
        except Exception:
            pass


def _hd(widget, scale: int = 3, transparent: bool = True):
    """Render a widget at `scale`x with the painter scaled (vector quality, not an upscaled bitmap).
    Transparent background by default so rounded shapes blend into any page colour."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap

    pix = QPixmap(widget.width() * scale, widget.height() * scale)
    pix.fill(Qt.GlobalColor.transparent if transparent else QColor("black"))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.scale(scale, scale)
    from PySide6.QtCore import QPoint
    widget.render(painter, QPoint(0, 0))
    painter.end()
    return pix


def _save(widget, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _hd(widget, 2, transparent=False).save(str(OUT / name))  # dashboards: 2x, opaque
    print("saved", name)


def _compose(parts, pad: int = 36, gap: int = 36, vertical: bool = False, labels=None):
    """Lay transparent images out in a row/column on a transparent canvas."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap, QPainter

    if vertical:
        width = max(i.width() for i in parts) + 2 * pad
        height = sum(i.height() for i in parts) + gap * (len(parts) - 1) + 2 * pad
    else:
        width = sum(i.width() for i in parts) + gap * (len(parts) - 1) + 2 * pad
        height = max(i.height() for i in parts) + 2 * pad
    sheet = QPixmap(width, height)
    sheet.fill(Qt.GlobalColor.transparent)
    q = QPainter(sheet)
    x = y = pad
    for img in parts:
        if vertical:
            q.drawPixmap((width - img.width()) // 2, y, img)
            y += img.height() + gap
        else:
            q.drawPixmap(x, (height - img.height()) // 2, img)
            x += img.width() + gap
    q.end()
    return sheet


def _demo_usage(engine) -> None:
    """Typical, made-up numbers so the System Usage image never shows this machine's real stats."""
    import types
    from src import storage_usage
    from src.system_monitor import SystemMonitor

    GB = 1024 ** 3
    snapshot = {
        "gpu_total_mb": 8192.0, "gpu_used_mb": 3480.0, "app_vram_mb": 3230.0, "app_shared_mb": 0.0,
        "app_vram_source": "per-process counter", "gpu_util_pct": 8, "gpu_temp_c": 47,
        "ram_total_mb": 32768.0, "ram_used_mb": 14100.0, "app_ram_mb": 2300.0, "thread_count": 41, "cpu_util_pct": 6.0,
    }
    SystemMonitor.snapshot = lambda self: snapshot
    storage_usage.storage_breakdown = lambda *a, **k: {
        "app": int(1.8 * GB), "models": int(3.0 * GB), "history": 240 * 1024, "recordings": 6 * 1024 ** 2, "free": 212 * GB,
    }
    engine.transcriber = types.SimpleNamespace(config=types.SimpleNamespace(model_name="large-v3-turbo", compute_type="int8_float16"))
    engine.transformer = types.SimpleNamespace(
        llm=object(), active_model_layers=29, active_model_name="Qwen2.5-1.5B-Instruct-Q8_0",
        config=types.SimpleNamespace(n_gpu_layers=-1),
    )


def _goto(win, tab) -> None:
    """Click the real sidebar entry, so the highlighted nav item matches the page shown."""
    from PySide6.QtWidgets import QListWidget

    win.findChild(QListWidget, "sidebarNav").setCurrentRow(win.stack.indexOf(tab))


def dashboard_shots() -> None:
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.ui import theme
    from test_ui_layout import _build_main_window

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    with mock.patch("src.recent_audio.has_audio", return_value=True):
        app, win, engine = _build_main_window()
        _seed(engine)
        _demo_usage(engine)
        win.resize(1280, 860)
        win.setStyleSheet(theme.MAIN_WINDOW_QSS)
        app.processEvents()
        tabs = {"history": win.history_tab, "transforms": win.transforms_tab, "dictionary": win.dictionary_tab,
                "snippets": win.snippets_tab}
        for name, tab in tabs.items():
            if hasattr(tab, "refresh"):
                tab.refresh()
            _goto(win, tab)
            QTest.qWait(1800)  # let the metric count-up animations finish
            _save(win, f"{name}.png")

        _goto(win, win.system_usage_tab)
        win.system_usage_tab.refresh()
        win.system_usage_tab.refresh_storage()
        QTest.qWait(1500)
        win.system_usage_tab._timer.stop()
        _save(win, "system-usage.png")

        # One image per Settings tab.
        _goto(win, win.settings_tab)
        sub_tabs = win.settings_tab.sub_tabs
        for i in range(sub_tabs.count()):
            sub_tabs.setCurrentIndex(i)
            QTest.qWait(300)
            _save(win, "settings-" + sub_tabs.tabText(i).lower().replace(" ", "-") + ".png")
        win.close()


def position_preset_diagram() -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QApplication
    from src.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    w, h, m = 640, 380, 28
    pm = QPixmap((w + 2 * m) * 3, (h + 2 * m) * 3)
    pm.fill(Qt.GlobalColor.transparent)
    q = QPainter(pm)
    q.scale(3, 3)
    q.setRenderHint(QPainter.RenderHint.Antialiasing)
    q.setPen(QPen(QColor(theme.BORDER_STRONG), 2))
    q.setBrush(QColor(theme.BG_CARD))
    q.drawRoundedRect(QRectF(m, m, w, h - 24), 10, 10)
    q.setBrush(QColor(theme.BG_SIDEBAR))
    q.drawRect(QRectF(m, m + h - 24, w, 24))  # taskbar
    spots = {"Top left": (0.12, 0.1), "Top center": (0.5, 0.1), "Top right": (0.88, 0.1),
             "Bottom left": (0.12, 0.78), "Bottom center\n(default)": (0.5, 0.78), "Bottom right": (0.88, 0.78)}
    font = QFont("Inter Tight"); font.setPointSize(9); q.setFont(font)
    for label, (fx, fy) in spots.items():
        cx, cy = m + fx * w, m + fy * (h - 24)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(theme.ACCENT_PRIMARY))
        q.drawRoundedRect(QRectF(cx - 36, cy - 8, 72, 16), 8, 8)
        q.setPen(QColor(theme.TEXT_SECONDARY))
        q.drawText(QRectF(cx - 70, cy + 12 if fy < 0.5 else cy - 46, 140, 34), Qt.AlignmentFlag.AlignCenter, label)
    q.end()
    OUT.mkdir(parents=True, exist_ok=True)
    pm.save(str(OUT / "pill-positions.png"))
    print("saved pill-positions.png")


def extra_window_shots() -> None:
    """Transform editor, Live Transcription window and the pill's three hover states (demo text only)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.ui import theme
    from src.ui.floating_pill import FloatingPill
    from src.ui.live_window import LiveTranscriptionWindow
    from test_ui_layout import _build_main_window

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    from PySide6.QtGui import QFont
    for family in ("Inter Tight", "Segoe UI Variable Text", "Segoe UI"):  # the offscreen backend has no emoji fallback of its own
        QFont.insertSubstitutions(family, ["Segoe UI Emoji"])

    # --- Transform editor (the Polite tone, with its prompt)
    with mock.patch("src.recent_audio.has_audio", return_value=True):
        app, win, engine = _build_main_window()
        win.resize(1280, 860)
        win.setStyleSheet(theme.MAIN_WINDOW_QSS)
        _goto(win, win.transforms_tab)
        win.transforms_tab._open_editor("tone_polite")
        win.transforms_tab.editor.test_input.setPlainText("hey can you send me the report by tomorrow i need it for the meeting")
        win.transforms_tab.editor.test_output.setPlainText("Could you please send me the report by tomorrow? I need it for the meeting.")
        QTest.qWait(600)
        _save(win, "transforms-editor.png")
        win.close()

    # --- Live Transcription window
    live = LiveTranscriptionWindow()
    live.append_chunk("Welcome everyone, thanks for joining the call. ")
    live.append_chunk("Today we will walk through the release plan and the open questions from last week. ")
    live.set_speculative_text("First, the installer is ready for")
    live.show()
    QTest.qWait(400)
    _hd(live, 3).save(str(OUT / "live-transcription.png"))
    live.close()

    # --- The pill when hovered: resting strip, mic + wand, wand open (arrow shown)
    _compose([_pill("idle"), _pill("idle", hover=True), _pill("idle", hover=True, wand=True)], pad=20, gap=50).save(
        str(OUT / "pill-hover.png"))
    print("saved pill-hover.png")


def _pill(state: str = "idle", hover: bool = False, wand: bool = False, shape: str = "pill"):
    import math
    from PySide6.QtTest import QTest
    from src.ui.floating_pill import FloatingPill

    p = FloatingPill(shape=shape)
    p.set_state(state)
    p._hover, p._hover_wand = hover, wand
    p._apply_size_targets()
    p._width_current, p._height_current = p._width_target, p._height_target
    p.resize(int(p._width_current), int(p._height_current))
    if state.startswith("recording"):
        for i in range(90):
            p.set_level(0.005 + 0.05 * abs(math.sin(i * 0.35)) * (1 if i % 7 else 0.3))
            p._tick()
    QTest.qWait(40)
    img = _hd(p, 4)
    p.close()
    return img


def pill_shots() -> None:
    """Every pill state, crisp and transparent: two rows (Pill shape, Box shape)."""
    from PySide6.QtWidgets import QApplication
    from src.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    states = ["idle", "loading", "recording:POLISH", "processing", "success", "mode_changed"]
    rows = [_compose([_pill(st, shape=shape) for st in states], pad=20, gap=40) for shape in ("pill", "box")]
    sheet = _compose(rows, pad=10, gap=24, vertical=True)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(str(OUT / "pill-states.png"))
    print("saved pill-states.png")


def pill_menu_shot() -> None:
    """The wand open (arrow shown) with the transform menu above it."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.ui import theme
    from src.ui.pill_menu import build_transform_menu

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    items = [("polish", "Polish"), ("prompt_engineer", "Prompt Engineer"), ("code_fix", "Detailed Code Fix Prompt"),
             ("grammar_correct", "Grammar Correct"), ("tone_polite", "Polite"), ("tone_professional", "Professional"),
             ("tone_casual", "Casual"), ("tone_concise", "Concise")]
    menu = build_transform_menu(None, items, "polish", lambda t: None, lambda: None)
    menu.popup(QPoint(0, 0))
    QTest.qWait(200)
    menu_img = _hd(menu, 3)
    menu.close()
    sheet = _compose([menu_img, _pill("idle", hover=True, wand=True)], vertical=True, gap=28, pad=20)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(str(OUT / "pill-menu.png"))
    print("saved pill-menu.png")


def paste_card_shot() -> None:
    """The 'No active text field detected' card (demo text only), before and after pressing Copy."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from src.ui import theme
    from src.ui.paste_card import PasteCard

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    card = PasteCard()
    card.show_for("Send the quarterly numbers to Priya by Friday, and cc the finance team. "
                  "Also remind everyone that the installer is ready for testing.", QPoint(900, 800))
    QTest.qWait(120)
    before = _hd(card, 3)
    card._copy()
    QTest.qWait(400)
    after = _hd(card, 3)
    card.close()
    before.save(str(OUT / "paste-card-single.png"))
    _compose([before, after], pad=16, gap=36).save(str(OUT / "paste-card.png"))
    print("saved paste-card.png")


def hero_image() -> None:
    """The README header: the dashboard with the pill and the paste card laid over it (all crisp)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from src.ui import theme

    dash = QPixmap(str(OUT / "history.png"))
    pill = _compose([_pill("idle", hover=True), _pill("idle", hover=True, wand=True)], pad=0, gap=40)
    card = QPixmap(str(OUT / "paste-card-single.png"))
    pad = 60
    canvas = QPixmap(dash.width() + 2 * pad, dash.height() + 2 * pad)
    canvas.fill(QColor(theme.BG_APP))
    q = QPainter(canvas)
    q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    q.drawPixmap(pad, pad, dash)
    pill_small = pill.scaledToWidth(int(canvas.width() * 0.30), Qt.TransformationMode.SmoothTransformation)
    card_small = card.scaledToWidth(int(canvas.width() * 0.27), Qt.TransformationMode.SmoothTransformation)
    px = canvas.width() - pill_small.width() - pad
    py = canvas.height() - pill_small.height() - pad // 2
    q.drawPixmap(px, py, pill_small)
    q.drawPixmap(canvas.width() - card_small.width() - pad, py - card_small.height() - 30, card_small)
    q.end()
    canvas.save(str(OUT / "hero.png"))
    print("saved hero.png")


if __name__ == "__main__":
    pill_shots()
    paste_card_shot()
    pill_menu_shot()
    position_preset_diagram()
    dashboard_shots()
    extra_window_shots()
    hero_image()
