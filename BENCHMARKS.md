# Benchmarks

Measured directly on the dev machine (RTX-class NVIDIA GPU, CUDA) via
`tests/benchmark_models.py`, not estimated. Whisper `large-v3-turbo`
(int8_float16) loaded throughout, matching the real app's combined VRAM
footprint. Last measured 2026-09-09 against `llama-cpp-python==0.3.26`.
The VRAM column is whole-GPU memory in use (pynvml), so it also includes
Windows and any other app on the GPU, not just Wisperno.

| Preset | VRAM | Process RAM | Avg decode speed | 100-word latency | Fidelity |
|---|---|---|---|---|---|
| **Turbo Flagship (default)** | 3491 MB | 2311 MB | **113.8 tok/s** | 0.82s | 97.6% |
| Standard (Q4_K_M, 3B) | 3691 MB | 2559 MB | 91.7 tok/s | 1.04s | 98.8% |

"Fidelity" on Turbo is measured on raw model output and bypasses the
app's own guardrail (`sanity_check()`) by design - real usage always goes
through it, which is why the conversational-trap suite (adversarial prompts
designed to make the model answer back instead of cleaning dictation) still
passes 100% on every tier above despite the lower raw-fidelity score on the
smaller models.

## Wisperno Pro vs Wisperno, same GPU (measured 2026-09-25)

RTX 4070 Laptop (8 GB), driver 595.79, torch 2.6.0+cu124,
`llama-cpp-python==0.3.26`. The same harness (`tests/benchmark_models.py`
from this branch) run back to back against this branch's code and the
original Wisperno's `main`, same model files:

| Preset | Build | Avg decode speed | 100-word latency | Fidelity | Traps |
|---|---|---|---|---|---|
| Turbo Flagship | Wisperno Pro | 110.2 tok/s | 0.85s | 97.6% | pass |
| Turbo Flagship | Wisperno | 112.2 tok/s | 0.82s | 97.6% | pass |
| Standard | Wisperno Pro | 88.0 tok/s | 1.05s | 99.2% | pass |
| Standard | Wisperno | 89.1 tok/s | 1.07s | 98.8% | pass |

Decode speed is the same within run-to-run noise: Pro didn't change the
model, quantization or inference engine, so it isn't faster. Its changes are
in what happens around the model - list formatting, cleanup quality, the
dictionary and per-app styles (see the sections below). VRAM isn't in this
table: pynvml reads whole-GPU usage, and other apps holding models on the GPU
during this run made it 6.8-7.0 GB for both builds, not comparable with the
3.5 GB above.

## Why these numbers moved since the last release

