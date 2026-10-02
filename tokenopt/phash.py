"""DCT perceptual hash (pHash), 64 bits.

Shrink to 32x32 grey, take the 2-D DCT (as an explicit matrix product), keep the
8x8 lowest frequencies and threshold them at their median. Visually similar
images land within a small Hamming distance of each other; compression noise,
small shifts and brightness changes barely move the hash.
"""
from __future__ import annotations

import math

import cv2
import numpy as np


def _dct_matrix(n: int) -> np.ndarray:
    m = np.empty((n, n))
    for k in range(n):
        scale = math.sqrt(1 / n) if k == 0 else math.sqrt(2 / n)
        for i in range(n):
            m[k, i] = scale * math.cos(math.pi * (2 * i + 1) * k / (2 * n))
    return m


_D = _dct_matrix(32)


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img.astype(np.float64)
    return img[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])


def phash(img: np.ndarray) -> int:
    g = cv2.resize(to_gray(img), (32, 32), interpolation=cv2.INTER_AREA)
    low = (_D @ g @ _D.T)[:8, :8].flatten()
    median = np.median(low[1:])  # skip DC: it only encodes overall brightness
    h = 0
    for bit in low > median:
        h = (h << 1) | int(bit)
    return h
