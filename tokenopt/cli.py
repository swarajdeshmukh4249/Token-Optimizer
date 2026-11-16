"""`tokenopt` command, installed by `pip install -e .`

    tokenopt optimize screenshot.png [--manifest out.json]
    tokenopt chat screenshot.png [--provider openai|claude] [--prev earlier.png] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from .image_opt import DEFAULT_PATCH, DEFAULT_VAR_THRESHOLD, load_image, optimize_image


def _optimize(args) -> None:
    img = load_image(args.image)
    res = optimize_image(img, patch=args.patch, var_threshold=args.var_threshold)
    h, w = img.shape[:2]
    print(f"{args.image}  {w}x{h}  patch {args.patch}px")
    print(f"  tokens   {res.baseline_tokens:,} -> {res.tokens:,}  ({res.reduction:.1%} fewer)")
    print(f"  quadtree {len(res.leaves):,} leaves in {res.elapsed_ms:.1f} ms")
    if args.manifest:
        from .manifest import image_manifest, save
        save(image_manifest(str(args.image), res), args.manifest)
        print(f"  manifest {args.manifest}")


def _chat(args) -> None:
    from .adapters.chat import plan_followup
    img = load_image(args.image)
    prev = load_image(args.prev) if args.prev else None
    plan = plan_followup(prev, img, args.provider)
    print(f"{args.image}  {plan.width}x{plan.height}  provider {args.provider}  mode {plan.mode}")
    print(f"  tokens   {plan.full_tokens:,} -> {plan.tokens:,}  ({plan.reduction:.1%} fewer, estimate)")
    print(f"  formula  {plan.formula}")
    if plan.fallback:
        print("  original kept: optimizing would not save enough")
    if plan.note:
        print(f"  note     {plan.note}")
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, im in plan.images:
            path = args.out / f"{name}.png"
            cv2.imwrite(str(path), cv2.cvtColor(im, cv2.COLOR_RGB2BGR))
            print(f"  wrote    {path}")
        (args.out / "plan.json").write_text(json.dumps(
            {"mode": plan.mode, "provider": plan.provider, "full_tokens": plan.full_tokens,
             "tokens": plan.tokens, "boxes": plan.boxes, "note": plan.note}, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="tokenopt", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("optimize", help="quadtree token plan for one image")
    o.add_argument("image", type=Path)
    o.add_argument("--patch", type=int, default=DEFAULT_PATCH)
    o.add_argument("--var-threshold", type=float, default=DEFAULT_VAR_THRESHOLD)
    o.add_argument("--manifest", type=Path, help="write the Optimized Token Manifest (otm/0.1) here")
    o.set_defaults(fn=_optimize)
    c = sub.add_parser("chat", help="what to send a chat app instead of this screenshot")
    c.add_argument("image", type=Path)
    c.add_argument("--provider", choices=["openai", "claude"], default="openai")
    c.add_argument("--prev", type=Path, help="previous screenshot already in the conversation")
    c.add_argument("--out", type=Path, help="folder to write the images to send")
    c.set_defaults(fn=_chat)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
