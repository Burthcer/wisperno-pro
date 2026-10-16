"""
Shared helper for giving a dashboard tab its own isolated, internal scroll
area - own scrollbar, own scroll position, never shared with another tab's
(see main_window.py's MainWindow._on_nav_changed / content_scroll comments
for the cross-tab scroll-leakage bug this pattern fixes).
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QScrollArea


def make_scrollable_layout(outer: QWidget) -> QVBoxLayout:
    """Wraps `outer`'s content in its own QScrollArea and returns the inner
    QVBoxLayout to build content on - a drop-in replacement for
    QVBoxLayout(outer). Stores the QScrollArea as `outer._scroll_area` so
    callers can reset scroll position (`outer._scroll_area.verticalScrollBar().setValue(0)`)
    on tab switch, e.g. via a `reset_scroll()` method."""
    outer_layout = QVBoxLayout(outer)
    outer_layout.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    outer_layout.addWidget(scroll)
    container = QWidget()
    inner_layout = QVBoxLayout(container)
    scroll.setWidget(container)
    outer._scroll_area = scroll
    return inner_layout


def clamp_to_screen(widget, margin: int = 8) -> None:
    """Shrink and move a top-level window so it sits fully inside the usable
    area (screen minus taskbar) of the screen it is on - so a tall panel is
    never cut off by the screen edge or hidden behind the taskbar."""
    screen = widget.screen()
    if screen is None:
        return
    geo = screen.availableGeometry().adjusted(margin, margin, -margin, -margin)
    w, h = min(widget.width(), geo.width()), min(widget.height(), geo.height())
    if (w, h) != (widget.width(), widget.height()):
        widget.resize(w, h)
    widget.move(min(max(widget.x(), geo.left()), geo.right() - w + 1),
                min(max(widget.y(), geo.top()), geo.bottom() - h + 1))
