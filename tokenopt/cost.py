"""Token cost models.

grid_tokens    -- uniform ViT-style patch grid: the model-agnostic baseline the
                  optimizer is measured against.
pixel_area_tokens -- provider-style estimate (tokens ~ width*height / px_per_token
                  after downscaling to a max long edge). The defaults follow the
                  commonly documented Claude rule of thumb but are an APPROXIMATION
                  and may differ per model: confirm with the provider's
                  token-counting endpoint (see adapters/claude.py).
"""
from __future__ import annotations

import math


def grid_tokens(width: int, height: int, patch: int) -> int:
    return math.ceil(width / patch) * math.ceil(height / patch)


def fit_long_edge(width: int, height: int, max_long_edge: int) -> tuple[int, int]:
    scale = min(1.0, max_long_edge / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def pixel_area_tokens(width: int, height: int, px_per_token: int = 750,
                      max_long_edge: int = 1568) -> int:
    w, h = fit_long_edge(width, height, max_long_edge)
    return math.ceil(w * h / px_per_token)
