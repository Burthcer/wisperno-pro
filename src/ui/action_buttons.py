"""
Dashboard action buttons: real bordered buttons that show a drawn vector icon (star, pin, copy, pencil, trash, retry...)
instead of plain text links. Drawn with QPainter like src/ui/icons.py, so no image files are needed.

    IconButton("copy", "Copy to clipboard")      - hover + press states, tooltip
    button.flash("Copied!")                      - swaps to a green check + label for a moment, then goes back
    button.set_active(True)                      - filled/accent look for a pinned / favourited entry

Colours come from theme.py tokens only.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QPushButton

from src.ui import theme

H = 30
ICON = 16


def _tint(hex_color: str, alpha: float) -> QColor:
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c


def draw_icon(p: QPainter, kind: str, rect: QRectF, color: str, filled: bool = False) -> None:
    """Draw `kind` centred in `rect` (a square). Strokes use `color`; `filled` fills star/pin shapes."""
    c = QColor(color)
    pen = QPen(c, 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(c if filled else Qt.BrushStyle.NoBrush)
    x, y, s = rect.x(), rect.y(), rect.width()

    def pt(fx: float, fy: float) -> QPointF:
        return QPointF(x + fx * s, y + fy * s)

    if kind == "star":
        import math

        points = []
        for i in range(10):
            r = 0.46 if i % 2 == 0 else 0.20
            a = -math.pi / 2 + i * math.pi / 5
            points.append(pt(0.5 + r * math.cos(a), 0.52 + r * math.sin(a)))
        path = QPainterPath(points[0])
        for q in points[1:]:
            path.lineTo(q)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "pin":
        p.setBrush(c if filled else Qt.BrushStyle.NoBrush)
        body = QPainterPath(pt(0.34, 0.10))
        body.lineTo(pt(0.66, 0.10))
        body.lineTo(pt(0.62, 0.40))
        body.lineTo(pt(0.78, 0.56))
        body.lineTo(pt(0.22, 0.56))
        body.lineTo(pt(0.38, 0.40))
        body.closeSubpath()
        p.drawPath(body)
        p.drawLine(pt(0.5, 0.56), pt(0.5, 0.92))
    elif kind == "copy":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x + 0.32 * s, y + 0.30 * s, 0.52 * s, 0.58 * s), 0.09 * s, 0.09 * s)
        back = QPainterPath(pt(0.20, 0.64))
        back.lineTo(pt(0.20, 0.20))
        back.quadTo(pt(0.20, 0.12), pt(0.28, 0.12))
        back.lineTo(pt(0.58, 0.12))
        p.drawPath(back)
    elif kind == "edit":
        p.setBrush(Qt.BrushStyle.NoBrush)
        pencil = QPainterPath(pt(0.18, 0.82))
        pencil.lineTo(pt(0.22, 0.60))
        pencil.lineTo(pt(0.64, 0.18))
        pencil.lineTo(pt(0.82, 0.36))
        pencil.lineTo(pt(0.40, 0.78))
        pencil.closeSubpath()
        p.drawPath(pencil)
        p.drawLine(pt(0.56, 0.26), pt(0.74, 0.44))
    elif kind == "trash":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(pt(0.16, 0.24), pt(0.84, 0.24))
        p.drawLine(pt(0.38, 0.24), pt(0.40, 0.12))
        p.drawLine(pt(0.40, 0.12), pt(0.60, 0.12))
        p.drawLine(pt(0.60, 0.12), pt(0.62, 0.24))
        body = QPainterPath(pt(0.24, 0.24))
        body.lineTo(pt(0.29, 0.86))
        body.lineTo(pt(0.71, 0.86))
        body.lineTo(pt(0.76, 0.24))
        p.drawPath(body)
        p.drawLine(pt(0.42, 0.40), pt(0.43, 0.72))
        p.drawLine(pt(0.58, 0.40), pt(0.57, 0.72))
    elif kind == "retry":
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc = QRectF(x + 0.16 * s, y + 0.16 * s, 0.68 * s, 0.68 * s)
        p.drawArc(arc, 60 * 16, 270 * 16)
        p.drawLine(pt(0.80, 0.12), pt(0.78, 0.34))
        p.drawLine(pt(0.80, 0.12), pt(0.58, 0.20))
    elif kind == "book-plus":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x + 0.10 * s, y + 0.12 * s, 0.42 * s, 0.76 * s), 0.07 * s, 0.07 * s)
        p.drawLine(pt(0.22, 0.12), pt(0.22, 0.88))
        p.drawLine(pt(0.76, 0.40), pt(0.76, 0.76))
        p.drawLine(pt(0.58, 0.58), pt(0.94, 0.58))
    elif kind == "check":
        path = QPainterPath(pt(0.18, 0.54))
        path.lineTo(pt(0.42, 0.76))
        path.lineTo(pt(0.84, 0.26))
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.drawPath(path)


class IconButton(QPushButton):
    def __init__(self, kind: str, tooltip: str = "", danger: bool = False, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.danger = danger
        self.active = False
        self._flash_text = ""
        self._pop = 1.0
        self._hover = False
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(34, H)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._timer = QTimer(self, singleShot=True, interval=1300)
        self._timer.timeout.connect(self._end_flash)
        self._anim = QVariantAnimation(self, duration=220, startValue=0.55, endValue=1.0)
        self._anim.valueChanged.connect(self._on_pop)

    # -- state ------------------------------------------------------------
    def set_active(self, active: bool) -> None:
        self.active = active
        self.update()

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def flash(self, text: str = "Done") -> None:
        """Click feedback: a green check and a short label (e.g. "Copied!"), then back to normal."""
        self._flash_text = text
        font = QFont(self.font())
        font.setPointSizeF(9.0)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFixedWidth(40 + QFontMetrics(font).horizontalAdvance(text))
        self._anim.stop()
        self._anim.start()
        self._timer.start()
        self.update()

    def _end_flash(self) -> None:
        self._flash_text = ""
        self.setFixedWidth(34)
        self._pop = 1.0
        self.update()

    def _on_pop(self, value) -> None:
        self._pop = float(value)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        flashing = bool(self._flash_text)
        accent = theme.DANGER if self.danger else theme.ACCENT_PRIMARY_ACTIVE
        if flashing:
            border, fill, ink = theme.SUCCESS, _tint(theme.SUCCESS, 0.14), theme.SUCCESS
        elif self.isDown():
            border, fill, ink = accent, _tint(accent, 0.22), accent
        elif self._hover:
            border = accent if self.danger else theme.BORDER_STRONG
            fill, ink = (_tint(accent, 0.12) if self.danger else theme.BG_CARD_HOVER), (accent if self.danger else theme.TEXT_PRIMARY)
        elif self.active:
            border, fill, ink = _tint(accent, 0.55), _tint(accent, 0.12), accent
        else:
            border, fill, ink = theme.BORDER_SUBTLE, theme.BG_CARD, (theme.DANGER if self.danger else theme.TEXT_SECONDARY)
        p.setPen(QPen(QColor(border), 1))
        p.setBrush(QColor(fill))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 9, 9)

        size = ICON * (self._pop if flashing else 1.0)
        cy = self.height() / 2.0
        if flashing:
            icon_rect = QRectF(12 - (size - ICON) / 2.0, cy - size / 2.0, size, size)
            draw_icon(p, "check", icon_rect, ink)
            font = QFont(self.font())
            font.setPointSizeF(9.0)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            p.setPen(QColor(ink))
            p.drawText(QRectF(32, 0, self.width() - 36, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._flash_text)
        else:
            draw_icon(p, self.kind, QRectF((self.width() - ICON) / 2.0, cy - ICON / 2.0, ICON, ICON), ink, filled=self.active)
        p.end()
