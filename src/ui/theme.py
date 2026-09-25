"""
Centralized design tokens for Wisperno's Qt UI (floating pill + main dashboard).
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
# Stays dark on purpose: it floats over whatever app you're typing in, and a
# dark capsule reads on light and dark apps alike (as Wispr Flow's does).
PILL_BG = "#0B0B0F"
PILL_BG_ALPHA = 0.92
PILL_BORDER = "#1F1F2B"
PILL_TEXT = "#A0A0B0"
PILL_TEXT_PRIMARY = "#EDEDED"
PILL_SURFACE = "#17171F"           # inset areas (Live Transcription's text box)
PILL_BUTTON = "#1C1C26"
PILL_BUTTON_HOVER = "#262632"
# The dark overlays (pill, Live Transcription window) use only PILL_* text and
# surface colours - the dashboard's TEXT_*/BG_* below are for a light canvas.

ACCENT_RECORDING = "#EF4444"       # clean red - listening
ACCENT_RECORDING_DIM = "#5C2222"
ACCENT_PROCESSING = "#A855F7"      # radiant violet-purple - transforming
ACCENT_PROCESSING_DIM = "#3B2158"
ACCENT_SUCCESS = "#30D158"         # emerald - injected
ACCENT_ERROR = "#FF9F0A"           # amber - init taking abnormally long / failed

# --- Main dashboard ---------------------------------------------------------
# Warm light design (Wispr Flow-like): cream canvas, white cards, ink text,
# serif display headings, black ink primary buttons, and one violet accent
# kept for selection, focus and the active tab.
BG_APP = "#FAF8F5"
BG_SIDEBAR = "#F3F0EA"
SIDEBAR_BORDER = "#E8E3DA"
BG_CARD = "#FFFFFF"
BG_CARD_HOVER = "#F5F2EC"
BORDER_SUBTLE = "#E8E3DA"
BORDER_STRONG = "#CFC8BC"
INPUT_BG = "#FFFFFF"
INPUT_BORDER = "#DDD7CD"
TEXT_PRIMARY = "#1C1B1A"
TEXT_SECONDARY = "#6B665E"
TEXT_PLACEHOLDER = "#A29C93"
INK = "#1C1B1A"                    # primary buttons
INK_HOVER = "#3A3732"
ACCENT_PRIMARY = "#7C3AED"
ACCENT_PRIMARY_ACTIVE = "#6D28D9"  # accent text on light surfaces
ACCENT_PRIMARY_HOVER = "#6D28D9"
ACCENT_PRIMARY_WASH = "rgba(124, 58, 237, 0.10)"
ACCENT_SECONDARY = "#7C5CD6"       # jargon/category badges
DANGER = "#DC2626"
DANGER_WASH = "#FEF2F2"
SUCCESS = "#15803D"

FONT_FAMILY = "Segoe UI Variable Text, Segoe UI, Inter"
FONT_FAMILY_DISPLAY = "Georgia, Cambria, serif"  # headings only: Georgia's old-style 0 reads as "o"
FONT_FAMILY_NUMERIC = "Segoe UI Variable Display, Segoe UI"  # big numbers (metrics)
FONT_FAMILY_MONO = "Cascadia Mono, Consolas, monospace"

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
    background-color: {INK};
    color: #FFFFFF;
    border: none;
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
    border-radius: 10px;
    border: 1px solid transparent;
}}
QListWidget#sidebarNav::item:selected {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
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
    color: {TEXT_PRIMARY};
    padding: 8px 20px 12px 20px;
}}
QPushButton#liveTranscribeBtn {{
    background-color: {DANGER_WASH};
    border: 1px solid #F5C2C2;
    border-radius: 10px;
    margin: 0 10px 12px 10px;
    padding: 9px 12px;
    color: {DANGER};
    font-weight: 600;
    text-align: left;
}}
QPushButton#liveTranscribeBtn:hover {{
    background-color: #FDE4E4;
    border-color: {DANGER};
}}
QLabel#versionFooter {{
    color: {TEXT_PLACEHOLDER};
    font-size: 8pt;
    padding: 6px 20px;
}}
QFrame#card, QFrame#metricCard {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 14px;
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {INPUT_BG};
    border: 1px solid {INPUT_BORDER};
    border-radius: 10px;
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY};
    selection-color: #FFFFFF;
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
    border-radius: 10px;
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
    color: #FFFFFF;
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
    border-color: #F5C2C2;
}}
QPushButton#filterPill {{
    background-color: transparent;
    border: 1px solid {INPUT_BORDER};
    border-radius: 16px;
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
    color: #FFFFFF;
    font-weight: 600;
}}
QTableWidget, QListWidget, QTreeWidget {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 14px;
    gridline-color: {BG_SIDEBAR};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT_PRIMARY_WASH};
    selection-color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: {BG_CARD};
    color: {TEXT_SECONDARY};
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
    border-bottom: 2px solid {INK};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 2px 2px 0px;
}}
QScrollBar::handle:vertical {{
    background: #DAD4CA;
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
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    background-color: {BG_CARD};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT_PRIMARY};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT_PRIMARY};
    border-color: {ACCENT_PRIMARY};
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
QLabel#metricLabel {{ color: {TEXT_SECONDARY}; font-size: 8pt; }}
QLabel#sectionTitle {{
    font-family: {FONT_FAMILY_DISPLAY};
    font-size: 17pt;
    font-weight: 400;
    color: {TEXT_PRIMARY};
    padding: 4px 0 8px 0;
}}
"""
