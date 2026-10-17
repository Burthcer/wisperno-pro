"""
Qt worker layer for Wisperno. Keeps the GUI thread free for 60fps rendering by
running audio capture, hotkey polling, and the STT->LLM->injection pipeline
off the main thread, communicating back via Qt signals (thread-safe: PySide6
auto-marshals a signal emitted on a worker thread into a queued call on the
thread that owns the connected slot).

AudioWorker and HotkeyWorker wrap the existing, independently-tested
AudioRecorder / HotkeyManager (sounddevice's callback and the GetAsyncKeyState
poll already run on their own non-Qt threads) rather than re-implementing that
logic as QThread subclasses - the win from QThread here is signal delivery,
not the threading itself, which was already correct.

InferenceWorker (the main dictation hotkey) runs one of two pipelines after
Whisper: the instant, zero-LLM src/direct_formatter.py (Mode 1 - default), or
the full src/transformer.py LLM polish (opt-in via config.auto_llm_polish, or
always for a Transforms-hub hotkey's own prompt). SelectionPolishWorker
(the dedicated Polish Selected Text hotkey) always uses the LLM.
"""

import time
from typing import Dict, Optional

from PySide6.QtCore import QObject, QThread, Signal
from loguru import logger

from src.audio_recorder import AudioRecorder
from src.app_context import apply_app_style, foreground_app, style_for_app, wants_trailing_space
from src.direct_formatter import format_direct, is_short_and_clean
from src.hotkey_manager import HotkeyManager
from src.config import AppConfig
from src.paragraphing import split_into_paragraphs
from src.focus_check import has_text_target
from src.ramble_trim import trim_rambling
from src.self_correction import apply_self_correction
from src.swear_filter import apply_profanity_filter


def with_trailing_space(text: str) -> str:
    """'Sentence.' -> 'Sentence. ' so back-to-back dictations don't fuse. Left
    alone: multi-line output (lists), and anything not ending a sentence."""
    if text and "\n" not in text and text.endswith((".", "!", "?")):
        return text + " "
    return text


