"""Summed-area table (integral image).

Stores prefix sums of I and I^2 so the mean and variance of ANY axis-aligned
rectangle can be read in O(1) -- this is what keeps quadtree construction
O(number of nodes) instead of O(pixels * depth).
"""
from __future__ import annotations

import numpy as np


class SummedAreaTable:
    def __init__(self, image: np.ndarray):
        a = image.astype(np.float64)
        if a.ndim == 2:
            a = a[:, :, None]
        h, w, c = a.shape
        self.h, self.w, self.channels = h, w, c
        # One row/column of zero padding so rectangle queries need no bounds checks.
        self._s = np.zeros((h + 1, w + 1, c))
        self._s2 = np.zeros((h + 1, w + 1, c))
        self._s[1:, 1:] = a.cumsum(0).cumsum(1)
        self._s2[1:, 1:] = (a * a).cumsum(0).cumsum(1)

    @staticmethod
    def _rect(t: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        return t[y + h, x + w] - t[y, x + w] - t[y + h, x] + t[y, x]

    def sum(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        return self._rect(self._s, x, y, w, h)

    def stats(self, x: int, y: int, w: int, h: int) -> tuple[np.ndarray, float]:
        """Per-channel mean and channel-averaged variance of the rectangle."""
        n = w * h
        mean = self._rect(self._s, x, y, w, h) / n
        var = self._rect(self._s2, x, y, w, h) / n - mean * mean
        return mean, float(np.maximum(var, 0.0).mean())

    def mean(self, x: int, y: int, w: int, h: int) -> float:
        return float((self._rect(self._s, x, y, w, h) / (w * h)).mean())
