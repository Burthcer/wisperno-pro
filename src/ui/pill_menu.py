"""
The transform menu that opens from the floating pill's wand button:

    Polish                                  (tick)
    Prompt Engineer
    Detailed Code Fix Prompt
    ------------------------------------------
    (gear) Configure transforms

Drawn by hand (rows are small custom widgets) so it matches the pill's dark look exactly and never needs
image assets. Colours come from the PILL_* tokens in theme.py only.
"""

from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QWidget, QWidgetAction

from src.ui import theme

ROW_H = 36
MENU_W = 264


def _font(weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    families = [f.strip() for f in theme.FONT_FAMILY.split(",")]
    font = QFont(families[0])
    font.setFamilies(families)
    font.setPointSizeF(10.0)
    font.setWeight(weight)
    return font


class _Row(QWidget):
    """One clickable line: text on the left, an optional tick (selected) or gear on the right."""

    def __init__(self, text: str, on_click: Callable[[], None], checked: bool = False, gear: bool = False):
        super().__init__()
        self._text, self._on_click, self._checked, self._gear = text, on_click, checked, gear
        self._hover = False
        self.setFixedSize(MENU_W - 12, ROW_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.PILL_BUTTON_HOVER))
            p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 9, 9)
        left = 38 if self._gear else 14
        p.setPen(QColor(theme.PILL_TEXT_PRIMARY if (self._checked or self._hover or self._gear) else theme.PILL_TEXT))
        p.setFont(_font(QFont.Weight.DemiBold if self._checked else QFont.Weight.Normal))
        p.drawText(QRectF(left, 0, self.width() - left - 40, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        if self._checked:
            cx, cy = self.width() - 24.0, self.height() / 2.0
            pen = QPen(QColor(theme.PILL_ACCENT), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            tick = QPainterPath(QPointF(cx - 5.5, cy + 0.5))
            tick.lineTo(cx - 1.5, cy + 4.5)
            tick.lineTo(cx + 6.0, cy - 4.0)
            p.drawPath(tick)
        if self._gear:
            self._paint_gear(p, QPointF(21.0, self.height() / 2.0))
        p.end()

    @staticmethod
    def _paint_gear(p: QPainter, c: QPointF) -> None:
        pen = QPen(QColor(theme.PILL_TEXT_PRIMARY), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 4.0, 4.0)
        import math

        for k in range(8):  # eight short teeth around the ring
            a = k * math.pi / 4
            p.drawLine(QPointF(c.x() + 6.2 * math.cos(a), c.y() + 6.2 * math.sin(a)),
                       QPointF(c.x() + 8.2 * math.cos(a), c.y() + 8.2 * math.sin(a)))


class _Divider(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(MENU_W - 12, 13)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setPen(QPen(QColor(theme.PILL_BORDER), 1))
        p.drawLine(8, 6, self.width() - 8, 6)
        p.end()


def build_transform_menu(
    parent: Optional[QWidget],
    items: List[Tuple[str, str]],
    active_id: str,
    on_select: Callable[[str], None],
    on_configure: Callable[[], None],
) -> QMenu:
    """`items` is [(transform id, title), ...]. Picking one makes it the pill's wand transform and closes the menu."""
    menu = QMenu(parent)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    menu.setStyleSheet(
        f"QMenu {{ background-color: {theme.PILL_BG}; border: 1px solid {theme.PILL_BORDER}; border-radius: 14px; padding: 6px; }}"
    )

    def add(widget: QWidget) -> None:
        action = QWidgetAction(menu)
        action.setDefaultWidget(widget)
        menu.addAction(action)

    for transform_id, title in items:
        add(_Row(title, lambda t=transform_id: (on_select(t), menu.close()), checked=(transform_id == active_id)))
    add(_Divider())
    add(_Row("Configure transforms", lambda: (menu.close(), on_configure()), gear=True))
    return menu