class AudioWorker(QObject):
    """Wraps AudioRecorder; emits level_changed(float) on every audio block during recording,
    and auto_silence_triggered() once per recording if the user pauses past their configured
    auto-stop threshold. Both callbacks fire from PortAudio's own native callback thread - Qt
    signals are safe to emit cross-thread (auto-queued onto the receiving thread)."""

    level_changed = Signal(float)
    auto_silence_triggered = Signal()
    mic_live = Signal()  # first real audio of this recording arrived - safe to speak now

    def __init__(self, config, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.recorder = AudioRecorder(
            config=config, level_callback=self.level_changed.emit,
            silence_callback=self.auto_silence_triggered.emit,
            started_callback=self.mic_live.emit,
        )

    def start_recording(self) -> bool:
        return self.recorder.start_recording()

    def stop_recording(self):
        return self.recorder.stop_recording()

    def set_device_index(self, device_index: Optional[int]) -> None:
        """Live device swap for Settings -> General's auto-save (no engine restart
        needed - the next start_recording() call picks it up)."""
        self.recorder.device_index = device_index

    def set_auto_silence_seconds(self, seconds: int) -> None:
        self.recorder.set_auto_silence_seconds(seconds)


class HotkeyWorker(QObject):
    """Wraps HotkeyManager; translates its callbacks into Qt signals."""

    recording_started = Signal()
    recording_stopped = Signal()
    mode_cycled = Signal(str)
    settings_requested = Signal()
    dashboard_toggle_requested = Signal()
    live_transcribe_toggle_requested = Signal()
    writing_styles_triggered = Signal()
    transform_press_requested = Signal(str)
    transform_release_requested = Signal(str)

    def __init__(self, config: AppConfig, transform_hotkeys: Optional[Dict[str, str]] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.manager = HotkeyManager(
            tap_toggle_hotkey=config.tap_toggle_hotkey,
            tap_toggle_enabled=config.tap_toggle_enabled,
            hold_to_talk_hotkey=config.hold_to_talk_hotkey,
            hold_to_talk_enabled=config.hold_to_talk_enabled,
            cycle_mode_hotkey=config.cycle_mode_hotkey,
            settings_hotkey=config.settings_hotkey,
            dashboard_hotkey=config.dashboard_hotkey,
            live_transcribe_hotkey=config.live_transcribe_hotkey,
            writing_styles_hotkey=config.writing_styles_hotkey,
            transform_hotkeys=transform_hotkeys or {},
            on_press=self.recording_started.emit,
            on_release=self.recording_stopped.emit,
            on_mode_cycle=self.mode_cycled.emit,
            on_settings_open=self.settings_requested.emit,
            on_dashboard_toggle=self.dashboard_toggle_requested.emit,
            on_live_transcribe_toggle=self.live_transcribe_toggle_requested.emit,
            on_writing_styles_trigger=self.writing_styles_triggered.emit,
            on_transform_press=self.transform_press_requested.emit,
            on_transform_release=self.transform_release_requested.emit,
            available_modes=["polish", "prompt_engineer", "bullets", "code", "raw"],
            initial_mode=config.active_mode,
        )

    def start(self) -> None:
        self.manager.start()

    def stop(self) -> None:
        self.manager.stop()

    def set_tap_toggle_hotkey(self, hotkey_str: str) -> None:
        self.manager.set_tap_toggle_hotkey(hotkey_str)

    def set_tap_toggle_enabled(self, enabled: bool) -> None:
        self.manager.set_tap_toggle_enabled(enabled)

    def set_hold_to_talk_hotkey(self, hotkey_str: str) -> None:
        self.manager.set_hold_to_talk_hotkey(hotkey_str)

    def set_hold_to_talk_enabled(self, enabled: bool) -> None:
        self.manager.set_hold_to_talk_enabled(enabled)

    def set_transform_hotkeys(self, transform_hotkeys: Dict[str, str]) -> None:
        self.manager.set_transform_hotkeys(transform_hotkeys)


class InferenceWorker(QThread):
    """
    Runs one full pipeline pass off the GUI thread:
    audio -> Whisper STT -> vocabulary correction -> snippet expansion (bypasses
    formatting entirely when a trigger matches) -> direct_formatter OR SLM
    transform (see use_direct_formatter) -> Win32 paste injection -> SQLite
    history insert.
    """

    state_changed = Signal(str)          # 'processing' | 'success' | 'idle'
    result_ready = Signal(dict)          # history row payload, for the History tab
    recording_saved = Signal(int)        # history id whose audio is now kept (History can offer Re-transcribe)
    paste_missed = Signal(str)           # the text, when no text box had focus (the pill shows a Copy card)
    error = Signal(str)

    def __init__(
        self, audio_array, transcriber, transformer, injector, db, snippets,
        mode: str, record_duration_ms: float, system_prompt: Optional[str] = None,
        use_direct_formatter: bool = False, status_label: Optional[str] = None,
        save_recording: bool = False, trailing_space: bool = False, app_styles: Optional[Dict[str, str]] = None,
        keep_recent: int = 0, self_correction: bool = False, auto_paragraphs: bool = False, trim_rambling: bool = False,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.audio_array = audio_array
        self.transcriber = transcriber
        self.transformer = transformer
        self.injector = injector
        self.db = db
        self.snippets = snippets  # dict[str, str]: lowercase trigger -> expansion
        self.mode = mode
        self.record_duration_ms = record_duration_ms
        # When set (a Transforms-hub entry triggered this recording directly,
        # e.g. Alt+X), use its own prompt instead of looking `mode` up in
        # config.yaml - lets DB-defined transforms drive dictation directly.
        self.system_prompt = system_prompt
        # A Transforms-hub entry's display title (e.g. "Prompt Engineer") -
        # carried on the "processing" pill state as "processing:<label>" so
        # the pill shows "Prompt Engineering..." instead of a generic message.
        self.status_label = status_label
        # Mode 1 (Instant Direct Dictation): skip the LLM entirely and run
        # src/direct_formatter.py instead - set by the engine from the
        # `auto_llm_polish` config toggle, only for the main dictation hotkey
        # (never for a Transforms-hub hotkey, which is an explicit LLM gesture).
        self.use_direct_formatter = use_direct_formatter
        # Settings -> General -> "Save Recordings for Testing" (off by default).
        self.save_recording = save_recording
        self.trailing_space = trailing_space
        # Per-app styles (src/app_context.py); None = off.
        self.app_styles = app_styles
        # Newest N dictations keep their audio for History -> Re-transcribe (0 = none).
        self.keep_recent = keep_recent
        # Settings -> "Remove what I retract" (src/self_correction.py).
        self.self_correction = self_correction
        # Settings -> Writing -> topic paragraphs for long dictation (src/paragraphing.py).
        self.auto_paragraphs = auto_paragraphs
        # Settings -> Writing -> drop spoken padding like "and yeah" (src/ramble_trim.py).
        self.trim_rambling = trim_rambling

    def _emit_final(self, state: str) -> None:
        """The state that ends this dictation ("success" / "idle"). Every way out of run() must send one - a
        pill left on "processing" with nothing coming to clear it is exactly the stuck-pill bug."""
        self._final_sent = True
        self.state_changed.emit(state)

    def run(self) -> None:
        self._final_sent = False
        try:
            if self.use_direct_formatter:
                self.state_changed.emit("typing")
            elif self.status_label:
                self.state_changed.emit(f"processing:{self.status_label}")
            else:
                self.state_changed.emit("processing")
            t0 = time.perf_counter()

            raw_text = self.transcriber.transcribe(self.audio_array)
            if not raw_text or not raw_text.strip():
                logger.info("No speech detected in audio segment.")
                self._emit_final("idle")
                return
            if self.self_correction:
                corrected = apply_self_correction(raw_text)
                if corrected != raw_text:
                    logger.info(f"[SELF-CORRECTION] '{raw_text}' -> '{corrected}'")
                    if not corrected.strip():
                        self._emit_final("idle")
                        return
                    raw_text = corrected
            if self.trim_rambling:
                trimmed = trim_rambling(raw_text)
                if trimmed != raw_text:
                    logger.info(f"[RAMBLE TRIM] '{raw_text}' -> '{trimmed}'")
                    raw_text = trimmed

            # Snippet expansion bypasses formatting entirely when the transcript matches a trigger.
            normalized = raw_text.strip().lower().rstrip(".!? ")
            if normalized in self.snippets:
                final_text = self.snippets[normalized]
                logger.info(f"Snippet matched '{normalized}' -> bypassing formatting.")
            elif self.use_direct_formatter or (self.mode == "polish" and is_short_and_clean(raw_text)):
                # Mode 1: instant, zero-LLM rule-based cleanup (see src/direct_formatter.py) -
                # also used for Polish when the utterance is short and has no filler/corrections,
                # where the LLM would only add latency.
                if not self.use_direct_formatter:
                    logger.info("[POLISH] Short, already-clean utterance - skipped the LLM.")
                profanity_mode = getattr(self.transformer, "profanity_filter", "allow")
                final_text = apply_profanity_filter(format_direct(raw_text), profanity_mode)
            elif self.system_prompt:
                final_text = self.transformer.transform_with_prompt(raw_text, self.system_prompt, label=self.mode)
            else:
                final_text = self.transformer.transform(raw_text, mode=self.mode)

            style = "default"
            if self.app_styles is not None and normalized not in self.snippets:
                app = foreground_app()
                style = style_for_app(app, self.app_styles)
                if style != "default":
                    final_text = apply_app_style(final_text, style)
                    logger.info(f"[APP STYLE] {app} -> '{style}' formatting.")
            # A long monologue becomes readable paragraphs - but only for plain Polish dictation into a
            # normal-sentence app: never a custom transform, snippet, chat app, editor or terminal (a
            # blank line pasted into a terminal could run a command).
            if (self.auto_paragraphs and style == "default" and self.mode == "polish"
                    and not self.system_prompt and normalized not in self.snippets):
                final_text = split_into_paragraphs(final_text)
            add_space = self.trailing_space and wants_trailing_space(style)
            had_target = has_text_target()  # asked before the paste; the paste still happens either way
            injected = self.injector.inject_text(with_trailing_space(final_text) if add_space else final_text)
            if injected and not had_target:
                self.paste_missed.emit(final_text)
            latency_ms = (time.perf_counter() - t0) * 1000

            # A Transforms-hub hotkey drove this recording (status_label set) vs
            # the plain dictation hotkey (active mode, no transform) - see
            # database.py's add_history() docstring for what each source means.
            history_source = "transform" if self.status_label else "dictation"
            history_id = None
            if self.db:
                try:
                    history_id = self.db.add_history(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        duration_seconds=self.record_duration_ms / 1000.0,
                        raw_transcript=raw_text,
                        polished_transcript=final_text,
                        mode_used=self.mode,
                        latency_ms=latency_ms,
                        source=history_source,
                    )
                except Exception as e:
                    logger.warning(f"Could not write history row: {e}")

            # A soft guardrail fallback (rare now - see sanity_check()'s narrowed
            # scope) still injected working, correctly-capitalized text, just not
            # LLM-polished - shown as a normal success, not a warning pill. The
            # warning pill is reserved for the except block below (an actual
            # unhandled failure), per the mission's own "don't flash an annoying
            # warning pill unless something actually broke" instruction.
            # [FALLBACK_DEBUG] in the log is where a soft fallback stays visible.
            self._emit_final("success" if injected else "idle")
            # The History refresh goes AFTER the pill is told it's done: it runs on the same (GUI) thread as the
            # pill, and used to make the pill sit on "processing" for as long as the list took to redraw.
            self.result_ready.emit({
                "raw_transcript": raw_text,
                "polished_transcript": final_text,
                "mode_used": self.mode,
                "latency_ms": latency_ms,
            })

            # After the paste, so it never adds latency to the dictation itself.
            if self.save_recording:
                try:
                    from src.test_recordings import save_recording
                    save_recording(self.audio_array, raw_text, final_text)
                except Exception as e:
                    logger.warning(f"Could not save test recording: {e}")
            if history_id and self.keep_recent > 0:
                try:
                    from src import recent_audio
                    recent_audio.save(history_id, self.audio_array, self.keep_recent)
                    self.recording_saved.emit(history_id)
                except Exception as e:
                    logger.warning(f"Could not keep the recording for re-transcribe: {e}")

        except Exception as e:
            logger.error(f"InferenceWorker pipeline error: {e}", exc_info=True)
            self.error.emit(str(e))
        finally:
            if not self._final_sent:
                self.state_changed.emit("idle")  # whatever happened above, never leave the pill busy


class RetranscribeWorker(QThread):
    """
    History -> "Re-transcribe": runs a kept recording through Whisper's careful
    method (Transcriber.transcribe(careful=True)), cleans it the way a normal
    dictation is cleaned, and overwrites that History row. Nothing is typed into
    any window - the result goes to the History row and the clipboard. Shares
    the engine's single-flight guard (both models are one-at-a-time).
    """

    result_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, history_id: int, audio_array, transcriber, transformer, db, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.history_id = history_id
        self.audio_array = audio_array
        self.transcriber = transcriber
        self.transformer = transformer
        self.db = db

    def run(self) -> None:
        try:
            raw_text = self.transcriber.transcribe(self.audio_array, careful=True)
            if not raw_text.strip():
                self.error.emit("The careful pass heard no speech in that recording.")
                return
            if is_short_and_clean(raw_text):
                mode = getattr(self.transformer, "profanity_filter", "allow")
                final_text = apply_profanity_filter(format_direct(raw_text), mode)
            else:
                final_text = self.transformer.transform(raw_text, mode="polish")
            self.db.update_history_text(self.history_id, raw_text, final_text)
            self.result_ready.emit({"id": self.history_id, "raw_transcript": raw_text, "polished_transcript": final_text})
        except Exception as e:
            logger.error(f"RetranscribeWorker error: {e}", exc_info=True)
            self.error.emit(str(e))


class SelectionPolishWorker(QThread):
    """
    "Polish Selected Text" pipeline, off the GUI thread: Ctrl+C the current
    selection -> SLM polish -> Ctrl+V it back in place -> SQLite history insert
    (mode 'text_polish'). Shares the engine's single-flight guard with
    InferenceWorker since both drive the same non-thread-safe Llama instance.
    """

    state_changed = Signal(str)   # 'selection_processing' | 'selection_success' | 'idle'
    result_ready = Signal(dict)
    error = Signal(str)

    def __init__(
        self, injector, transformer, db, mode: str = "polish",
        system_prompt: Optional[str] = None, parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.injector = injector
        self.transformer = transformer
        self.db = db
        self.mode = mode
        self.system_prompt = system_prompt  # set -> a specific Transforms-hub entry drove this, not config.yaml's mode

    def run(self) -> None:
        try:
            self.state_changed.emit("selection_processing")
            t0 = time.perf_counter()

            selected_text = self.injector.copy_selection()
            if not selected_text or len(selected_text.strip()) < 2:
                logger.info("Polish Selected Text: nothing usable was selected - dismissing.")
                self.state_changed.emit("idle")
                return

            if self.system_prompt:
                polished_text = self.transformer.transform_with_prompt(selected_text, self.system_prompt, label=self.mode)
            else:
                polished_text = self.transformer.transform(selected_text, mode=self.mode)
            injected = self.injector.inject_text(polished_text)
            latency_ms = (time.perf_counter() - t0) * 1000

            if self.db:
                try:
                    self.db.add_history(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        duration_seconds=0.0,
                        raw_transcript=selected_text,
                        polished_transcript=polished_text,
                        mode_used="text_polish",
                        latency_ms=latency_ms,
                        source="text_polish",
                    )
                except Exception as e:
                    logger.warning(f"Could not write history row for selection polish: {e}")

            self.result_ready.emit({
                "raw_transcript": selected_text,
                "polished_transcript": polished_text,
                "mode_used": "text_polish",
                "latency_ms": latency_ms,
            })
            # See InferenceWorker.run() for why a soft guardrail fallback shows
            # a normal success state instead of a warning pill.
            self.state_changed.emit("selection_success" if injected else "idle")

        except Exception as e:
            logger.error(f"SelectionPolishWorker pipeline error: {e}", exc_info=True)
            self.error.emit(str(e))
            self.state_changed.emit("idle")


class WritingStylesWorker(QThread):
    """
    Alt+V "Writing Styles" pipeline: Ctrl+C the current selection, then run
    it through every style in src/writing_styles.WRITING_STYLES as its own
    separate, independent LLM call - emitting style_ready() as each one
    finishes so the HUD can populate cards progressively instead of blocking
    on all five. Injection/history-recording happens on style SELECTION
    (see engine.py), not here - this worker's only job is capture + generate.
    """

    no_selection = Signal()            # nothing was highlighted - show the pill toast, no HUD
    selection_captured = Signal(str)   # HUD should appear now, cards start in a loading state
    style_ready = Signal(str, str)     # (style_id, styled_text)
    all_styles_done = Signal()
    error = Signal(str)

    def __init__(self, injector, transformer, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.injector = injector
        self.transformer = transformer
        self._cancelled = False

    def cancel(self) -> None:
        """Called when the user dismisses the HUD before generation finishes -
        the in-flight LLM call still completes (llama.cpp has no cooperative
        cancel), but no further styles are started afterward."""
        self._cancelled = True

    def run(self) -> None:
        from src.writing_styles import WRITING_STYLES

        try:
            selected_text = self.injector.copy_selection()
            if not selected_text or len(selected_text.strip()) < 2:
                logger.info("Writing Styles: nothing usable was selected - dismissing.")
                self.no_selection.emit()
                return

            self.selection_captured.emit(selected_text)

            for style in WRITING_STYLES:
                if self._cancelled:
                    return
                styled_text = self.transformer.transform_with_prompt(
                    selected_text, style.system_prompt, label=f"style_{style.id}"
                )
                if self._cancelled:
                    return
                self.style_ready.emit(style.id, styled_text)

            if not self._cancelled:
                self.all_styles_done.emit()

        except Exception as e:
            logger.error(f"WritingStylesWorker pipeline error: {e}", exc_info=True)
            self.error.emit(str(e))
