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
