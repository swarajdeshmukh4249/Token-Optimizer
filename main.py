"""Adaptive Multimodal Token Optimizer - command line entry point.

    python main.py demo                     build synthetic test set, run full evaluation
    python main.py image path/to/img.png    optimize one image
    python main.py video path/to/clip.mp4   optimize one video
    python main.py race                     near-duplicate search race (linear vs BK-tree vs MIH)
    python main.py complexity               measured cost vs theoretical complexity per structure
    python main.py agent                    computer-use agent screenshots, encoded causally per turn
    python main.py ocr                      does the text survive? free Tesseract word-recall check
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tokenopt import benchmark
from tokenopt.image_opt import DEFAULT_PATCH, DEFAULT_VAR_THRESHOLD
from tokenopt.synth import build_dataset

ROOT = Path(__file__).parent
MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".mp4", ".mov", ".avi", ".mkv", ".webm"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patch", type=int, default=DEFAULT_PATCH, help="encoder patch size in px")
    ap.add_argument("--var-threshold", type=float, default=DEFAULT_VAR_THRESHOLD,
                    help="split a region while its variance exceeds this")
    ap.add_argument("--fps", type=float, default=2.0, help="video sampling rate")
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="synthetic set + anything in data/real/")
    sub.add_parser("race", help="linear scan vs BK-tree vs multi-index hashing")
    sub.add_parser("complexity", help="measured cost vs theoretical complexity")
    sub.add_parser("agent", help="agent-screenshot compression over a 20-turn session")
    sub.add_parser("ocr", help="word recall after optimization, read by Tesseract")
    for kind in ("image", "video"):
        p = sub.add_parser(kind)
        p.add_argument("path", type=Path)
    args = ap.parse_args()

    if args.cmd == "race":
        from tokenopt.ds_race import run_race
        print("Racing near-duplicate search structures ...")
        run_race(args.out / "ds_race")
        print(f"\nReport: {args.out / 'ds_race' / 'RACE.md'}")
        return

    if args.cmd == "ocr":
        from tokenopt.ocr_eval import run_ocr
        print("Reading every variant with Tesseract ...")
        run_ocr(args.out / "ocr", ROOT)
        print(f"\nReport: {args.out / 'ocr' / 'OCR.md'}")
        return

    if args.cmd == "agent":
        from tokenopt.agent import run_agent
        print("Encoding a 20-turn agent session causally ...")
        s = run_agent(args.out / "agent")["summary"]
        print(f"  screenshot tokens: {s['screenshot_tokens_baseline']:,} -> {s['screenshot_tokens_optimized']:,} "
              f"({s['screenshot_reduction']:.1%} less)")
        print(f"  context tokens:    {s['context_tokens_baseline']:,} -> {s['context_tokens_optimized']:,} "
              f"({s['context_reduction']:.1%} less)")
        print(f"\nReport: {args.out / 'agent' / 'AGENT.md'}")
        return

    if args.cmd == "complexity":
        from tokenopt.complexity import run_complexity
        print("Measuring data structure complexity ...")
        run_complexity(args.out / "complexity")
        print(f"\nReport: {args.out / 'complexity' / 'COMPLEXITY.md'}")
        return

    if args.cmd == "demo":
        print("Building synthetic test set in data/synthetic/ ...")
        inputs = build_dataset(ROOT / "data" / "synthetic")
        real = ROOT / "data" / "real"
        if real.is_dir():
            for p in sorted(real.iterdir()):
                if p.suffix.lower() in MEDIA:
                    inputs[f"real_{p.stem}"] = p
    else:
        inputs = {args.path.stem: args.path}

    print("Optimizing:")
    benchmark.run_all(inputs, args.out, args.patch, args.var_threshold, args.fps)
    print(f"\nReport: {args.out / 'REPORT.md'}")


if __name__ == "__main__":
    main()
