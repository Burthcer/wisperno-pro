"""
Centralized design tokens for Wisperno's Qt UI (floating pill + main dashboard),
dark theme.
Plain hex strings - usable directly in QSS stylesheets or wrapped in QColor by
callers. Every surface/text colour in the dashboard comes from here; tabs
shouldn't hard-code their own.
"""

from PySide6.QtGui import QIcon

from src.config import get_base_dir


def get_app_icon() -> QIcon:
    """Resolve assets/icons/wisperno.ico next to the app root (frozen-safe)."""
    icon_path = get_base_dir() / "assets" / "icons" / "wisperno.ico"
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()

# --- Floating pill ------------------------------------------------------
# Same warm near-black as the dashboard (and devbhamaria.com); it floats over
# whatever app you're typing in, so it stays opaque-ish and hairline-bordered.
PILL_BG = "#0C0C0B"
PILL_BG_ALPHA = 0.94
PILL_BORDER = "#2A2926"
PILL_TEXT = "#AAA79E"
PILL_TEXT_PRIMARY = "#ECEBE6"
PILL_SURFACE = "#151513"           # inset areas (Live Transcription's text box)
PILL_BUTTON = "#1E1D1B"
PILL_BUTTON_HOVER = "#2A2926"
# Capsule tint per state (the accent colour below carries the state's hue).
PILL_BG_RECORDING = "#140E0B"
PILL_BG_PROCESSING = "#120F0C"
PILL_BG_TYPING = "#0F0F0E"
PILL_BG_SUCCESS = "#0D1410"
PILL_BG_WARNING = "#17130A"
PILL_ACCENT = "#FF5714"            # filled buttons on the overlays (dark text 6.2:1)
PILL_ACCENT_HOVER = "#FF7A3D"
PILL_ON_ACCENT = "#0C0C0B"
# The overlays (pill, Live Transcription window) use only PILL_* text and
# surface colours, so the dashboard palette can change without touching them.

ACCENT_RECORDING = "#FF5714"       # brand orange - listening
ACCENT_RECORDING_DIM = "#5A2410"
ACCENT_PROCESSING = "#ECEBE6"      # warm white - transforming
ACCENT_PROCESSING_DIM = "#3A3834"
ACCENT_SUCCESS = "#5FD38D"         # injected
ACCENT_ERROR = "#F5C542"           # yellow - init taking abnormally long / failed

# --- Main dashboard ---------------------------------------------------------
# Taken from devbhamaria.com: warm near-black canvas (#0c0c0b / #151513 /
# #1e1d1b), warm off-white ink, hairline #2a2926 borders and ONE orange accent
# (#ff5714) whose fills carry dark text. Contrast of every text/background pair
# is checked in tests/test_ui_theme.py.
BG_APP = "#0C0C0B"
BG_SIDEBAR = "#0F0F0E"
SIDEBAR_BORDER = "#2A2926"
BG_CARD = "#151513"
BG_CARD_HOVER = "#1E1D1B"
BORDER_SUBTLE = "#2A2926"
BORDER_STRONG = "#3E3C38"
INPUT_BG = "#151513"
INPUT_BORDER = "#2A2926"
TEXT_PRIMARY = "#ECEBE6"
TEXT_SECONDARY = "#AAA79E"
TEXT_PLACEHOLDER = "#8A877E"
INK = "#FF5714"                    # primary buttons / active filter pill (dark text: 6.6:1)
INK_HOVER = "#FF7A3D"
ON_INK = "#0C0C0B"                 # text on INK / ACCENT_PRIMARY fills
ACCENT_PRIMARY = "#FF5714"
ACCENT_PRIMARY_ACTIVE = "#FF7A3D"  # accent text on dark surfaces
ACCENT_PRIMARY_HOVER = "#FF7A3D"
ACCENT_PRIMARY_WASH = "rgba(255, 87, 20, 0.14)"
ACCENT_SECONDARY = "#E3C07A"       # jargon/category badges
BADGE_EMERALD = "#6FCF97"          # History "transform"/"live" badges
DANGER = "#F26B5B"
DANGER_WASH = "rgba(242, 107, 91, 0.10)"
DANGER_WASH_HOVER = "rgba(242, 107, 91, 0.18)"
DANGER_BORDER = "#5C2A24"
SUCCESS = "#5FD38D"
TOOLTIP_BG = "#1E1D1B"
SCROLLBAR_HANDLE = "#34322F"
VRAM_GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF5714, stop:1 #FF9A3D)"
RAM_GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6B6962, stop:1 #AAA79E)"

