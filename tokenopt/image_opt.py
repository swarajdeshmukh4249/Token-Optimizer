"""Single-image pipeline: decode -> quadtree allocation -> token-faithful rendering."""
from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from .cost import grid_tokens
from .ds.quadtree import AdaptiveQuadtree, QuadNode

DEFAULT_PATCH = 16
DEFAULT_VAR_THRESHOLD = 40.0  # channel-averaged variance on the 0-255 scale (std ~ 6.3)


@dataclass
class ImageResult:
    image: np.ndarray
    patch: int
    leaves: list[QuadNode]
    grid_w: int
    grid_h: int
    baseline_tokens: int
    var_threshold: float
    budget: int | None
    elapsed_ms: float

    @property
    def tokens(self) -> int:
        return len(self.leaves)

    @property
    def reduction(self) -> float:
        return 1.0 - self.tokens / self.baseline_tokens


def load_image(path: str, max_side: int = 1568) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"could not decode image: {path}")
    img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    if max(h, w) > max_side:
        s = max_side / max(h, w)
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    return img


def optimize_image(img: np.ndarray, patch: int = DEFAULT_PATCH,
                   var_threshold: float = DEFAULT_VAR_THRESHOLD,
                   budget: int | None = None, budget_ratio: float | None = None) -> ImageResult:
    t0 = time.perf_counter()
    tree = AdaptiveQuadtree(img, patch)
    if budget is None and budget_ratio is not None:
        budget = max(1, round(budget_ratio * tree.baseline_tokens))
    if budget is None:
        leaves = tree.build_recursive(var_threshold)
    else:
        leaves = tree.build_budgeted(budget, var_threshold)
    elapsed = (time.perf_counter() - t0) * 1000
    return ImageResult(img, patch, leaves, tree.grid_w, tree.grid_h,
                       tree.baseline_tokens, var_threshold, budget, elapsed)


def render_leaf(img: np.ndarray, leaf: QuadNode, patch: int) -> np.ndarray:
    """What one token 'sees': the region squeezed into a single patch, then stretched back."""
    crop = img[leaf.y:leaf.y + leaf.h, leaf.x:leaf.x + leaf.w]
    small = cv2.resize(crop, (min(patch, leaf.w), min(patch, leaf.h)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (leaf.w, leaf.h), interpolation=cv2.INTER_LINEAR)


def render_leaves(img: np.ndarray, leaves: list[QuadNode], patch: int,
                  canvas: np.ndarray | None = None) -> np.ndarray:
    out = np.zeros_like(img) if canvas is None else canvas
    for leaf in leaves:
        out[leaf.y:leaf.y + leaf.h, leaf.x:leaf.x + leaf.w] = render_leaf(img, leaf, patch)
    return out


def uniform_at_budget(img: np.ndarray, budget: int, patch: int) -> tuple[np.ndarray, int]:
    """Baseline at equal cost: shrink the whole image until its uniform grid fits the budget."""
    h, w = img.shape[:2]
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if grid_tokens(max(1, round(w * mid)), max(1, round(h * mid)), patch) <= budget:
            lo = mid
        else:
            hi = mid
    sw, sh = max(1, round(w * lo)), max(1, round(h * lo))
    small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR), grid_tokens(sw, sh, patch)
