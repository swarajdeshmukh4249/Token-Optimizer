"""Adapter for chat apps (ChatGPT, Claude.ai): one pasted image -> overview + crops.

The chat app bills images by its provider's published formula, which we cannot
change, so the only lever is *which pixels* we hand it. We send:

    1. a small overview of the whole image, and
    2. full-resolution crops of the detailed regions (quadtree single-patch leaves,
       grouped into crops with Union-Find -- see adapters/claude.detail_regions).

Every candidate crop count covers all detailed cells (fewer crops just means
bigger, merged boxes), so we may pick the one that is cheapest under the
provider's formula. If even the cheapest costs >= fallback_ratio of the original,
the original goes through untouched: an honest "no gain" instead of a loss.

All token numbers are ESTIMATES from the providers' published image formulas.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..cost import fit_long_edge, openai_image_tokens, pixel_area_tokens
from ..ds.hash_table import hamming
from ..image_opt import optimize_image
from ..phash import phash
from ..video_opt import _diff_grid
from .claude import detail_regions, group_cells

PROVIDERS = {
    "claude": ("Anthropic image formula: ceil(w*h/750), long edge capped at 1568 px",
               pixel_area_tokens),
    "openai": ("OpenAI GPT-4o high-detail formula: 85 + 170 per 512 px tile",
               openai_image_tokens),
}
CROP_CANDIDATES = (1, 2, 3, 4, 6, 8)


@dataclass
class ChatPlan:
    provider: str
    formula: str
    width: int
    height: int
    full_tokens: int
    tokens: int
    fallback: bool
    images: list[tuple[str, np.ndarray]]
    boxes: list[tuple[int, int, int, int]]
    image_tokens: list[int]
    elapsed_ms: float
    note: str = ""
    leaves: int = field(default=0)
    mode: str = "new"   # new | delta | duplicate

    @property
    def reduction(self) -> float:
        return 1 - self.tokens / self.full_tokens


def plan_for_chat(img: np.ndarray, provider: str = "claude", patch: int = 16,
                  var_threshold: float = 40.0, thumb_long_edge: int = 512,
                  fallback_ratio: float = 0.85) -> ChatPlan:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; use one of {sorted(PROVIDERS)}")
    formula, cost = PROVIDERS[provider]
    t0 = time.perf_counter()
    res = optimize_image(img, patch=patch, var_threshold=var_threshold)
    h, w = img.shape[:2]
    full = cost(w, h)

    tw, th = fit_long_edge(w, h, thumb_long_edge)
    thumb = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
    best: tuple[int, list] | None = None
    for k in CROP_CANDIDATES:
        boxes = detail_regions(res, max_crops=k)
        total = cost(tw, th) + sum(cost(bw, bh) for _, _, bw, bh in boxes)
        if best is None or total < best[0]:
            best = (total, boxes)
    total, boxes = best

    if total >= fallback_ratio * full:
        return ChatPlan(provider, formula, w, h, full, full, True, [("original", img)], [], [full],
                        (time.perf_counter() - t0) * 1000, leaves=len(res.leaves))

    crops = [img[y:y + bh, x:x + bw] for x, y, bw, bh in boxes]
    images = [("overview", thumb)] + [(f"crop_{i + 1}", c) for i, c in enumerate(crops)]
    layout = "; ".join(f"image {i + 2} = crop at x={x} y={y} ({bw}x{bh})"
                       for i, (x, y, bw, bh) in enumerate(boxes))
    note = (f"Image 1 is a {tw}x{th} overview of a {w}x{h} screenshot. "
            + (f"The other images are full-resolution crops of its detailed regions, "
               f"in original pixel coordinates: {layout}." if boxes else ""))
    return ChatPlan(provider, formula, w, h, full, total, False, images, boxes,
                    [cost(im.shape[1], im.shape[0]) for _, im in images],
                    (time.perf_counter() - t0) * 1000, note, len(res.leaves))


def plan_followup(prev: np.ndarray | None, img: np.ndarray, provider: str = "claude",
                  patch: int = 16, scene_distance: int = 14, change_threshold: float = 6.0,
                  fallback_ratio: float = 0.85) -> ChatPlan:
    """Plan a screenshot that follows `prev` in the same conversation.

    Same pipeline as the video optimizer, one frame at a time:
      * pHash distance > scene_distance (or a size change) -> new scene: plan_for_chat
      * no patch changed by more than change_threshold     -> "duplicate": send nothing
      * otherwise -> crops of the changed cells only (Union-Find groups them),
        because the model already holds the previous screenshot in its context.
    """
    if prev is None or prev.shape != img.shape or \
            hamming(phash(prev), phash(img)) > scene_distance:
        plan = plan_for_chat(img, provider, patch=patch, fallback_ratio=fallback_ratio)
        plan.mode = "new"
        return plan

    formula, cost = PROVIDERS[provider]
    t0 = time.perf_counter()
    h, w = img.shape[:2]
    full = cost(w, h)
    gw, gh = math.ceil(w / patch), math.ceil(h / patch)
    changed = _diff_grid(img, prev, gw, gh)
    cells = [(int(x), int(y)) for y, x in zip(*np.nonzero(changed > change_threshold))]
    if not cells:
        return ChatPlan(provider, formula, w, h, full, 0, False, [], [], [],
                        (time.perf_counter() - t0) * 1000,
                        "Same screen as the previous screenshot (no visible change).", mode="duplicate")

    best: tuple[int, list] | None = None
    for k in CROP_CANDIDATES:
        boxes = group_cells(cells, patch, w, h, max_crops=k)
        total = sum(cost(bw, bh) for _, _, bw, bh in boxes)
        if best is None or total < best[0]:
            best = (total, boxes)
    total, boxes = best
    if total >= fallback_ratio * full:
        return ChatPlan(provider, formula, w, h, full, full, True, [("original", img)], [], [full],
                        (time.perf_counter() - t0) * 1000, mode="new")

    images = [(f"change_{i + 1}", img[y:y + bh, x:x + bw]) for i, (x, y, bw, bh) in enumerate(boxes)]
    layout = "; ".join(f"x={x} y={y} ({bw}x{bh})" for x, y, bw, bh in boxes)
    note = (f"Same {w}x{h} screen as the previous screenshot; only these regions changed, "
            f"attached in order at original pixel coordinates: {layout}.")
    return ChatPlan(provider, formula, w, h, full, total, False, images, boxes,
                    [cost(im.shape[1], im.shape[0]) for _, im in images],
                    (time.perf_counter() - t0) * 1000, note, mode="delta")
