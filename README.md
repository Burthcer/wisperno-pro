<p align="center"><img src="assets/icon.png" alt="Wisperno Pro" width="120"></p>

<h1 align="center">Wisperno Pro</h1>

<p align="center"><b>Talk. It types. Nothing ever leaves your PC.</b><br>
Private, offline dictation for Windows that runs on your own graphics card.</p>

<p align="center">
  <img alt="Windows 11" src="https://img.shields.io/badge/Windows-11-0078D6?logo=windows&logoColor=white">
  <img alt="NVIDIA GPU" src="https://img.shields.io/badge/NVIDIA-GPU%20accelerated-76B900?logo=nvidia&logoColor=white">
  <img alt="Offline" src="https://img.shields.io/badge/internet-not%20needed-success">
  <img alt="Network calls" src="https://img.shields.io/badge/network%20calls-zero-success">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-blue">
</p>

<p align="center"><img src="docs/images/hero.png" alt="Wisperno Pro: the dashboard, the floating pill and the paste card" width="900"></p>

---

## Why you will like it

<table>
<tr>
<td width="33%" valign="top"><h3>Private by design</h3>Your voice and your words stay on your computer. There is no account, no cloud and no tracking, and it works with the internet unplugged.</td>
<td width="33%" valign="top"><h3>Fast</h3>Speak, press a key, and clean text appears in the app you are using, usually in about a second. It runs on your graphics card, not a server.</td>
<td width="33%" valign="top"><h3>Clean writing, not a raw transcript</h3>"Um"s, repeats and "no wait" corrections are tidied up, lists are formatted, long speech is split into paragraphs, and your names and jargon are spelled right.</td>
</tr>
</table>

## How it feels to use

1. **Press the key** (or click the little pill) and start talking. A live waveform shows it is listening.
2. **Press again** (or click the tick). The text is cleaned up and typed into whatever you were using.
3. **Need something rewritten?** Select any text, click the pill's **wand**, and it is rewritten in place (more polite, shorter, as a prompt...).

That is all there is to it. Everything below is optional.

---

## A tour of the app

<table>
<tr>
<td width="50%"><a href="docs/images/history.png"><img src="docs/images/history.png" alt="History"></a><br><b>History</b><br>Every dictation, searchable, with one-click copy, pin, favorite, re-transcribe and delete.</td>
<td width="50%"><a href="docs/images/transforms.png"><img src="docs/images/transforms.png" alt="Transforms"></a><br><b>Transforms</b><br>Rewrite text with one hotkey or one click: Polish, Prompt Engineer, Grammar, and the tones Polite, Professional, Casual and Concise.</td>
</tr>
<tr>
<td width="50%"><a href="docs/images/transforms-editor.png"><img src="docs/images/transforms-editor.png" alt="Transform editor"></a><br><b>Make your own transform</b><br>Write a prompt, set a hotkey, and try it on sample text right inside the editor.</td>
<td width="50%"><a href="docs/images/dictionary.png"><img src="docs/images/dictionary.png" alt="Dictionary"></a><br><b>Dictionary</b><br>Teach it your names, products and jargon so they are spelled right every time.</td>
</tr>
<tr>
<td width="50%"><a href="docs/images/snippets.png"><img src="docs/images/snippets.png" alt="Snippets"></a><br><b>Snippets</b><br>Say a short phrase and a longer block of text is typed for you (an email, a sign-off, a standup note).</td>
<td width="50%"><a href="docs/images/system-usage.png"><img src="docs/images/system-usage.png" alt="System Usage"></a><br><b>System Usage</b><br>See what the app is using on your graphics card, memory and disk, and what you can safely delete.</td>
</tr>
</table>

### The floating pill

A tiny capsule that floats above your other windows and never steals focus from what you are typing into.

<p align="center"><img src="docs/images/pill-states.png" alt="The pill in every state" width="760"></p>

| State | What you see |
|---|---|
| Starting | Orange dots sweep while the AI loads (a few seconds) |
| Idle | A thin strip that opens up when your mouse is near |
| Listening | `x` on the left, a live waveform of your voice, a tick on the right |
| Working | Three pulsing dots (and the name of a transform if one is running) |
| Done | A green tick |

**Hover it** and it opens into a wide microphone button and a wand. The wand transforms the text you have selected; the small arrow beside it chooses which transform:

<p align="center"><img src="docs/images/pill-hover.png" alt="The pill resting, hovered, and with the transform arrow" width="560"></p>
<p align="center"><img src="docs/images/pill-menu.png" alt="The transform menu" width="380"></p>

**Move it anywhere** by dragging, or snap it to one of six spots from Settings or its right-click menu. It remembers where you put it, and if that screen is ever unplugged it comes back to the default spot.

<p align="center"><img src="docs/images/pill-positions.png" alt="The six pill positions" width="520"></p>

**When nothing could be pasted** (the desktop or a button had focus), a card appears above the pill with your text, so it is never lost. Press **Copy text**, scroll long text with the mouse wheel, or dismiss it. It clears itself when you start the next dictation, and it never appears over a chat box or editor.

<p align="center"><img src="docs/images/paste-card.png" alt="The paste card before and after copying" width="680"></p>

### Live Transcription

For meetings, lectures and calls: a separate floating window that transcribes continuously while you pause, resume, save or discard (default `Ctrl+Shift+L`).

<p align="center"><img src="docs/images/live-transcription.png" alt="Live Transcription window" width="420"></p>

---

## Everyday shortcuts

