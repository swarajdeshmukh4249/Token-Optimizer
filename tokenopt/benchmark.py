"""End-to-end evaluation: runs every input, writes manifests, figures and REPORT.md."""
from __future__ import annotations

import json
from pathlib import Path

from . import manifest, viz
from .adapters.claude import build_payload
from .image_opt import load_image, optimize_image, render_leaves, uniform_at_budget
from .metrics import psnr, ssim
from .video_opt import optimize_video, read_video

BUDGET_FRACTIONS = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75]
OPUS_INPUT_USD_PER_MTOK = 4.00  # claude-opus-5-5 list price, used only for the $ illustration


def _fmt_db(x: float) -> str:
    return "lossless" if x == float("inf") else f"{x:.1f}"


def run_image(name: str, path: Path, out: Path, patch: int, var_threshold: float) -> dict:
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    img = load_image(path)
    res = optimize_image(img, patch=patch, var_threshold=var_threshold)
    rec = render_leaves(img, res.leaves, patch)
    uni, uni_tokens = uniform_at_budget(img, res.tokens, patch)

    manifest.save(manifest.image_manifest(str(path), res), d / "manifest.json")
    viz.save_panels(d / "comparison.png", [
        ("Original", img),
        (f"Quadtree: {res.tokens} leaves (red = detail)", viz.quadtree_overlay(img, res.leaves, patch)),
        (f"Adaptive @ {res.tokens} tok - PSNR {_fmt_db(psnr(img, rec))}", rec),
        (f"Uniform @ {uni_tokens} tok - PSNR {_fmt_db(psnr(img, uni))}", uni),
    ], title=f"{name}: {res.baseline_tokens} -> {res.tokens} tokens ({100 * res.reduction:.1f}% fewer)")

    curve = {"frac": [], "adaptive": [], "uniform": []}
    for frac in BUDGET_FRACTIONS:
        r = optimize_image(img, patch=patch, budget_ratio=frac, var_threshold=0.0)
        u, _ = uniform_at_budget(img, r.tokens, patch)
        curve["frac"].append(frac)
        curve["adaptive"].append(min(psnr(img, render_leaves(img, r.leaves, patch)), 60.0))
        curve["uniform"].append(min(psnr(img, u), 60.0))

    pay = build_payload(res)
    for label, im in pay.images:
        viz.save_png(d / f"claude_{label}.png", im)
    (d / "claude_content_meta.json").write_text(json.dumps({
        "full_image_tokens_est": pay.full_tokens_est,
        "payload_tokens_est": pay.payload_tokens_est,
        "used_fallback": pay.used_fallback, "crops": pay.crops,
        "note": pay.content[-1]["text"],
    }, indent=1))

    return {
        "name": name, "kind": "image", "size": f"{img.shape[1]}x{img.shape[0]}",
        "baseline": res.baseline_tokens, "optimized": res.tokens,
        "reduction": res.reduction, "ms": res.elapsed_ms,
        "psnr": psnr(img, rec), "ssim": ssim(img, rec),
        "uniform_psnr": psnr(img, uni), "uniform_ssim": ssim(img, uni),
        "claude_full": pay.full_tokens_est, "claude_opt": pay.payload_tokens_est,
        "claude_fallback": pay.used_fallback, "claude_preview_psnr": psnr(img, pay.preview),
        "curve": curve,
    }


def run_video(name: str, path: Path, out: Path, patch: int, var_threshold: float,
              sample_fps: float) -> tuple[dict, object]:
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    frames, times = read_video(path, sample_fps=sample_fps)
    res = optimize_video(frames, times, patch=patch, var_threshold=var_threshold)
    manifest.save(manifest.video_manifest(str(path), res), d / "manifest.json")
    viz.plot_video_timeline(d / "timeline.png", res)
    picks = [g[0] for g in res.scenes][:3]
    viz.save_panels(d / "frames.png",
                    [(f"frame {i} ({res.frames[i].role}, {res.frames[i].tokens} tok)", res.recon[i])
                     for i in picks], title=f"{name}: first frame of each scene, as the model sees it")
    psnrs = [f.psnr for f in res.frames]
    roles = {r: sum(f.role == r for f in res.frames) for r in ("key", "delta", "duplicate")}
    return {
        "name": name, "kind": "video", "size": f"{res.width}x{res.height} x {len(frames)} frames",
        "baseline": res.baseline_tokens, "optimized": res.tokens,
        "reduction": 1 - res.tokens / res.baseline_tokens, "ms": res.elapsed_ms,
        "psnr": sum(psnrs) / len(psnrs), "min_psnr": min(psnrs),
        "scenes": len(res.scenes), "overlays": len(res.overlays), "roles": roles,
    }, res


