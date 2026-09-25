"""
Render tests/fixtures/speech_cases.json into a synthetic test set for
scripts/eval_dictation.py, using Piper (offline neural text-to-speech):
for each case, <id>.wav (16kHz mono) + <id>.txt (what was said, for WER) +
<id>.expected.txt (the ideal final text, for formatting).

Synthetic voices are cleaner than a real laptop mic, so a light noise bed is
mixed in (about 25 dB below the speech) - WER here is a relative measure for
comparing settings, not a prediction of accuracy on your own voice.

  pip install piper-tts
  python scripts/make_synthetic_clips.py --voices DIR --out DIR

DIR for --voices must hold Piper voice files (e.g. en_US-lessac-medium.onnx
+ .onnx.json from huggingface.co/rhasspy/piper-voices).
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import signal

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.test_recordings import SAMPLE_RATE, write_wav  # noqa: E402

CASES_PATH = BASE_DIR / "tests" / "fixtures" / "speech_cases.json"
NOISE_BELOW_SPEECH_DB = 25.0
LEAD_IN_SEC, TAIL_SEC = 0.35, 0.4  # a real press/release has a little air around the words
SILENCE_NOISE_RMS = 0.002          # a quiet room, for the "nothing was said" clip


def _find_voice(voices_dir: Path, name: str) -> Path:
    matches = sorted(voices_dir.rglob(f"*-{name}-*.onnx"))
    if not matches:
        sys.exit(f"No Piper voice matching '{name}' under {voices_dir}")
    return matches[0]


def _synthesize(voice, text: str) -> np.ndarray:
    chunks = [c.audio_float_array for c in voice.synthesize(text)]
    audio = np.concatenate(chunks).astype(np.float32)
    rate = voice.config.sample_rate
    if rate != SAMPLE_RATE:
        gcd = np.gcd(rate, SAMPLE_RATE)
        audio = signal.resample_poly(audio, SAMPLE_RATE // gcd, rate // gcd).astype(np.float32)
    return audio


def _pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400]
    pink = signal.lfilter(b, a, white)
    return (pink / (np.sqrt(np.mean(pink ** 2)) + 1e-12)).astype(np.float32)


def _spoken_reference(text: str) -> str:
    """What was said, as words (WER ignores case/punctuation anyway)."""
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voices", required=True, help="folder with Piper .onnx voices")
    parser.add_argument("--out", required=True, help="output folder for the clips")
    args = parser.parse_args()

    from piper import PiperVoice

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    voices = {}
    rng = np.random.default_rng(1234)
    for case in cases:
        if case.get("voice"):
            if case["voice"] not in voices:
                voices[case["voice"]] = PiperVoice.load(str(_find_voice(Path(args.voices), case["voice"])))
            speech = _synthesize(voices[case["voice"]], case["say"])
            speech *= 10 ** (case.get("gain_db", 0) / 20)
            pad = lambda sec: np.zeros(int(sec * SAMPLE_RATE), dtype=np.float32)  # noqa: E731
            audio = np.concatenate([pad(LEAD_IN_SEC), speech, pad(TAIL_SEC)])
            speech_rms = float(np.sqrt(np.mean(speech ** 2)))
            noise_rms = speech_rms * 10 ** (-NOISE_BELOW_SPEECH_DB / 20)
        else:
            audio = np.zeros(int(case.get("silence_sec", 2.0) * SAMPLE_RATE), dtype=np.float32)
            noise_rms = SILENCE_NOISE_RMS
        audio = audio + noise_rms * _pink_noise(len(audio), rng)
        write_wav(out / f"{case['id']}.wav", audio)
        (out / f"{case['id']}.txt").write_text(_spoken_reference(case["say"]), encoding="utf-8")
        (out / f"{case['id']}.expected.txt").write_text(case["expected"], encoding="utf-8")
        print(f"{case['id']}: {len(audio) / SAMPLE_RATE:.1f}s")
    print(f"\n{len(cases)} clips written to {out}")


if __name__ == "__main__":
    main()
