"""
Measure Wisperno on YOUR voice: accuracy (word error rate) and speed per
pipeline stage, on recordings saved with Settings -> General -> "Save
Recordings for Testing". Run it before and after a change to see whether the
change actually helped.

Setting up a test set (once):
  1. Turn on "Save Recordings for Testing", dictate ~20 things you normally
     say (short replies, a long ramble, jargon/names, a question, a "wait no"
     correction, a list said in points), then turn it back off.
  2. Click "Open Recordings Folder". For each clip, copy <stamp>.heard.txt to
     <stamp>.txt and fix it so it matches exactly what you SAID (words only -
     casing/punctuation don't count). Delete clips you don't want to keep.
  3. Optional: add <stamp>.expected.txt with the ideal final text (the way
     Wispr Flow would format it, e.g. as a numbered list). That scores the
     formatting, not just the words.

Usage (from the project root, with the app closed so the GPU is free):
  python scripts/eval_dictation.py                    # Whisper + instant formatter
  python scripts/eval_dictation.py --llm              # also the LLM polish (active preset)
  python scripts/eval_dictation.py --save baseline    # keep this run's results
  python scripts/eval_dictation.py --compare baseline # compare against a kept run
  python scripts/eval_dictation.py --text-cases       # formatting-only cases, no audio/GPU needed
  python scripts/eval_dictation.py --folder D:\\clips  # a different recordings folder
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.direct_formatter import format_direct  # noqa: E402
from src.eval_metrics import exact_match, normalize_words, text_similarity, word_error_rate  # noqa: E402

TEXT_CASES_PATH = BASE_DIR / "tests" / "fixtures" / "formatting_cases.json"


def _load_transformer(config):
    from src.transformer import Transformer

    transformer = Transformer(config=config.llm, prompts=config.prompts, profanity_filter=config.profanity_filter)
    if transformer.llm is None:
        sys.exit(f"LLM model not found ({config.llm.model_path}) - run without --llm or download it first.")
    return transformer


def _run_llm(transformer, text: str, mode: str):
    t0 = time.perf_counter()
    out = transformer.transform(text, mode=mode)
    return out, (time.perf_counter() - t0) * 1000


def run_text_cases(args, config) -> None:
    cases = json.loads(TEXT_CASES_PATH.read_text(encoding="utf-8"))
    transformer = _load_transformer(config) if args.llm else None
    direct_pass = llm_pass = 0
    for case in cases:
        direct = format_direct(case["raw"])
        ok = exact_match(case["expected"], direct)
        direct_pass += ok
        print(f"[{'PASS' if ok else 'FAIL'}] direct  {case['name']}")
        if not ok:
            print(f"    expected: {case['expected']!r}\n    got:      {direct!r}")
        if transformer:
            polished, ms = _run_llm(transformer, case["raw"], "polish")
            ok = exact_match(case["expected"], polished)
            llm_pass += ok
            print(f"[{'PASS' if ok else 'FAIL'}] llm     {case['name']} ({ms:.0f}ms, "
                  f"similarity {text_similarity(case['expected'], polished):.0%})")
            if not ok:
                print(f"    got:      {polished!r}")
    print(f"\nInstant formatter: {direct_pass}/{len(cases)} exact")
    if transformer:
        print(f"LLM polish ({config.model_preset}): {llm_pass}/{len(cases)} exact")


def _results_dir(folder: Path) -> Path:
    path = folder / "results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_recordings(args, config) -> dict:
    from src.config import get_db_path
    from src.database import WispernoDB
    from src.swear_filter import apply_profanity_filter
    from src.test_recordings import SAMPLE_RATE, read_wav, recordings_dir
    from src.transcriber import Transcriber
    from src.vocabulary import Vocabulary

    folder = Path(args.folder) if args.folder else recordings_dir()
    clips = sorted(p for p in folder.glob("*.wav"))
    scored = [p for p in clips if p.with_suffix(".txt").exists()]
    if not scored:
        sys.exit(
            f"No clips with a reference transcript in {folder}.\n"
            f"Found {len(clips)} .wav file(s); add a <name>.txt next to each with what you actually said."
        )
    print(f"{len(scored)} scored clip(s) in {folder} ({len(clips) - len(scored)} without a .txt skipped)\n")

    db = WispernoDB(get_db_path())
    transcriber = Transcriber(config=config.whisper, vocabulary=Vocabulary(db=db))
    transcriber.transcribe(read_wav(scored[0])[:SAMPLE_RATE])  # warm-up: GPU init shouldn't count against clip 1
    transformer = _load_transformer(config) if args.llm else None
    mode = config.active_mode

    rows = []
    header = f"{'clip':<24} {'dur':>6} {'whisper':>8} {'WER':>6} {'fmt':>6}" + (f" {'llm':>8} {'llm fmt':>8}" if transformer else "")
    print(header)
    print("-" * len(header))
    for wav in scored:
        audio = read_wav(wav)
        reference = wav.with_suffix(".txt").read_text(encoding="utf-8")
        expected_path = wav.with_name(wav.stem + ".expected.txt")
        expected = expected_path.read_text(encoding="utf-8") if expected_path.exists() else None

        t0 = time.perf_counter()
        heard = transcriber.transcribe(audio)
        whisper_ms = (time.perf_counter() - t0) * 1000
        direct = apply_profanity_filter(format_direct(heard), config.profanity_filter)

        row = {
            "clip": wav.stem, "duration_s": len(audio) / SAMPLE_RATE, "whisper_ms": whisper_ms,
            "ref_words": len(normalize_words(reference)), "wer": word_error_rate(reference, heard),
            "heard": heard, "direct": direct,
            "direct_similarity": text_similarity(expected, direct) if expected else None,
        }
        if transformer:
            row["llm"], row["llm_ms"] = _run_llm(transformer, heard, mode)
            row["llm_similarity"] = text_similarity(expected, row["llm"]) if expected else None
        rows.append(row)

        fmt = f"{row['direct_similarity']:.0%}" if expected else "-"
        line = f"{wav.stem[:24]:<24} {row['duration_s']:>5.1f}s {whisper_ms:>6.0f}ms {row['wer']:>6.1%} {fmt:>6}"
        if transformer:
            llm_fmt = f"{row['llm_similarity']:.0%}" if expected else "-"
            line += f" {row['llm_ms']:>6.0f}ms {llm_fmt:>8}"
        print(line)
        if args.verbose:
            print(f"    said:  {reference.strip()}\n    heard: {heard}")

    total_words = sum(r["ref_words"] for r in rows) or 1
    whisper_times = [r["whisper_ms"] for r in rows]
    summary = {
        "clips": len(rows),
        "wer": sum(r["wer"] * r["ref_words"] for r in rows) / total_words,
        "whisper_ms_median": statistics.median(whisper_times),
        "whisper_ms_max": max(whisper_times),
        "rtf": sum(whisper_times) / 1000 / sum(r["duration_s"] for r in rows),
    }
    formatted = [r["direct_similarity"] for r in rows if r["direct_similarity"] is not None]
    if formatted:
        summary["direct_format_similarity"] = statistics.mean(formatted)
    if transformer:
        summary["llm_ms_median"] = statistics.median(r["llm_ms"] for r in rows)
        llm_formatted = [r["llm_similarity"] for r in rows if r["llm_similarity"] is not None]
        if llm_formatted:
            summary["llm_format_similarity"] = statistics.mean(llm_formatted)

    print("\nSUMMARY")
    print(f"  Word error rate (all clips):  {summary['wer']:.2%}  (lower is better)")
    print(f"  Whisper time, median / worst: {summary['whisper_ms_median']:.0f}ms / {summary['whisper_ms_max']:.0f}ms")
    print(f"  Real-time factor:             {summary['rtf']:.3f}  (0.1 = 10x faster than real time)")
    if "direct_format_similarity" in summary:
        print(f"  Instant formatter vs expected: {summary['direct_format_similarity']:.0%}")
    if transformer:
        print(f"  LLM polish time, median:      {summary['llm_ms_median']:.0f}ms")
        if "llm_format_similarity" in summary:
            print(f"  LLM polish vs expected:       {summary['llm_format_similarity']:.0%}")

    result = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "settings": {
            "whisper_model": config.whisper.model_name, "compute_type": config.whisper.compute_type,
            "beam_size": config.whisper.beam_size, "preset": config.model_preset, "llm": bool(transformer),
        },
        "summary": summary, "clips": rows,
    }
    if args.save:
        out = _results_dir(folder) / f"{args.save}.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nSaved as '{args.save}' ({out})")
    if args.compare:
        compare(_results_dir(folder) / f"{args.compare}.json", result)
    return result


def compare(baseline_path: Path, current: dict) -> None:
    if not baseline_path.exists():
        print(f"\nNo saved run at {baseline_path}")
        return
    base = json.loads(baseline_path.read_text(encoding="utf-8"))
    b, c = base["summary"], current["summary"]
    print(f"\nCOMPARED WITH '{baseline_path.stem}' ({base['timestamp']}, {base['settings']})")
    for key, label, fmt in (
        ("wer", "Word error rate", "{:.2%}"), ("whisper_ms_median", "Whisper median", "{:.0f}ms"),
        ("direct_format_similarity", "Formatter vs expected", "{:.0%}"),
        ("llm_ms_median", "LLM median", "{:.0f}ms"), ("llm_format_similarity", "LLM vs expected", "{:.0%}"),
    ):
        if key in b and key in c:
            print(f"  {label:<22} {fmt.format(b[key]):>8} -> {fmt.format(c[key]):>8}")
    base_clips = {r["clip"]: r for r in base["clips"]}
    changed = [
        (r, base_clips[r["clip"]]) for r in current["clips"]
        if r["clip"] in base_clips and abs(r["wer"] - base_clips[r["clip"]]["wer"]) > 1e-9
    ]
    for now, before in changed:
        print(f"  {now['clip']}: WER {before['wer']:.1%} -> {now['wer']:.1%}\n"
              f"      before: {before['heard']}\n      now:    {now['heard']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", help="recordings folder (default: %%APPDATA%%\\Wisperno\\recordings)")
    parser.add_argument("--llm", action="store_true", help="also run the LLM polish with the active preset")
    parser.add_argument("--save", metavar="NAME", help="save this run's results under NAME")
    parser.add_argument("--compare", metavar="NAME", help="compare with a run saved earlier under NAME")
    parser.add_argument("--text-cases", action="store_true", help="formatting-only cases (no audio needed)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print what was said vs heard per clip")
    args = parser.parse_args()

    from src.config import load_config
    config = load_config()
    if args.text_cases:
        run_text_cases(args, config)
    else:
        run_recordings(args, config)


if __name__ == "__main__":
    main()
