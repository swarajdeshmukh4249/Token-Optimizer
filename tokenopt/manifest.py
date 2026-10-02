"""Optimized Token Manifest (OTM): the model-agnostic output of the optimizer.

Each region is one token: a rectangle of the source that the adapter must
present to the model as a single patch. Adapters translate this into a concrete
provider format; the core engine never needs to know which model is downstream.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ds.quadtree import QuadNode

SCHEMA = "otm/0.1"


def region(leaf: QuadNode) -> dict[str, Any]:
    return {
        "x": leaf.x, "y": leaf.y, "w": leaf.w, "h": leaf.h,
        "grid": [leaf.gx, leaf.gy, leaf.gw, leaf.gh],
        "tokens": 1,
        "variance": round(leaf.var, 2),
    }


def image_manifest(source: str, result) -> dict[str, Any]:
    h, w = result.image.shape[:2]
    return {
        "schema": SCHEMA,
        "kind": "image",
        "source": {"path": source, "width": w, "height": h},
        "patch_size": result.patch,
        "params": {"var_threshold": result.var_threshold, "budget": result.budget},
        "baseline_tokens": result.baseline_tokens,
        "optimized_tokens": result.tokens,
        "reduction_pct": round(100 * result.reduction, 2),
        "timing_ms": round(result.elapsed_ms, 2),
        "frames": [{"index": 0, "role": "key", "ref": None,
                    "regions": [region(l) for l in result.leaves]}],
    }


def video_manifest(source: str, result) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": "video",
        "source": {"path": source, "width": result.width, "height": result.height,
                   "sampled_frames": len(result.frames)},
        "patch_size": result.patch,
        "params": result.params,
        "baseline_tokens": result.baseline_tokens,
        "optimized_tokens": result.tokens,
        "reduction_pct": round(100 * (1 - result.tokens / result.baseline_tokens), 2),
        "timing_ms": round(result.elapsed_ms, 2),
        "scenes": result.scenes,
        "static_overlays": result.overlays,
        "frames": [
            {"index": f.index, "t": round(f.t, 3), "role": f.role, "ref": f.ref,
             "scene": f.scene, "tokens": f.tokens, "phash": f"{f.phash:016x}",
             "overlay_reused": f.overlay_reused, "regions": f.regions}
            for f in result.frames
        ],
    }


def save(manifest: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(manifest, indent=1))
