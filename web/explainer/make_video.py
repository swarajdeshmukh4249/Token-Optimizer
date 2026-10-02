"""Render the narrated explainer video shown on the website's Explainer page.

    .venv/bin/python web/explainer/make_video.py

Every visual is computed from the real engine (quadtree, heap, pHash, union-find,
trie, adapter). Narration uses macOS `say`; captions are burned in so the video
also works muted. Outputs go to web/media/:
    explainer.mp4   the video (H.264 + AAC)
    chapters.json   chapter titles, start/end times and transcript lines
    poster.jpg      poster frame
    hero.png        quadtree overlay used on the landing page
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tokenopt.adapters.claude import build_payload  # noqa: E402
from tokenopt.ds.hash_table import hamming  # noqa: E402
from tokenopt.ds.quadtree import AdaptiveQuadtree  # noqa: E402
from tokenopt.ds.summed_area import SummedAreaTable  # noqa: E402
from tokenopt.image_opt import optimize_image, render_leaves, uniform_at_budget  # noqa: E402
from tokenopt.metrics import psnr  # noqa: E402
from tokenopt.phash import _D, phash, to_gray  # noqa: E402
from tokenopt.synth import make_document, make_screen_recording, make_ui  # noqa: E402
from tokenopt.video_opt import optimize_video, read_video  # noqa: E402

OUT = ROOT / "web" / "media"
W, H, FPS = 1280, 720, 24
VOICE, RATE, SR = "Samantha", 178, 22050
LEAD, GAP, TAIL = 0.5, 0.3, 1.0

# Palette shared with the website (web/index.html)
BG = (10, 11, 13)
PANEL = (19, 21, 26)
BORDER = (40, 44, 52)
TEXT = (236, 238, 241)
MUTED = (139, 145, 156)
LIME = (212, 255, 63)
CYAN = (103, 232, 249)
ORANGE = (255, 107, 53)
DIM = (62, 68, 80)

AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"


@lru_cache(None)
def F(size: int, weight: str = "demi") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(AVENIR, size, index={"bold": 0, "demi": 2, "medium": 5, "regular": 7}[weight])


@lru_cache(None)
def M(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MENLO, size, index=1 if bold else 0)


# ---------------------------------------------------------------- helpers
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def ease(x: float) -> float:
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def span(p: float, a: float, b: float) -> float:
    return ease((p - a) / (b - a))


def mix(c, a: float, base=BG):
    return tuple(int(base[i] + (c[i] - base[i]) * a) for i in range(3))


def pil(arr: np.ndarray, size: tuple[int, int] | None = None, nearest: bool = False) -> Image.Image:
    if size:
        arr = cv2.resize(arr, size, interpolation=cv2.INTER_NEAREST if nearest else cv2.INTER_AREA)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def paste(base: Image.Image, im: Image.Image, xy: tuple[int, int], a: float = 1.0) -> None:
    if a <= 0.001:
        return
    if a >= 0.999:
        base.paste(im, xy)
        return
    box = (xy[0], xy[1], xy[0] + im.width, xy[1] + im.height)
    base.paste(Image.blend(base.crop(box).convert(im.mode), im, a), xy)


def frame_box(d, x: int, y: int, w: int, h: int, color=BORDER, width: int = 1) -> None:
    d.rectangle((x - 1, y - 1, x + w, y + h), outline=color, width=width)


def panel(d, x, y, w, h, a=1.0, fill=PANEL):
    d.rounded_rectangle((x, y, x + w, y + h), 14, fill=mix(fill, a), outline=mix(BORDER, a))


def label(d, xy, s, a=1.0, color=MUTED, size=14):
    d.text(xy, s.upper(), font=M(size), fill=mix(color, a))


def arrow(d, x0, y, x1, a=1.0, color=MUTED):
    if a <= 0:
        return
    xe = x0 + (x1 - x0) * a
    d.line((x0, y, xe, y), fill=color, width=2)
    if a > 0.95:
        d.polygon([(x1, y), (x1 - 9, y - 6), (x1 - 9, y + 6)], fill=color)


def wrap(text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if font.getlength(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def counter(d, xy, value: float, a=1.0, size=56, color=TEXT):
    d.text(xy, f"{int(round(value)):,}", font=F(size, "bold"), fill=mix(color, a))


# ---------------------------------------------------------------- assets
class Assets:
    def __init__(self) -> None:
        print("  computing assets from the engine ...")
        self.ui = make_ui()
        self.doc = make_document()
        self.P = 16
        self.box = (56, 138, 720, 450)  # where the main image sits
        self.s = s = self.box[2] / self.ui.shape[1]
        self.ui_disp = cv2.resize(self.ui, (720, 450), interpolation=cv2.INTER_AREA)
        self.ui_dark = (self.ui_disp.astype(np.float32) * 0.40).astype(np.uint8)

        tree = AdaptiveQuadtree(self.ui, self.P)
        self.leaves = tree.build_recursive(40.0)
        self.baseline = tree.baseline_tokens
        self.depth = tree.depth()
        self.levels, self.level_counts = [], []
        for L in range(self.depth + 1):
            rects = self._frontier(tree.root, L)
            self.level_counts.append(len(rects))
            self.levels.append(self._outline(self.ui_dark, rects))
        self.final_overlay = self.levels[-1]

        # problem scene: grid lines + blank patches tinted
        sat = SummedAreaTable(self.ui)
        tint = self.ui_disp.astype(np.float32).copy()
        self.blank = 0
        for gy in range(tree.grid_h):
            for gx in range(tree.grid_w):
                x, y = gx * self.P, gy * self.P
                _, var = sat.stats(x, y, min(self.P, self.ui.shape[1] - x), min(self.P, self.ui.shape[0] - y))
                if var < 4:
                    self.blank += 1
                    x0, y0, x1, y1 = int(x * s), int(y * s), int((x + self.P) * s), int((y + self.P) * s)
                    tint[y0:y1, x0:x1] = tint[y0:y1, x0:x1] * 0.45 + np.array(ORANGE) * 0.55
        self.grid_img = self._grid(self.ui_disp.astype(np.float32), tree)
        self.blank_img = self._grid(tint, tree)

        # heap scene: best-first refinement under growing budgets
        self.heap_states = []
        for b in (1, 4, 13, 40, 100, 200, 300):
            lv = AdaptiveQuadtree(self.ui, self.P).build_budgeted(b, 0.0)
            rec = render_leaves(self.ui, lv, self.P)
            disp = cv2.resize(rec, (720, 450), interpolation=cv2.INTER_AREA)
            top = sorted([l for l in lv if l.splittable], key=lambda l: -l.sse)[:6]
            self.heap_states.append({"img": self._outline(disp, lv, colors=False, alpha=0.45),
                                     "tokens": len(lv), "psnr": psnr(self.ui, rec), "top": top})

        # fidelity at equal cost
        rec = render_leaves(self.ui, self.leaves, self.P)
        uni, self.uni_tokens = uniform_at_budget(self.ui, len(self.leaves), self.P)
        self.psnr_adaptive, self.psnr_uniform = psnr(self.ui, rec), psnr(self.ui, uni)
        cy0, cy1, cx0, cx1 = 546, 676, 272, 610
        zoom = lambda im: pil(cv2.resize(im[cy0:cy1, cx0:cx1], (560, 215), interpolation=cv2.INTER_CUBIC))
        self.crop_uni, self.crop_ada = zoom(uni), zoom(rec)
        self.curves = {name: self._curve(img) for name, img in (("UI screenshot", self.ui), ("Document", self.doc))}

        # video
        vid = ROOT / "data" / "synthetic" / "screen_rec.mp4"
        if not vid.exists():
            vid.parent.mkdir(parents=True, exist_ok=True)
            make_screen_recording(vid)
        self.frames, times = read_video(vid, sample_fps=2)
        self.vres = optimize_video(self.frames, times)
        self.hashes = [phash(f) for f in self.frames]

        # adapter
        self.doc_pay = build_payload(optimize_image(self.doc))
        print(f"  quadtree depth {self.depth}, {len(self.leaves)} leaves; video {self.vres.tokens} tokens")

    def _grid(self, base: np.ndarray, tree) -> Image.Image:
        g = base.copy()
        for gx in range(tree.grid_w + 1):
            xx = min(719, int(gx * self.P * self.s))
            g[:, xx] = g[:, xx] * 0.35 + 255 * 0.65
        for gy in range(tree.grid_h + 1):
            yy = min(449, int(gy * self.P * self.s))
            g[yy, :] = g[yy, :] * 0.35 + 255 * 0.65
        return pil(g)

    @staticmethod
    def _frontier(root, L):
        out, stack = [], [root]
        while stack:
            n = stack.pop()
            if n.depth == L or n.is_leaf:
                out.append(n)
            else:
                stack.extend(n.children)
        return out

    def _outline(self, base: np.ndarray, rects, colors=True, alpha=1.0) -> Image.Image:
        im = pil(base)
        d = ImageDraw.Draw(im)
        s = self.s
        for n in rects:
            c = ((ORANGE if n.patches == 1 else CYAN) if n.is_leaf else (150, 156, 168)) if colors else LIME
            d.rectangle((n.x * s, n.y * s, (n.x + n.w) * s - 1, (n.y + n.h) * s - 1), outline=c)
        return Image.blend(pil(base), im, alpha) if alpha < 1 else im

    def _curve(self, img):
        out = []
        for frac in (0.05, 0.1, 0.2, 0.3, 0.5, 0.75):
            r = optimize_image(img, budget_ratio=frac, var_threshold=0.0)
            u, _ = uniform_at_budget(img, r.tokens, self.P)
            out.append((frac, min(psnr(img, render_leaves(img, r.leaves, self.P)), 60), min(psnr(img, u), 60)))
        return out


# ---------------------------------------------------------------- scenes
@dataclass
class Scene:
    tag: str
    title: str
    lines: list[str]
    draw: Callable


def s_intro(A: Assets):
    def draw(img, d, t, dur, p):
        a = span(p, 0.0, 0.25)
        label(d, (64, 210), "pre-tokenization layer for vision-language models", a, LIME, 15)
        d.text((60, 244), "Adaptive", font=F(64, "bold"), fill=mix(TEXT, a))
        d.text((60, 314), "Token Optimizer", font=F(64, "bold"), fill=mix(TEXT, a))
        d.text((64, 430), "Pay for detail, not for blank space.", font=F(28, "medium"), fill=mix(MUTED, span(p, 0.25, 0.5)))
        b = span(p, 0.15, 0.55)
        paste(img, A.final_overlay.resize((520, 325)), (704, 180), b)
        if b > 0:
            frame_box(d, 704, 180, 520, 325, mix(BORDER, b))
    return draw


def s_problem(A: Assets):
    x, y, w, h = A.box

    def draw(img, d, t, dur, p):
        paste(img, pil(A.ui_disp), (x, y))
        paste(img, A.grid_img, (x, y), span(p, 0.08, 0.3))
        paste(img, A.blank_img, (x, y), span(p, 0.5, 0.62))
        frame_box(d, x, y, w, h)
        panel(d, 808, 138, 416, 450)
        label(d, (836, 164), "vision encoder")
        d.text((836, 190), "uniform grid", font=F(26), fill=TEXT)
        d.text((836, 226), "80 × 50 patches of 16 px", font=M(15), fill=MUTED)
        label(d, (836, 290), "input tokens")
        counter(d, (832, 312), A.baseline * span(p, 0.12, 0.42), size=64)
        c = span(p, 0.5, 0.62)
        label(d, (836, 420), "blank patches", c, ORANGE)
        counter(d, (832, 442), A.blank * c, c, size=44, color=ORANGE)
        d.text((836, 500), f"{100 * A.blank / A.baseline:.0f}% of the bill buys", font=F(18, "medium"), fill=mix(MUTED, c))
        d.text((836, 524), "pixels with nothing in them", font=F(18, "medium"), fill=mix(MUTED, c))
    return draw


def s_quadtree(A: Assets):
    x, y, w, h = A.box
    n = len(A.levels)

    def draw(img, d, t, dur, p):
        q = clamp01((p - 0.1) / 0.62) * (n - 1)
        i = int(q)
        paste(img, A.levels[i], (x, y))
        if i + 1 < n:
            paste(img, A.levels[i + 1], (x, y), ease(q - i))
        frame_box(d, x, y, w, h)
        panel(d, 808, 138, 416, 450)
        label(d, (836, 164), "rule applied to every region")
        code = ["if variance(region) > τ:", "    split into 4 children", "else:", "    keep as 1 token"]
        for k, line in enumerate(code):
            d.text((836, 194 + k * 26), line, font=M(16), fill=LIME if k in (0, 2) else TEXT)
        label(d, (836, 320), f"depth {min(n - 1, round(q))}")
        nxt = A.level_counts[min(n - 1, i + 1)]
        counter(d, (832, 342), A.level_counts[i] + (nxt - A.level_counts[i]) * ease(q - i), size=64, color=LIME)
        d.text((836, 418), f"tokens  (uniform: {A.baseline:,})", font=M(14), fill=MUTED)
        f = span(p, 0.78, 0.9)
        d.text((836, 452), f"−{100 * (1 - len(A.leaves) / A.baseline):.0f}%", font=F(46, "bold"), fill=mix(LIME, f))
        d.text((836, 524), "■ detail leaf (1 patch)", font=M(14), fill=ORANGE)
        d.text((836, 548), "■ merged leaf (many patches)", font=M(14), fill=CYAN)
    return draw


def s_sat(A: Assets):
    rng = np.random.default_rng(7)
    grid = rng.integers(0, 10, (6, 6))
    sat = grid.cumsum(0).cumsum(1)
    cs = 52
    gx0, gy0, sx0 = 96, 190, 660
    r0, c0, r1, c1 = 2, 1, 4, 3  # query rectangle: rows r0..r1, cols c0..c1

    def cells(d, x0, y0, vals, hl, a):
        for r in range(6):
            for c in range(6):
                X, Y = x0 + c * cs, y0 + r * cs
                fill = mix(LIME, 0.25 * a) if hl(r, c) else PANEL
                d.rectangle((X, Y, X + cs - 2, Y + cs - 2), fill=fill, outline=BORDER)
                d.text((X + cs / 2, Y + cs / 2), str(vals[r, c]), font=M(17), fill=TEXT, anchor="mm")

    def draw(img, d, t, dur, p):
        label(d, (gx0, 160), "pixels")
        cells(d, gx0, gy0, grid, lambda r, c: r0 <= r <= r1 and c0 <= c <= c1, span(p, 0.3, 0.45))
        b = span(p, 0.12, 0.3)
        label(d, (sx0, 160), "summed-area table", b)
        if b > 0:
            cells(d, sx0, gy0, sat, lambda r, c: False, 0)
        arrow(d, 430, gy0 + 3 * cs, sx0 - 30, b)
        e = span(p, 0.45, 0.6)
        corners = {"A": (r0 - 1, c0 - 1), "B": (r0 - 1, c1), "C": (r1, c0 - 1), "D": (r1, c1)}
        for k, (r, c) in corners.items():
            X, Y = sx0 + c * cs, gy0 + r * cs
            col = LIME if k in ("D", "A") else ORANGE
            d.rectangle((X, Y, X + cs - 2, Y + cs - 2), outline=mix(col, e), width=3)
            d.text((X + cs - 6, Y + 4), k, font=M(12, True), fill=mix(col, e), anchor="rt")
        total = sat[r1, c1] - sat[r0 - 1, c1] - sat[r1, c0 - 1] + sat[r0 - 1, c0 - 1]
        f = span(p, 0.58, 0.72)
        d.text((sx0, 520), f"sum = D − B − C + A = {total}", font=M(20, True), fill=mix(LIME, f))
        d.text((sx0, 552), f"(check: {grid[r0:r1 + 1, c0:c1 + 1].sum()})   4 lookups, any size", font=M(15), fill=mix(MUTED, f))
        g = span(p, 0.75, 0.88)
        d.text((gx0, 520), "variance = E[x²] − E[x]²", font=M(20, True), fill=mix(CYAN, g))
        d.text((gx0, 552), "second table over x² → O(1) per region", font=M(15), fill=mix(MUTED, g))
    return draw


def s_heap(A: Assets):
    x, y, w, h = A.box
    n = len(A.heap_states)

    def draw(img, d, t, dur, p):
        st = A.heap_states[min(n - 1, int(clamp01((p - 0.12) / 0.68) * n))]
        paste(img, st["img"], (x, y))
        frame_box(d, x, y, w, h)
        panel(d, 808, 138, 416, 450)
        label(d, (836, 160), "token budget")
        d.rounded_rectangle((836, 188, 1196, 200), 6, fill=DIM)
        d.rounded_rectangle((836, 188, 836 + 360 * st["tokens"] / 300, 200), 6, fill=LIME)
        d.text((836, 208), f"{st['tokens']} / 300 tokens    PSNR {st['psnr']:.1f} dB", font=M(14), fill=TEXT)
        label(d, (836, 254), "max-heap  (key = squared error)")
        top = st["top"]
        if top:
            mx = top[0].sse
            for k, leaf in enumerate(top):
                Y = 284 + k * 46
                d.text((836, Y), f"({leaf.x},{leaf.y}) {leaf.w}×{leaf.h}", font=M(14), fill=LIME if k == 0 else TEXT)
                d.rounded_rectangle((836, Y + 22, 836 + 300 * leaf.sse / mx, Y + 30), 4, fill=LIME if k == 0 else DIM)
                if k == 0:
                    d.text((1196, Y), "pop → split", font=M(13, True), fill=LIME, anchor="ra")
    return draw


def s_fidelity(A: Assets):
    def chart(d, x0, y0, cw, ch, name, curve, a):
        label(d, (x0, y0 - 26), name)
        ys = [v for _, ad, un in curve for v in (ad, un)]
        lo, hi = math.floor(min(ys) / 5) * 5, math.ceil(max(ys) / 5) * 5
        X = lambda f: x0 + f / 0.75 * cw
        Y = lambda v: y0 + ch - (v - lo) / (hi - lo) * ch
        d.line((x0, y0 + ch, x0 + cw, y0 + ch), fill=BORDER)
        for v in (lo, hi):
            d.text((x0 - 8, Y(v)), f"{v} dB", font=M(11), fill=MUTED, anchor="rm")
        k = max(2, math.ceil(len(curve) * a))
        for idx, col in ((2, MUTED), (1, LIME)):
            pts = [(X(c[0]), Y(c[idx])) for c in curve[:k]]
            d.line(pts, fill=col, width=3)
            for px, py in pts:
                d.ellipse((px - 3, py - 3, px + 3, py + 3), fill=col)

    def draw(img, d, t, dur, p):
        a = span(p, 0.15, 0.3)
        label(d, (56, 140), f"uniform grid · {A.uni_tokens} tokens · {A.psnr_uniform:.1f} dB", a)
        paste(img, A.crop_uni, (56, 166), a)
        b = span(p, 0.35, 0.5)
        label(d, (664, 140), f"adaptive quadtree · {len(A.leaves)} tokens · {A.psnr_adaptive:.1f} dB", b, LIME)
        paste(img, A.crop_ada, (664, 166), b)
        frame_box(d, 56, 166, 560, 215, mix(BORDER, a))
        frame_box(d, 664, 166, 560, 215, mix(LIME, b))
        c = span(p, 0.62, 0.95)
        if c > 0:
            for k, (name, curve) in enumerate(A.curves.items()):
                chart(d, 120 + k * 600, 440, 460, 120, f"{name}: PSNR vs token budget", curve, c)
            d.text((1060, 412), "— adaptive", font=M(13, True), fill=LIME)
            d.text((1160, 412), "— uniform", font=M(13, True), fill=MUTED)
    return draw


def s_phash(A: Assets):
    f = A.frames[3]
    g32 = cv2.resize(to_gray(f), (32, 32), interpolation=cv2.INTER_AREA)
    gray = pil(np.repeat(g32[:, :, None], 3, 2), (160, 160), nearest=True)
    mag = np.log1p(np.abs(_D @ g32 @ _D.T))
    heat = pil(mag[:, :, None] / mag.max() * np.array(LIME)[None, None], (160, 160), nearest=True)
    h = A.hashes[3]
    bits = [(h >> (63 - i)) & 1 for i in range(64)]
    others = [(2, "previous frame"), (3, "this frame"), (10, "slide (new scene)")]

    def draw(img, d, t, dur, p):
        st = [span(p, 0.1 + 0.08 * k, 0.18 + 0.08 * k) for k in range(5)]
        label(d, (56, 142), "sampled frame", st[0])
        paste(img, pil(f, (240, 150)), (56, 170), st[0])
        arrow(d, 304, 245, 340, st[1])
        label(d, (350, 142), "32×32 grey", st[1])
        paste(img, gray, (350, 165), st[1])
        arrow(d, 518, 245, 552, st[2])
        label(d, (562, 142), "DCT, keep 8×8", st[2])
        paste(img, heat, (562, 165), st[2])
        if st[2] > 0:
            d.rectangle((562, 165, 602, 205), outline=mix(ORANGE, st[2]), width=2)
        arrow(d, 730, 245, 764, st[3])
        label(d, (774, 142), "> median → bit", st[3])
        for i, bt in enumerate(bits):
            X, Y = 774 + (i % 8) * 20, 165 + (i // 8) * 20
            d.rectangle((X, Y, X + 18, Y + 18), fill=mix(LIME if bt else DIM, st[3]))
        label(d, (962, 142), "64-bit hash", st[4])
        d.text((962, 200), f"{h:016x}", font=M(20, True), fill=mix(LIME, st[4]))
        e = span(p, 0.62, 0.8)
        for k, (idx, name) in enumerate(others):
            X = 56 + k * 400
            paste(img, pil(A.frames[idx], (208, 130)), (X, 400), e)
            dist = hamming(A.hashes[idx], h)
            d.text((X + 222, 404), name, font=F(18), fill=mix(TEXT, e))
            d.text((X + 222, 436), f"{A.hashes[idx]:016x}", font=M(12), fill=mix(MUTED, e))
            d.text((X + 222, 466), f"{dist} bits differ", font=F(22, "bold"), fill=mix(LIME if dist <= 4 else ORANGE, e))
    return draw


def s_mih(A: Assets):
    stored = A.hashes[2]
    flips = [5, 20, 45]
    query = stored
    for b in flips:
        query ^= 1 << (63 - b)
    m = 5
    bounds = [(i * 64 // m, (i + 1) * 64 // m) for i in range(m)]
    band_of = [next(k for k, (lo, hi) in enumerate(bounds) if lo <= i < hi) for i in range(64)]
    match = [all(not (lo <= i < hi) for i in flips) for lo, hi in bounds]
    cw, x0 = 16, 170
    tints = [(36, 40, 50), (26, 29, 36)]

    def row(d, y, h_, a, mark):
        for i in range(64):
            bt = (h_ >> (63 - i)) & 1
            X = x0 + i * cw
            d.rectangle((X, y, X + cw - 2, y + 24), fill=mix(LIME if bt else tints[band_of[i] % 2], a))
            if mark and i in flips:
                d.rectangle((X - 1, y - 1, X + cw - 1, y + 25), outline=mix(ORANGE, mark), width=2)

    def draw(img, d, t, dur, p):
        a = span(p, 0.05, 0.2)
        d.text((56, 166), "stored", font=M(15), fill=mix(MUTED, a))
        d.text((56, 206), "query", font=M(15), fill=mix(MUTED, a))
        row(d, 162, stored, a, 0)
        row(d, 202, query, a, span(p, 0.2, 0.3))
        b = span(p, 0.25, 0.4)
        c = span(p, 0.42, 0.52)
        for k, (lo, hi) in enumerate(bounds):
            X0, X1 = x0 + lo * cw, x0 + hi * cw - 2
            d.line((X0, 240, X1, 240), fill=mix(MUTED, b), width=2)
            d.text(((X0 + X1) / 2, 250), f"band {k + 1}", font=M(13), fill=mix(MUTED, b), anchor="mt")
            d.text(((X0 + X1) / 2, 272), "match" if match[k] else "differs", font=M(14, True),
                   fill=mix(LIME if match[k] else ORANGE, c), anchor="mt")
        e = span(p, 0.55, 0.7)
        g = span(p, 0.7, 0.8)
        for k in range(m):
            X = 170 + k * 210
            d.text((X, 322), f"table {k + 1}  (chained)", font=M(13), fill=mix(MUTED, e))
            for r in range(4):
                Y = 348 + r * 50
                hit = match[k] and r == (k * 3 + 1) % 4
                d.rounded_rectangle((X, Y, X + 40, Y + 38), 6, fill=mix(PANEL, e),
                                    outline=mix(LIME if hit and g > 0 else BORDER, e), width=2)
                for cc in range((k + r * 2) % 3 + (2 if hit else 0)):
                    d.rounded_rectangle((X + 52 + cc * 38, Y + 10, X + 82 + cc * 38, Y + 28), 4,
                                        fill=mix(LIME if hit and cc == 0 and g > 0 else DIM, e))
        d.text((56, 568), "≤ 4 differing bits can spoil at most 4 of 5 bands  →  at least 1 band matches exactly",
               font=M(16, True), fill=mix(LIME, span(p, 0.3, 0.45)))
    return draw


def s_unionfind(A: Assets):
    tw, th, gap = 88, 55, 10
    thumbs = [pil(fr, (tw, th)) for fr in A.frames]
    pos = [(56 + (i % 12) * (tw + gap), 170 + (i // 12) * 170) for i in range(len(thumbs))]
    scene_of = {m: s for s, g in enumerate(A.vres.scenes) for m in g}
    colors = [LIME, CYAN, ORANGE, (200, 160, 255)]

    def draw(img, d, t, dur, p):
        for i, im in enumerate(thumbs):
            paste(img, im, pos[i], span(p, 0.02 + i * 0.006, 0.1 + i * 0.006))
        k_max = int(span(p, 0.15, 0.45) * (len(thumbs) - 1))
        for i in range(k_max):
            if scene_of[i] == scene_of[i + 1] and (i + 1) % 12:
                x0_, y0_ = pos[i][0] + tw, pos[i][1] + th // 2
                d.line((x0_ + 1, y0_, x0_ + gap - 1, y0_), fill=LIME, width=3)
        c = span(p, 0.5, 0.62)
        for i in range(len(thumbs)):
            col = colors[scene_of[i] % len(colors)]
            frame_box(d, *pos[i], tw, th, mix(col, c) if c > 0 else BORDER, 2 if c > 0 else 1)
        e = span(p, 0.7, 0.82)
        for i, r in enumerate(A.vres.frames):
            sym = {"key": "KEY", "delta": "Δ", "duplicate": "="}[r.role]
            col = {"key": LIME, "delta": CYAN, "duplicate": MUTED}[r.role]
            d.text((pos[i][0] + tw / 2, pos[i][1] + th + 8), sym, font=M(13, True), fill=mix(col, e), anchor="mt")
            d.text((pos[i][0] + tw / 2, pos[i][1] + th + 28), f"{r.tokens} tok", font=M(11), fill=mix(MUTED, e), anchor="mt")
        for s, g in enumerate(A.vres.scenes[:3]):
            d.text((56 + s * 400, 540), f"scene {s + 1}: frames {g[0]}–{g[-1]}", font=F(20), fill=mix(colors[s], c))
    return draw


def s_trie(A: Assets):
    disp = pil(A.frames[16], (480, 300))
    nodes = {}
    tx0, ty0, tw_, lvl_h = 640, 190, 580, 78
    for depth in range(5):
        for k in range(2 ** depth):
            nodes[(depth, k)] = (tx0 + (k + 0.5) * tw_ / 2 ** depth, ty0 + depth * lvl_h)
    path = [0, 1, 3, 6, 13]
    scattered = [2, 5, 9]

    def draw(img, d, t, dur, p):
        a = span(p, 0.05, 0.2)
        paste(img, disp, (56, 170), a)
        for gx in range(0, 481, 32):
            d.line((56 + gx, 170, 56 + gx, 470), fill=mix((90, 96, 110), a * 0.6))
        for gy in range(0, 301, 32):
            d.line((56, 170 + gy, 536, 170 + gy), fill=mix((90, 96, 110), a * 0.6))
        b = span(p, 0.3, 0.42)
        d.rectangle((504, 426, 536, 458), outline=mix(LIME, b), width=3)
        d.rectangle((120, 202, 152, 234), outline=mix(ORANGE, b), width=3)
        d.text((56, 490), "key = block position + pHash(block)", font=M(15), fill=mix(TEXT, a))
        d.text((56, 516), "■ logo block (static)   ■ code block (changing)", font=M(13), fill=mix(MUTED, b))
        for (depth, k), (X, Y) in nodes.items():
            if depth < 4:
                for c in (0, 1):
                    X2, Y2 = nodes[(depth + 1, 2 * k + c)]
                    on = path[depth] == k and path[depth + 1] == 2 * k + c and b > 0
                    d.line((X, Y, X2, Y2), fill=mix(LIME if on else DIM, max(a, 0.01)), width=3 if on else 1)
            d.ellipse((X - 7, Y - 7, X + 7, Y + 7), fill=mix(PANEL, a), outline=mix(DIM, a))
        X, Y = nodes[(4, path[4])]
        d.ellipse((X - 9, Y - 9, X + 9, Y + 9), fill=mix(LIME, b))
        d.text((X, Y + 18), f"×{1 + int(17 * span(p, 0.42, 0.75))}", font=M(15, True), fill=mix(LIME, b), anchor="mt")
        for j, leaf in enumerate(scattered):
            e = span(p, 0.45 + 0.07 * j, 0.52 + 0.07 * j)
            X, Y = nodes[(4, leaf)]
            d.ellipse((X - 8, Y - 8, X + 8, Y + 8), fill=mix(ORANGE, e))
            d.text((X, Y + 18), "×1", font=M(14), fill=mix(ORANGE, e), anchor="mt")
        d.text((640, 556), "count ≥ ½ of frames  →  static overlay: send once, then reference",
               font=M(15, True), fill=mix(LIME, span(p, 0.78, 0.9)))
    return draw


def s_results(A: Assets):
    fr = A.vres.frames
    per = A.vres.baseline_tokens // len(fr)
    x0, y0, cw, ch = 56, 250, 1168, 290
    bw = cw / len(fr)

    def draw(img, d, t, dur, p):
        a = span(p, 0.05, 0.6)
        shown = math.ceil(a * len(fr))
        d.line((x0, y0, x0 + cw, y0), fill=MUTED)
        d.text((x0 + cw, y0 - 8), f"uniform baseline: {per:,} tokens / frame", font=M(13), fill=MUTED, anchor="rb")
        d.line((x0, y0 + ch, x0 + cw, y0 + ch), fill=BORDER)
        total = 0
        for i, f in enumerate(fr[:shown]):
            hgt = (6 + 94 * math.log10(f.tokens + 1) / math.log10(per + 1)) if f.tokens else 1.5
            col = {"key": LIME, "delta": CYAN, "duplicate": DIM}[f.role]
            X = x0 + i * bw
            d.rectangle((X + 3, y0 + ch - ch * hgt / 100, X + bw - 3, y0 + ch), fill=col)
            total += f.tokens
        label(d, (56, 140), "uniform")
        counter(d, (52, 158), per * shown, size=48, color=MUTED)
        label(d, (420, 140), "optimized", 1, LIME)
        counter(d, (416, 158), total, size=48, color=LIME)
        c = span(p, 0.62, 0.75)
        d.text((800, 166), f"−{100 * (1 - A.vres.tokens / A.vres.baseline_tokens):.0f}%", font=F(48, "bold"), fill=mix(LIME, c))
        d.text((56, 556), "■ key", font=M(14), fill=LIME)
        d.text((130, 556), "■ delta", font=M(14), fill=CYAN)
        d.text((220, 556), "■ duplicate (0 tokens)", font=M(14), fill=MUTED)
        d.text((1224, 556), f"min fidelity {min(f.psnr for f in fr):.1f} dB · log-scaled bars", font=M(14),
               fill=mix(MUTED, c), anchor="ra")
    return draw


def s_manifest(A: Assets):
    js = ["{", '  "schema": "otm/0.1",', '  "patch_size": 16,', f'  "baseline_tokens": {A.baseline},',
          f'  "optimized_tokens": {len(A.leaves)},', '  "frames": [{ "role": "key",', '    "regions": [']
    js += [f'      {{"x": {l.x}, "y": {l.y}, "w": {l.w}, "h": {l.h}, "tokens": 1}},' for l in A.leaves[:4]]
    js += ["      ...", "    ]}]", "}"]
    total_chars = sum(len(s) for s in js)
    pay = A.doc_pay
    crops = [c for _, c in pay.images[1:4]]

    def draw(img, d, t, dur, p):
        panel(d, 56, 138, 560, 420)
        label(d, (80, 156), "optimized token manifest (json)")
        chars = int(span(p, 0.05, 0.4) * total_chars)
        y = 190
        for line in js:
            if chars <= 0:
                break
            d.text((80, y), line[:chars], font=M(14), fill=CYAN if line.strip().startswith('{"x"') else TEXT)
            chars -= len(line)
            y += 24
        a = span(p, 0.42, 0.55)
        arrow(d, 626, 350, 690, a, LIME)
        d.text((658, 326), "adapter", font=M(13), fill=mix(LIME, a), anchor="mm")
        b = span(p, 0.5, 0.7)
        label(d, (704, 140), "claude payload: overview + detail crops", b)
        paste(img, pil(pay.images[0][1], (190, 245)), (704, 168), b)
        if b > 0:
            frame_box(d, 704, 168, 190, 245, mix(BORDER, b))
        cy = 168
        for k, c in enumerate(crops):
            hgt = min(120, int(c.shape[0] * 320 / c.shape[1]))
            paste(img, pil(c, (320, hgt)), (904, cy), span(p, 0.55 + 0.05 * k, 0.65 + 0.05 * k))
            cy += hgt + 8
        e = span(p, 0.72, 0.85)
        d.text((704, 436), f"{pay.full_tokens_est:,} → {pay.payload_tokens_est:,}", font=M(34, True), fill=mix(LIME, e))
        d.text((704, 486), f"estimated tokens, this document page (−{100 * pay.reduction:.0f}%)", font=M(14), fill=mix(MUTED, e))
        d.text((704, 510), "exact count: Claude count_tokens endpoint", font=M(14), fill=mix(MUTED, e))
    return draw


def s_limits(A: Assets):
    left = ["Dense texture: ~0% saved (nothing is redundant)", "Fidelity is pixel-level (PSNR / SSIM)",
            "Test inputs are synthetic so far", "Variance over-splits gradients and noise"]
    right = ["Answer accuracy with a real vision model", "Real documents, UIs and recordings",
             "A detail-energy split rule", "Break-even: preprocessing vs tokens saved"]

    def draw(img, d, t, dur, p):
        for title, items, color, x, a0 in (("Limits today", left, ORANGE, 56, 0.05),
                                            ("Next steps", right, LIME, 664, 0.4)):
            a = span(p, a0, a0 + 0.12)
            panel(d, x, 138, 560, 360, a)
            d.text((x + 28, 160), title, font=F(28), fill=mix(color, a))
            for k, item in enumerate(items):
                b = span(p, a0 + 0.05 + 0.05 * k, a0 + 0.12 + 0.05 * k)
                d.text((x + 28, 228 + k * 62), "→", font=M(18, True), fill=mix(color, b))
                d.text((x + 60, 224 + k * 62), item, font=F(20, "medium"), fill=mix(TEXT, b))
        d.text((640, 540), "Try every step in the live playground", font=F(26), fill=mix(TEXT, span(p, 0.82, 0.95)), anchor="mm")
    return draw


def scenes(A: Assets) -> list[Scene]:
    red = 100 * (1 - len(A.leaves) / A.baseline)
    v = A.vres
    return [
        Scene("00", "Adaptive Token Optimizer", [
            "This is the Adaptive Token Optimizer.",
            "It sits in front of a vision language model, and decides how many tokens each part of an image or a video really deserves, before the model ever sees it.",
        ], s_intro(A)),
        Scene("01 · The problem", "Every patch costs the same", [
            "When you send an image to a multimodal model, the vision encoder cuts it into a uniform grid of small patches, and every patch becomes one input token.",
            f"This screenshot is eighty by fifty patches, so it costs {A.baseline:,} tokens.",
            "Now look at the highlighted patches. They are completely blank, yet they cost exactly as much as the patches full of text.",
            "Over every frame of a video, and every turn of a conversation, that waste keeps repeating.",
        ], s_problem(A)),
        Scene("02 · Adaptive quadtree", "Split only where there is detail", [
            "Our idea is to make the allocation decision before tokenization, using a quadtree.",
            "We start with the whole image as a single region.",
            "If a region's pixel variance is above a threshold, it contains detail, so we split it into four children.",
            "Flat regions stop splitting early, and every final leaf becomes exactly one token.",
            f"For this screenshot, that is {len(A.leaves)} tokens instead of {A.baseline:,}: {red:.0f} percent fewer.",
        ], s_quadtree(A)),
        Scene("03 · Summed-area table", "Variance of any region in O(1)", [
            "Computing the variance of every region by scanning its pixels would be slow.",
            "So we precompute a summed area table, where each cell stores the sum of all pixels above and to its left.",
            "The sum of any rectangle then needs only four lookups: D, minus B, minus C, plus A.",
            "A second table of squared pixels gives the variance too, so building the whole tree costs time proportional to the number of nodes, not the number of pixels.",
        ], s_sat(A)),
        Scene("04 · Max-heap budget", "Spend a fixed budget where it matters", [
            "Sometimes we need a hard limit, for example, at most three hundred tokens.",
            "For that, regions go into a max heap, keyed on their squared error: how much detail we would lose by keeping the region as one token.",
            "We repeatedly pop the worst region, split it, and push its children back, until the budget is spent.",
            "Watch the text sharpen first, while the empty background stays coarse.",
        ], s_heap(A)),
        Scene("05 · Fidelity", "Better than shrinking the image", [
            "Is this actually better than just shrinking the image? We compare both at the same number of tokens.",
            "Uniform downscaling blurs everything, including the text.",
            f"The adaptive version keeps the text sharp and only simplifies the empty areas: {A.psnr_adaptive:.0f} decibels of fidelity, against {A.psnr_uniform:.0f}.",
            "Across the whole budget range, the adaptive curve stays above the uniform one.",
        ], s_fidelity(A)),
        Scene("06 · Perceptual hash", "A 64-bit fingerprint per frame", [
            "Video adds a second kind of redundancy: time.",
            "For every sampled frame, we compute a perceptual hash.",
            "The frame is shrunk to thirty two by thirty two pixels, transformed with a discrete cosine transform, and its sixty four lowest frequencies are compared with their median, giving sixty four bits.",
            "Frames that look alike differ in only a few bits, while a different scene differs in about half of them.",
        ], s_phash(A)),
        Scene("07 · Multi-index hash table", "Find every near-duplicate, fast", [
            "To find near duplicates without comparing against every earlier frame, we cut each hash into five bands.",
            "Each band is stored in its own hash table, with separate chaining for collisions.",
            "Here is the pigeonhole trick: if two hashes differ in at most four bits, those bits can spoil at most four bands, so at least one band must match exactly.",
            "So we only look inside a few buckets, and we are still guaranteed to find every near duplicate, even when a video cuts back to an earlier scene.",
        ], s_mih(A)),
        Scene("08 · Union-find", "Group frames into scenes", [
            "Next, union find groups the frames into scenes.",
            "Consecutive frames that look similar are merged into the same set, and so are duplicates.",
            f"Here we end up with {len(v.scenes)} scenes: the code editor, the results slide, and the editor again.",
            "Each scene's first frame is a key frame and is encoded fully. Later frames send only the regions that changed, and duplicates cost zero tokens.",
        ], s_unionfind(A)),
        Scene("09 · Overlay trie", "Send static overlays once", [
            "Some things never change, like a logo or a toolbar.",
            "We cut each frame into blocks, and insert each block's position and hash into a binary trie that counts how often each key appears.",
            "The logo block reaches the same leaf in almost every frame, while changing blocks scatter across different leaves.",
            "Keys seen in at least half of the frames are static overlays. The model receives them once, and afterwards they are only referenced.",
        ], s_trie(A)),
        Scene("10 · Result", f"From {v.baseline_tokens:,} to {v.tokens:,} tokens", [
            f"Put together, on our twelve second screen recording, {len(v.frames)} sampled frames would normally cost {v.baseline_tokens:,} tokens.",
            f"The optimizer sends {v.tokens:,}: a few key frames, small deltas, and free duplicates.",
            f"And every frame the model receives stays above {math.floor(min(f.psnr for f in v.frames))} decibels of fidelity.",
        ], s_results(A)),
        Scene("11 · Manifest & adapter", "Model-agnostic output", [
            "The engine's output is an Optimized Token Manifest: a model agnostic list of regions, each worth one token.",
            "A thin adapter converts the manifest for a specific model.",
            "For Claude, which charges images by pixel area, we send one low resolution overview, plus full resolution crops of only the detailed regions.",
            f"For this document page, that is an estimated {100 * A.doc_pay.reduction:.0f} percent fewer tokens, and the exact count can be confirmed with Claude's token counting endpoint.",
        ], s_manifest(A)),
        Scene("12 · Limits & next steps", "What we have not proven yet", [
            "To be clear about the limits: dense textures gain nothing, because nothing in them is redundant.",
            "Our fidelity numbers are pixel based so far, and our test inputs are synthetic.",
            "Next, we will measure answer accuracy with a real vision model on real documents and screen recordings, and try a better split rule than plain variance.",
            "That is the Adaptive Token Optimizer. You can try every step yourself in the live playground.",
        ], s_limits(A)),
    ]


# ---------------------------------------------------------------- audio + render
def synth(text: str, tmp: Path, idx: int) -> np.ndarray:
    path = tmp / f"line_{idx:03d}.wav"
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "--file-format=WAVE",
                    f"--data-format=LEI16@{SR}", "-o", str(path), text], check=True)
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def chrome(img, d, sc: Scene, t: float, caption: str | None, progress: float) -> None:
    a = span(t, 0.0, 0.45)
    if sc.tag != "00":
        d.text((56, 40), sc.tag.upper(), font=M(15, True), fill=mix(LIME, a))
        d.text((54, 64), sc.title, font=F(36), fill=mix(TEXT, a))
    d.text((1224, 44), "TokenOpt", font=F(18), fill=MUTED, anchor="ra")
    if caption:
        lines = wrap(caption, F(21, "medium"), 1080)[:3]
        top = 700 - 14 - 30 * len(lines)
        d.rounded_rectangle((80, top - 12, 1200, 696), 12, fill=(16, 18, 22), outline=BORDER)
        for k, line in enumerate(lines):
            d.text((640, top + k * 30), line, font=F(21, "medium"), fill=TEXT, anchor="mt")
    d.rectangle((0, H - 3, int(W * progress), H), fill=LIME)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    A = Assets()
    scs = scenes(A)
    bg = Image.new("RGB", (W, H), BG)
    bd = ImageDraw.Draw(bg)
    for yy in range(20, H, 40):
        for xx in range(20, W, 40):
            bd.point((xx, yy), fill=(30, 33, 40))

    print("  synthesizing narration ...")
    plans, audio = [], []
    with tempfile.TemporaryDirectory() as td:
        k = 0
        for sc in scs:
            t, cues, chunks = LEAD, [], [np.zeros(int(LEAD * SR), np.int16)]
            for line in sc.lines:
                clip = synth(line, Path(td), k)
                k += 1
                cues.append((t, t + len(clip) / SR, line))
                chunks += [clip, np.zeros(int(GAP * SR), np.int16)]
                t += len(clip) / SR + GAP
            nf = int(round((t - GAP + TAIL) * FPS))
            pcm = np.concatenate(chunks)
            n_samples = nf * SR // FPS
            pcm = np.concatenate([pcm, np.zeros(max(0, n_samples - len(pcm)), np.int16)])[:n_samples]
            audio.append(pcm)
            plans.append((sc, nf, cues))

    total = sum(nf for _, nf, _ in plans) / FPS
    print(f"  rendering {total:.0f}s of video ...")
    silent = OUT / "_video.mp4"
    writer = imageio_ffmpeg.write_frames(str(silent), (W, H), fps=FPS, codec="libx264",
                                         pix_fmt_out="yuv420p", quality=8, macro_block_size=8)
    writer.send(None)
    chapters, elapsed = [], 0.0
    for idx, (sc, nf, cues) in enumerate(plans):
        dur = nf / FPS
        chapters.append({"tag": sc.tag, "title": sc.title, "start": round(elapsed, 2),
                         "end": round(elapsed + dur, 2), "lines": sc.lines,
                         "cues": [{"start": round(elapsed + s0, 2), "end": round(elapsed + s1, 2), "text": c}
                                  for s0, s1, c in cues]})
        for fi in range(nf):
            t = fi / FPS
            img = bg.copy()
            d = ImageDraw.Draw(img)
            sc.draw(img, d, t, dur, t / dur)
            cap = next((c for s0, s1, c in cues if s0 - 0.15 <= t <= s1 + GAP), None)
            chrome(img, d, sc, t, cap, (elapsed + t) / total)
            writer.send(np.asarray(img).tobytes())
            if idx == 0 and fi == int(nf * 0.85):
                img.save(OUT / "poster.jpg", quality=90)
        elapsed += dur
        print(f"    {sc.tag:<30} {dur:5.1f}s")
    writer.close()

    wav = OUT / "_audio.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.concatenate(audio).tobytes())
    final = OUT / "explainer.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
                    str(final)], check=True)
    silent.unlink()
    wav.unlink()

    A.final_overlay.save(OUT / "hero.png")
    (OUT / "chapters.json").write_text(json.dumps({"duration": round(elapsed, 2), "chapters": chapters}, indent=1))
    print(f"  wrote {final} ({final.stat().st_size / 1e6:.1f} MB, {elapsed:.0f}s)")


if __name__ == "__main__":
    main()
