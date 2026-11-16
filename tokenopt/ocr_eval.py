"""Does the text survive? OCR answer-quality check with free, local Tesseract.

Token savings only matter if the model can still read the screen. Here a
stand-in reader (Tesseract OCR) reads each image as the model would receive it,
and we count how many words of the original it still recovers:

    word recall = |words(variant) ∩ words(original)| / |words(original)|   (multiset)

Variants, each with its token cost:
  * original          -- the full image (the reference, recall 1.0 by definition)
  * adaptive          -- quadtree reconstruction at the default variance threshold
  * uniform @ same    -- plain downscale given exactly the adaptive token count
  * adaptive @ 25%    -- quadtree with a hard budget of 25% of the patch grid (max-heap)
  * uniform @ 25%     -- plain downscale at the same 25% budget
  * claude payload    -- overview + full-resolution crops, as the Claude adapter sends

Tesseract is a much weaker reader than a vision LLM, so recall here is a
conservative proxy: text Tesseract can read, a VLM can generally read too.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .adapters.claude import build_payload  # noqa: E402
from .agent import _screen  # noqa: E402
from .image_opt import load_image, optimize_image, render_leaves, uniform_at_budget  # noqa: E402
from .synth import build_dataset  # noqa: E402

PATCH = 16
METHODS = ["adaptive", "uniform @ same", "adaptive @ 25%", "uniform @ 25%", "claude payload"]
COLOURS = {"adaptive": "#1a73e8", "uniform @ same": "#9aa0a6", "adaptive @ 25%": "#174ea6",
           "uniform @ 25%": "#dadce0", "claude payload": "#e8710a"}


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr(img: np.ndarray) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        out = subprocess.run(["tesseract", f.name, "stdout", "--psm", "3"],
                             capture_output=True, text=True, check=True)
    return out.stdout


def words(text: str) -> Counter:
    return Counter(w for w in re.findall(r"[a-z0-9$.,/%']+", text.lower())
                   if len(w.strip(".,'")) >= 2)


def word_recall(ref: Counter, got: Counter) -> float:
    total = sum(ref.values())
    return 1.0 if total == 0 else sum((ref & got).values()) / total


def _samples(root: Path) -> dict[str, np.ndarray]:
    synth = root / "data" / "synthetic"
    if not (synth / "document.png").exists():
        build_dataset(synth)
    modal = dict(name="Agent demo", focused=True, dropdown_open=False, plan="1M / week", hover_create=False)
    return {
        "document": load_image(synth / "document.png"),
        "ui": load_image(synth / "ui.png"),
        "agent dashboard": _screen("dashboard", (700, 420)),
        "agent projects": _screen("projects", (90, 200)),
        "agent modal": _screen("projects", (640, 310), modal=modal),
    }


def _variants(img: np.ndarray) -> dict[str, tuple[np.ndarray, int]]:
    res = optimize_image(img, patch=PATCH)
    tight = optimize_image(img, patch=PATCH, budget_ratio=0.25)
    pay = build_payload(res)
    return {
        "adaptive": (render_leaves(img, res.leaves, PATCH), res.tokens),
        "uniform @ same": uniform_at_budget(img, res.tokens, PATCH),
        "adaptive @ 25%": (render_leaves(img, tight.leaves, PATCH), tight.tokens),
        "uniform @ 25%": uniform_at_budget(img, tight.tokens, PATCH),
        # The Claude payload is billed by pixel area, not patches: report its patch-grid
        # equivalent so every row uses the same unit (tokens of the 16 px grid).
        "claude payload": (pay.preview, round(pay.payload_tokens_est / pay.full_tokens_est * res.baseline_tokens)),
    }


def run_ocr(out: Path, root: Path) -> dict:
    if not tesseract_available():
        raise RuntimeError("tesseract not found: brew install tesseract")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, img in _samples(root).items():
        ref_text = ocr(img)
        ref = words(ref_text)
        baseline = optimize_image(img, patch=PATCH).baseline_tokens
        row = {"name": name, "ref_words": sum(ref.values()), "baseline_tokens": baseline, "methods": []}
        for method, (variant, tokens) in _variants(img).items():
            text = ocr(variant)
            row["methods"].append({
                "method": method, "tokens": int(tokens),
                "token_share": round(tokens / baseline, 3),
                "word_recall": round(word_recall(ref, words(text)), 3),
                "char_similarity": round(SequenceMatcher(None, ref_text, text).ratio(), 3),
            })
        rows.append(row)
        print(f"  {name:16} " + "  ".join(f"{m['method']}: {m['word_recall']:.2f}" for m in row["methods"]))
    result = {"patch": PATCH, "samples": rows}
    _plot(rows, out / "ocr_recall.png")
    (out / "ocr.json").write_text(json.dumps(result, indent=2))
    (out / "OCR.md").write_text(_report(result))
    return result


def _plot(rows: list[dict], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.4))
    n, width = len(METHODS), 0.16
    xs = np.arange(len(rows))
    for i, m in enumerate(METHODS):
        vals = [next(x for x in r["methods"] if x["method"] == m) for r in rows]
        bars = ax.bar(xs + (i - (n - 1) / 2) * width, [v["word_recall"] for v in vals], width,
                      color=COLOURS[m], label=m, edgecolor="#5f6368", linewidth=0.4)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"{v['token_share']:.0%}",
                    ha="center", va="bottom", fontsize=6.5, color="#5f6368", rotation=90)
    ax.set_xticks(xs, [r["name"] for r in rows])
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("word recall vs original (Tesseract)")
    ax.set_title("Does the text survive?  (label above bar = tokens as share of the full patch grid)")
    ax.legend(ncol=5, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _report(res: dict) -> str:
    lines = [
        "# Does the text survive? (OCR check)",
        "",
        "Tesseract 5 (free, local) reads each image as the model would receive it. Word recall = share of the "
        "words Tesseract reads in the original that it still reads in the variant. Tokens are on the "
        f"{res['patch']} px patch grid (the Claude payload is converted to the same unit from its pixel-area estimate).",
        "",
        "| sample | words | " + " | ".join(METHODS) + " |",
        "|---|---:|" + "---:|" * len(METHODS),
    ]
    for r in res["samples"]:
        cells = []
        for m in METHODS:
            v = next(x for x in r["methods"] if x["method"] == m)
            cells.append(f"{v['word_recall']:.0%} @ {v['token_share']:.0%}")
        lines.append(f"| {r['name']} | {r['ref_words']} | " + " | ".join(cells) + " |")
    lines += ["", "Each cell: word recall @ tokens as a share of the full grid.", "",
              "A claude payload at 100% means the adapter fell back to the original image because overview + crops "
              "would not have saved enough; on dense text the plain downscale is as good as the quadtree, "
              "which is the honest limit of the method.", "",
              "Tesseract is far weaker than a vision LLM, so these recalls are a conservative proxy.", "",
              "![ocr](ocr_recall.png)", ""]
    return "\n".join(lines)
