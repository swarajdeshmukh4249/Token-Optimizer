"""Adaptive Multimodal Token Optimizer - command line entry point.

    python main.py demo                     build synthetic test set, run full evaluation
    python main.py image path/to/img.png    optimize one image
    python main.py video path/to/clip.mp4   optimize one video
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
    for kind in ("image", "video"):
        p = sub.add_parser(kind)
        p.add_argument("path", type=Path)
    args = ap.parse_args()

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
