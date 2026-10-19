# Wisperno Pro: advanced details

This page is for people who want to know how Wisperno Pro works, how fast it is, and how to build it. You never need any of it to use the app. Back to the [README](README.md).

## How it works

1. **Listen.** The microphone is opened only while a dictation runs.
2. **Transcribe.** `faster-whisper large-v3-turbo` (CTranslate2, CUDA, int8/fp16) turns speech into text on your GPU.
3. **Clean up.** Either an instant rule-based formatter (no AI, well under a second) or a small local language model removes fillers, resolves self-corrections and formats lists.
4. **Type.** The result is pasted into the active app with that app's style (chat apps drop the final period, code editors skip the trailing space). After the models are on disk the app makes **zero** network calls.

## Writing features in detail

- **Two cleanup engines, chosen per trigger.** Instant *Direct Dictation* (rules only) and *Smart Cleanup* (the local language model: grammar, fillers, "no wait" corrections, lists). Short, already-clean utterances skip the AI so they stay instant.
- **Tap to toggle, hold to talk, or the pill**, plus auto-stop after a silence you choose (default 5 seconds).
- **Per-app styles** for chat apps, editors and terminals, extendable with your own apps.
- **Paragraphs from pauses and from topics.** A pause of about 1.3 s starts a new paragraph. A minute of unbroken speech is split where the topic changes (a transition like "Also," or "Finally," helps, as does a change of vocabulary). No words are changed or dropped, and it never happens in chat apps, editors or terminals.
- **Spoken domains and lists.** "visit dev dot to slash janedoe" types `dev.to/janedoe`. "Question one ... Question two ..." (or "first ... second ...", even across pauses) becomes a numbered list, with `?` on question items.
- **Cut spoken padding.** Drops empty phrases like "and yeah", "so yeah" and ", I guess," while never touching answers or opinions ("yeah, I can do that"). Skipped automatically if it would delete more than 40% of the words. The raw transcript stays in History.
- **Profanity filter**, three modes (Settings > Writing): *Allow* (verbatim, the default), *Censor* (`f***`), *Remove*. It matches whole words (so `class`, `assess` and `Scunthorpe` are safe), covers inflections and compounds, and restores words the speech model itself masked as `f**king`, `f#cking` or `f-ing`. In *Allow* mode a safety net also catches the cleanup AI quietly dropping a swear word. Tone transforms always remove swear words.
- **Retractions ("scratch that")**, opt-in. When a sentence *starts* with a retraction phrase (scratch that, no wait, wait no, ignore that, delete that, start over, and "no, no" / "actually no" / "never mind" only when punctuated), the sentence before it is dropped. Rule-based on purpose: a small AI deciding what you "meant" can silently delete real content.
- **When a dictation comes out wrong.** The last 3 recordings are kept (0, 3, 5 or 10 in Settings; older ones are deleted automatically; audio never leaves your PC). *Re-transcribe* in History re-runs one with a slower, more careful method (no voice-activity trimming, wider search, retries at higher temperature) and puts the result on your clipboard. The raw transcript is always available under *Show Raw Transcript*.
- **Transforms.** Polish, Prompt Engineer, Detailed Code Fix Prompt, Grammar Correct, AI Relay and four tones (Polite, Professional, Casual, Concise), plus your own prompts. Tone rewrites lay out any spoken list first, rewrite it one line at a time, and re-ask once if the model returns the text unchanged. The small local model sometimes rewords a *statement* as a request in Polite/Professional; the slower 3B preset follows tone instructions better.
- **Start/stop sounds** (Settings > Sounds): seven synthesized presets, or your own `.wav` (up to 3 seconds and 1 MB, at most 12). Windows keeps a per-program volume and can remember Wisperno at 0; the app restores its own volume at start-up and before each sound.
- **Keyboard and clipboard handling.** Text is injected with a scan-code `Ctrl+V` after the clipboard is written and verified, with fallbacks, and your previous clipboard can be restored.

## Measured performance

Measured on the target hardware (RTX 4070 Laptop GPU, 8 GB) with `tests/benchmark_models.py` and `tests/test_startup_time.py`, which ship in this repo so you can reproduce it. Full write-up: [BENCHMARKS.md](BENCHMARKS.md).

**The two cleanup models:**

