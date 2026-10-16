"""
Settings tab for the Wisperno dashboard, split into topic tabs: Microphone, Shortcuts,
Writing, Pill, App Styles, AI Engine (model/hardware tuning), Privacy and Startup.
Rows are grouped into titled cards (see _group / _row / _check_row).
"""

from typing import Optional

import sounddevice as sd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFileDialog, QMessageBox,
    QProgressBar, QTabWidget, QSpinBox, QSlider, QFrame, QDialog, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from src.app_context import STYLE_LABELS, STYLES
from src.presets import BENCHMARK_MATRIX, DEFAULT_PRESET, MODEL_PRESETS
from src.ui import theme
from src.ui.scroll_utils import make_scrollable_layout
from src.ui.floating_pill import POSITION_PRESETS
from src.ui.shortcut_recorder import KeySequenceRecorder
from src.branding import APP_NAME

# Fallback layer count for the slider range/estimate before a model has
# finished loading (so Transformer.active_model_layers isn't known yet - the
# common case, since SettingsTab is built right after engine.start() fires
# the background load thread, well before it completes). Matches the shipped
# default model's real layer count (Qwen2.5-3B-Instruct: 36, read via GGUF
# metadata) - the real value is read from the loaded GGUF once available.
DEFAULT_TOTAL_LAYERS = 36


def _label_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def _show_help_dialog(parent, title: str, what: str, recommended: str) -> None:
    """Modern modal: deep obsidian surface, subtle outline, 12px rounded corners,
    high-contrast typography, a single centered indigo "Got it" button."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(520, 360)
    dlg.setStyleSheet(
        f"QDialog {{ background-color: {theme.BG_APP}; border: 1px solid {theme.BORDER_SUBTLE}; border-radius: 12px; }}"
    )
    v = QVBoxLayout(dlg)
    v.setContentsMargins(28, 24, 28, 24)
    v.setSpacing(10)

    heading = QLabel(title)
    heading.setStyleSheet(f"font-family: {theme.FONT_FAMILY_DISPLAY}; font-size: 16pt; color: {theme.TEXT_PRIMARY};")
    heading.setWordWrap(True)
    v.addWidget(heading)

    def _subhead(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-weight: 600; color: {theme.ACCENT_PRIMARY_ACTIVE}; margin-top: 8px; font-size: 10pt;")
        return lbl

    def _body(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 13px; line-height: 1.5;")
        return lbl

    v.addWidget(_subhead("What it does"))
    v.addWidget(_body(what))
    v.addWidget(_subhead("Recommended value"))
    v.addWidget(_body(recommended))
    v.addStretch()

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    got_it_btn = QPushButton("Got it")
    got_it_btn.setFixedWidth(140)
    got_it_btn.setObjectName("primary")
    got_it_btn.clicked.connect(dlg.accept)
    btn_row.addWidget(got_it_btn)
    btn_row.addStretch()
    v.addLayout(btn_row)

    dlg.exec()


def _help_button(title: str, what: str, recommended: str) -> QPushButton:
    """A small clickable '(?)' that opens a plain-English explanation modal (title /
    what it does / recommended value) - replaces the old hover-only tooltip, which
    did nothing on click. Fixed width AND height so it never stretches to match a
    taller sibling in the same row/grid cell (the actual cause of it looking
    misaligned/"floating" against its input field)."""
    btn = QPushButton("(?)")
    btn.setFixedSize(30, 28)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(f"What does '{title}' do?")
    btn.setStyleSheet(
        f"QPushButton {{ background: transparent; border: 1px solid {theme.BORDER_SUBTLE}; "
        f"border-radius: 6px; color: {theme.TEXT_SECONDARY}; font-weight: 600; padding: 0; }}"
        f"QPushButton:hover {{ border-color: {theme.ACCENT_PRIMARY}; color: {theme.ACCENT_PRIMARY}; }}"
    )
    btn.clicked.connect(lambda: _show_help_dialog(btn, title, what, recommended))
    return btn


def _no_wheel(widget):
    """Prevents accidental value changes from scrolling the Settings page: a QSlider/
    QComboBox/QSpinBox under the mouse cursor otherwise steals the wheel event from
    the surrounding QScrollArea and silently changes its own value instead of
    scrolling the page past it. event.ignore() makes Qt's own event propagation
    hand the wheel event up to the parent scroll area instead - the widget still
    responds normally to a click, drag, or the up/down arrows, just not to scrolling
    over it. Applied at construction, not by subclassing every widget type."""
    widget.wheelEvent = lambda event: event.ignore()
    if isinstance(widget, QComboBox):
        # Size to a short minimum, not the longest option's full text - the
        # drop-down list still shows every option in full.
        widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(12)
    return widget


def _shortcut_card(title: str, description: str):
    """An elevated surface card (12px padding) holding one shortcut recorder,
    so paired shortcuts sit side-by-side in a two-column grid instead of full-width rows."""
    frame = QFrame(objectName="shortcutCard")
    # Scoped by id - an unscoped style cascades to (and boxes) every label inside.
    frame.setStyleSheet(f"#shortcutCard {{ background-color: {theme.BG_CARD}; border: 1px solid {theme.BORDER_SUBTLE}; border-radius: 12px; }}")
    v = QVBoxLayout(frame)
    v.setContentsMargins(12, 12, 12, 12)
    heading = QLabel(title)
    heading.setStyleSheet(f"font-weight: 600; color: {theme.TEXT_PRIMARY};")
    v.addWidget(heading)
    desc = QLabel(f'<span style="color:{theme.TEXT_SECONDARY}; font-size: 8pt;">{description}</span>')
    desc.setWordWrap(True)
    v.addWidget(desc)
    return frame, v


def _desc_label(html: str) -> QLabel:
    """A description/help QLabel that wraps instead of forcing the window's minimum
    width out to its full unwrapped text length (the real cause of a past window-
    resize/sidebar-collapse report: an unwrapped label's minimumSizeHint equals its
    full single-line width, which propagates up through every parent layout)."""
    label = QLabel(html)
    label.setWordWrap(True)
    return label


class SettingsTab(QWidget):
    """Settings, split into topic tabs. Everything saves instantly except AI Engine,
    which has its own Apply button because changing it reloads the models."""

    def __init__(self, engine, controller, main_window=None):
        super().__init__()
        self.engine = engine
        self.controller = controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.addWidget(_label_title("Settings"))
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setUsesScrollButtons(True)
        layout.addWidget(self.sub_tabs)

        # general_tab / advanced_tab keep their names (other code and tests reach the
        # controls through them) but are no longer tabs themselves: each owns pages.
        self.general_tab = _GeneralSettings(engine, controller)
        self.advanced_tab = _AdvancedSettings(engine)
        pages = dict(self.general_tab.pages)
        pages["AI Engine"] = self.advanced_tab
        order = ["Microphone", "Shortcuts", "Writing", "Pill", "App Styles", "AI Engine", "Privacy", "Startup"]
        for name in order:
            self.sub_tabs.addTab(pages[name], name)
        self._pages = [pages[name] for name in order]

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Always land on the first tab when Settings is (re)opened - the hardware-tuning
        # controls shouldn't be the first thing a user sees after, say, just checking
        # Dictionary and coming back.
        self.sub_tabs.setCurrentIndex(0)
        self.reset_scroll()

    def reset_scroll(self) -> None:
        for page in self._pages:
            page._scroll_area.verticalScrollBar().setValue(0)


def _group(title: str, hint: str = ""):
    """A titled surface card that holds one topic's rows (see _row / _check_row).
    Scoped by object name - a bare QFrame rule would also box every QLabel inside it."""
    frame = QFrame(objectName="settingsGroup")
    frame.setStyleSheet(
        f"#settingsGroup {{ background-color: {theme.BG_CARD}; border: 1px solid {theme.BORDER_SUBTLE}; border-radius: 14px; }}"
    )
    v = QVBoxLayout(frame)
    v.setContentsMargins(22, 18, 22, 20)
    v.setSpacing(14)
    head = QVBoxLayout()
    head.setSpacing(3)
    heading = QLabel(title)
    heading.setStyleSheet(f"font-family: {theme.FONT_FAMILY_DISPLAY}; font-size: 12pt; font-weight: 600; color: {theme.TEXT_PRIMARY}; background: transparent;")
    head.addWidget(heading)
    if hint:
        head.addWidget(_hint(hint))
    v.addLayout(head)
    return frame, v


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 8.5pt; background: transparent;")
    return label


def _row(label: str, hint: str, control) -> QWidget:
    """label + explanation on the left, the control on the right."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(18)
    left = QVBoxLayout()
    left.setSpacing(2)
    title = QLabel(label)
    title.setStyleSheet(f"font-weight: 600; color: {theme.TEXT_PRIMARY}; background: transparent;")
    left.addWidget(title)
    if hint:
        left.addWidget(_hint(hint))
    h.addLayout(left, 3)
    if isinstance(control, QWidget):
        h.addWidget(control, 2)
    else:
        h.addLayout(control, 2)
    return row