def write_report(out: Path, rows: list[dict], patch: int, var_threshold: float) -> Path:
    images = [r for r in rows if r["kind"] == "image"]
    videos = [r for r in rows if r["kind"] == "video"]
    L = ["# Adaptive Multimodal Token Optimizer - evaluation report", "",
         f"Patch size **{patch}px**, variance threshold **{var_threshold}**. "
         "Baseline = uniform patch grid (one token per patch), the allocation a standard "
         "ViT-style encoder makes regardless of content.", "",
         "## Images", "",
         "| input | size | baseline tok | optimized tok | reduction | PSNR | SSIM | uniform@same-budget PSNR / SSIM | time |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in images:
        L.append(f"| {r['name']} | {r['size']} | {r['baseline']} | {r['optimized']} | "
                 f"**{100 * r['reduction']:.1f}%** | {_fmt_db(r['psnr'])} | {r['ssim']:.3f} | "
                 f"{_fmt_db(r['uniform_psnr'])} / {r['uniform_ssim']:.3f} | {r['ms']:.0f} ms |")
    L += ["", "PSNR/SSIM compare the original with what the model would receive "
          "(each leaf squeezed into one patch). 'Uniform@same-budget' downsizes the whole "
          "image to the same token count - the fair baseline for the allocation decision.", "",
          "![token bars](token_bars.png)", "", "![rd curves](rd_curves.png)", ""]
    if videos:
        L += ["## Video", "",
              "| input | size | baseline tok | optimized tok | reduction | mean / min PSNR | scenes | key / delta / dup | static overlay blocks | time |",
              "|---|---|---:|---:|---:|---:|---:|---|---:|---:|"]
        for r in videos:
            ro = r["roles"]
            L.append(f"| {r['name']} | {r['size']} | {r['baseline']} | {r['optimized']} | "
                     f"**{100 * r['reduction']:.1f}%** | {r['psnr']:.1f} / {r['min_psnr']:.1f} | {r['scenes']} | "
                     f"{ro['key']} / {ro['delta']} / {ro['duplicate']} | {r['overlays']} | {r['ms']:.0f} ms |")
        L += [""] + [f"![{r['name']} timeline]({r['name']}/timeline.png)" for r in videos] + [""]
    L += ["## Claude adapter (estimated)", "",
          "Overview thumbnail + full-resolution crops of detailed regions. Estimates use "
          "`tokens ~ w*h/750` after fitting to a 1568px long edge - an approximation; "
          "`count_tokens_with_claude()` gives exact numbers.", "",
          "| input | full image est. | optimized payload est. | reduction | fallback to original? | preview PSNR |",
          "|---|---:|---:|---:|---|---:|"]
    for r in images:
        red = 1 - r["claude_opt"] / r["claude_full"]
        L.append(f"| {r['name']} | {r['claude_full']} | {r['claude_opt']} | {100 * red:.1f}% | "
                 f"{'yes' if r['claude_fallback'] else 'no'} | {_fmt_db(r['claude_preview_psnr'])} |")
    total_saved = sum(r["baseline"] - r["optimized"] for r in rows)
    L += ["", "## Cost framing", "",
          f"Across this run the optimizer removed **{total_saved:,} patch tokens**. "
          f"At ${OPUS_INPUT_USD_PER_MTOK:.2f}/M input tokens that is "
          f"${total_saved * OPUS_INPUT_USD_PER_MTOK / 1e6:.4f} per pass over this set - "
          "negligible once, but it repeats on every call and every agent turn that re-sends "
          "the attachment, while the preprocessing cost is paid once.", "",
          "## Honest limitations (so far)", "",
          "* Dense texture gets ~0% reduction by design - nothing is redundant.",
          "* Variance is a conservative split rule: smooth gradients and fine noise both "
          "look 'busy'. A detail-energy criterion (variance lost after resampling) is the next step.",
          "* Fidelity is measured as pixel fidelity (PSNR/SSIM). Answer-quality evaluation on a "
          "fixed question set against a real vision model is not done yet.",
          "* The synthetic screen recording is a favourable case for temporal reuse; real "
          "camera footage will reduce less.", ""]
    path = out / "REPORT.md"
    path.write_text("\n".join(L))
    return path


def run_all(inputs: dict[str, Path], out: Path, patch: int, var_threshold: float,
            sample_fps: float = 2.0) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    rows, curves = [], {}
    for name, path in inputs.items():
        if path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
            row, _ = run_video(name, path, out, patch, var_threshold, sample_fps)
        else:
            row = run_image(name, path, out, patch, var_threshold)
            curves[name] = row.pop("curve")
        rows.append(row)
        print(f"  {name:12s} {row['baseline']:>7d} -> {row['optimized']:>6d} tokens "
              f"({100 * row['reduction']:5.1f}% fewer)  {row['ms']:.0f} ms")
    if curves:
        viz.plot_rd_curves(out / "rd_curves.png", curves)
    viz.plot_token_bars(out / "token_bars.png", rows)
    (out / "results.json").write_text(json.dumps(rows, indent=1, default=str))
    write_report(out, rows, patch, var_threshold)
    return rows
