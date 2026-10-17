"""
The card shown when a dictation had nowhere to be pasted: the full text, a Copy button and a Dismiss button.
Stands just above the floating pill, never takes focus, hides itself after a while. Nothing is copied unless you
press Copy. Colours: PILL_* tokens only.
"""

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QClipboard, QColor, QFont, QGuiApplication, QPainter, QPen, QTextOption
from PySide6.QtWidgets import QWidget

from src.ui import theme

CARD_W, CARD_H = 340, 190
SHOW_SECONDS = 30
MAX_CHARS = 420  # the card previews long dictations; Copy still copies all of it


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
        self._copy_rect = QRectF(CARD_W - 190, CARD_H - 46, 84, 32)
        self._dismiss_rect = QRectF(CARD_W - 98, CARD_H - 46, 84, 32)
        self._hover = ""
        self._timer = QTimer(self, singleShot=True, interval=SHOW_SECONDS * 1000)
        self._timer.timeout.connect(self.hide)

    def show_for(self, text: str, above: QPoint) -> None:
        """`above` = top-centre of the pill; the card stands over it, nudged to stay on its screen."""
        self._text, self._copied = text, False
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

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        hover = "copy" if self._copy_rect.contains(pos) else "dismiss" if self._dismiss_rect.contains(pos) else ""
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
            self._timer.start()
            self.update()
        elif self._dismiss_rect.contains(pos):
            self.hide()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(theme.PILL_BORDER), 1))
        p.setBrush(QColor(theme.PILL_BG))
        p.drawRoundedRect(QRectF(0.5, 0.5, CARD_W - 1, CARD_H - 1), 16, 16)

        title = QFont(theme.FONT_FAMILY.split(",")[0].strip())
        title.setPointSizeF(10.0)
        title.setWeight(QFont.Weight.DemiBold)
        p.setFont(title)
        p.setPen(QColor(theme.PILL_TEXT_PRIMARY))
        p.drawText(QRectF(18, 14, CARD_W - 36, 22), Qt.AlignmentFlag.AlignVCenter, "Couldn't find a text box to paste into")

        body = QFont(title)
        body.setWeight(QFont.Weight.Normal)
        body.setPointSizeF(9.5)
        p.setFont(body)
        p.setPen(QColor(theme.PILL_TEXT))
        shown = self._text if len(self._text) <= MAX_CHARS else self._text[:MAX_CHARS].rstrip() + "..."
        option = QTextOption(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        p.drawText(QRectF(18, 44, CARD_W - 36, CARD_H - 100), shown, option)

        p.setFont(title)
        for rect, label, key, primary in ((self._copy_rect, "Copied" if self._copied else "Copy", "copy", True),
                                          (self._dismiss_rect, "Dismiss", "dismiss", False)):
            hovered = self._hover == key
            p.setPen(Qt.PenStyle.NoPen)
            if primary:
                p.setBrush(QColor(theme.PILL_ACCENT))
            else:
                p.setBrush(QColor(theme.PILL_BUTTON_HOVER if hovered else theme.PILL_BUTTON))
            p.drawRoundedRect(rect, 16, 16)
            p.setPen(QColor(theme.PILL_ON_ACCENT if primary else theme.PILL_TEXT_PRIMARY))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        p.end()
