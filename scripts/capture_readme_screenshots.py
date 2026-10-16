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
DEMO_SNIPPETS = [("my email", "hello@example.com"), ("sign off", "Best regards,\nDev"), ("standup", "Yesterday: shipped the installer. Today: testing. Blockers: none.")]


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


def _save(widget, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(OUT / name))
    print("saved", name)


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
        "app": int(4.9 * GB), "models": int(3.1 * GB), "history": 240 * 1024, "recordings": 6 * 1024 ** 2, "free": 212 * GB,
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


def pill_shots() -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication
    from src.ui import theme
    from src.ui.floating_pill import FloatingPill

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    states = [("Idle", "idle"), ("Starting", "loading"), ("Recording", "recording:POLISH"), ("Processing", "processing"), ("Done", "success"), ("Mode change", "mode_changed")]
    import math
    rows = []
    for shape in ("pill", "box"):
        row = []
        for label, state in states:
            p = FloatingPill(shape=shape)
            p.set_state(state)
            p._width_current, p._height_current = p._width_target, p._height_target
            p.resize(int(p._width_current), int(p._height_current))
            if state.startswith("recording"):
                for i in range(90):
                    p.set_level(0.005 + 0.05 * abs(math.sin(i * 0.35)) * (1 if i % 7 else 0.3))
                    p._tick()
            row.append((label, p.grab()))
            p.close()
        rows.append((shape, row))
    scale, pad, label_h = 3, 24, 22
    col_w = max(img.width() for _, r in rows for _, img in r) + pad
    width = col_w * len(states) + pad + 110
    height = (30 + label_h + pad) * len(rows) + 40
    sheet = QPixmap(width * scale // 3, height)
    sheet.fill(QColor(theme.BG_APP))
    q = QPainter(sheet)
    q.setPen(QColor(theme.TEXT_SECONDARY))
    font = QFont("Inter Tight"); font.setPointSize(9); q.setFont(font)
    y = 20
    for shape, row in rows:
        q.drawText(10, y + 28, "Pill" if shape == "pill" else "Box")
        for i, (label, img) in enumerate(row):
            x = 110 + i * col_w
            q.drawPixmap(x + (col_w - img.width()) // 2, y + 8, img)
            q.drawText(QRectF(x, y + 8 + 30 + 4, col_w, 20), Qt.AlignmentFlag.AlignCenter, label)
        y += 30 + label_h + pad
    q.end()
    sheet = sheet.scaled(sheet.width() * 2, sheet.height() * 2, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    OUT.mkdir(parents=True, exist_ok=True)
    sheet.save(str(OUT / "pill-states.png"))
    print("saved pill-states.png")


def position_preset_diagram() -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QApplication
    from src.ui import theme

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    w, h, m = 640, 380, 28
    pm = QPixmap(w + 2 * m, h + 2 * m)
    pm.fill(QColor(theme.BG_APP))
    q = QPainter(pm)
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


if __name__ == "__main__":
    pill_shots()
    position_preset_diagram()
    dashboard_shots()