| Preset | Model | VRAM | System RAM | Decode speed | 100-word latency | Fidelity |
|---|---|---|---|---|---|---|
| **Turbo Flagship** (default) | Qwen2.5-1.5B-Instruct Q8_0 | 3,491 MB | 2,311 MB | **113.8 tok/s** | 0.82 s | 97.6% |
| Standard | Llama-3.2-3B | 3,691 MB | 2,559 MB | 91.7 tok/s | 1.04 s | 98.8% |

**The speech model:** `faster-whisper large-v3-turbo` (int8_float16) loads in about 3-5 s on a cold start. A real 9.75-second spoken sample was transcribed in 0.945 s (real-time factor 0.097, about 10x faster than speaking), word for word. A typical end-of-speech-to-typed-text time on the dashboard is 1-3 seconds including cleanup.

The VRAM column is whole-GPU use during the benchmark (Whisper + language model + Windows and any other app on the GPU). System Usage shows the app's own share. Both presets stay under 4 GB of GPU memory.

**About the memory numbers in the app.** *Graphics memory* matches Task Manager's "Dedicated GPU memory". *Memory (RAM)* shows the app's **private** memory (what Task Manager shows), typically under 1 GB; Windows can also list about 3 GB more of memory-mapped model files in the process's working set, which is shared, file-backed and reclaimable, and is not counted.

## How it compares

| | Cloud dictation apps | Local Whisper `large-v3` | Wisperno Pro |
|---|---|---|---|
| Where audio is processed | The provider's servers | On your PC | On your PC |
| Works with no internet | No | Yes | Yes |
| Speech model | A cloud model | Full `large-v3` (about 10 GB of VRAM to run comfortably) | `large-v3-turbo`, about 7x faster decoding, 4 GB+ is enough |
| Cleanup | A cloud LLM | None | A local 1.5B-3B model, or instant rules |
| Per-app styles, transforms, dictionary, snippets | Varies | None | Built in |

## Engineering notes

- **Slim installer.** The app no longer bundles PyTorch. It ships only the three NVIDIA CUDA libraries it actually loads (`cublas64_12`, `cublasLt64_12`, `cudart64_12`), which took the installer from 7.9 GB to 4.9 GB. A transcript of the same audio was compared between the full and the slim library set and was identical, including word timings and confidences.
- **Installer.** Inno Setup with disk spanning (one small `.exe` plus three `.bin` parts), an in-place upgrade that removes the old PyTorch folders, and a per-user install under `%LOCALAPPDATA%`. Builds keep only the newest two versions in `Final App`.
- **Resilient pill.** Every dictation ends in a final state even on errors, dictations finished while busy are queued instead of dropped, and a 90-second watchdog resets a pill that ever sticks.
- **Paste check.** After a dictation, Windows UI Automation tells whether the focused element can take text. It leans toward "yes" and raises the card only for elements that clearly cannot (buttons, lists, a page with nothing focused). `WispernoPro.exe --probe-focus` logs what it sees.

## Build from source

```
git clone https://github.com/<your-account>/wisperno-pro.git
cd wisperno-pro
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python download_models.py
.venv\Scripts\python main.py
```

`requirements.txt` pins `torch` 2.6.0 from the CUDA 12.4 index only so its CUDA DLLs can be found and copied into the installer; the running app never imports PyTorch.

```
python build_exe.py                         # the app, into "Final App\v<version>"
python scripts\build_installer.py           # the installer (also prunes old versions)
python tests\run_all.py                     # every test, against a throw-away %APPDATA%
python scripts\capture_readme_screenshots.py   # regenerate the screenshots above (made-up demo data only)
```

Always run the full test suite through `tests/run_all.py`: several tests open the real history database, and it points them at a temporary folder so your data is never touched.

## Release history

| Version | Highlights |
|

## Credits and third-party models

Speech recognition: [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) with the `large-v3-turbo` weights. Cleanup: `Qwen2.5-1.5B-Instruct` (Apache-2.0) and `Llama-3.2-3B`, run through `llama-cpp-python`. UI: PySide6 (Qt). Fonts: Inter Tight and JetBrains Mono (bundled). See [LICENSE](LICENSE); the model licenses apply to the model files.

## License

Wisperno's own code is [MIT](LICENSE). Third-party models and libraries keep their own licenses.
