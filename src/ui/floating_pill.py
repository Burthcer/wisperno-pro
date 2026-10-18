"""
Qt Floating Pill widget.

A small, always-on-top capsule drawn with true per-pixel alpha
(WA_TranslucentBackground + a custom paintEvent). It stays tiny:

  idle         a thin capsule of faint bars (grows a little on hover)
  recording    [x]  live scrolling waveform from the real mic level  [check]
  processing   animated dots (+ the name of a Transforms run, if any)
  toasts       one short line (mode change, warnings, errors)

The mic is never open while the pill is idle: "recording" is only painted once
real audio has arrived (see engine._on_mic_live) and "mic_starting" before that.

Interaction: drag it anywhere (the spot is remembered), click it to start a
dictation (or open the dashboard / do nothing - Settings -> General), and while
recording the x cancels (nothing is typed) and the check finishes.
"""

import math
from collections import deque
from typing import Optional, Sequence

from loguru import logger
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPainterPath, QGuiApplication, QPen
from PySide6.QtWidgets import QWidget, QMenu

from src.ui import theme
from src.branding import APP_NAME, OVERLAY_WINDOW_TITLE

STATE_LOADING = "loading"
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_TYPING = "typing"
STATE_SUCCESS = "success"
STATE_MODE_CHANGED = "mode_changed"
STATE_ERROR = "error"
STATE_SELECTION_PROCESSING = "selection_processing"
STATE_SELECTION_SUCCESS = "selection_success"
STATE_FALLBACK_WARNING = "fallback_warning"
STATE_CPU_MODE = "cpu_mode"
STATE_NO_SELECTION = "no_selection"
STATE_ENGINE_FALLBACK = "engine_fallback"
# Key pressed (or pill clicked), mic still opening - "wait". Becomes
# STATE_RECORDING ("speak now") only once real audio arrives from the device.
STATE_MIC_STARTING = "mic_starting"
STATE_MIC_ERROR = "mic_error"

CLICK_DICTATE = "dictate"
CLICK_DASHBOARD = "dashboard"
CLICK_NONE = "none"

SHAPE_PILL = "pill"
SHAPE_BOX = "box"
BOX_RADIUS = 4.0             # corner radius of the "box" shape

# Settings -> "Pill position" presets: id -> (label, horizontal edge, vertical edge).
POSITION_PRESETS = {
    "bottom_center": ("Bottom center (default)", "center", "bottom"),
    "bottom_left": ("Bottom left", "left", "bottom"),
    "bottom_right": ("Bottom right", "right", "bottom"),
    "top_center": ("Top center", "center", "top"),
    "top_left": ("Top left", "left", "top"),
    "top_right": ("Top right", "right", "top"),
}
PRESET_MARGIN = 24

PILL_H = 30                  # height while something is happening
IDLE_W, IDLE_H = 54, 14      # at rest
HOVER_W, HOVER_H = 90, 36    # under the cursor: a wide capsule mic button and a round transform wand
MIC_W = 44                   # the mic is a capsule, much easier to hit than a small circle
WAND_EXTRA = 24              # the wand button slides open this much to show its arrow while the mouse is on it
ACTIVE_W = 156               # [x] waveform [check]
BUSY_W = 72                  # dots only
SUCCESS_W = 60
TOAST_MIN_W, TOAST_MAX_W = 120, 420
BOTTOM_OFFSET = 110          # default spot: bottom centre, this far up
DRAG_THRESHOLD_PX = 4
WAVE_BARS = 22
EDGE_PAD = 5                 # gap between the capsule edge and the x / check buttons

# Toast text per state, painted in the state's own colour.
_TOASTS = {
    STATE_MIC_ERROR: "Microphone didn't start - check Settings",
    STATE_ERROR: f"{APP_NAME} startup is stuck - see logs/wisperno.log",
    STATE_FALLBACK_WARNING: "Formatting fallback applied",
    STATE_CPU_MODE: "Running in CPU Compatibility Mode (no dedicated GPU)",
    STATE_NO_SELECTION: "Highlight text to change style",
    STATE_ENGINE_FALLBACK: "Old engine preset retired - switched to a supported one",
}
# Safety net: a busy pill that has not been told it's finished after this long goes back to idle by itself.
# (Normal dictations finish in seconds; even a 10-minute one is done well inside this.)
BUSY_TIMEOUT_SECONDS = 90.0