This build's `llama-cpp-python` inference engine was upgraded twice this
session, `0.2.90` -> `0.3.4` -> `0.3.26` (see `handoff.md` in the source repo,
Rounds 39-40, for the full investigation - version-bisected against a range
of releases that crash on this hardware to find the newest one that doesn't).
Net effect versus the previous release's published numbers: **every preset
decodes roughly 20-30% faster** with identical output fidelity and unchanged
VRAM - a pure engine-level win, not a model or quantization change. Cold-start
latency (time to first token after a mode switch) also improved separately
via the `0.2.90` -> `0.3.4` half of that upgrade (~2x faster, not reflected in
the steady-state numbers above).

## Reproducing this benchmark

From a full source checkout (not this portable download - see INSTALL.md's
"Building from source" section for setup):

```
python tests/benchmark_models.py
```

Requires both preset model files present in `models/` - see
`models/MODELS.md` for where to get each one.

The Flagship (Qwen2.5-3B Q8_0, ~5.1GB), Eco (Qwen2.5-3B IQ4_XS) and Gemma 2
2B (Beta) presets were retired: Flagship went over the 4GB target for no
fidelity gain over Standard, Eco matched Standard with no advantage, and
Gemma was slower than Turbo. See `src/presets.py`.

## Accuracy and cleanup quality (measured 2026-09-25)

Measured with the real models on CPU (4 cores; relative numbers - absolute
times on an RTX GPU are roughly 10x lower) using the harness in this repo:

- `scripts/make_synthetic_clips.py` renders `tests/fixtures/speech_cases.json`
  (24 dictation-style clips: filler, "wait no" corrections, questions, lists
  said in points, jargon, a long ramble, quiet speech, silence) with Piper
  voices and light background noise.
- `scripts/eval_dictation.py` runs clips through the real pipeline, or text
  cases (`tests/fixtures/llm_cases.json`: 30 transcripts incl. questions,
  commands and prompt-injection that must be cleaned, never obeyed).

**Whisper settings** (large-v3-turbo, 24 clips): word error rate 1.79% for
int8 and float32, beam 1 and beam 5 alike - neither precision nor beam size
changed a single word, while float32 doubled the time. The shipped settings
(int8_float16, beam 1) stay. The one real miss was "poll request" for "pull
request" (a dictionary job).

**LLM cleanup** (30 text cases, share of output matching the ideal text):

| | Before (prompt as shipped) | After |
|---|---|---|
| Instant formatter only | 94.1% | 94.7% (+ 44/44 formatting cases) |
| Turbo Flagship | 96.7% | **98.3%** |
| Standard | 95.3% | **98.6%** |
| Questions answered instead of kept | 0 | 0 |
| Dictated commands obeyed ("translate this...", "tell me a joke") | 2 slipped through on Standard | 0 (caught, instant formatter used) |

What moved it: the transcript is fenced off as data rather than sent as a
chat message; um/uh are removed and spoken lists laid out before the model
sees the text; "scratch that" is applied in code; and three new guardrails
(content replaced, dictated sentence dropped, list flattened) fall back to
the instant formatter. End to end on the audio clips, Turbo scores 97%
against 96% for the instant formatter alone; short, already-clean
dictations skip the LLM entirely.

## Smart formatting (measured 2026-09-25, RTX 4070 Laptop, Turbo)

Wispr Flow-style formatting added to the deterministic formatter, so both
the instant path and the LLM path get it:

- Lists spoken without cue words, announced by their intro ("I need to do
  three things today, call the bank, finish the report and book the
  flights") become an intro line plus "•" bullets. The count must match the
  items; an ordinary series ("bought milk, eggs and bread") stays prose.
- Restarted phrases ("we should we should", "can you, can you") kept once.
- A sentence Whisper left unpunctuated gets "?" when it's a question.
- New guardrail: Turbo dropped "I think" / "I believe" / "I guess" on 3 of 8
  hedged sentences, turning an opinion into a statement of fact; that output
  now falls back to the instant formatter. 0 of 8 after.

| | Before | After |
|---|---|---|
| `llm_cases.json`, LLM path exact | 23/30 | 24/30 |
| `llm_cases.json`, instant formatter exact | 19/30 | 20/30 |
| `formatting_cases.json` (68, 17 new), instant exact | - | 68/68 |
| Questions answered / commands obeyed | 0 / 0 | 0 / 0 |

## Custom dictionary (measured 2026-09-25)

16 clips full of names and jargon (`tests/fixtures/vocab_cases.json`: Supabase,
Vercel, Nguyen, Siobhan, kubectl, OAuth, ...), real Whisper large-v3-turbo,
run through the app's own transcriber with and without those 16 words in
the dictionary:

| | No dictionary | With dictionary |
|---|---|---|
| Word error rate, jargon clips | 7.19% | **2.16%** |
| Terms spelled exactly right | 13/22 | **21/22** (only "kubectl" missed) |
| Word error rate, the 24 general clips | 1.79% | 1.19% (no harm; "pull request" fixed) |

How: dictionary words go into Whisper's prompt first and spill into its
separate hotwords slot when the prompt is full (together roughly 60 words;
newest first beyond that - an 86-word dictionary crammed into the prompt
alone fell to 16/22), and a sound-alike pass snaps near-misses Whisper
writes as names ("Superbase" -> Supabase, "Versil" -> Vercel, "NuYen" ->
Nguyen) - zero changes across ~200 unrelated transcripts.
