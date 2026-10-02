"""Figures for the evaluation report."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ADAPTIVE, UNIFORM, NEUTRAL = "#2563eb", "#9ca3af", "#111827"
ROLE_COLORS = {"key": "#2563eb", "delta": "#10b981", "duplicate": "#d1d5db"}


def quadtree_overlay(img: np.ndarray, leaves, patch: int) -> np.ndarray:
    """Leaf borders coloured by size: red = single patch (detail), blue = merged."""
    out = (img.astype(np.float32) * 0.75 + 255 * 0.25).astype(np.uint8)
    for leaf in leaves:
        color = (220, 38, 38) if leaf.patches == 1 else (37, 99, 235)
        cv2.rectangle(out, (leaf.x, leaf.y), (leaf.x + leaf.w - 1, leaf.y + leaf.h - 1), color, 1)
    return out


def save_panels(path: Path, panels: list[tuple[str, np.ndarray]], title: str = "") -> None:
    fig, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), 4.6))
    for ax, (label, im) in zip(np.atleast_1d(axes), panels):
        ax.imshow(im)
        ax.set_title(label, fontsize=10)
        ax.axis("off")
    if title:
        fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def _style(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)


def plot_rd_curves(path: Path, curves: dict[str, dict[str, list[float]]]) -> None:
    """PSNR vs token budget: adaptive quadtree vs uniform downscaling at equal cost."""
    n = len(curves)
    cols = min(n, 2)
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(5.6 * cols, 3.9 * rows), squeeze=False)
    for ax, (name, c) in zip(axes.flat, curves.items()):
        ax.plot(c["frac"], c["adaptive"], "-o", color=ADAPTIVE, lw=2, ms=4, label="Adaptive quadtree")
        ax.plot(c["frac"], c["uniform"], "-o", color=UNIFORM, lw=2, ms=4, label="Uniform grid")
        ax.set_title(name, fontsize=11, loc="left")
        ax.set_xlabel("Token budget (fraction of uniform baseline)")
        ax.set_ylabel("PSNR (dB)")
        _style(ax)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    axes.flat[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Fidelity at equal token cost", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_token_bars(path: Path, rows: list[dict]) -> None:
    names = [r["name"] for r in rows]
    base = np.array([r["baseline"] for r in rows])
    opt = np.array([r["optimized"] for r in rows])
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(1.6 * len(names) + 3, 4))
    ax.bar(x - 0.2, base, 0.38, color=UNIFORM, label="Uniform grid (baseline)")
    ax.bar(x + 0.2, opt, 0.38, color=ADAPTIVE, label="Optimized")
    for i, (b, o) in enumerate(zip(base, opt)):
        ax.text(i + 0.2, o, f"-{100 * (1 - o / b):.0f}%", ha="center", va="bottom", fontsize=9, color=NEUTRAL)
    ax.set_xticks(x, names)
    ax.set_ylabel("Input tokens")
    ax.set_yscale("log")
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    ax.set_title("Tokens before vs after optimization", fontsize=13, fontweight="bold", loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_video_timeline(path: Path, result) -> None:
    per_frame = result.baseline_tokens / len(result.frames)
    fig, ax = plt.subplots(figsize=(10, 3.8))
    for f in result.frames:
        ax.bar(f.index, f.tokens, color=ROLE_COLORS[f.role], width=0.8)
        if f.tokens == 0:  # invisible on a log axis otherwise
            ax.text(f.index, 0.15, "0", ha="center", va="bottom", fontsize=8, color="#6b7280")
    ax.axhline(per_frame, color=UNIFORM, ls="--", lw=1.5)
    ax.text(len(result.frames) - 0.5, per_frame, " uniform baseline / frame", va="bottom", ha="right",
            fontsize=9, color="#6b7280")
    for group in result.scenes[1:]:
        ax.axvline(min(group) - 0.5, color="#e5e7eb", lw=1)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ROLE_COLORS.values()]
    ax.legend(handles, list(ROLE_COLORS), frameon=False, fontsize=9, loc="upper center", ncol=3)
    ax.set_yscale("symlog", linthresh=10)
    ax.set_xlabel("Sampled frame")
    ax.set_ylabel("Tokens charged")
    _style(ax)
    ax.set_title("Video: tokens per frame by role", fontsize=13, fontweight="bold", loc="left")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def save_png(path: Path, img: np.ndarray) -> None:
    cv2.imwrite(str(path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
