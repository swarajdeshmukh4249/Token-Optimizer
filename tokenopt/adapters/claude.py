"""Adapter: Optimized Token Manifest -> Claude Messages API image content.

Claude bills images by pixel area rather than by our patch leaves, so the
manifest is translated into a pixel-cheap equivalent:

    1. one low-resolution overview of the whole image (cheap context), plus
    2. full-resolution crops of the DETAILED regions only.

Detailed regions = quadtree leaves that stayed at single-patch size. Adjacent
detailed patches are merged into connected components with Union-Find; the
neighbourhood radius grows until there are at most `max_crops` components.
If the crops would cost nearly as much as the original, the adapter falls back
to sending the original image (the honest "no gain" case).

Token numbers here are ESTIMATES from tokenopt.cost.pixel_area_tokens. Use
count_tokens_with_claude() to get the provider's exact count.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..cost import fit_long_edge, pixel_area_tokens
from ..ds.union_find import UnionFind

DEFAULT_MODEL = "claude-opus-5-5"


@dataclass
class ClaudePayload:
    content: list[dict]
    images: list[tuple[str, np.ndarray]]
    crops: list[tuple[int, int, int, int]]
    full_tokens_est: int
    payload_tokens_est: int
    used_fallback: bool
    preview: np.ndarray = field(repr=False, default=None)

    @property
    def reduction(self) -> float:
        return 1 - self.payload_tokens_est / self.full_tokens_est


def detail_regions(result, max_crops: int = 6, pad_patches: int = 1) -> list[tuple[int, int, int, int]]:
    p = result.patch
    h, w = result.image.shape[:2]
    cells = [(l.gx, l.gy) for l in result.leaves if l.patches == 1]
    if not cells:
        return []
    pos = {c: i for i, c in enumerate(cells)}
    radius = 1
    while True:
        uf = UnionFind(len(cells))
        for (gx, gy), i in pos.items():
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    j = pos.get((gx + dx, gy + dy))
                    if j is not None:
                        uf.union(i, j)
        if uf.components <= max_crops or radius >= 16:
            break
        radius *= 2
    boxes = []
    for group in uf.groups():
        xs = [cells[i][0] for i in group]
        ys = [cells[i][1] for i in group]
        x0 = max(0, (min(xs) - pad_patches) * p)
        y0 = max(0, (min(ys) - pad_patches) * p)
        x1 = min(w, (max(xs) + 1 + pad_patches) * p)
        y1 = min(h, (max(ys) + 1 + pad_patches) * p)
        boxes.append((x0, y0, x1 - x0, y1 - y0))
    return sorted(boxes, key=lambda b: -b[2] * b[3])


def _png_block(img: np.ndarray) -> dict:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    assert ok
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(buf.tobytes()).decode()}}


def build_payload(result, thumb_long_edge: int = 512, max_crops: int = 6,
                  fallback_ratio: float = 0.85) -> ClaudePayload:
    img = result.image
    h, w = img.shape[:2]
    full = pixel_area_tokens(w, h)
    tw, th = fit_long_edge(w, h, thumb_long_edge)
    thumb = cv2.resize(img, (tw, th), interpolation=cv2.INTER_AREA)
    boxes = detail_regions(result, max_crops=max_crops)
    crops = [img[y:y + bh, x:x + bw] for x, y, bw, bh in boxes]
    est = pixel_area_tokens(tw, th) + sum(pixel_area_tokens(c.shape[1], c.shape[0]) for c in crops)

    if est >= fallback_ratio * full:
        content = [_png_block(img), {"type": "text", "text": "(original image, unoptimized)"}]
        return ClaudePayload(content, [("original", img)], [], full, full, True, img.copy())

    # What the model effectively receives: blurry overview with sharp crops pasted in.
    preview = cv2.resize(thumb, (w, h), interpolation=cv2.INTER_LINEAR)
    for (x, y, bw, bh), c in zip(boxes, crops):
        preview[y:y + bh, x:x + bw] = c

    layout = "; ".join(f"image {k + 2} = crop x={x} y={y} w={bw} h={bh}"
                       for k, (x, y, bw, bh) in enumerate(boxes))
    note = (f"Image 1 is a {tw}x{th} overview of a {w}x{h} original. "
            f"The remaining images are full-resolution crops of its detailed regions, "
            f"in original pixel coordinates: {layout}.")
    content = [_png_block(thumb)] + [_png_block(c) for c in crops] + [{"type": "text", "text": note}]
    images = [("overview", thumb)] + [(f"crop_{k + 1}", c) for k, c in enumerate(crops)]
    return ClaudePayload(content, images, boxes, full, est, False, preview)


def count_tokens_with_claude(content: list[dict], model: str = DEFAULT_MODEL) -> int:
    """Exact input-token count from the API (requires `pip install anthropic` + credentials)."""
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.count_tokens(model=model, messages=[{"role": "user", "content": content}])
    return resp.input_tokens