# The site's own faces (bundled in assets/fonts - see load_fonts()), with the
# Windows system faces as the fallback if a font file is ever missing.
FONT_FAMILY = "Inter Tight, Segoe UI Variable Text, Segoe UI"
FONT_FAMILY_DISPLAY = "Inter Tight, Segoe UI Variable Display, Segoe UI"
FONT_FAMILY_NUMERIC = "Inter Tight, Segoe UI Variable Display, Segoe UI"  # big numbers (metrics)
FONT_FAMILY_MONO = "JetBrains Mono, Cascadia Mono, Consolas, monospace"


def load_fonts() -> None:
    """Register the bundled Inter Tight / JetBrains Mono so QSS font-family
    names resolve on machines that don't have them installed. Call once after
    the QApplication exists; a missing file just means the fallback faces."""
    from PySide6.QtGui import QFontDatabase

    fonts_dir = get_base_dir() / "assets" / "fonts"
    for name in ("InterTight-Variable.ttf", "JetBrainsMono-Variable.ttf"):
        path = fonts_dir / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))

# Checkboxes: an unticked box needs an outline you can actually see on the dark
# cards, and a ticked one needs a tick (an orange fill alone reads as "maybe").
CHECKBOX_OFF_BORDER = "#8A877E"
CHECKMARK_ICON = (get_base_dir() / "assets" / "icons" / "check.png").as_posix()