_TOAST_SECONDS = {
    STATE_MIC_ERROR: 3.0, STATE_FALLBACK_WARNING: 2.5, STATE_CPU_MODE: 4.0,
    STATE_NO_SELECTION: 2.0, STATE_ENGINE_FALLBACK: 4.0, STATE_MODE_CHANGED: 1.0,
    STATE_PROCESSING: BUSY_TIMEOUT_SECONDS, STATE_TYPING: BUSY_TIMEOUT_SECONDS,
    STATE_SELECTION_PROCESSING: BUSY_TIMEOUT_SECONDS,
    # STATE_ERROR never auto-collapses: an init failure stays visible until
    # fixed, rather than quietly reverting to a "ready" look that would be a lie.
}


def _font(point_size: float, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False) -> QFont:
    families = [f.strip() for f in (theme.FONT_FAMILY_MONO if mono else theme.FONT_FAMILY).split(",")]
    font = QFont(families[0])
    font.setFamilies(families)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


class FloatingPill(QWidget):
    """The always-visible dictation pill."""

    dashboard_requested = Signal()
    cycle_mode_requested = Signal()
    hide_pill_requested = Signal()
    quit_requested = Signal()
    toggle_dictation_requested = Signal()   # click on the idle pill (when set to "dictate")
    finish_dictation_requested = Signal()   # the check while recording
    cancel_dictation_requested = Signal()   # the x while recording
    position_changed = Signal(int, int)     # centre (x, y) after the user drags it
    position_reset_requested = Signal()
    transform_menu_requested = Signal()     # the wand button on the hovered pill

    def __init__(
        self,
        initial_mode: str = "POLISH",
        hotkey_label: str = "Ctrl+Alt",
        always_on_top: bool = True,
        click_action: str = CLICK_DICTATE,
        position: Optional[Sequence[int]] = None,
        shape: str = SHAPE_PILL,
    ):
        # WindowDoesNotAcceptFocus (WS_EX_NOACTIVATE): clicking/dragging the pill
        # must never take the keyboard focus from the app being dictated into -
        # the text is typed into whatever window was focused when you clicked.
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Hard ceiling independent of any width-computation code path: the pill
        # must never be able to stretch toward screen width.
        self.setMaximumWidth(TOAST_MAX_W)
        self.setWindowTitle(OVERLAY_WINDOW_TITLE)  # matched by src.single_instance to focus a running instance
        self.setWindowIcon(theme.get_app_icon())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.current_mode = initial_mode.upper()
        self.hotkey_label = hotkey_label
        self.click_action = click_action
        self.shape = shape if shape in (SHAPE_PILL, SHAPE_BOX) else SHAPE_PILL
        self.state = STATE_LOADING
        # "processing:<Label>" names a Transforms run; "recording:<Label>" says
        # what this recording will do (e.g. DIRECT = no LLM) - see set_state.
        self._status_label = ""

        self._smoothed_level = 0.0
        self._levels = deque([0.0] * WAVE_BARS, maxlen=WAVE_BARS)
        self._pulse_phase = 0.0
        self._tick_count = 0
        self._hover = False
        self._cancel_rect = QRectF()
        self._finish_rect = QRectF()
        self._hover_cancel = False
        self._hover_finish = False
        self._mic_rect = QRectF()    # the hover buttons (empty unless the idle pill is expanded)
        self._wand_rect = QRectF()
        self._hover_mic = False
        self._hover_wand = False
        self._menu_open = False      # the transform menu is showing: keep the pill expanded under it
        self._press_global: Optional[QPoint] = None
        self._press_anchor: Optional[QPointF] = None
        self._dragging = False

        self._anchor: Optional[QPointF] = None  # centre of the capsule; None = default spot
        if position is not None and len(position) == 2:
            self.set_position(position[0], position[1])

        self._width_current = float(IDLE_W)
        self._width_target = float(IDLE_W)
        self._height_current = float(IDLE_H)
        self._height_target = float(IDLE_H)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)  # ~60fps
        self._anim_timer.timeout.connect(self._tick)

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._on_collapse_timeout)

        self._apply_size_targets()
        self._width_current, self._height_current = self._width_target, self._height_target
        self.resize(int(self._width_current), int(self._height_current))
        self._update_tooltip()
        self._reposition()
        self.show()
        self._anim_timer.start()

    # --- Geometry ------------------------------------------------------------

    def _default_anchor(self) -> QPointF:
        screen = QGuiApplication.primaryScreen().geometry()
        return QPointF(screen.x() + screen.width() / 2.0, screen.y() + screen.height() - BOTTOM_OFFSET + PILL_H / 2.0)

    def _screen_geometry_at(self, point: QPointF):
        screen = QGuiApplication.screenAt(point.toPoint()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _reposition(self) -> None:
        """Keep the capsule centred on its anchor while it grows/shrinks, and
        inside the visible screen area."""
        anchor = self._anchor if self._anchor is not None else self._default_anchor()
        geo = self._screen_geometry_at(anchor)
        w, h = self.width(), self.height()
        x = min(max(anchor.x() - w / 2.0, geo.left()), geo.right() - w + 1)
        y = min(max(anchor.y() - h / 2.0, geo.top()), geo.bottom() - h + 1)
        self.move(int(round(x)), int(round(y)))

    def set_position(self, cx: int, cy: int) -> None:
        """Restore a remembered spot - ignored if it is no longer on any screen
        (a monitor was unplugged), which falls back to the default spot."""
        point = QPointF(float(cx), float(cy))
        if QGuiApplication.screenAt(point.toPoint()) is None:
            self._anchor = None
        else:
            self._anchor = point
        if hasattr(self, "_width_current"):
            self._reposition()

    def reset_position(self) -> None:
        self._anchor = None
        self._reposition()

    def has_custom_position(self) -> bool:
        return self._anchor is not None

    def apply_position_preset(self, preset: str) -> None:
        """Snap to a named corner/edge of the screen the pill is on, and remember it.
        'bottom_center' is the default spot, so it clears the saved position instead."""
        if preset not in POSITION_PRESETS:
            return
        if preset == "bottom_center":
            self.reset_position()
            self.position_reset_requested.emit()
            return
        _, horizontal, vertical = POSITION_PRESETS[preset]
        here = self._anchor if self._anchor is not None else self._default_anchor()
        geo = self._screen_geometry_at(here)
        half_w, half_h = ACTIVE_W / 2.0, PILL_H / 2.0
        x = {"left": geo.left() + PRESET_MARGIN + half_w, "right": geo.right() - PRESET_MARGIN - half_w,
             "center": geo.center().x()}[horizontal]
        y = geo.top() + PRESET_MARGIN + half_h if vertical == "top" else geo.bottom() - BOTTOM_OFFSET + PILL_H / 2.0
        self._anchor = QPointF(float(x), float(y))
        self._reposition()
        self.position_changed.emit(int(self._anchor.x()), int(self._anchor.y()))

    def set_shape(self, shape: str) -> None:
        self.shape = shape if shape in (SHAPE_PILL, SHAPE_BOX) else SHAPE_PILL
        self.update()

    def _corner_radius(self, h: float) -> float:
        half = (h - 1) / 2.0
        return half if self.shape == SHAPE_PILL else min(BOX_RADIUS, half)

    def _apply_size_targets(self) -> None:
        state = self.state
        if state in (STATE_IDLE, STATE_LOADING):
            expanded = state == STATE_IDLE and (self._hover or self._menu_open)
            wand_open = expanded and (self._hover_wand or self._menu_open)
            self._width_target, self._height_target = (
                (HOVER_W + (WAND_EXTRA if wand_open else 0), HOVER_H) if expanded else (IDLE_W, IDLE_H))
        elif state in (STATE_RECORDING, STATE_MIC_STARTING):
            self._width_target, self._height_target = ACTIVE_W, PILL_H
        elif state in (STATE_PROCESSING, STATE_SELECTION_PROCESSING):
            label = self._processing_label()
            extra = QFontMetrics(_font(8, mono=True)).horizontalAdvance(label) + 10 if label else 0
            self._width_target, self._height_target = min(BUSY_W + extra, TOAST_MAX_W), PILL_H
        elif state == STATE_TYPING:
            self._width_target, self._height_target = BUSY_W, PILL_H
        elif state in (STATE_SUCCESS, STATE_SELECTION_SUCCESS):
            self._width_target, self._height_target = SUCCESS_W, PILL_H
        else:
            text = self._toast_text()
            text_w = QFontMetrics(_font(8, QFont.Weight.DemiBold, mono=True)).horizontalAdvance(text)
            self._width_target = float(min(max(text_w + 36, TOAST_MIN_W), TOAST_MAX_W))
            self._height_target = PILL_H

    def _tick(self) -> None:
        # Ease size toward target (drives the expand/collapse feel).
        moved = False
        if abs(self._width_current - self._width_target) > 0.5:
            self._width_current += (self._width_target - self._width_current) * 0.35
            moved = True
        elif self._width_current != self._width_target:
            self._width_current, moved = self._width_target, True
        if abs(self._height_current - self._height_target) > 0.5:
            self._height_current += (self._height_target - self._height_current) * 0.35
            moved = True
        elif self._height_current != self._height_target:
            self._height_current, moved = self._height_target, True
        if moved:
            self.resize(int(round(self._width_current)), int(round(self._height_current)))
            self._reposition()

        self._tick_count += 1
        self._pulse_phase += 0.12
        if self.state == STATE_RECORDING:
            # ~20 samples/s of the real mic level scroll the waveform left.
            # Fast attack, slow release so a syllable reads as a bump, not a blip.
            if self._tick_count % 3 == 0:
                self._levels.append(self._smoothed_level)
            self._smoothed_level *= 0.9

        self.update()

    # --- Public thread-safe-ish API (Qt slots; call via signals from workers) --

    def set_state(self, state: str) -> None:
        """`state` is normally a bare state name (STATE_PROCESSING etc.). A
        "processing:<Label>" form additionally carries a display name for a
        Transforms-hub-driven dictation (e.g. "processing:Prompt Engineering").
        A "recording:<Label>" form carries what this recording will do (e.g.
        "recording:DIRECT" when it skips the LLM entirely) - shown in the
        tooltip."""
        self._set_state(state)

    def _set_state(self, state: str) -> None:
        self._collapse_timer.stop()
        if ":" in state:
            state, self._status_label = state.split(":", 1)
        else:
            self._status_label = ""
        previous = self.state
        self.state = state
        if state == STATE_RECORDING and previous != STATE_RECORDING:
            self._smoothed_level = 0.0
            self._levels = deque([0.0] * WAVE_BARS, maxlen=WAVE_BARS)
        if state not in (STATE_RECORDING, STATE_MIC_STARTING):
            self._cancel_rect = self._finish_rect = QRectF()
            self._hover_cancel = self._hover_finish = False

        seconds = _TOAST_SECONDS.get(state)
        if state in (STATE_SUCCESS, STATE_SELECTION_SUCCESS):
            seconds = 0.7
        if seconds:
            self._collapse_timer.start(int(seconds * 1000))

        self._apply_size_targets()
        self._update_tooltip()
        self.update()

    def set_mode(self, mode: str) -> None:
        self.current_mode = mode.upper()
        self._set_state(STATE_MODE_CHANGED)

    def set_level(self, rms: float) -> None:
        """Live mic level (RMS per audio block) while recording."""
        if self.state != STATE_RECORDING:
            return
        # Typical speech on a laptop mic is RMS ~0.01-0.05; the old *12 gain left
        # the bars barely moving. *40 with a softer curve makes ordinary speech
        # swing the bars across most of their height.
        level = min((rms * 40.0) ** 0.7, 1.0)
        if level > self._smoothed_level:
            self._smoothed_level = 0.5 * self._smoothed_level + 0.5 * level
        else:
            self._smoothed_level = 0.85 * self._smoothed_level + 0.15 * level

    def set_hotkey_label(self, label: str) -> None:
        self.hotkey_label = label
        self._update_tooltip()
        self.update()

    def set_click_action(self, action: str) -> None:
        self.click_action = action if action in (CLICK_DICTATE, CLICK_DASHBOARD, CLICK_NONE) else CLICK_DICTATE
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        if self.state == STATE_LOADING:
            tip = f"{APP_NAME} is starting..."
        elif self.state == STATE_IDLE:
            action = {
                CLICK_DICTATE: "Click to dictate",
                CLICK_DASHBOARD: "Click to open the dashboard",
                CLICK_NONE: "Drag to move",
            }[self.click_action]
            tip = f"{action} - or press {self.hotkey_label}"
        elif self.state in (STATE_RECORDING, STATE_MIC_STARTING):
            tip = f"Mode: {self._status_label or self.current_mode}"
        else:
            tip = ""
        self.setToolTip(tip)

    # --- Painting --------------------------------------------------------------

    def _processing_label(self) -> str:
        if self.state == STATE_SELECTION_PROCESSING:
            return "Polishing selection"
        return self._status_label

    def _toast_text(self) -> str:
        if self.state == STATE_MODE_CHANGED:
            return f"Mode: {self.current_mode}"
        return _TOASTS.get(self.state, "")

    def _colors_for_state(self):
        """(background, border) of the capsule."""
        s = self.state
        if s == STATE_RECORDING:
            return theme.PILL_BG_RECORDING, theme.ACCENT_RECORDING_DIM
        if s in (STATE_PROCESSING, STATE_SELECTION_PROCESSING, STATE_MODE_CHANGED):
            return theme.PILL_BG_PROCESSING, theme.PILL_BORDER
        if s == STATE_TYPING:
            return theme.PILL_BG_TYPING, theme.PILL_BORDER
        if s in (STATE_SUCCESS, STATE_SELECTION_SUCCESS):
            return theme.PILL_BG_SUCCESS, theme.ACCENT_SUCCESS
        if s in (STATE_MIC_ERROR, STATE_ERROR, STATE_FALLBACK_WARNING, STATE_CPU_MODE, STATE_ENGINE_FALLBACK):
            return theme.PILL_BG_WARNING, theme.ACCENT_ERROR
        return theme.PILL_BG, theme.PILL_BORDER

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w, h = self.width(), self.height()
        bg, border = self._colors_for_state()
        path = QPainterPath()
        radius = self._corner_radius(h)
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), radius, radius)
        fill = QColor(bg)
        fill.setAlphaF(theme.PILL_BG_ALPHA)
        painter.fillPath(path, fill)
        edge = QColor(border)
        if self.state in (STATE_IDLE, STATE_LOADING) and self._hover:
            edge = QColor(theme.PILL_TEXT)
        painter.setPen(QPen(edge, 1))
        painter.drawPath(path)

        self._paint_content(painter, w, h)
        painter.end()

    def _paint_content(self, painter: QPainter, w: int, h: int) -> None:
        cy = h / 2.0
        s = self.state

        if s in (STATE_IDLE, STATE_LOADING):
            self._paint_idle(painter, w, h)
        elif s in (STATE_RECORDING, STATE_MIC_STARTING):
            self._paint_recording(painter, w, h)
        elif s in (STATE_PROCESSING, STATE_SELECTION_PROCESSING):
            label = self._processing_label()
            if label:
                self._paint_dots(painter, QRectF(14, 0, 30, h), theme.ACCENT_PROCESSING)
                painter.setPen(QColor(theme.PILL_TEXT_PRIMARY))
                painter.setFont(_font(8, QFont.Weight.DemiBold, mono=True))
                painter.drawText(QRectF(50, 0, w - 50 - 12, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            else:
                self._paint_dots(painter, QRectF(0, 0, w, h), theme.ACCENT_PROCESSING)
        elif s == STATE_TYPING:
            self._paint_dots(painter, QRectF(0, 0, w, h), theme.ACCENT_PROCESSING)
        elif s in (STATE_SUCCESS, STATE_SELECTION_SUCCESS):
            d = h - 10.0
            circle = QRectF((w - d) / 2.0, (h - d) / 2.0, d, d)
            self._paint_circle_button(painter, circle, theme.ACCENT_SUCCESS, "check", theme.PILL_ON_ACCENT)
        else:
            text = self._toast_text()
            color = theme.PILL_TEXT_PRIMARY if s in (STATE_MODE_CHANGED, STATE_NO_SELECTION) else theme.ACCENT_ERROR
            painter.setPen(QColor(color))
            font = _font(8, QFont.Weight.DemiBold, mono=True)
            painter.setFont(font)
            rect = QRectF(14, 0, w - 28, h)
            elided = QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, elided)

    def _hover_buttons_visible(self) -> bool:
        return self.state == STATE_IDLE and (self._hover or self._menu_open) and self.width() >= HOVER_W - 6

    def _paint_hover_buttons(self, painter: QPainter, w: int, h: int) -> None:
        """[mic] [wand v] - start dictating, and choose which transform runs after dictation."""
        d = h - 2.0 * EDGE_PAD
        cy = h / 2.0
        self._mic_rect = QRectF(EDGE_PAD, cy - d / 2.0, MIC_W, d)
        gap = 10.0  # air between the mic and wand buttons
        wand_w = w - EDGE_PAD * 2 - MIC_W - gap
        self._wand_rect = QRectF(self._mic_rect.right() + gap, cy - d / 2.0, wand_w, d)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.PILL_BUTTON_HOVER if self._hover_mic else theme.PILL_BUTTON))
        painter.drawRoundedRect(self._mic_rect, d / 2.0, d / 2.0)
        glyph_box = QRectF(0, 0, d, d)
        glyph_box.moveCenter(self._mic_rect.center())  # the glyph stays square inside the wider capsule
        self._paint_mic_glyph(painter, glyph_box, theme.PILL_TEXT_PRIMARY if self._hover_mic else theme.PILL_TEXT)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.PILL_BUTTON_HOVER if (self._hover_wand or self._menu_open) else theme.PILL_BUTTON))
        painter.drawRoundedRect(self._wand_rect, d / 2.0, d / 2.0)
        glyph_color = theme.PILL_TEXT_PRIMARY if (self._hover_wand or self._menu_open) else theme.PILL_TEXT
        # The arrow only appears once the mouse is on the wand (or its menu is open); until then the wand sits centred.
        show_chevron = (self._hover_wand or self._menu_open) and self._wand_rect.width() > d + 8.0
        icon_left = self._wand_rect.left() + 3.0 if show_chevron else self._wand_rect.center().x() - d / 2.0
        self._paint_wand_glyph(painter, QRectF(icon_left, self._wand_rect.top(), d, d), glyph_color)
        if show_chevron:
            self._paint_chevron(painter, QPointF(self._wand_rect.right() - 11.0, cy), glyph_color)

    @staticmethod
    def _paint_mic_glyph(painter: QPainter, rect: QRectF, color: str) -> None:
        cx, cy, u = rect.center().x(), rect.center().y(), rect.width()
        pen = QPen(QColor(color), max(1.3, u * 0.075))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(cx - u * 0.11, cy - u * 0.30, u * 0.22, u * 0.36), u * 0.11, u * 0.11)  # capsule
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(cx - u * 0.21, cy - u * 0.20, u * 0.42, u * 0.40), 200 * 16, 140 * 16)          # cradle
        painter.drawLine(QPointF(cx, cy + u * 0.20), QPointF(cx, cy + u * 0.30))                              # stem
        painter.drawLine(QPointF(cx - u * 0.10, cy + u * 0.30), QPointF(cx + u * 0.10, cy + u * 0.30))        # base

    @staticmethod
    def _paint_wand_glyph(painter: QPainter, rect: QRectF, color: str) -> None:
        cx, cy, u = rect.center().x(), rect.center().y(), rect.width()
        pen = QPen(QColor(color), max(1.3, u * 0.075))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(cx - u * 0.28, cy + u * 0.28), QPointF(cx + u * 0.06, cy - u * 0.06))        # the wand
        for sx, sy, r in ((cx + u * 0.20, cy - u * 0.22, u * 0.15), (cx + u * 0.28, cy + u * 0.10, u * 0.08)):  # sparkles
            painter.drawLine(QPointF(sx - r, sy), QPointF(sx + r, sy))
            painter.drawLine(QPointF(sx, sy - r), QPointF(sx, sy + r))

    @staticmethod
    def _paint_chevron(painter: QPainter, c: QPointF, color: str) -> None:
        pen = QPen(QColor(color), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        chevron = QPainterPath(QPointF(c.x() - 3.2, c.y() + 1.6))
        chevron.lineTo(c.x(), c.y() - 1.6)
        chevron.lineTo(c.x() + 3.2, c.y() + 1.6)
        painter.drawPath(chevron)

    def _paint_idle(self, painter: QPainter, w: int, h: int) -> None:
        if self._hover_buttons_visible():
            self._paint_hover_buttons(painter, w, h)
            return
        self._mic_rect = self._wand_rect = QRectF()
        loading = self.state == STATE_LOADING
        n = 5
        bar_w, gap = 2.0, 3.0
        total = n * bar_w + (n - 1) * gap
        x0 = (w - total) / 2.0
        cy = h / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            if loading:
                # a soft orange sweep while the engines load
                phase = (self._pulse_phase * 0.6 - i * 0.5) % (2 * math.pi)
                glow = max(0.0, 1.0 - abs(phase - 1.5) / 1.5)
                color = QColor(theme.PILL_ACCENT)
                color.setAlphaF(0.25 + 0.75 * glow)
                bar_h = 3.0 + 3.0 * glow
            else:
                color = QColor(theme.PILL_TEXT_PRIMARY if self._hover else theme.PILL_TEXT)
                color.setAlphaF(0.9 if self._hover else 0.55)
                bar_h = (7.0 if self._hover else 3.0) + (4.0 if i == n // 2 and self._hover else 0.0)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x0 + i * (bar_w + gap), cy - bar_h / 2.0, bar_w, bar_h), 1.0, 1.0)

    def _paint_recording(self, painter: QPainter, w: int, h: int) -> None:
        live = self.state == STATE_RECORDING
        d = h - 2.0 * EDGE_PAD
        cy = h / 2.0
        self._cancel_rect = QRectF(EDGE_PAD, cy - d / 2.0, d, d)
        self._finish_rect = QRectF(w - EDGE_PAD - d, cy - d / 2.0, d, d)

        self._paint_circle_button(
            painter, self._cancel_rect,
            theme.PILL_BUTTON_HOVER if self._hover_cancel else theme.PILL_BUTTON, "x", theme.PILL_TEXT_PRIMARY,
        )
        if live:
            bg = theme.PILL_ACCENT_HOVER if self._hover_finish else theme.PILL_ACCENT
            self._paint_circle_button(painter, self._finish_rect, bg, "check", theme.PILL_ON_ACCENT)
        else:
            # Mic still opening: nothing to finish yet.
            self._paint_circle_button(painter, self._finish_rect, theme.PILL_BUTTON, "check", theme.PILL_TEXT)

        wave = QRectF(self._cancel_rect.right() + 10, 0, self._finish_rect.left() - self._cancel_rect.right() - 20, h)
        if live:
            self._paint_wave(painter, wave)
        else:
            self._paint_waiting_dots(painter, wave)

    def _paint_wave(self, painter: QPainter, rect: QRectF) -> None:
        n = len(self._levels)
        step = rect.width() / n
        bar_w = max(1.5, step * 0.55)
        max_h = rect.height() - 6.0   # nearly the full capsule height at a loud peak
        cy = rect.height() / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        for i, level in enumerate(self._levels):
            bar_h = 3.0 + (max_h - 3.0) * level
            color = QColor(theme.PILL_TEXT_PRIMARY if level > 0.08 else theme.PILL_TEXT)
            color.setAlphaF(1.0 if level > 0.08 else 0.5)
            painter.setBrush(color)
            bx = rect.left() + i * step + (step - bar_w) / 2.0
            painter.drawRoundedRect(QRectF(bx, cy - bar_h / 2.0, bar_w, bar_h), bar_w / 2.0, bar_w / 2.0)

    def _paint_waiting_dots(self, painter: QPainter, rect: QRectF) -> None:
        """Mic opening: a row of faint dots pulsing in turn - 'wait', not 'speak'."""
        n = 9
        step = rect.width() / n
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            pulse = 0.5 + 0.5 * math.sin(self._pulse_phase * 1.5 - i * 0.6)
            color = QColor(theme.PILL_TEXT)
            color.setAlphaF(0.25 + 0.5 * pulse)
            painter.setBrush(color)
            r = 1.5
            painter.drawEllipse(QPointF(rect.left() + step * (i + 0.5), rect.height() / 2.0), r, r)

    def _paint_dots(self, painter: QPainter, rect: QRectF, color: str) -> None:
        """Three dots that swell in turn (processing / pasting)."""
        painter.setPen(Qt.PenStyle.NoPen)
        cx, cy = rect.center().x(), rect.height() / 2.0
        for i in range(3):
            swell = 0.5 + 0.5 * math.sin(self._pulse_phase * 1.4 - i * 0.9)
            c = QColor(color)
            c.setAlphaF(0.35 + 0.65 * swell)
            painter.setBrush(c)
            painter.drawEllipse(QPointF(cx + (i - 1) * 9.0, cy), 2.0 + 1.2 * swell, 2.0 + 1.2 * swell)

    def _paint_circle_button(self, painter: QPainter, rect: QRectF, bg: str, glyph: str, fg: str) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawEllipse(rect)
        pen = QPen(QColor(fg), max(1.4, rect.width() * 0.085))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy, u = rect.center().x(), rect.center().y(), rect.width()
        if glyph == "x":
            r = u * 0.2
            painter.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
            painter.drawLine(QPointF(cx - r, cy + r), QPointF(cx + r, cy - r))
        else:
            check = QPainterPath(QPointF(cx - u * 0.2, cy + u * 0.01))
            check.lineTo(cx - u * 0.05, cy + u * 0.16)
            check.lineTo(cx + u * 0.22, cy - u * 0.14)
            painter.drawPath(check)

    # --- Mouse interaction -----------------------------------------------------
    # Press + move past a few pixels drags the pill; press + release in place is
    # a click: the x / check while recording, otherwise Settings' "click action".

    def _over_buttons(self, pos) -> bool:
        return self._cancel_rect.contains(pos) or (self.state == STATE_RECORDING and self._finish_rect.contains(pos))

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_global is not None:
            delta = event.globalPosition().toPoint() - self._press_global
            if self._dragging or abs(delta.x()) + abs(delta.y()) > DRAG_THRESHOLD_PX:
                self._dragging = True
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self._anchor = QPointF(self._press_anchor.x() + delta.x(), self._press_anchor.y() + delta.y())
                self._reposition()
            return
        pos = event.position()
        hover_cancel = self._cancel_rect.contains(pos)
        hover_finish = self.state == STATE_RECORDING and self._finish_rect.contains(pos)
        hover_mic = self._mic_rect.contains(pos)
        hover_wand = self._wand_rect.contains(pos)
        if (hover_cancel, hover_finish, hover_mic, hover_wand) != (self._hover_cancel, self._hover_finish, self._hover_mic, self._hover_wand):
            self._hover_cancel, self._hover_finish = hover_cancel, hover_finish
            self._hover_mic, self._hover_wand = hover_mic, hover_wand
            self._apply_size_targets()  # the wand opens (and closes) as the mouse moves on/off it
            self.update()
        if hover_mic or hover_wand:
            self.setToolTip(f"Start dictating  ({self.hotkey_label})" if hover_mic else "Choose a transform")
        elif self.state == STATE_IDLE:
            self._update_tooltip()
        clickable = (hover_cancel or hover_finish or hover_mic or hover_wand
                     or (self.state == STATE_IDLE and self.click_action != CLICK_NONE))
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)

    def enterEvent(self, event) -> None:
        self._hover = True
        self._apply_size_targets()
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._hover_cancel = self._hover_finish = False
        self._hover_mic = self._hover_wand = False
        self._apply_size_targets()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_global = event.globalPosition().toPoint()
        self._press_anchor = QPointF(self.x() + self.width() / 2.0, self.y() + self.height() / 2.0)
        self._dragging = False

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press_global is None:
            return
        was_dragging = self._dragging
        self._press_global = self._press_anchor = None
        self._dragging = False
        if was_dragging:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.position_changed.emit(int(self._anchor.x()), int(self._anchor.y()))
            return
        self._on_clicked(event.position())

    def _on_collapse_timeout(self) -> None:
        if self.state in (STATE_PROCESSING, STATE_TYPING, STATE_SELECTION_PROCESSING):
            logger.warning(f"Pill was still '{self.state}' after {BUSY_TIMEOUT_SECONDS:.0f}s - resetting it to idle.")
        self._set_state(STATE_IDLE)

    def _on_clicked(self, pos) -> None:
        if self.state in (STATE_RECORDING, STATE_MIC_STARTING):
            if self._cancel_rect.contains(pos):
                self._set_state(STATE_IDLE)  # instant feedback; the engine confirms it right after
                self.cancel_dictation_requested.emit()
            elif self.state == STATE_RECORDING and self._finish_rect.contains(pos):
                # Instant feedback on the tick: show the busy dots straight away instead of sitting on the
                # waveform until the engine gets round to it. The engine/worker then drives the real states.
                self._set_state(STATE_PROCESSING)
                self.finish_dictation_requested.emit()
            return
        if self.state != STATE_IDLE:
            return
        if self._mic_rect.contains(pos):
            self.toggle_dictation_requested.emit()  # the mic button always dictates, whatever "click the pill" is set to
            return
        if self._wand_rect.contains(pos):
            self.transform_menu_requested.emit()
            return
        if self.click_action == CLICK_DICTATE:
            self.toggle_dictation_requested.emit()
        elif self.click_action == CLICK_DASHBOARD:
            self.dashboard_requested.emit()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction("Open Dashboard", self.dashboard_requested.emit)
        menu.addAction("Cycle Mode", self.cycle_mode_requested.emit)
        move_menu = menu.addMenu("Move Pill To")
        for key, (label, _h, _v) in POSITION_PRESETS.items():
            move_menu.addAction(label.replace(" (default)", ""), lambda k=key: self.apply_position_preset(k))
        if self.has_custom_position():
            menu.addAction("Reset Pill Position", self.position_reset_requested.emit)
        menu.addSeparator()
        menu.addAction("Hide Pill", self.hide_pill_requested.emit)
        menu.addAction(f"Quit {APP_NAME} Completely", self.quit_requested.emit)
        menu.exec(event.globalPos())

    # --- Transform menu --------------------------------------------------------

    def popup_transform_menu(self, items, active_id, auto_apply, on_select, on_auto_toggle, on_configure) -> None:
        """Open the wand's menu above the pill (below it if there's no room), keeping the pill expanded meanwhile."""
        from src.ui.pill_menu import MENU_W, build_transform_menu

        menu = build_transform_menu(self, items, active_id, auto_apply, on_select, on_auto_toggle, on_configure)
        self._menu_open = True
        self._apply_size_targets()
        menu.aboutToHide.connect(self._on_menu_closed)
        menu.ensurePolished()
        size = menu.sizeHint()
        geo = self._screen_geometry_at(QPointF(self.x() + self.width() / 2.0, self.y() + self.height() / 2.0))
        x = int(self.x() + self.width() / 2.0 - max(size.width(), MENU_W) / 2.0)
        x = max(geo.left() + 6, min(x, geo.right() - size.width() - 6))
        y = self.y() - size.height() - 10
        if y < geo.top() + 6:
            y = self.y() + self.height() + 10
        menu.popup(QPoint(x, y))

    def _on_menu_closed(self) -> None:
        self._menu_open = False
        self._hover_wand = False
        self._apply_size_targets()
        self.update()

    # --- Visibility toggle (tray) --------------------------------------------

    def set_pill_visible(self, visible: bool) -> None:
        if visible:
            self.show()
        else:
            self.hide()

    def set_always_on_top(self, enabled: bool) -> None:
        """Qt only picks up a changed WindowStaysOnTopHint flag on the next
        show() - a bare setWindowFlag() call leaves the window unmapped."""
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        if was_visible:
            self.show()
