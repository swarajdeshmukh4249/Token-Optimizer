"""Video pipeline: temporal redundancy elimination on top of the image quadtree.

Pass 1  frame signatures
        * 64-bit pHash per sampled frame.
        * MultiIndexHashTable finds near-duplicates of ANY earlier frame (not just
          the previous one), so cutting back to an earlier slide is caught too.
          Hash hits are confirmed at pixel level before being trusted.
        * UnionFind merges consecutive similar frames and duplicates into scenes.
Pass 2  recurring overlays
        * Every frame is cut into fixed blocks; (block position || block pHash) keys
          go into a BitTrie. Keys seen in many frames are static overlays (logos,
          toolbars) -- sent once, then referenced.
Pass 3  encoding (what the model is charged for)
        duplicate -> 0 tokens, reference earlier frame
        key       -> first frame of a scene: full quadtree allocation
        delta     -> later frame of a scene: only quadtree leaves that changed
                     versus what the model already has
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from .cost import grid_tokens
from .ds.hash_table import MultiIndexHashTable, hamming
from .ds.quadtree import AdaptiveQuadtree, QuadNode
from .ds.trie import BitTrie
from .ds.union_find import UnionFind
from .image_opt import DEFAULT_PATCH, DEFAULT_VAR_THRESHOLD, render_leaves
from .manifest import region
from .metrics import psnr
from .phash import phash


@dataclass
class FrameRecord:
    index: int
    t: float
    role: str          # key | delta | duplicate
    ref: int | None    # frame this one builds on
    scene: int
    tokens: int
    phash: int
    psnr: float
    overlay_reused: int = 0
    regions: list[dict] = field(default_factory=list)


@dataclass
class VideoResult:
    frames: list[FrameRecord]
    scenes: list[list[int]]
    overlays: list[dict]
    width: int
    height: int
    patch: int
    baseline_tokens: int
    elapsed_ms: float
    params: dict
    recon: list[np.ndarray]

    @property
    def tokens(self) -> int:
        return sum(f.tokens for f in self.frames)


def read_video(path: str, sample_fps: float = 2.0, max_side: int = 960):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"could not open video: {path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / sample_fps))
    frames, times, i = [], [], 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if i % step == 0:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            if max(h, w) > max_side:
                s = max_side / max(h, w)
                rgb = cv2.resize(rgb, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
            frames.append(rgb)
            times.append(i / src_fps)
        i += 1
    cap.release()
    return frames, times


def _diff_grid(a: np.ndarray, b: np.ndarray, grid_w: int, grid_h: int) -> np.ndarray:
    """Mean absolute pixel difference per patch cell."""
    d = np.abs(a.astype(np.float32) - b.astype(np.float32)).mean(axis=2)
    return cv2.resize(d, (grid_w, grid_h), interpolation=cv2.INTER_AREA)


def _leaf_block(leaf: QuadNode, ob: int, bgw: int, bgh: int) -> int | None:
    """Index of the overlay block that fully contains this leaf, if any."""
    bx, by = leaf.gx // ob, leaf.gy // ob
    if (leaf.gx + leaf.gw - 1) // ob != bx or (leaf.gy + leaf.gh - 1) // ob != by:
        return None
    if bx >= bgw or by >= bgh:
        return None
    return by * bgw + bx


def optimize_video(frames: list[np.ndarray], times: list[float] | None = None,
                   patch: int = DEFAULT_PATCH, var_threshold: float = DEFAULT_VAR_THRESHOLD,
                   dup_distance: int = 4, scene_distance: int = 14,
                   change_threshold: float = 6.0, overlay_block: int = 4,
                   overlay_min_frac: float = 0.5) -> VideoResult:
    t0 = time.perf_counter()
    n = len(frames)
    times = times if times is not None else [float(i) for i in range(n)]
    H, W = frames[0].shape[:2]
    gw, gh = math.ceil(W / patch), math.ceil(H / patch)

    # ---- pass 1: signatures, near-duplicates, scenes -----------------------
    hashes = [phash(f) for f in frames]
    index = MultiIndexHashTable(max_distance=dup_distance)
    uf = UnionFind(n)
    dup_of: list[int | None] = [None] * n
    for i, h in enumerate(hashes):
        for _, j in index.query(h):
            if _diff_grid(frames[i], frames[j], gw, gh).max() <= change_threshold:
                dup_of[i] = j
                uf.union(i, j)
                break
        if dup_of[i] is None:
            index.add(h, i)
        if i and hamming(h, hashes[i - 1]) <= scene_distance:
            uf.union(i, i - 1)
    scenes = uf.groups()
    scene_of = {m: s for s, group in enumerate(scenes) for m in group}

    # ---- pass 2: recurring overlays via the trie ---------------------------
    bpx = overlay_block * patch
    bgw, bgh = W // bpx, H // bpx
    idx_bits = max(1, (bgw * bgh - 1).bit_length())
    trie = BitTrie(64 + idx_bits)
    block_keys: list[dict[int, int]] = []
    kept = [i for i in range(n) if dup_of[i] is None]
    for i in range(n):
        keys = {}
        if dup_of[i] is None:
            for by in range(bgh):
                for bx in range(bgw):
                    blk = frames[i][by * bpx:(by + 1) * bpx, bx * bpx:(bx + 1) * bpx]
                    b = by * bgw + bx
                    keys[b] = (b << 64) | phash(blk)
                    trie.insert(keys[b])
        block_keys.append(keys)
    min_count = max(2, math.ceil(overlay_min_frac * len(kept)))
    static = {k for k, _ in trie.frequent(min_count)}

    # ---- pass 3: encode -----------------------------------------------------
    recon: list[np.ndarray | None] = [None] * n
    records: list[FrameRecord] = []
    last_in_scene: dict[int, int] = {}
    sent_overlay: dict[int, np.ndarray] = {}
    for i, f in enumerate(frames):
        scene = scene_of[i]
        if dup_of[i] is not None:
            ref = dup_of[i]
            recon[i] = recon[ref]
            records.append(FrameRecord(i, times[i], "duplicate", ref, scene, 0, hashes[i],
                                       psnr(f, recon[i])))
            last_in_scene[scene] = i
            continue

        leaves = AdaptiveQuadtree(f, patch).build_recursive(var_threshold)
        ref = last_in_scene.get(scene)
        if ref is None:
            role, canvas, send = "key", np.zeros_like(f), leaves
        else:
            role, canvas = "delta", recon[ref].copy()
            changed = _diff_grid(f, recon[ref], gw, gh)
            send = [l for l in leaves
                    if changed[l.gy:l.gy + l.gh, l.gx:l.gx + l.gw].max() > change_threshold]

        # Leaves inside an overlay block the model has already seen cost nothing.
        reused: list[tuple[QuadNode, int]] = []
        to_send: list[QuadNode] = []
        for leaf in send:
            b = _leaf_block(leaf, overlay_block, bgw, bgh)
            key = block_keys[i].get(b) if b is not None else None
            if key in static and key in sent_overlay:
                bx, by = (b % bgw) * bpx, (b // bgw) * bpx
                cached = sent_overlay[key]
                if np.abs(cached.astype(np.float32) -
                          f[by:by + bpx, bx:bx + bpx].astype(np.float32)).mean() <= change_threshold:
                    reused.append((leaf, key))
                    continue
            to_send.append(leaf)

        render_leaves(f, to_send, patch, canvas)
        for leaf, key in reused:
            b = int(key >> 64)
            bx, by = (b % bgw) * bpx, (b // bgw) * bpx
            canvas[leaf.y:leaf.y + leaf.h, leaf.x:leaf.x + leaf.w] = \
                sent_overlay[key][leaf.y - by:leaf.y - by + leaf.h, leaf.x - bx:leaf.x - bx + leaf.w]
        for b, key in block_keys[i].items():
            if key in static and key not in sent_overlay:
                bx, by = (b % bgw) * bpx, (b // bgw) * bpx
                sent_overlay[key] = canvas[by:by + bpx, bx:bx + bpx].copy()

        recon[i] = canvas
        last_in_scene[scene] = i
        records.append(FrameRecord(i, times[i], role, ref, scene, len(to_send), hashes[i],
                                   psnr(f, canvas), len(reused), [region(l) for l in to_send]))

    overlays = [{"block": int(k >> 64), "x": int((k >> 64) % bgw) * bpx,
                 "y": int((k >> 64) // bgw) * bpx, "size": bpx,
                 "phash": f"{k & ((1 << 64) - 1):016x}", "frames": trie.count(k)}
                for k in sorted(static)]
    return VideoResult(
        frames=records, scenes=scenes, overlays=overlays, width=W, height=H, patch=patch,
        baseline_tokens=n * grid_tokens(W, H, patch),
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        params={"var_threshold": var_threshold, "dup_distance": dup_distance,
                "scene_distance": scene_distance, "change_threshold": change_threshold,
                "overlay_block_px": bpx, "overlay_min_frac": overlay_min_frac},
        recon=recon,
    )
