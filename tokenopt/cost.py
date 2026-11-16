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


def openai_image_tokens(width: int, height: int) -> int:
    """OpenAI's published GPT-4o high-detail image cost (an estimate for other models).

    Fit inside 2048x2048, then shrink so the short side is at most 768 px, then
    charge 85 + 170 per 512x512 tile.
    """
    w, h = fit_long_edge(width, height, 2048)
    s = min(1.0, 768 / min(w, h))
    w, h = max(1, round(w * s)), max(1, round(h * s))
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)
