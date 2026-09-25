"""
Settings tab for the Wisperno dashboard: General (everyday controls) and
Advanced (model/hardware tuning) sub-tabs, plus the KeySequenceRecorder
widget used for hotkey rebinding.
"""

from typing import Optional

import sounddevice as sd
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFileDialog, QMessageBox,
    QProgressBar, QTabWidget, QSpinBox, QSlider, QFrame, QDialog, QScrollArea,
)

from src.presets import BENCHMARK_MATRIX, DEFAULT_PRESET, MODEL_PRESETS
from src.ui import theme
from src.ui.scroll_utils import make_scrollable_layout
from src.ui.shortcut_recorder import KeySequenceRecorder

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
        f"QDialog {{ background-color: #161622; border: 1px solid #2E2E42; border-radius: 12px; }}"
    )
    v = QVBoxLayout(dlg)
    v.setContentsMargins(28, 24, 28, 24)
    v.setSpacing(10)

    heading = QLabel(title)
    heading.setStyleSheet("font-size: 15pt; font-weight: 700; color: #FFFFFF;")
    heading.setWordWrap(True)
    v.addWidget(heading)

    def _subhead(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; color: #818CF8; margin-top: 8px; font-size: 10pt;")
        return lbl

    def _body(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #D1D5DB; font-size: 13px; line-height: 1.5;")
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
    got_it_btn.setStyleSheet(
        f"QPushButton {{ background-color: {theme.ACCENT_PRIMARY}; color: white; border: none; "
        f"border-radius: 8px; padding: 9px 0; font-weight: 600; }}"
        f"QPushButton:hover {{ background-color: {theme.ACCENT_PRIMARY_HOVER}; }}"
    )
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
    return widget


def _shortcut_card(title: str, description: str):
    """An elevated surface card (#181824, 12px padding) holding one shortcut recorder,
    so paired shortcuts sit side-by-side in a two-column grid instead of full-width rows."""
    frame = QFrame()
    frame.setStyleSheet(f"background-color: #181824; border: 1px solid #262638; border-radius: 10px;")
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
    """General (default view, instant auto-save) + Advanced (explicit Apply) sub-tabs."""

    def __init__(self, engine, controller, main_window=None):
        super().__init__()
        self.engine = engine
        self.controller = controller

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.addWidget(_label_title("Settings"))
        self.sub_tabs = QTabWidget()
        layout.addWidget(self.sub_tabs)

        self.general_tab = _GeneralSettings(engine, controller)
        self.advanced_tab = _AdvancedSettings(engine)
        self.sub_tabs.addTab(self.general_tab, "General")
        self.sub_tabs.addTab(self.advanced_tab, "Advanced")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Always land on General when Settings is (re)opened - Advanced's
        # hardware-tuning controls shouldn't be the first thing a user sees
        # after, say, just checking Dictionary and coming back.
        self.sub_tabs.setCurrentIndex(0)
        self.reset_scroll()

    def reset_scroll(self) -> None:
        for tab in (self.general_tab, self.advanced_tab):
            tab._scroll_area.verticalScrollBar().setValue(0)


class _GeneralSettings(QWidget):
    """Everyday controls: mic, dual dictation triggers, autostart, pill visibility.
    Every control here auto-saves instantly on change - there is no Save button
    on this tab (see SettingsTab; Advanced keeps its own explicit Apply)."""

    def __init__(self, engine, controller):
        super().__init__()
        self.engine = engine
        self.controller = controller
        layout = make_scrollable_layout(self)
        layout.setContentsMargins(28, 22, 28, 22)

        # --- Audio ---
        layout.addWidget(_label_title("Audio Input"))
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
        layout.addWidget(self.device_cb)

        self.level_meter = QProgressBar()
        self.level_meter.setRange(0, 100)
        layout.addWidget(self.level_meter)
        self.test_mic_btn = QPushButton("Test Microphone (3s)")
        self.test_mic_btn.clicked.connect(self._test_mic)
        layout.addWidget(self.test_mic_btn)

        # --- Dictation triggers: two fully independent cards, each with its own
        # shortcut recorder and its own enable switch. Both, either, or neither
        # can be active at once. "Polish Selected Text" has no card here anymore
        # - it lives in the Transforms hub (any transform's hotkey already
        # falls back to polishing the current selection when nothing is spoken).
        layout.addWidget(_label_title("Dictation Triggers"))
        triggers_row = QHBoxLayout()
        triggers_row.setSpacing(12)

        tap_card, tap_v = _shortcut_card(
            "Tap to Toggle Dictation",
            "Tap once to start listening, tap again to stop. Instant speech-to-text with automatic "
            "list detection and filler removal (sub-second, zero LLM delay by default).",
        )
        self.tap_enable_cb = QCheckBox("Enable Tap to Toggle")
        self.tap_enable_cb.setChecked(engine.config.tap_toggle_enabled)
        self.tap_enable_cb.stateChanged.connect(lambda s: engine.set_tap_toggle_enabled(s != 0))
        tap_v.addWidget(self.tap_enable_cb)
        self.tap_toggle_recorder = KeySequenceRecorder(engine.config.tap_toggle_hotkey)
        self.tap_toggle_recorder.sequence_captured.connect(engine.set_tap_toggle_hotkey)
        tap_v.addWidget(self.tap_toggle_recorder)
        triggers_row.addWidget(tap_card)

        hold_card, hold_v = _shortcut_card(
            "Hold to Talk Dictation",
            "Hold the shortcut down to record, release to stop - classic push-to-talk. Independent "
            "of Tap to Toggle above; enable either, both (with different keys), or neither.",
        )
        self.hold_enable_cb = QCheckBox("Enable Hold to Talk")
        self.hold_enable_cb.setChecked(engine.config.hold_to_talk_enabled)
        self.hold_enable_cb.stateChanged.connect(lambda s: engine.set_hold_to_talk_enabled(s != 0))
        hold_v.addWidget(self.hold_enable_cb)
        self.hold_to_talk_recorder = KeySequenceRecorder(engine.config.hold_to_talk_hotkey)
        self.hold_to_talk_recorder.sequence_captured.connect(engine.set_hold_to_talk_hotkey)
        hold_v.addWidget(self.hold_to_talk_recorder)
        triggers_row.addWidget(hold_card)

        layout.addLayout(triggers_row)

        # --- Auto-Stop Silence Detection ---
        silence_card, silence_v = _shortcut_card(
            "Auto-Stop Silence Detection",
            "Automatically stops recording and pastes text when you pause speaking.",
        )
        self.auto_silence_cb = _no_wheel(QComboBox())
        self.auto_silence_cb.addItem("Disabled (Manual Stop Only)", 0)
        self.auto_silence_cb.addItem("3 seconds", 3)
        self.auto_silence_cb.addItem("5 seconds (Default)", 5)
        self.auto_silence_cb.addItem("8 seconds", 8)
        self.auto_silence_cb.addItem("10 seconds", 10)
        current_idx = self.auto_silence_cb.findData(engine.config.audio.auto_silence_seconds)
        self.auto_silence_cb.setCurrentIndex(current_idx if current_idx >= 0 else 2)
        self.auto_silence_cb.currentIndexChanged.connect(
            lambda _i: engine.set_auto_silence_seconds(self.auto_silence_cb.currentData())
        )
        silence_v.addWidget(self.auto_silence_cb)
        layout.addWidget(silence_card)

        self.auto_llm_polish_cb = QCheckBox("Automatically run LLM polish after dictation (slower, full semantic rewrite)")
        self.auto_llm_polish_cb.setChecked(engine.config.auto_llm_polish)
        self.auto_llm_polish_cb.setToolTip(
            "Off (default): the dictation triggers above use the instant rule-based formatter, zero LLM delay.\n"
            "On: dictation is routed through your active Engine Preset instead, like Polish Selected Text."
        )
        self.auto_llm_polish_cb.stateChanged.connect(lambda s: engine.set_auto_llm_polish(s != 0))
        layout.addWidget(self.auto_llm_polish_cb)

        # --- Profanity Filter ---
        profanity_card, profanity_v = _shortcut_card(
            "Profanity Filter", "Choose how spoken profanity and swear words are handled in polished output."
        )
        profanity_row = QHBoxLayout()
        self.profanity_cb = _no_wheel(QComboBox())
        self.profanity_cb.addItem("Allow All (Verbatim)", "allow")
        self.profanity_cb.addItem("Censor with Asterisks (e.g., f***, s***)", "censor")
        self.profanity_cb.addItem("Clean / Remove", "remove")
        current_idx = self.profanity_cb.findData(engine.config.profanity_filter)
        self.profanity_cb.setCurrentIndex(current_idx if current_idx >= 0 else 0)
        self.profanity_cb.currentIndexChanged.connect(lambda _i: engine.set_profanity_filter(self.profanity_cb.currentData()))
        profanity_row.addWidget(self.profanity_cb, 1)
        profanity_row.addWidget(_help_button(
            "Profanity Filter",
            "Controls whether spoken swear words are kept exactly as said, or sanitized, in the text "
            "that gets typed. The LLM never makes this call itself - it always transcribes profanity "
            "verbatim, and this setting is applied as a separate step afterward.",
            "Allow All for personal notes/chat where your own words should show up unedited. Censor or "
            "Clean/Remove for anything that might be shared, screen-recorded, or read by someone else.",
        ))
        profanity_v.addLayout(profanity_row)
        layout.addWidget(profanity_card)

        # --- System ---
        layout.addWidget(_label_title("System"))
        from src import autostart

        self.autostart_cb = QCheckBox("Start with Windows")
        self.autostart_cb.setChecked(autostart.is_enabled())
        self.autostart_cb.stateChanged.connect(lambda s: autostart.set_enabled(s != 0))
        layout.addWidget(self.autostart_cb)

        self.pill_cb = QCheckBox("Show Floating Pill")
        self.pill_cb.setChecked(True)
        self.pill_cb.stateChanged.connect(self._on_pill_visibility_changed)
        layout.addWidget(self.pill_cb)

        self.minimize_to_tray_cb = QCheckBox("Minimize to Tray on Close (uncheck to quit fully)")
        self.minimize_to_tray_cb.setChecked(engine.config.minimize_to_tray)
        self.minimize_to_tray_cb.stateChanged.connect(lambda s: engine.set_minimize_to_tray(s != 0))
        layout.addWidget(self.minimize_to_tray_cb)

        self.always_on_top_cb = QCheckBox("Always Keep Pill on Top (including fullscreen apps/games)")
        self.always_on_top_cb.setChecked(engine.config.pill_always_on_top)
        self.always_on_top_cb.stateChanged.connect(self._on_always_on_top_changed)
        layout.addWidget(self.always_on_top_cb)

        # --- Audio Feedback ---
        layout.addWidget(_label_title("Audio Feedback"))

        self.audio_cues_cb = QCheckBox("Play a Sound When Dictation Starts/Stops")
        self.audio_cues_cb.setChecked(engine.config.audio_cues_enabled)
        self.audio_cues_cb.stateChanged.connect(lambda s: engine.set_audio_cues_enabled(s != 0))
        layout.addWidget(self.audio_cues_cb)

        self.auto_copy_cb = QCheckBox("Always Copy Transcribed Text to Clipboard")
        self.auto_copy_cb.setChecked(engine.config.injector.auto_copy_to_clipboard)
        self.auto_copy_cb.stateChanged.connect(lambda s: engine.set_auto_copy_to_clipboard(s != 0))
        layout.addWidget(self.auto_copy_cb)

        # --- Testing ---
        layout.addWidget(_label_title("Testing"))
        self.save_recordings_cb = QCheckBox("Save Recordings for Testing (stores your dictation audio on this PC)")
        self.save_recordings_cb.setToolTip(
            "Keeps each dictation's audio and transcript so scripts/eval_dictation.py can measure accuracy "
            "and speed on your own voice. Nothing leaves this machine. Leave off for normal use."
        )
        self.save_recordings_cb.setChecked(engine.config.save_recordings_for_testing)
        self.save_recordings_cb.stateChanged.connect(lambda s: engine.set_save_recordings_for_testing(s != 0))
        layout.addWidget(self.save_recordings_cb)
        open_recordings_btn = QPushButton("Open Recordings Folder")
        open_recordings_btn.clicked.connect(self._open_recordings_folder)
        layout.addWidget(open_recordings_btn, alignment=Qt.AlignLeft)

        layout.addStretch()

    def _open_recordings_folder(self) -> None:
        import os
        from src.test_recordings import recordings_dir

        folder = recordings_dir()
        if hasattr(os, "startfile"):
            os.startfile(folder)  # Windows Explorer
        else:
            QMessageBox.information(self, "Wisperno", f"Recordings folder:\n{folder}")

    def _on_device_changed(self, _index: int) -> None:
        self.engine.set_audio_device(self.selected_device_index())

    def _on_pill_visibility_changed(self, state: int) -> None:
        if hasattr(self.controller, "set_pill_visible"):
            self.controller.set_pill_visible(state != 0)

    def _on_always_on_top_changed(self, state: int) -> None:
        if hasattr(self.controller, "set_pill_always_on_top"):
            self.controller.set_pill_always_on_top(state != 0)

    def selected_device_index(self) -> Optional[int]:
        idx = self.device_cb.currentIndex()
        return self._device_indices[idx] if 0 <= idx < len(self._device_indices) else None

    def _test_mic(self) -> None:
        if not self.engine.audio_worker:
            QMessageBox.warning(self, "Wisperno", "Audio engine hasn't finished loading yet.")
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
    """Model/hardware tuning: Whisper model, LLM path, GPU layer offload, VAD sensitivity."""

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        layout = make_scrollable_layout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.addWidget(_desc_label(
            f'<span style="color:{theme.TEXT_SECONDARY}">These control model selection and hardware '
            "offloading. The defaults work well on most GPUs - change them only if you know why. "
            "Live VRAM/RAM telemetry moved to the System Usage tab.</span>"
        ))

        # --- Engine Preset - a bordered, padded container (mockup:
        # assets/screenshots/new assets/) rather than laid straight into the
        # tab's own outer layout like every other Advanced control. ---
        preset_card = QFrame()
        preset_card.setStyleSheet(
            f"QFrame {{ background-color: #12121A; border: 1px solid #1E1E2C; "
            f"border-radius: 12px; }}"
        )
        preset_layout = QVBoxLayout(preset_card)
        preset_layout.setContentsMargins(20, 20, 20, 20)

        preset_row = QHBoxLayout()
        preset_title = _label_title("Engine Preset")
        preset_title.setToolTip(
            "Selects the local AI engine. All tiers run 100% locally on your machine with zero data leaving your device."
        )
        preset_row.addWidget(preset_title)
        preset_row.addStretch()
        compare_btn = QPushButton("Compare Presets & Benchmarks")
        compare_btn.setStyleSheet(
            f"QPushButton {{ background-color: {theme.ACCENT_PRIMARY}; color: white; border: none; "
            f"border-radius: 8px; padding: 6px 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: {theme.ACCENT_PRIMARY_HOVER}; }}"
        )
        compare_btn.clicked.connect(self._show_compare_presets)
        preset_row.addWidget(compare_btn)
        preset_layout.addLayout(preset_row)
        self.preset_cb = _no_wheel(QComboBox())
        for i, (key, preset) in enumerate(MODEL_PRESETS.items()):
            self.preset_cb.addItem(preset["label"], key)
            self.preset_cb.setItemData(i, preset["tooltip"], Qt.ToolTipRole)
        self.preset_cb.setCurrentIndex(self._initial_preset_index(engine))
        self.preset_badge = QLabel("")
        self.preset_badge.setStyleSheet(
            f"color: {theme.ACCENT_PRIMARY}; font-size: 8pt; font-weight: 600;"
        )
        self.preset_description = QLabel("")
        self.preset_description.setWordWrap(True)
        self.preset_description.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 8pt;")
        self.preset_cb.currentIndexChanged.connect(self._update_preset_description)
        self._update_preset_description()
        preset_layout.addWidget(self.preset_cb)
        preset_layout.addWidget(self.preset_badge)
        preset_layout.addWidget(self.preset_description)
        layout.addWidget(preset_card)

        # Transition indicator: hidden until a preset switch triggers a reload,
        # then tracks engine.state_changed's "loading" state so the user sees
        # a clean in-progress signal instead of the GUI silently doing nothing
        # (reload itself already runs off the GUI thread - see restart_engines()).
        # Wording deliberately generic, not "switching preset" specifically -
        # this same "loading" state also fires on the app's very first startup
        # (state_changed.emit("loading") in engine.start()), and the banner
        # would otherwise be visible then too, before any preset switch happened.
        self.reload_banner = QLabel("⟳ Loading engine (Whisper + LLM) - this can take a few seconds...")
        self.reload_banner.setWordWrap(True)
        self.reload_banner.setStyleSheet(
            f"background-color: {theme.INPUT_BG}; color: {theme.ACCENT_PRIMARY}; "
            f"border-radius: 6px; padding: 6px 10px; font-weight: 600;"
        )
        self.reload_banner.setVisible(False)
        layout.addWidget(self.reload_banner)
        if hasattr(engine, "state_changed"):
            engine.state_changed.connect(self._on_engine_state_changed)

        # Each control gets its own "label + (?) header row, input below" block -
        # a fixed-size help button (see _help_button) directly adjacent to its
        # own label, never sharing a row with a growing input widget, which was
        # the actual cause of it looking misaligned/floating/clipped before.
        def _labeled_row(label_text: str, help_btn: QPushButton) -> QVBoxLayout:
            block = QVBoxLayout()
            header = QHBoxLayout()
            header.addWidget(QLabel(label_text))
            header.addStretch()
            header.addWidget(help_btn)
            block.addLayout(header)
            return block

        whisper_block = _labeled_row("Whisper Model:", _help_button(
            "Whisper Model",
            "The speech-to-text engine that turns your voice into raw text before any cleanup or "
            "polish happens. A larger model recognizes speech more accurately, especially accents, "
            "background noise, and technical vocabulary, at the cost of more VRAM and (slightly) more latency.",
            "large-v3-turbo for typical desktop use - near-perfect recognition with low latency on any "
            "modern GPU. Drop to medium.en / small.en / base.en only if VRAM is genuinely tight.",
        ))
        self.whisper_cb = _no_wheel(QComboBox())
        self.whisper_cb.setFont(QFont(theme.FONT_FAMILY_MONO))
        self.whisper_cb.addItems(["large-v3-turbo", "medium.en", "small.en", "base.en"])
        idx = self.whisper_cb.findText(engine.config.whisper.model_name)
        if idx >= 0:
            self.whisper_cb.setCurrentIndex(idx)
        whisper_block.addWidget(self.whisper_cb)
        layout.addLayout(whisper_block)

        llm_path_block = _labeled_row("Local LLM Path:", _help_button(
            "Local LLM Path",
            "The GGUF model file that powers LLM-based text transformation (Polish Selected Text, "
            "Transforms, and dictation when 'Automatically run LLM polish' is on). This always points "
            "at a file already on disk - selecting an Engine Preset above fills this in for you.",
            "Leave this on whichever Engine Preset you picked above. Only Browse to a custom .gguf "
            "file if you've downloaded one yourself and know what it needs (chat-template compatible, "
            "fits your VRAM).",
        ))
        path_row = QHBoxLayout()
        self.llm_path_edit = QLineEdit(engine.config.llm.model_path)
        self.llm_path_edit.setFont(QFont(theme.FONT_FAMILY_MONO))
        path_row.addWidget(self.llm_path_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_model)
        path_row.addWidget(browse_btn)
        llm_path_block.addLayout(path_row)
        layout.addLayout(llm_path_block)

        vad_block = _labeled_row("VAD Silence Sensitivity (ms):", _help_button(
            "VAD Silence Sensitivity",
            "Voice Activity Detection (VAD) watches for silence to know when you've stopped talking "
            "and automatically ends the recording. This value is how long a pause has to last before "
            "that happens.",
            "1200ms (the default) works well for normal speech with natural pauses. Lower it (e.g. "
            "600-800ms) in a quiet room if recordings feel slow to end; raise it if mid-sentence "
            "pauses are cutting your dictation off early.",
        ))
        self.vad_sensitivity_spin = _no_wheel(QSpinBox())
        self.vad_sensitivity_spin.setRange(50, 2000)
        self.vad_sensitivity_spin.setSingleStep(50)
        self.vad_sensitivity_spin.setValue(engine.config.whisper.vad_min_silence_duration_ms)
        vad_block.addWidget(self.vad_sensitivity_spin)
        layout.addLayout(vad_block)

        # --- VRAM offload ---
        self._total_layers = self._resolve_total_layers(engine)
        offload_tooltip = (
            f"Controls how much of the AI model runs on your graphics card. {self._total_layers}/"
            f"{self._total_layers} (Full GPU) gives the fastest speed (~1.5s). Lower this only if you "
            "need to free up GPU memory for games or creative software."
        )
        offload_row = QHBoxLayout()
        offload_title = _label_title("Offload Layers to GPU")
        offload_row.addWidget(offload_title)
        offload_row.addStretch()
        offload_row.addWidget(_help_button(
            "Offload Layers to GPU",
            "The LLM is made of layers; each one can run on your graphics card (fast) or fall back to "
            f"system RAM/CPU (slower). This machine's loaded model has {self._total_layers} layers total.",
            f"{self._total_layers}/{self._total_layers} (Full GPU, the slider's max) for the fastest "
            "generation. Lower it only if you need to free VRAM for something else running "
            "simultaneously, like a game or creative app - expect noticeably slower dictation in exchange.",
        ))
        layout.addLayout(offload_row)
        layout.addWidget(_desc_label(
            f'<span style="color:{theme.TEXT_SECONDARY}">Adjust to balance VRAM usage and CPU RAM '
            "offloading. Lower = less VRAM, more system RAM and slower generation. Estimates below are "
            "indicative (scaled from the loaded model's own file size and layer count) - the actual "
            "reload after Save measures the real numbers.</span>"
        ))
        slider_row = QHBoxLayout()
        self.n_gpu_layers_slider = _no_wheel(QSlider(Qt.Orientation.Horizontal))
        self.n_gpu_layers_slider.setRange(min(8, self._total_layers), self._total_layers)
        self.n_gpu_layers_slider.setToolTip(offload_tooltip)
        # n_gpu_layers=-1 means "all layers" (llama.cpp's own convention) - map
        # that to the slider's max rather than clamping it down to the min,
        # which would silently misrepresent a 100%-GPU config as barely-offloaded.
        configured = engine.config.llm.n_gpu_layers
        initial_value = self._total_layers if configured < 0 else max(8, min(self._total_layers, configured))
        self.n_gpu_layers_slider.setValue(initial_value)
        self.n_gpu_layers_value_label = QLabel("")
        slider_row.addWidget(self.n_gpu_layers_slider, 1)
        slider_row.addWidget(self.n_gpu_layers_value_label)
        layout.addLayout(slider_row)

        self.gpu_estimate_label = QLabel("")
        self.gpu_estimate_label.setWordWrap(True)
        self.gpu_estimate_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        layout.addWidget(self.gpu_estimate_label)
        self._update_gpu_layers_label(self.n_gpu_layers_slider.value())
        self.n_gpu_layers_slider.valueChanged.connect(self._update_gpu_layers_label)

        kv_row = QHBoxLayout()
        self.kv_cache_quant_cb = QCheckBox("Q8_0 KV Cache Compression (saves ~600MB VRAM)")
        self.kv_cache_quant_cb.setChecked(engine.config.llm.kv_cache_quantization)
        kv_row.addWidget(self.kv_cache_quant_cb)
        kv_row.addStretch()
        kv_row.addWidget(_help_button(
            "KV-Cache Compression",
            "The KV (key/value) cache is the model's short-term working memory for the conversation "
            "it's currently processing. Compressing it to 8-bit precision (Q8_0) shrinks its VRAM "
            "footprint by roughly 600MB.",
            "Leave it on for Standard/Turbo (the default) - no measurable quality loss. Flagship ships "
            "it off on purpose, trading that VRAM back for maximum output fidelity instead.",
        ))
        layout.addLayout(kv_row)

        # --- Disk / retention ---
        retention_title = _label_title("History Storage")
        retention_title.setToolTip(
            "Automatically deletes older transcripts after the selected period to save disk space. "
            "Pinned entries are always preserved."
        )
        layout.addWidget(retention_title)
        self.storage_stats_label = QLabel("")
        layout.addWidget(self.storage_stats_label)
        self._refresh_storage_stats(engine)

        retention_row = QHBoxLayout()
        retention_row.addWidget(QLabel("Auto-delete history older than:"))
        self.retention_cb = _no_wheel(QComboBox())
        self.retention_cb.addItem("Never", "never")
        self.retention_cb.addItem("3 months", "3_months")
        self.retention_cb.addItem("6 months", "6_months")
        self.retention_cb.addItem("1 year", "1_year")
        idx = self.retention_cb.findData(engine.config.db_retention_policy)
        if idx >= 0:
            self.retention_cb.setCurrentIndex(idx)
        self.retention_cb.setToolTip(
            "Automatically deletes older transcripts after the selected period to save disk space. "
            "Pinned entries are always preserved."
        )
        retention_row.addWidget(self.retention_cb)
        layout.addLayout(retention_row)

        clear_btn = QPushButton("Clear Oldest Transcripts (oldest 25%, pinned kept)")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(lambda: self._clear_oldest(engine))
        layout.addWidget(clear_btn)

        layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply)
        layout.addWidget(apply_btn)

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
        cfg.db_retention_policy = self.retention_cb.currentData()
        pruned = self.engine.db.prune_history(cfg.db_retention_policy)

        self.engine.save_config()
        note = f" ({pruned} old record(s) pruned.)" if pruned else ""
        if model_dirty:
            self.engine.restart_engines()
            QMessageBox.information(
                self, "Wisperno",
                f"Settings applied.{note}\nReloading Whisper/LLM with the new hardware settings now - "
                "dictation is briefly unavailable while this finishes."
            )
        else:
            QMessageBox.information(self, "Wisperno", f"Settings applied.{note}")

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
        heading.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {theme.TEXT_PRIMARY};")
        v.addWidget(heading)
        v.addWidget(_desc_label(
            f'<span style="color:{theme.TEXT_SECONDARY};">All tiers run 100% locally, on this machine, '
            "with zero data leaving your device. Figures below are the most recent measured results "
            "from tests/benchmark_models.py.</span>"
        ))

        cards_row = QHBoxLayout()
        for key, preset in MODEL_PRESETS.items():
            card = QFrame()
            card.setStyleSheet(f"background-color: #181824; border: 1px solid #262638; border-radius: 10px;")
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

    def _refresh_storage_stats(self, engine) -> None:
        stats = engine.db.get_database_storage_stats()
        self.storage_stats_label.setText(
            f'<span style="color:{theme.TEXT_SECONDARY}">{stats["size_mb_formatted"]} - '
            f'{stats["record_count"]} records</span>'
        )

    def _clear_oldest(self, engine) -> None:
        deleted = engine.db.clear_oldest_transcripts(fraction=0.25)
        self._refresh_storage_stats(engine)
        QMessageBox.information(self, "Wisperno", f"Deleted {deleted} of the oldest transcripts (pinned ones kept).")

    def _browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select GGUF LLM model", "", "GGUF model (*.gguf);;All files (*.*)")
        if path:
            self.llm_path_edit.setText(path)
