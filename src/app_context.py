"""
Per-app dictation styles: the same words are formatted a little differently
depending on which app they're typed into, adapting to the
app you're in.

  default    - normal sentences: capitalized, final period, trailing space
  messaging  - chat apps (Slack, Discord, Teams, WhatsApp...): a one-line
               message drops its final period, as people text ("see you at 3")
  code       - editors and terminals (VS Code, Cursor, JetBrains, Windows
               Terminal...): a one-line dictation drops its final period and
               no trailing space is typed, so "git status" never becomes
               "git status. " at a prompt

Only the final period and the trailing space change. Questions and
exclamations keep their "?"/"!", multi-sentence and multi-line text (lists,
paragraphs) is left exactly as formatted, and nothing about the words
themselves changes. The app is read at paste time from the foreground
window's process name; users edit the app -> style table in Settings.
"""

import re
import sys
from typing import Dict, Optional

from loguru import logger

STYLES = ("default", "messaging", "code")
STYLE_LABELS = {
    "default": "Normal sentences",
    "messaging": "Chat (no final period)",
    "code": "Code / terminal (no final period, no trailing space)",
}

DEFAULT_APP_STYLES: Dict[str, str] = {
    # Messaging
    "slack.exe": "messaging", "discord.exe": "messaging", "ms-teams.exe": "messaging", "teams.exe": "messaging",
    "whatsapp.exe": "messaging", "telegram.exe": "messaging", "signal.exe": "messaging",
    "messenger.exe": "messaging", "element.exe": "messaging", "skype.exe": "messaging",
    # Code editors and terminals
    "code.exe": "code", "cursor.exe": "code", "windsurf.exe": "code", "devenv.exe": "code",
    "idea64.exe": "code", "pycharm64.exe": "code", "webstorm64.exe": "code", "rider64.exe": "code",
    "clion64.exe": "code", "goland64.exe": "code", "sublime_text.exe": "code", "notepad++.exe": "code",
    "windowsterminal.exe": "code", "cmd.exe": "code", "powershell.exe": "code", "pwsh.exe": "code",
    "wezterm-gui.exe": "code", "alacritty.exe": "code", "mintty.exe": "code",
}


def foreground_app() -> Optional[str]:
    """Lowercase executable name of the window that will receive the paste
    (e.g. "slack.exe"), or None if it can't be read (non-Windows, no window)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        import psutil

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower() if pid.value else None
    except Exception as e:
        logger.debug(f"Could not read the foreground app: {e}")
        return None


def style_for_app(app: Optional[str], app_styles: Dict[str, str]) -> str:
    style = app_styles.get((app or "").lower(), "default")
    return style if style in STYLES else "default"


def is_single_line_sentence(text: str) -> bool:
    """One line holding a single sentence - the only shape the chat/code
    styles touch. "Sounds good." yes; "Done. Shipping now." or a list, no."""
    stripped = text.strip()
    if not stripped or "\n" in stripped:
        return False
    body = stripped.rstrip(".!?")
    return not any(mark in body for mark in (". ", "! ", "? "))


def apply_app_style(text: str, style: str) -> str:
    """Final-period rule for chat/code styles; see the module docstring."""
    if style not in ("messaging", "code") or not is_single_line_sentence(text) or not text.endswith("."):
        return text
    if text.endswith("..") or re.search(r"\b\w+\.\w+\.$", text):
        return text  # an ellipsis, or an abbreviation like "U.S." / "e.g." - the period is part of it
    return text[:-1]


def wants_trailing_space(style: str) -> bool:
    return style != "code"