def _check_row(checkbox: QCheckBox, hint: str = "") -> QWidget:
    """A checkbox with its explanation underneath, lined up with the label text."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    v = QVBoxLayout(row)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    v.addWidget(checkbox)
    if hint:
        note = _hint(hint)
        note.setContentsMargins(28, 0, 0, 0)
        v.addWidget(note)
    return row


class _GeneralSettings(QWidget):
    """Everyday controls, grouped into topic pages (Microphone, Shortcuts, Writing, Pill,
    App Styles, Privacy, Startup). This object only owns the widgets and their handlers;
    SettingsTab shows each entry of `self.pages` as its own tab. Every control auto-saves
    instantly on change - there is no Save button here (the AI Engine tab keeps its own Apply)."""

    def __init__(self, engine, controller):
        super().__init__()
        self.engine = engine
        self.controller = controller
        self.pages = {}  # tab name -> page widget, in tab order

        def page(name: str, intro: str):
            widget = QWidget()
            lay = make_scrollable_layout(widget)
            lay.setContentsMargins(28, 22, 28, 22)
            lay.setSpacing(16)
            lay.addWidget(_hint(intro))
            self.pages[name] = widget
            return lay

        mic = page("Microphone", "Which microphone to listen to, when to stop, and the sound that tells you it's listening.")
        keys = page("Shortcuts", "Start and stop dictation from the keyboard. More hotkeys (transforms, live transcription) are in the Transforms tab and the README.")
        writing = page("Writing", "How your words are cleaned up and typed.")
        pill = page("Pill", "The small floating control that shows what Wisperno is doing - and starts and stops dictation when you click it.")
        apps = page("App Styles", "Different apps want different punctuation: chat apps drop the final period, code editors skip the trailing space.")
        privacy = page("Privacy", "Everything stays on this PC. Choose what is kept, for how long, and how much space it uses.")
        startup = page("Startup", "How Wisperno Pro starts and what the window's close button does.")

        # ---------- Microphone ----------
        g, v = _group("Input device")
        self.device_cb = _no_wheel(QComboBox())
        self._device_indices = [None]
        self.device_cb.addItem("Auto-detect (default device)")
        try:
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_input_channels", 0) > 0:
                    # Some WASAPI/BT-driver device names run 90+ raw chars (e.g. a
                    # paired Bluetooth headset's hands-free profile string) - an
                    # untruncated one blows the combo box's minimumSizeHint out to
                    # 1300+px, which propagates up through every parent layout to
                    # the whole window (same failure mode as an unwrapped QLabel).
                    name = d["name"].replace("\r", "").replace("\n", "")
                    if len(name) > 42:
                        name = name[:42] + "…"
                    item_text = f"[{i}] {name}"
                    self.device_cb.addItem(item_text)
                    self.device_cb.setItemData(self.device_cb.count() - 1, f"[{i}] {d['name']}", Qt.ToolTipRole)
                    self._device_indices.append(i)
        except Exception:
            pass
        if engine.config.audio.device_index in self._device_indices:
            self.device_cb.setCurrentIndex(self._device_indices.index(engine.config.audio.device_index))
        self.device_cb.currentIndexChanged.connect(self._on_device_changed)
        v.addWidget(self.device_cb)
        self.level_meter = QProgressBar()
        self.level_meter.setRange(0, 100)
        self.level_meter.setTextVisible(False)
        self.level_meter.setFixedHeight(6)
        v.addWidget(self.level_meter)
        self.test_mic_btn = QPushButton("Test microphone (3 seconds)")
        self.test_mic_btn.clicked.connect(self._test_mic)
        v.addWidget(self.test_mic_btn, alignment=Qt.AlignLeft)
        mic.addWidget(g)

        g, v = _group("Auto-stop")
        self.auto_silence_cb = _no_wheel(QComboBox())
        self.auto_silence_cb.addItem("Off - I'll stop it myself", 0)
        self.auto_silence_cb.addItem("3 seconds", 3)
        self.auto_silence_cb.addItem("5 seconds (default)", 5)
        self.auto_silence_cb.addItem("8 seconds", 8)
        self.auto_silence_cb.addItem("10 seconds", 10)
        current_idx = self.auto_silence_cb.findData(engine.config.audio.auto_silence_seconds)
        self.auto_silence_cb.setCurrentIndex(current_idx if current_idx >= 0 else 2)
        self.auto_silence_cb.currentIndexChanged.connect(
            lambda _i: engine.set_auto_silence_seconds(self.auto_silence_cb.currentData())
        )
        v.addWidget(_row("Stop after a pause of", "When you go quiet for this long, recording ends and the text is typed.", self.auto_silence_cb))
        mic.addWidget(g)

        g, v = _group("Sounds")
        self.audio_cues_cb = QCheckBox("Play a soft chime when dictation starts and stops")
        self.audio_cues_cb.setChecked(engine.config.audio_cues_enabled)
        self.audio_cues_cb.stateChanged.connect(lambda s: engine.set_audio_cues_enabled(s != 0))
        v.addWidget(_check_row(self.audio_cues_cb, "A short two-note chime: rising when it starts listening, falling when it stops."))
        mic.addWidget(g)
        mic.addStretch()

        # ---------- Shortcuts ----------
        # Two fully independent cards, each with its own recorder and enable switch.
        # Both, either, or neither can be active at once. "Polish Selected Text" lives
        # in the Transforms hub (any transform's hotkey falls back to polishing the
        # current selection when nothing is spoken).
        triggers_row = QHBoxLayout()
        triggers_row.setSpacing(16)

        tap_card, tap_v = _group("Tap to toggle")
        tap_v.addWidget(_hint("Tap once to start listening, tap again to stop."))
        self.tap_enable_cb = QCheckBox("Enable tap to toggle")
        self.tap_enable_cb.setChecked(engine.config.tap_toggle_enabled)
        self.tap_enable_cb.stateChanged.connect(lambda s: engine.set_tap_toggle_enabled(s != 0))
        tap_v.addWidget(self.tap_enable_cb)
        self.tap_toggle_recorder = KeySequenceRecorder(engine.config.tap_toggle_hotkey)
        self.tap_toggle_recorder.sequence_captured.connect(engine.set_tap_toggle_hotkey)
        tap_v.addWidget(self.tap_toggle_recorder)
        triggers_row.addWidget(tap_card)

        hold_card, hold_v = _group("Hold to talk")
        hold_v.addWidget(_hint("Hold the keys down to record, release to stop - classic push-to-talk."))
        self.hold_enable_cb = QCheckBox("Enable hold to talk")
        self.hold_enable_cb.setChecked(engine.config.hold_to_talk_enabled)
        self.hold_enable_cb.stateChanged.connect(lambda s: engine.set_hold_to_talk_enabled(s != 0))
        hold_v.addWidget(self.hold_enable_cb)
        self.hold_to_talk_recorder = KeySequenceRecorder(engine.config.hold_to_talk_hotkey)
        self.hold_to_talk_recorder.sequence_captured.connect(engine.set_hold_to_talk_hotkey)
        hold_v.addWidget(self.hold_to_talk_recorder)
        triggers_row.addWidget(hold_card)
        keys.addLayout(triggers_row)
        keys.addWidget(_hint("Use either, both (with different keys), or neither - you can always click the pill instead. "
                             "Click a shortcut box, then press the keys you want."))
        keys.addStretch()

        # ---------- Writing ----------
        g, v = _group("Cleanup")
        self.auto_llm_polish_cb = QCheckBox("Smart cleanup with the local AI")
        self.auto_llm_polish_cb.setChecked(engine.config.auto_llm_polish)
        self.auto_llm_polish_cb.setToolTip(
            "On (default): dictation is cleaned by your active AI engine - filler words, \"wait no\" "
            "corrections, punctuation, lists. Short phrases that are already clean skip it, so they stay instant.\n"
            "Off: the instant rule-based formatter only - no AI delay at all.\n"
            "Always off in CPU Compatibility Mode (no usable GPU), where it would be too slow."
        )
        self.auto_llm_polish_cb.stateChanged.connect(lambda s: engine.set_auto_llm_polish(s != 0))
        v.addWidget(_check_row(self.auto_llm_polish_cb, "Removes filler words, fixes \"wait no\" corrections and formats lists. "
                                                        "Short, clean phrases stay instant. Turn off for rule-based formatting only."))
        self.auto_copy_cb = QCheckBox("Also copy the text to the clipboard")
        self.auto_copy_cb.setChecked(engine.config.injector.auto_copy_to_clipboard)
        self.auto_copy_cb.stateChanged.connect(lambda s: engine.set_auto_copy_to_clipboard(s != 0))
        v.addWidget(_check_row(self.auto_copy_cb, "Handy if a dictation lands in the wrong window - just paste it again."))
        self.trailing_space_cb = QCheckBox("Add a space after each dictated sentence")
        self.trailing_space_cb.setChecked(engine.config.injector.trailing_space)
        self.trailing_space_cb.stateChanged.connect(lambda s: engine.set_trailing_space(s != 0))
        v.addWidget(_check_row(self.trailing_space_cb, "So the next dictation doesn't run into the previous one (\"today.Next\")."))
        writing.addWidget(g)

        g, v = _group("Profanity filter")
        self.profanity_cb = _no_wheel(QComboBox())
        self.profanity_cb.addItem("Keep every word as spoken", "allow")
        self.profanity_cb.addItem("Censor with asterisks (f***)", "censor")
        self.profanity_cb.addItem("Remove swear words", "remove")
        current_idx = self.profanity_cb.findData(engine.config.profanity_filter)
        self.profanity_cb.setCurrentIndex(current_idx if current_idx >= 0 else 0)
        self.profanity_cb.currentIndexChanged.connect(lambda _i: engine.set_profanity_filter(self.profanity_cb.currentData()))
        profanity_row = QHBoxLayout()
        profanity_row.addWidget(self.profanity_cb, 1)
        profanity_row.addWidget(_help_button(
            "Profanity Filter",
            "Controls whether spoken swear words are kept exactly as said, or sanitized, in the text "
            "that gets typed. The LLM never makes this call itself - it always transcribes profanity "
            "verbatim, and this setting is applied as a separate step afterward.",
            "Keep every word for personal notes/chat where your own words should show up unedited. Censor or "
            "Remove for anything that might be shared, screen-recorded, or read by someone else.",
        ))
        v.addWidget(_row("When I swear", "Applied after the AI has cleaned up your text.", profanity_row))
        writing.addWidget(g)

        g, v = _group("Corrections")
        self.self_correction_cb = QCheckBox("Remove what I retract")
        self.self_correction_cb.setChecked(engine.config.self_correction)
        self.self_correction_cb.stateChanged.connect(lambda s: engine.set_self_correction(s != 0))
        v.addWidget(_check_row(
            self.self_correction_cb,
            "Say \"scratch that\", \"no wait\" or \"no, no, ...\" at the start of a sentence and the sentence before it is dropped, "
            "keeping the rest. Only those exact phrases count, so ordinary speech is never cut, and the original wording stays in "
            "History under Show Raw Transcript. Off by default.",
        ))
        writing.addWidget(g)
        writing.addStretch()

        # ---------- Pill ----------
        g, v = _group("Floating pill")
        self.pill_cb = QCheckBox("Show the floating pill")
        self.pill_cb.setChecked(True)
        self.pill_cb.stateChanged.connect(self._on_pill_visibility_changed)
        v.addWidget(_check_row(self.pill_cb, "Hide it and you can still use the keyboard shortcuts or the tray icon."))
        self.always_on_top_cb = QCheckBox("Keep it on top, even over fullscreen apps and games")
        self.always_on_top_cb.setChecked(engine.config.pill_always_on_top)
        self.always_on_top_cb.stateChanged.connect(self._on_always_on_top_changed)
        v.addWidget(_check_row(self.always_on_top_cb))
        self.pill_click_cb = _no_wheel(QComboBox())
        self.pill_click_cb.addItem("Start dictating", "dictate")
        self.pill_click_cb.addItem("Open the dashboard", "dashboard")
        self.pill_click_cb.addItem("Nothing (keyboard only)", "none")
        click_idx = self.pill_click_cb.findData(engine.config.pill_click_action)
        self.pill_click_cb.setCurrentIndex(click_idx if click_idx >= 0 else 0)
        self.pill_click_cb.currentIndexChanged.connect(self._on_pill_click_action_changed)
        v.addWidget(_row("Clicking the pill", "While recording, its x cancels (nothing is typed) and its check finishes.", self.pill_click_cb))
        pill.addWidget(g)

        g, v = _group("Shape and position", "Drag the pill anywhere, or snap it to a spot. Reset puts it back at the bottom centre.")
        self.pill_shape_cb = _no_wheel(QComboBox())
        self.pill_shape_cb.addItem("Pill (rounded)", "pill")
        self.pill_shape_cb.addItem("Box (rounded rectangle)", "box")
        shape_idx = self.pill_shape_cb.findData(engine.config.pill_shape)
        self.pill_shape_cb.setCurrentIndex(shape_idx if shape_idx >= 0 else 0)
        self.pill_shape_cb.currentIndexChanged.connect(self._on_pill_shape_changed)
        v.addWidget(_row("Shape", "", self.pill_shape_cb))
        self.pill_preset_cb = _no_wheel(QComboBox())
        self.pill_preset_cb.addItem("Move to...", None)
        for key, (label, _h, _v) in POSITION_PRESETS.items():
            self.pill_preset_cb.addItem(label, key)
        self.pill_preset_cb.activated.connect(self._on_pill_preset_chosen)
        self.reset_pill_btn = QPushButton("Reset position")
        self.reset_pill_btn.clicked.connect(self._on_reset_pill_position)
        position_row = QHBoxLayout()
        position_row.addWidget(self.pill_preset_cb, 1)
        position_row.addWidget(self.reset_pill_btn)
        v.addWidget(_row("Position", "", position_row))
        pill.addWidget(g)
        pill.addStretch()

        # ---------- App Styles (src/app_context.py) ----------
        g, v = _group("Adapt to the app I'm typing in")
        self.app_styles_cb = QCheckBox("Format differently per app")
        self.app_styles_cb.setToolTip(
            "Chat apps: a one-line message drops its final period.\n"
            "Code editors / terminals: also no final period, and no trailing space.\n"
            "Everything else: normal sentences."
        )
        self.app_styles_cb.setChecked(engine.config.app_styles_enabled)
        self.app_styles_cb.stateChanged.connect(self._on_app_styles_toggled)
        v.addWidget(_check_row(self.app_styles_cb, "Chat apps: no final period on one-line messages. Code editors and terminals: no final period and no trailing space."))
        self.app_styles_table = QTableWidget(0, 3)
        self.app_styles_table.setHorizontalHeaderLabels(["APP (.EXE)", "STYLE", ""])
        header = self.app_styles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.app_styles_table.setColumnWidth(2, 44)
        self.app_styles_table.verticalHeader().setVisible(False)
        self.app_styles_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.app_styles_table.setMinimumHeight(260)
        v.addWidget(self.app_styles_table)
        add_row = QHBoxLayout()
        self.app_name_in = QLineEdit(placeholderText="App to add, e.g. obsidian.exe")
        self.app_style_in = _no_wheel(QComboBox())
        for style in STYLES:
            self.app_style_in.addItem(STYLE_LABELS[style], style)
        add_app_btn = QPushButton("Add app")
        add_app_btn.clicked.connect(self._add_app_style)
        self.app_name_in.returnPressed.connect(self._add_app_style)
        add_row.addWidget(self.app_name_in, 1)
        add_row.addWidget(self.app_style_in, 1)
        add_row.addWidget(add_app_btn)
        v.addLayout(add_row)
        apps.addWidget(g)
        apps.addStretch()
        self._refresh_app_styles()

        # ---------- Privacy ----------
        g, v = _group("Recent recordings", "Keep the audio of your latest dictations so History can re-transcribe one that came out wrong.")
        self.keep_recent_cb = _no_wheel(QComboBox())
        for count, label in ((0, "Don't keep any"), (3, "Last 3"), (5, "Last 5"), (10, "Last 10")):
            self.keep_recent_cb.addItem(label, count)
        keep_idx = self.keep_recent_cb.findData(engine.config.keep_recent_recordings)
        self.keep_recent_cb.setCurrentIndex(keep_idx if keep_idx >= 0 else 1)
        self.keep_recent_cb.currentIndexChanged.connect(lambda _i: engine.set_keep_recent_recordings(self.keep_recent_cb.currentData()))
        v.addWidget(_row("Keep audio for", "Older clips are deleted automatically. The audio never leaves this PC.", self.keep_recent_cb))
        privacy.addWidget(g)

        g, v = _group("History")
        self.storage_stats_label = QLabel("")
        self.storage_stats_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; background: transparent;")
        v.addWidget(self.storage_stats_label)
        self.retention_cb = _no_wheel(QComboBox())
        self.retention_cb.addItem("Never", "never")
        self.retention_cb.addItem("After 3 months", "3_months")
        self.retention_cb.addItem("After 6 months", "6_months")
        self.retention_cb.addItem("After 1 year", "1_year")
        retention_idx = self.retention_cb.findData(engine.config.db_retention_policy)
        if retention_idx >= 0:
            self.retention_cb.setCurrentIndex(retention_idx)
        self.retention_cb.currentIndexChanged.connect(self._on_retention_changed)
        v.addWidget(_row("Auto-delete old history", "Pinned entries are always kept.", self.retention_cb))
        clear_btn = QPushButton("Clear the oldest 25% of history")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(self._clear_oldest)
        v.addWidget(clear_btn, alignment=Qt.AlignLeft)
        privacy.addWidget(g)
        self._refresh_storage_stats()

        g, v = _group("Testing")
        self.save_recordings_cb = QCheckBox("Save recordings for testing")
        self.save_recordings_cb.setToolTip(
            "Keeps each dictation's audio and transcript so scripts/eval_dictation.py can measure accuracy "
            "and speed on your own voice. Nothing leaves this machine. Leave off for normal use."
        )
        self.save_recordings_cb.setChecked(engine.config.save_recordings_for_testing)
        self.save_recordings_cb.stateChanged.connect(lambda s: engine.set_save_recordings_for_testing(s != 0))
        v.addWidget(_check_row(self.save_recordings_cb, "Stores every dictation's audio on this PC so accuracy can be measured on your own voice. Leave off for normal use."))
        open_recordings_btn = QPushButton("Open recordings folder")
        open_recordings_btn.clicked.connect(self._open_recordings_folder)
        v.addWidget(open_recordings_btn, alignment=Qt.AlignLeft)
        privacy.addWidget(g)
        privacy.addStretch()

        # ---------- Startup ----------
        g, v = _group("Startup and window")
        from src import autostart

        self.autostart_cb = QCheckBox("Start Wisperno Pro with Windows")
        self.autostart_cb.setChecked(autostart.is_enabled())
        self.autostart_cb.stateChanged.connect(lambda s: autostart.set_enabled(s != 0))
        v.addWidget(_check_row(self.autostart_cb, "So the pill is ready as soon as you sign in. The AI models take a few seconds to load."))
        self.minimize_to_tray_cb = QCheckBox("Keep running in the tray when I close the window")
        self.minimize_to_tray_cb.setChecked(engine.config.minimize_to_tray)
        self.minimize_to_tray_cb.stateChanged.connect(lambda s: engine.set_minimize_to_tray(s != 0))
        v.addWidget(_check_row(
            self.minimize_to_tray_cb,
            f"Ticked: closing the window hides it and dictation keeps working. Unticked: closing the window quits {APP_NAME} completely.",
        ))
        startup.addWidget(g)
        startup.addStretch()

    def _refresh_app_styles(self) -> None:
        styles = self.engine.config.app_styles
        apps = sorted(styles, key=lambda a: (STYLES.index(styles[a]) if styles[a] in STYLES else 0, a))
        self.app_styles_table.setRowCount(len(apps))
        for row, app in enumerate(apps):
            item = QTableWidgetItem(app)
            self.app_styles_table.setItem(row, 0, item)
            combo = _no_wheel(QComboBox())
            for style in STYLES:
                combo.addItem(STYLE_LABELS[style], style)
            combo.setCurrentIndex(STYLES.index(styles[app]) if styles[app] in STYLES else 0)
            combo.currentIndexChanged.connect(lambda _i, a=app, c=combo: self.engine.set_app_style(a, c.currentData()))
            self.app_styles_table.setCellWidget(row, 1, combo)
            remove = QPushButton("✕")
            remove.setToolTip(f"Remove {app} (it will use normal sentences)")
            remove.setFlat(True)
            remove.clicked.connect(lambda _c=False, a=app: self._remove_app_style(a))
            self.app_styles_table.setCellWidget(row, 2, remove)
        self.app_styles_table.setEnabled(self.engine.config.app_styles_enabled)

    def _on_app_styles_toggled(self, state: int) -> None:
        self.engine.set_app_styles_enabled(state != 0)
        self.app_styles_table.setEnabled(state != 0)

    def _add_app_style(self) -> None:
        app = self.app_name_in.text().strip().lower()
        if not app:
            return
        if not app.endswith(".exe"):
            app += ".exe"
        self.engine.set_app_style(app, self.app_style_in.currentData())
        self.app_name_in.clear()
        self._refresh_app_styles()

    def _remove_app_style(self, app: str) -> None:
        self.engine.set_app_style(app, None)
        self._refresh_app_styles()

    def _refresh_storage_stats(self) -> None:
        stats = self.engine.db.get_database_storage_stats()
        self.storage_stats_label.setText(f'{stats["size_mb_formatted"]} on disk - {stats["record_count"]} saved dictations')

    def _on_retention_changed(self, _index: int) -> None:
        cfg = self.engine.config
        cfg.db_retention_policy = self.retention_cb.currentData()
        self.engine.db.prune_history(cfg.db_retention_policy)
        self.engine.save_config()
        self._refresh_storage_stats()

    def _clear_oldest(self) -> None:
        deleted = self.engine.db.clear_oldest_transcripts(fraction=0.25)
        self._refresh_storage_stats()
        QMessageBox.information(self, APP_NAME, f"Deleted {deleted} of the oldest transcripts (pinned ones kept).")

    def _open_recordings_folder(self) -> None:
        import os
        from src.test_recordings import recordings_dir

        folder = recordings_dir()
        if hasattr(os, "startfile"):
            os.startfile(folder)  # Windows Explorer
        else:
            QMessageBox.information(self, APP_NAME, f"Recordings folder:\n{folder}")

    def _on_device_changed(self, _index: int) -> None:
        self.engine.set_audio_device(self.selected_device_index())

    def _on_pill_visibility_changed(self, state: int) -> None:
        if hasattr(self.controller, "set_pill_visible"):
            self.controller.set_pill_visible(state != 0)

    def _on_pill_click_action_changed(self, _index: int) -> None:
        action = self.pill_click_cb.currentData()
        if hasattr(self.controller, "set_pill_click_action"):
            self.controller.set_pill_click_action(action)
        else:
            self.engine.set_pill_click_action(action)

    def _on_pill_shape_changed(self, _index: int) -> None:
        shape = self.pill_shape_cb.currentData()
        if hasattr(self.controller, "set_pill_shape"):
            self.controller.set_pill_shape(shape)
        else:
            self.engine.set_pill_shape(shape)

    def _on_pill_preset_chosen(self, index: int) -> None:
        preset = self.pill_preset_cb.itemData(index)
        if preset and hasattr(self.controller, "set_pill_position_preset"):
            self.controller.set_pill_position_preset(preset)
        self.pill_preset_cb.setCurrentIndex(0)  # back to the "Move to..." prompt - it's an action, not a state

    def _on_reset_pill_position(self) -> None:
        if hasattr(self.controller, "reset_pill_position"):
            self.controller.reset_pill_position()

    def _on_always_on_top_changed(self, state: int) -> None:
        if hasattr(self.controller, "set_pill_always_on_top"):
            self.controller.set_pill_always_on_top(state != 0)

    def selected_device_index(self) -> Optional[int]:
        idx = self.device_cb.currentIndex()
        return self._device_indices[idx] if 0 <= idx < len(self._device_indices) else None

    def _test_mic(self) -> None:
        if not self.engine.audio_worker:
            QMessageBox.warning(self, APP_NAME, "Audio engine hasn't finished loading yet.")
            return
        self.test_mic_btn.setEnabled(False)
        self.engine.audio_worker.level_changed.connect(self._update_meter)
        self.engine.audio_worker.start_recording()
        QTimer.singleShot(3000, self._stop_test_mic)

    def _update_meter(self, rms: float) -> None:
        self.level_meter.setValue(min(100, int(rms * 400)))

    def _stop_test_mic(self) -> None:
        self.engine.audio_worker.stop_recording()
        try:
            self.engine.audio_worker.level_changed.disconnect(self._update_meter)
        except Exception:
            pass
        self.level_meter.setValue(0)
        self.test_mic_btn.setEnabled(True)


class _AdvancedSettings(QWidget):
    """AI Engine tab: model selection and hardware offloading. Unlike the other tabs this one
    batches its changes behind an explicit Apply, because most of them reload Whisper/the LLM."""

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        layout = make_scrollable_layout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)
        layout.addWidget(_hint(
            "The defaults work well on most graphics cards - change these only if you know why. "
            "Live GPU and memory use is in the System Usage tab."
        ))

        # ---------- Engine preset ----------
        g, v = _group("Engine preset", "Which local AI cleans up your dictation. Everything runs on this PC.")
        self.preset_cb = _no_wheel(QComboBox())
        for i, (key, preset) in enumerate(MODEL_PRESETS.items()):
            self.preset_cb.addItem(preset["label"], key)
            self.preset_cb.setItemData(i, preset["tooltip"], Qt.ToolTipRole)
        self.preset_cb.setCurrentIndex(self._initial_preset_index(engine))
        self.preset_badge = QLabel("")
        self.preset_badge.setStyleSheet(f"color: {theme.ACCENT_PRIMARY}; font-size: 9pt; font-weight: 600; background: transparent;")
        self.preset_description = _hint("")
        self.preset_cb.currentIndexChanged.connect(self._update_preset_description)
        self._update_preset_description()
        # "&&": a single "&" is a Qt mnemonic marker and was silently dropped from the label.
        compare_btn = QPushButton("Compare presets && benchmarks")
        compare_btn.clicked.connect(self._show_compare_presets)
        preset_row = QHBoxLayout()
        preset_row.addWidget(self.preset_cb, 1)
        preset_row.addWidget(compare_btn)
        v.addLayout(preset_row)
        v.addWidget(self.preset_badge)
        v.addWidget(self.preset_description)
        # Hidden until a preset switch triggers a reload, then tracks engine.state_changed's
        # "loading" state so the user sees a clean in-progress signal. Wording is generic on
        # purpose: the same "loading" state also fires on the app's first startup.
        self.reload_banner = QLabel("Loading the AI engine (Whisper + language model) - this can take a few seconds...")
        self.reload_banner.setWordWrap(True)
        self.reload_banner.setStyleSheet(
            f"background-color: {theme.BG_APP}; color: {theme.ACCENT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER_SUBTLE}; border-radius: 8px; padding: 8px 12px; font-weight: 600;"
        )
        self.reload_banner.setVisible(False)
        v.addWidget(self.reload_banner)
        if hasattr(engine, "state_changed"):
            engine.state_changed.connect(self._on_engine_state_changed)
        layout.addWidget(g)

        # ---------- Speech recognition ----------
        g, v = _group("Speech recognition")
        self.whisper_cb = _no_wheel(QComboBox())
        self.whisper_cb.setFont(QFont(theme.FONT_FAMILY_MONO))
        self.whisper_cb.addItems(["large-v3-turbo", "medium.en", "small.en", "base.en"])
        idx = self.whisper_cb.findText(engine.config.whisper.model_name)
        if idx >= 0:
            self.whisper_cb.setCurrentIndex(idx)
        whisper_row = QHBoxLayout()
        whisper_row.addWidget(self.whisper_cb, 1)
        whisper_row.addWidget(_help_button(
            "Whisper Model",
            "The speech-to-text engine that turns your voice into raw text before any cleanup or "
            "polish happens. A larger model recognizes speech more accurately, especially accents, "
            "background noise, and technical vocabulary, at the cost of more VRAM and (slightly) more latency.",
            "large-v3-turbo for typical desktop use - near-perfect recognition with low latency on any "
            "modern GPU. Drop to medium.en / small.en / base.en only if VRAM is genuinely tight.",
        ))
        v.addWidget(_row("Whisper model", "Bigger is more accurate and uses more graphics memory.", whisper_row))
        self.vad_sensitivity_spin = _no_wheel(QSpinBox())
        self.vad_sensitivity_spin.setRange(50, 2000)
        self.vad_sensitivity_spin.setSingleStep(50)
        self.vad_sensitivity_spin.setSuffix(" ms")
        self.vad_sensitivity_spin.setValue(engine.config.whisper.vad_min_silence_duration_ms)
        vad_row = QHBoxLayout()
        vad_row.addWidget(self.vad_sensitivity_spin, 1)
        vad_row.addWidget(_help_button(
            "VAD Silence Sensitivity",
            "Voice Activity Detection (VAD) watches for silence to know when you've stopped talking "
            "and automatically ends the recording. This value is how long a pause has to last before "
            "that happens.",
            "1200ms (the default) works well for normal speech with natural pauses. Lower it (e.g. "
            "600-800ms) in a quiet room if recordings feel slow to end; raise it if mid-sentence "
            "pauses are cutting your dictation off early.",
        ))
        v.addWidget(_row("Pause length that counts as silence", "Lower it in a quiet room; raise it if sentences get cut off.", vad_row))
        layout.addWidget(g)

        # ---------- Language model ----------
        g, v = _group("Language model")
        self.llm_path_edit = QLineEdit(engine.config.llm.model_path)
        self.llm_path_edit.setFont(QFont(theme.FONT_FAMILY_MONO))
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_model)
        path_row = QHBoxLayout()
        path_row.addWidget(self.llm_path_edit, 1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(_help_button(
            "Local LLM Path",
            "The GGUF model file that powers LLM-based text transformation (Polish Selected Text, "
            "Transforms, and dictation when 'Automatically run LLM polish' is on). This always points "
            "at a file already on disk - selecting an Engine Preset above fills this in for you.",
            "Leave this on whichever Engine Preset you picked above. Only Browse to a custom .gguf "
            "file if you've downloaded one yourself and know what it needs (chat-template compatible, "
            "fits your VRAM).",
        ))
        v.addWidget(_row("Model file", "Filled in for you by the preset above.", path_row))

        # --- VRAM offload ---
        self._total_layers = self._resolve_total_layers(engine)
        offload_tooltip = (
            f"Controls how much of the AI model runs on your graphics card. {self._total_layers}/"
            f"{self._total_layers} (Full GPU) gives the fastest speed (~1.5s). Lower this only if you "
            "need to free up GPU memory for games or creative software."
        )
        self.n_gpu_layers_slider = _no_wheel(QSlider(Qt.Orientation.Horizontal))
        self.n_gpu_layers_slider.setRange(min(8, self._total_layers), self._total_layers)
        self.n_gpu_layers_slider.setToolTip(offload_tooltip)
        # n_gpu_layers=-1 means "all layers" (llama.cpp's own convention) - map that to the
        # slider's max rather than clamping it down to the min, which would silently
        # misrepresent a 100%-GPU config as barely-offloaded.
        configured = engine.config.llm.n_gpu_layers
        initial_value = self._total_layers if configured < 0 else max(8, min(self._total_layers, configured))
        self.n_gpu_layers_slider.setValue(initial_value)
        self.n_gpu_layers_value_label = QLabel("")
        self.n_gpu_layers_value_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
        slider_row = QHBoxLayout()
        slider_row.addWidget(self.n_gpu_layers_slider, 1)
        slider_row.addWidget(self.n_gpu_layers_value_label)
        slider_row.addWidget(_help_button(
            "Offload Layers to GPU",
            "The LLM is made of layers; each one can run on your graphics card (fast) or fall back to "
            f"system RAM/CPU (slower). This machine's loaded model has {self._total_layers} layers total.",
            f"{self._total_layers}/{self._total_layers} (Full GPU, the slider's max) for the fastest "
            "generation. Lower it only if you need to free VRAM for something else running "
            "simultaneously, like a game or creative app - expect noticeably slower dictation in exchange.",
        ))
        v.addWidget(_row(
            "Layers on the graphics card",
            "All of them is fastest. Lower it only to free graphics memory for a game; dictation gets slower.",
            slider_row,
        ))
        self.gpu_estimate_label = _hint("")
        v.addWidget(self.gpu_estimate_label)
        self._update_gpu_layers_label(self.n_gpu_layers_slider.value())
        self.n_gpu_layers_slider.valueChanged.connect(self._update_gpu_layers_label)

        self.kv_cache_quant_cb = QCheckBox("Compress the model's working memory (saves ~600 MB)")
        self.kv_cache_quant_cb.setChecked(engine.config.llm.kv_cache_quantization)
        kv_hint = _check_row(
            self.kv_cache_quant_cb,
            "Q8_0 KV-cache compression. No measurable quality loss; the Flagship preset turns it off on purpose.",
        )
        kv_row = QHBoxLayout()
        kv_row.addWidget(kv_hint, 1)
        kv_row.addWidget(_help_button(
            "KV-Cache Compression",
            "The KV (key/value) cache is the model's short-term working memory for the conversation "
            "it's currently processing. Compressing it to 8-bit precision (Q8_0) shrinks its VRAM "
            "footprint by roughly 600MB.",
            "Leave it on for Standard/Turbo (the default) - no measurable quality loss. Flagship ships "
            "it off on purpose, trading that VRAM back for maximum output fidelity instead.",
        ), alignment=Qt.AlignTop)
        v.addLayout(kv_row)
        layout.addWidget(g)

        layout.addStretch()

        apply_row = QHBoxLayout()
        apply_row.addWidget(_hint("Applying reloads the AI models; dictation is unavailable for a few seconds."), 1)
        apply_btn = QPushButton("Apply changes")
        apply_btn.setObjectName("primary")
        apply_btn.setMinimumWidth(180)
        apply_btn.clicked.connect(self._apply)
        apply_row.addWidget(apply_btn)
        layout.addLayout(apply_row)

    def _apply(self) -> None:
        """Advanced settings can require a Whisper/LLM reload, so - unlike General's
        instant auto-save - these stay batched behind one explicit button."""
        cfg = self.engine.config

        # Slider max represents "all layers" - save that back as -1 (llama.cpp's
        # own "all layers" convention) rather than a hardcoded layer count that's
        # only valid for whichever model happened to be loaded when the slider's
        # range was set, and treat it as equal to an existing -1 for dirty-checking.
        slider_value = self.n_gpu_layers_slider.value()
        new_n_gpu_layers = -1 if slider_value >= self.n_gpu_layers_slider.maximum() else slider_value
        old_n_gpu_layers_normalized = self.n_gpu_layers_slider.maximum() if cfg.llm.n_gpu_layers < 0 else cfg.llm.n_gpu_layers

        model_dirty = (
            cfg.whisper.model_name != self.whisper_cb.currentText()
            or cfg.llm.model_path != self.llm_path_edit.text().strip()
            or old_n_gpu_layers_normalized != slider_value
            or cfg.llm.kv_cache_quantization != self.kv_cache_quant_cb.isChecked()
        )

        cfg.whisper.model_name = self.whisper_cb.currentText()
        cfg.llm.model_path = self.llm_path_edit.text().strip()
        # Keep repo_id/filename in sync when the path matches a known preset exactly
        # (so a later download_models.py run still resolves the right file) - leave
        # them alone for a manually Browse...'d path, which isn't a known preset.
        for _preset in MODEL_PRESETS.values():
            if _preset["model_path"] == cfg.llm.model_path:
                cfg.llm.repo_id = _preset["repo_id"] or cfg.llm.repo_id
                cfg.llm.filename = _preset["filename"]
                break
        cfg.llm.n_gpu_layers = new_n_gpu_layers
        cfg.model_preset = self.preset_cb.currentData()
        cfg.llm.kv_cache_quantization = self.kv_cache_quant_cb.isChecked()
        # n_ctx/flash_attn/chat_style are architecture-mandated, not a user
        # tuning knob (no checkbox for them) - always taken from the selected
        # preset's own dict, same way repo_id/filename already are above.
        _selected_preset = MODEL_PRESETS[cfg.model_preset]
        model_dirty = model_dirty or (
            cfg.llm.n_ctx != _selected_preset.get("n_ctx", cfg.llm.n_ctx)
            or cfg.llm.flash_attn != _selected_preset.get("flash_attn", cfg.llm.flash_attn)
            or cfg.llm.chat_style != _selected_preset.get("chat_style", cfg.llm.chat_style)
        )
        cfg.llm.n_ctx = _selected_preset.get("n_ctx", cfg.llm.n_ctx)
        cfg.llm.flash_attn = _selected_preset.get("flash_attn", cfg.llm.flash_attn)
        cfg.llm.chat_style = _selected_preset.get("chat_style", cfg.llm.chat_style)
        cfg.whisper.vad_min_silence_duration_ms = self.vad_sensitivity_spin.value()

        self.engine.save_config()
        note = ""
        if model_dirty:
            self.engine.restart_engines()
            QMessageBox.information(
                self, APP_NAME,
                f"Settings applied.{note}\nReloading Whisper/LLM with the new hardware settings now - "
                "dictation is briefly unavailable while this finishes."
            )
        else:
            QMessageBox.information(self, APP_NAME, f"Settings applied.{note}")

    def _initial_preset_index(self, engine) -> int:
        """Prefer the persisted preset key; fall back to matching the current
        model_path for configs saved before model_preset existed."""
        keys = list(MODEL_PRESETS.keys())
        saved_preset = getattr(engine.config, "model_preset", None)
        if saved_preset in keys:
            return keys.index(saved_preset)
        return self._preset_index_for_path(engine.config.llm.model_path)

    def _preset_index_for_path(self, model_path: str) -> int:
        keys = list(MODEL_PRESETS.keys())
        for i, key in enumerate(keys):
            if MODEL_PRESETS[key]["model_path"] == model_path:
                return i
        return keys.index(DEFAULT_PRESET)  # unknown/custom path (e.g. Browse...'d manually) - default preset's slot

    def _update_preset_description(self) -> None:
        key = self.preset_cb.currentData()
        self.preset_description.setText(MODEL_PRESETS[key]["description"])
        self.preset_badge.setText(MODEL_PRESETS[key]["badge"])
        # Reflect the preset's model file in the Local LLM Path field immediately -
        # Save still needs to be clicked to actually persist/reload it.
        if hasattr(self, "llm_path_edit"):
            self.llm_path_edit.setText(MODEL_PRESETS[key]["model_path"])
        # Every preset is a complete, fixed config (100% GPU offload by design,
        # not a starting point for manual tuning) - force the slider to max so
        # Save doesn't accidentally combine a new preset with a stale manual
        # layer-count from whatever model was loaded when this tab was built.
        if hasattr(self, "n_gpu_layers_slider"):
            self.n_gpu_layers_slider.setValue(self.n_gpu_layers_slider.maximum())
        # Each preset owns its KV-cache quantization setting (see
        # src/presets.py) - not a separate manual knob once a preset is selected.
        if hasattr(self, "kv_cache_quant_cb"):
            self.kv_cache_quant_cb.setChecked(MODEL_PRESETS[key]["kv_cache_quantization"])

    def _show_compare_presets(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Compare Engine Presets")
        dlg.setMinimumWidth(560)
        dlg.setStyleSheet(f"QDialog {{ background-color: {theme.BG_APP}; }}")
        v = QVBoxLayout(dlg)
        heading = QLabel("Compare Engine Presets")
        heading.setStyleSheet(f"font-family: {theme.FONT_FAMILY_DISPLAY}; font-size: 16pt; color: {theme.TEXT_PRIMARY};")
        v.addWidget(heading)
        v.addWidget(_desc_label(
            f'<span style="color:{theme.TEXT_SECONDARY};">All tiers run 100% locally, on this machine, '
            "with zero data leaving your device. Figures below are the most recent measured results "
            "from tests/benchmark_models.py.</span>"
        ))

        cards_row = QHBoxLayout()
        for key, preset in MODEL_PRESETS.items():
            card = QFrame(objectName="presetCompareCard")
            card.setStyleSheet(f"#presetCompareCard {{ background-color: {theme.BG_CARD}; border: 1px solid {theme.BORDER_SUBTLE}; border-radius: 12px; }}")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(12, 12, 12, 12)
            title = QLabel(preset["label"])
            title.setStyleSheet(f"font-weight: 700; color: {theme.TEXT_PRIMARY};")
            title.setWordWrap(True)
            cv.addWidget(title)
            badge = QLabel(preset["badge"])
            badge.setStyleSheet(f"color: {theme.ACCENT_PRIMARY}; font-size: 8pt; font-weight: 600;")
            badge.setWordWrap(True)
            cv.addWidget(badge)
            desc = QLabel(preset["description"])
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 8pt;")
            cv.addWidget(desc)
            cv.addStretch()
            cards_row.addWidget(card)
        v.addLayout(cards_row)

        table = QGridLayout()
        table.setHorizontalSpacing(18)
        table.setVerticalSpacing(6)
        headers = ["Tier", "GPU total*", "RAM", "Tokens/s", "100w Latency", "Fidelity"]
        for col, text in enumerate(headers):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-weight: 600; font-size: 8pt;")
            table.addWidget(lbl, 0, col)
        for row, bench in enumerate(BENCHMARK_MATRIX, start=1):
            values = [
                MODEL_PRESETS[bench["key"]]["label"],
                f"{bench['gpu_total_mb'] / 1024:.1f} GB",
                f"{bench['ram_mb'] / 1024:.1f} GB",
                f"{bench['tok_s']:.1f}",
                f"{bench['latency_100w_s']:.2f}s",
                f"{bench['fidelity_pct']:.1f}%",
            ]
            for col, text in enumerate(values):
                lbl = QLabel(text)
                lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
                table.addWidget(lbl, row, col)
        v.addLayout(table)
        v.addWidget(_desc_label(
            f'<span style="color:{theme.TEXT_SECONDARY}; font-size:8pt;">* Whole-GPU memory in use during '
            "the benchmark (Whisper + LLM + Windows and other apps). Wisperno's own share is shown live "
            "in System Usage.</span>"
        ))

        close_btn = QPushButton("Close")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(dlg.accept)
        v.addWidget(close_btn)
        dlg.exec()

    def _on_engine_state_changed(self, state: str) -> None:
        self.reload_banner.setVisible(state == "loading")

    def _resolve_total_layers(self, engine) -> int:
        transformer = getattr(engine, "transformer", None)
        if transformer is not None and transformer.active_model_layers:
            return transformer.active_model_layers
        return DEFAULT_TOTAL_LAYERS

    def _model_file_size_mb(self, engine) -> float:
        import os
        from src.config import get_base_dir
        path = self.llm_path_edit.text().strip() or engine.config.llm.model_path
        if not os.path.isabs(path):
            path = str(get_base_dir() / path)
        try:
            return os.path.getsize(path) / 1024 / 1024
        except OSError:
            return 0.0

    def _update_gpu_layers_label(self, value: int) -> None:
        total = self._total_layers
        cpu_layers = total - value
        self.n_gpu_layers_value_label.setText(f"{value} on GPU, {cpu_layers} in RAM")

        # Indicative estimate, not a measurement: scale the model's own file
        # size across its layer count for a rough per-layer VRAM cost, plus a
        # flat allowance for KV cache/context buffers/CUDA overhead.
        file_size_mb = self._model_file_size_mb(self.engine)
        per_layer_mb = (file_size_mb * 1.1 / total) if (file_size_mb > 0 and total > 0) else 0.0
        base_overhead_mb = 350.0
        est_vram_gb = (base_overhead_mb + value * per_layer_mb) / 1024

        if cpu_layers <= 0:
            latency_txt = "Instant (<1.5s) - 100% GPU"
        else:
            cpu_fraction = cpu_layers / total if total else 0.0
            est_extra_s = cpu_fraction * 8.0  # rough: CPU/PCIe layers cost roughly proportional extra latency
            latency_txt = f"Slower (+{est_extra_s:.1f}s) - CPU/PCIe Bottleneck ({cpu_layers} layer(s) off-GPU)"

        self.gpu_estimate_label.setText(
            f"Estimated VRAM Impact: ~{est_vram_gb:.1f} GB  |  Estimated Latency Impact: {latency_txt}"
        )

    def _browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select GGUF LLM model", "", "GGUF model (*.gguf);;All files (*.*)")
        if path:
            self.llm_path_edit.setText(path)