MAIN_WINDOW_QSS = f"""
QMainWindow, QWidget {{
    background-color: {BG_APP};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: 10pt;
}}
/* Text sits on whatever surface holds it - with BG_APP from the rule above,
   every label/checkbox inside a white card would show up as a cream block. */
QLabel, QCheckBox, QRadioButton {{
    background-color: transparent;
}}
QToolTip {{
    background-color: {TOOLTIP_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    padding: 6px 8px;
    border-radius: 6px;
}}
QWidget#sidebar {{
    background-color: {BG_SIDEBAR};
    border-right: 1px solid {SIDEBAR_BORDER};
}}
QListWidget#sidebarNav {{
    background-color: transparent;
    border: none;
    padding: 4px 10px;
    outline: none;
}}
QListWidget#sidebarNav::item {{
    color: {TEXT_SECONDARY};
    padding: 8px 12px;
    margin: 1px 0;
    height: 20px;
    border-radius: 8px;
    border: 1px solid transparent;
    border-left: 2px solid transparent;
}}
QListWidget#sidebarNav::item:selected {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-left: 2px solid {ACCENT_PRIMARY};
    color: {TEXT_PRIMARY};
    font-weight: 600;
}}
QListWidget#sidebarNav::item:hover:!selected {{
    background-color: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
}}
QLabel#brand {{
    font-family: {FONT_FAMILY_DISPLAY};
    font-size: 16pt;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    padding: 8px 20px 12px 20px;
}}
QPushButton#liveTranscribeBtn {{
    background-color: {DANGER_WASH};
    border: 1px solid {DANGER_BORDER};
    border-radius: 16px;
    margin: 0 10px 12px 10px;
    padding: 9px 12px;
    color: {DANGER};
    font-weight: 600;
    text-align: left;
}}
QPushButton#liveTranscribeBtn:hover {{
    background-color: {DANGER_WASH_HOVER};
    border-color: {DANGER};
}}
QLabel#versionFooter {{
    color: {TEXT_PLACEHOLDER};
    font-family: {FONT_FAMILY_MONO};
    font-size: 8pt;
    padding: 6px 20px;
}}
QFrame#card, QFrame#metricCard {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 12px;
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {INPUT_BG};
    border: 1px solid {INPUT_BORDER};
    border-radius: 8px;
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY};
    selection-color: {ON_INK};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
    border: 1px solid {BORDER_STRONG};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT_PRIMARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    padding: 4px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY_WASH};
    selection-color: {TEXT_PRIMARY};
    outline: none;
}}
QPushButton {{
    background-color: {BG_CARD};
    border: 1px solid {INPUT_BORDER};
    border-radius: 12px;   /* pill-ish, but never more than half the button height: Qt then draws square corners */
    padding: 7px 16px;
    color: {TEXT_PRIMARY};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {BG_CARD_HOVER};
    border-color: {BORDER_STRONG};
}}
QPushButton:pressed {{
    background-color: {BORDER_SUBTLE};
}}
QPushButton#primary {{
    background-color: {INK};
    border: none;
    color: {ON_INK};
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background-color: {INK_HOVER};
}}
QPushButton#danger {{
    color: {DANGER};
}}
QPushButton#danger:hover {{
    background-color: {DANGER_WASH};
    border-color: {DANGER_BORDER};
}}
QPushButton#filterPill {{
    background-color: transparent;
    border: 1px solid {INPUT_BORDER};
    border-radius: 12px;
    padding: 6px 14px;
    color: {TEXT_SECONDARY};
}}
QPushButton#filterPill:hover {{
    color: {TEXT_PRIMARY};
    background-color: {BG_CARD};
}}
QPushButton#filterPill[active="true"] {{
    background-color: {INK};
    border: 1px solid {INK};
    color: {ON_INK};
    font-weight: 600;
}}
QTableWidget, QListWidget, QTreeWidget {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 12px;
    gridline-color: {BG_SIDEBAR};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY_WASH};
    selection-color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: {BG_CARD};
    color: {TEXT_SECONDARY};
    font-family: {FONT_FAMILY_MONO};
    font-size: 8pt;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
    padding: 8px 6px;
}}
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {BORDER_SUBTLE};
    background-color: {BG_APP};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 8px 2px;
    margin-right: 22px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT_PRIMARY};
}}
QTabBar::tab:selected {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    font-weight: 600;
    border-bottom: 2px solid {ACCENT_PRIMARY};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 2px 2px 0px;
}}
QScrollBar::handle:vertical {{
    background: {SCROLLBAR_HANDLE};
    min-height: 28px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BORDER_STRONG};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {CHECKBOX_OFF_BORDER};
    border-radius: 5px;
    background-color: {BG_APP};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT_PRIMARY};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT_PRIMARY};
    border-color: {ACCENT_PRIMARY};
    image: url({CHECKMARK_ICON});
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER_SUBTLE};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    height: 4px;
    background: {ACCENT_PRIMARY};
    border-radius: 2px;
}}
QSlider::add-page:horizontal {{
    height: 4px;
    background: {BORDER_SUBTLE};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: {BG_CARD};
    border: 2px solid {ACCENT_PRIMARY};
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_PRIMARY_WASH};
}}
QProgressBar {{
    background-color: {BORDER_SUBTLE};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: {TEXT_PRIMARY};
}}
QProgressBar::chunk {{
    background-color: {ACCENT_PRIMARY};
    border-radius: 4px;
}}
QLabel#metric {{ font-family: {FONT_FAMILY_NUMERIC}; font-size: 20pt; font-weight: 600; color: {TEXT_PRIMARY}; }}
QLabel#metricLabel {{ color: {TEXT_SECONDARY}; font-family: {FONT_FAMILY_MONO}; font-size: 8pt; }}
QLabel#sectionTitle {{
    font-family: {FONT_FAMILY_DISPLAY};
    font-size: 17pt;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    padding: 4px 0 8px 0;
}}
"""
