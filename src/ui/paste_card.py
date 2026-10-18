"""
The card shown when a dictation had nowhere to be pasted ("No active text field detected"): a status dot and title,
the dictated text in an inset preview, a prominent orange Copy button (turns into a green check + "Copied!"), and a
round close button. Stands just above the floating pill, never takes focus, hides itself after a while. Nothing is
copied unless you press Copy. Colours: theme tokens only.
"""

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QClipboard, QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QWidget

from src.ui import theme
from src.ui.action_buttons import draw_icon

CARD_W, CARD_H = 372, 218
SHOW_SECONDS = 30
MAX_CHARS = 20000  # effectively the whole dictation: the preview scrolls (mouse wheel), and Copy copies all of it
PAD = 18


class PasteCard(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(CARD_W, CARD_H)
        self.setMouseTracking(True)
        self._text = ""
        self._copied = False
        self._pop = 1.0
        self._hover = ""
        self._scroll = 0.0
        self._copy_rect = QRectF(PAD, CARD_H - 56, CARD_W - 2 * PAD, 40)
        self._close_rect = QRectF(CARD_W - PAD - 26, 14, 26, 26)
        self._preview_rect = QRectF(PAD, 60, CARD_W - 2 * PAD, CARD_H - 128)
        self._timer = QTimer(self, singleShot=True, interval=SHOW_SECONDS * 1000)
        self._timer.timeout.connect(self.hide)
        self._anim = QVariantAnimation(self, duration=260, startValue=0.6, endValue=1.0)
        self._anim.valueChanged.connect(self._on_pop)

    def show_for(self, text: str, above: QPoint) -> None:
        """`above` = top-centre of the pill; the card stands over it, nudged to stay on its screen."""
        self._text, self._copied, self._pop = text, False, 1.0
        self._scroll = 0.0
        screen = QGuiApplication.screenAt(above) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = max(geo.left() + 8, min(above.x() - CARD_W // 2, geo.right() - CARD_W - 8))
        y = above.y() - CARD_H - 12
        if y < geo.top() + 8:
            y = above.y() + 60
        self.move(x, y)
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text, QClipboard.Mode.Clipboard)
        self._copied = True
        self._anim.stop()
        self._anim.start()
        self._timer.start()
        self.update()

    def _on_pop(self, value) -> None:
        self._pop = float(value)
        self.update()

    def _text_metrics(self) -> tuple:
        """(text rect inside the preview, wrapped text height, how far it can scroll)."""
        inner = self._preview_rect.adjusted(14, 10, -20, -10)
        shown = self._text if len(self._text) <= MAX_CHARS else self._text[:MAX_CHARS].rstrip() + "..."
        option = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        height = QFontMetricsF(self._font(9.6, QFont.Weight.Normal)).boundingRect(
            QRectF(0, 0, inner.width(), 100000), int(Qt.TextFlag.TextWordWrap), shown).height()
        return inner, shown, option, height, max(0.0, height - inner.height())

    def wheelEvent(self, event) -> None:
        _inner, _shown, _option, _height, limit = self._text_metrics()
        if limit > 0:
            self._scroll = min(limit, max(0.0, self._scroll - event.angleDelta().y() / 120.0 * 36.0))
            self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        hover = "copy" if self._copy_rect.contains(pos) else "close" if self._close_rect.contains(pos) else ""
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = ""
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if self._copy_rect.contains(pos):
            self._copy()
        elif self._close_rect.contains(pos):
            self.hide()

    def _font(self, size: float, weight: QFont.Weight) -> QFont:
        font = QFont(theme.FONT_FAMILY.split(",")[0].strip())
        font.setPointSizeF(size)
        font.setWeight(weight)
        return font

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # card
        p.setPen(QPen(QColor(theme.PILL_BORDER), 1))
        p.setBrush(QColor(theme.PILL_BG))
        p.drawRoundedRect(QRectF(0.5, 0.5, CARD_W - 1, CARD_H - 1), 18, 18)

        # status dot + title + subtitle
        p.setPen(Qt.PenStyle.NoPen)
        halo = QColor(theme.PILL_ACCENT)
        halo.setAlphaF(0.22)
        p.setBrush(halo)
        p.drawEllipse(QRectF(PAD, 20, 14, 14))
        p.setBrush(QColor(theme.PILL_ACCENT))
        p.drawEllipse(QRectF(PAD + 3, 23, 8, 8))
        p.setFont(self._font(10.5, QFont.Weight.DemiBold))
        p.setPen(QColor(theme.PILL_TEXT_PRIMARY))
        p.drawText(QRectF(PAD + 24, 14, CARD_W - 110, 26), Qt.AlignmentFlag.AlignVCenter, "No active text field detected")
        p.setFont(self._font(8.8, QFont.Weight.Normal))
        p.setPen(QColor(theme.PILL_TEXT))
        p.drawText(QRectF(PAD + 24, 36, CARD_W - 90, 18), Qt.AlignmentFlag.AlignVCenter, "Your text wasn't pasted anywhere")

        # round close button
        close_hot = self._hover == "close"
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.PILL_BUTTON_HOVER if close_hot else theme.PILL_BUTTON))
        p.drawEllipse(self._close_rect)
        cx, cy = self._close_rect.center().x(), self._close_rect.center().y()
        pen = QPen(QColor(theme.PILL_TEXT_PRIMARY if close_hot else theme.PILL_TEXT), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPoint(int(cx - 4), int(cy - 4)), QPoint(int(cx + 4), int(cy + 4)))
        p.drawLine(QPoint(int(cx - 4), int(cy + 4)), QPoint(int(cx + 4), int(cy - 4)))

        # preview card
        p.setPen(QPen(QColor(theme.PILL_BORDER), 1))
        p.setBrush(QColor(theme.PILL_SURFACE))
        p.drawRoundedRect(self._preview_rect, 12, 12)
        p.setFont(self._font(9.6, QFont.Weight.Normal))
        p.setPen(QColor(theme.PILL_TEXT_PRIMARY))
        inner, shown, option, text_h, limit = self._text_metrics()
        p.save()
        p.setClipRect(inner.adjusted(-2, -4, 6, 4))
        p.drawText(QRectF(inner.left(), inner.top() - self._scroll, inner.width(), text_h + 4), shown, option)
        p.restore()
        if limit > 0:  # a slim scrollbar thumb: the text is longer than the box (scroll with the mouse wheel)
            track_h = inner.height()
            thumb_h = max(18.0, track_h * inner.height() / text_h)
            thumb_y = inner.top() + (track_h - thumb_h) * (self._scroll / limit)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.PILL_BUTTON_HOVER))
            p.drawRoundedRect(QRectF(self._preview_rect.right() - 10, thumb_y, 4, thumb_h), 2, 2)

        # Copy button (orange; green check + "Copied!" after a click)
        hot = self._hover == "copy"
        rect = self._copy_rect
        if self._copied:
            scale = 0.96 + 0.04 * self._pop
            rect = QRectF(0, 0, rect.width() * scale, rect.height() * scale)
            rect.moveCenter(self._copy_rect.center())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SUCCESS if self._copied else (theme.PILL_ACCENT_HOVER if hot else theme.PILL_ACCENT)))
        p.drawRoundedRect(rect, 20, 20)
        p.setPen(QColor(theme.PILL_ON_ACCENT))
        p.setFont(self._font(10.5, QFont.Weight.DemiBold))
        if self._copied:
            icon = 18.0 * self._pop
            draw_icon(p, "check", QRectF(rect.center().x() - 44, rect.center().y() - icon / 2.0, icon, icon), theme.PILL_ON_ACCENT)
            p.drawText(QRectF(rect.center().x() - 20, rect.top(), 80, rect.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Copied!")
        else:
            draw_icon(p, "copy", QRectF(rect.center().x() - 44, rect.center().y() - 9, 18, 18), theme.PILL_ON_ACCENT)
            p.drawText(QRectF(rect.center().x() - 20, rect.top(), 80, rect.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Copy text")
        p.end()
