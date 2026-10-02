"""Variance-based adaptive quadtree over the vision encoder's patch grid.

The image is viewed as a ceil(W/P) x ceil(H/P) grid of P-pixel patches -- exactly
what a uniform ViT-style encoder would tokenize. Every quadtree LEAF becomes ONE
token (the region resampled to a single P x P patch), so:

    * a fully-split tree reproduces the uniform baseline exactly (leaves == patches),
    * every merge of homogeneous patches is a direct token saving.

Two builders:
    build_recursive(var_threshold)        -- classic top-down recursion.
    build_budgeted(budget, var_threshold) -- best-first refinement driven by a
        MaxHeap keyed on squared error (variance x area). It spends a hard token
        budget on whichever region currently loses the most detail.
With an unlimited budget the two produce identical leaf sets (tested).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .max_heap import MaxHeap
from .summed_area import SummedAreaTable


@dataclass
class QuadNode:
    gx: int  # rectangle in patch-grid units
    gy: int
    gw: int
    gh: int
    depth: int
    x: int  # rectangle in pixels (clipped to the image)
    y: int
    w: int
    h: int
    mean: np.ndarray
    var: float
    children: list["QuadNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    @property
    def splittable(self) -> bool:
        return self.gw > 1 or self.gh > 1

    @property
    def sse(self) -> float:
        """Squared error if the region were flattened to its mean -- the saliency key."""
        return self.var * self.w * self.h

    @property
    def patches(self) -> int:
        return self.gw * self.gh


def _halves(start: int, length: int) -> list[tuple[int, int]]:
    if length == 1:
        return [(start, 1)]
    first = (length + 1) // 2
    return [(start, first), (start + first, length - first)]


class AdaptiveQuadtree:
    def __init__(self, image: np.ndarray, patch: int = 16, sat: SummedAreaTable | None = None):
        self.patch = patch
        self.img_h, self.img_w = image.shape[:2]
        self.grid_w = math.ceil(self.img_w / patch)
        self.grid_h = math.ceil(self.img_h / patch)
        self.sat = sat if sat is not None else SummedAreaTable(image)
        self.root: QuadNode | None = None

    @property
    def baseline_tokens(self) -> int:
        return self.grid_w * self.grid_h

    def _node(self, gx: int, gy: int, gw: int, gh: int, depth: int) -> QuadNode:
        p = self.patch
        x, y = gx * p, gy * p
        w = min(gw * p, self.img_w - x)
        h = min(gh * p, self.img_h - y)
        mean, var = self.sat.stats(x, y, w, h)
        return QuadNode(gx, gy, gw, gh, depth, x, y, w, h, mean, var)

    def _split(self, n: QuadNode) -> list[QuadNode]:
        return [
            self._node(cx, cy, cw, ch, n.depth + 1)
            for cy, ch in _halves(n.gy, n.gh)
            for cx, cw in _halves(n.gx, n.gw)
        ]

    def _new_root(self) -> QuadNode:
        return self._node(0, 0, self.grid_w, self.grid_h, 0)

    def build_recursive(self, var_threshold: float) -> list[QuadNode]:
        def grow(n: QuadNode) -> None:
            if n.splittable and n.var > var_threshold:
                n.children = self._split(n)
                for c in n.children:
                    grow(c)

        self.root = self._new_root()
        grow(self.root)
        return self.leaves()

    def build_budgeted(self, budget: int, var_threshold: float = 0.0) -> list[QuadNode]:
        self.root = self._new_root()
        tokens = 1
        heap: MaxHeap[QuadNode] = MaxHeap()
        if self.root.splittable and self.root.var > var_threshold:
            heap.push(self.root.sse, self.root)
        while heap:
            _, node = heap.pop()
            kids = self._split(node)
            extra = len(kids) - 1
            if tokens + extra > budget:
                continue  # a cheaper (2-way) split elsewhere may still fit
            node.children = kids
            tokens += extra
            for c in kids:
                if c.splittable and c.var > var_threshold:
                    heap.push(c.sse, c)
        return self.leaves()

    def leaves(self) -> list[QuadNode]:
        if self.root is None:
            return []
        out, stack = [], [self.root]
        while stack:
            n = stack.pop()
            if n.is_leaf:
                out.append(n)
            else:
                stack.extend(reversed(n.children))
        return out

    def depth(self) -> int:
        return max((leaf.depth for leaf in self.leaves()), default=0)