| Keys | What they do |
|---|---|
| `Ctrl` + `Alt` | Tap to start dictating, tap again to finish |
| `Ctrl` + `Space` | Hold to talk (off by default; turn it on in Settings) |
| `Ctrl` + `Shift` + `L` | Start or stop Live Transcription |
| `Alt` + `C` | Polish the selected text (the default transform) |
| `Alt` + `X` / `Alt` + `D` | Prompt Engineer / Detailed Code Fix Prompt |
| `Alt` + `G` / `Alt` + `R` | Grammar Correct / AI Relay |
| `Ctrl` + `Shift` + `B` | Cycle the active mode |
| `Ctrl` + `,` | Open the dashboard |

Every shortcut can be changed in Settings. A transform's hotkey also works on the text you have selected if you do not speak.

---

## Settings, tab by tab

Settings is split into nine clearly named tabs. Everything saves the moment you change it, except **AI Engine**, which has an *Apply changes* button because it reloads the models. A ticked box is orange with a tick; an empty grey outline means off.

<details>
<summary><b>Microphone</b> - pick the input device, test it with a live level meter, auto-stop after a pause</summary>
<p align="center"><img src="docs/images/settings-microphone.png" alt="Microphone settings"></p>
</details>

<details>
<summary><b>Shortcuts</b> - choose your tap-to-talk and hold-to-talk keys</summary>
<p align="center"><img src="docs/images/settings-shortcuts.png" alt="Shortcut settings"></p>
</details>

<details>
<summary><b>Writing</b> - smart cleanup, paragraphs, profanity filter, "scratch that", cutting spoken padding</summary>
<p align="center"><img src="docs/images/settings-writing.png" alt="Writing settings"></p>
</details>

<details>
<summary><b>Pill</b> - show or hide it, what a click does, its shape and position</summary>
<p align="center"><img src="docs/images/settings-pill.png" alt="Pill settings"></p>
</details>

<details>
<summary><b>Sounds</b> - seven built-in start/stop sounds with Preview, or drag in your own .wav</summary>
<p align="center"><img src="docs/images/settings-sounds.png" alt="Sound settings"></p>
</details>

<details>
<summary><b>App Styles</b> - chat apps drop the final period, code editors skip the trailing space</summary>
<p align="center"><img src="docs/images/settings-app-styles.png" alt="App style settings"></p>
</details>

<details>
<summary><b>AI Engine</b> - choose the speed/quality preset and the speech model</summary>
<p align="center"><img src="docs/images/settings-ai-engine.png" alt="AI engine settings"></p>
</details>

<details>
<summary><b>Privacy</b> - how many recent recordings to keep, history auto-delete, storage</summary>
<p align="center"><img src="docs/images/settings-privacy.png" alt="Privacy settings"></p>
</details>

<details>
<summary><b>Startup</b> - start with Windows, and what the window's close button does</summary>
<p align="center"><img src="docs/images/settings-startup.png" alt="Startup settings"></p>
</details>

By default, closing the window **quits** the app. Tick *Keep running in the tray when I close the window* if you want it to hide instead and keep dictation working in the background.

---

## Install

**1. Download** every `WispernoPro-Setup-vX.Y.Z` file from the release into **one folder**: the small `.exe` and the three numbered `.bin` parts (about 4.9 GB in total).

**2. Run the `.exe`.** It upgrades an existing Wisperno Pro in place and keeps your settings, history and dictionary. It needs about 5 GB of free disk space. The very first launch can take about a minute while Windows scans the new files; after that it starts in a few seconds.

**3. Dictate.** Look for the pill, press `Ctrl` + `Alt`, and talk.

**You need:** Windows 11 (64-bit), an NVIDIA graphics card with 4 GB or more of memory, and about 5 GB of free disk space. (With less than 4 GB the app falls back to a slower processor-only mode.) More detail: [SYSTEM_REQUIREMENTS.md](SYSTEM_REQUIREMENTS.md) and [INSTALL.md](INSTALL.md).

Wisperno Pro is a separate app from the original Wisperno: its own installer identity and its own data folder, so the two can be installed side by side without touching each other.

## What is new

| Version | Highlights |
|---|---|
| **1.6.x** | The pill's wand transforms **selected text** (the arrow chooses the transform); dictation is no longer rewritten unless you turn that on. The paste card scrolls and clears itself. Closing the window now quits by default. The app's memory figure now shows the app's *own* memory, as Task Manager counts it. A refreshed README with screenshots of every feature. |
| **1.5.x** | Start/stop **sounds fixed** (Windows can mute a program's volume silently). Four tone transforms. Icon buttons with a "Copied!" confirmation. The "no text field" paste card with accurate detection in browsers. Launching the app again opens its dashboard. Swear words the speech model hides as `f-ing` are restored. A graphics-memory gauge that never reads zero. |
| **1.4.0** | Bigger pill buttons, "Cut spoken padding" setting. |
| **1.3.0** | Pill transform menu, sound picker, automatic paragraphs by topic, deletable disk space, installer shrunk from 7.9 GB to 4.9 GB. |
| 1.1.0 - 1.0.0 | Dashboard polish, System Usage, new logo, draggable pill with live waveform, Re-transcribe. |

---

<br>

# Advanced details

Everything below is for people who want to know how it works, how fast it is, and how to build it. You never need any of it to use the app.

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

## Credits and third-party models

Speech recognition: [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) with the `large-v3-turbo` weights. Cleanup: `Qwen2.5-1.5B-Instruct` (Apache-2.0) and `Llama-3.2-3B`, run through `llama-cpp-python`. UI: PySide6 (Qt). Fonts: Inter Tight and JetBrains Mono (bundled). See [LICENSE](LICENSE); the model licenses apply to the model files.

## License

Wisperno's own code is [MIT](LICENSE). Third-party models and libraries keep their own licenses.
