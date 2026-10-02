"""Reproducible synthetic test set spanning content density.

    document     -- mostly white page with text      (expected: large savings)
    ui           -- flat panels, buttons, labels     (expected: large savings)
    natural      -- gradient sky, textured ground    (expected: moderate)
    dense        -- texture everywhere               (expected: ~no savings, honest worst case)
    screen_rec   -- video: typing in an editor, cut to a static slide, cut back,
                    persistent logo in the corner
Real photos/screenshots can be dropped into data/real/ and are picked up by the demo.
"""
from __future__ import annotations

import random
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WORDS = ("data structure quadtree heap union find hash token budget model vision "
         "encoder patch region scene frame overlay manifest adapter latency cost").split()


def _font(size: int):
    return ImageFont.load_default(size=size)


def _sentence(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n)).capitalize() + "."


def make_document(w: int = 1024, h: int = 1320, seed: int = 1) -> np.ndarray:
    rng = random.Random(seed)
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.text((90, 80), "Adaptive Token Allocation: Technical Note", fill="black", font=_font(30))
    y = 150
    while y < h - 260:
        if rng.random() < 0.15:
            d.text((90, y), _sentence(rng, 4).rstrip("."), fill=(20, 20, 120), font=_font(22))
            y += 40
        for _ in range(rng.randint(3, 6)):
            d.text((90, y), _sentence(rng, rng.randint(7, 11)), fill=(30, 30, 30), font=_font(17))
            y += 26
        y += 22
    d.rectangle((90, h - 220, w - 90, h - 120), outline=(120, 120, 120))
    d.text((110, h - 200), "Table 1: tokens before / after", fill="black", font=_font(17))
    return np.array(im)


def make_ui(w: int = 1280, h: int = 800, seed: int = 2) -> np.ndarray:
    rng = random.Random(seed)
    im = Image.new("RGB", (w, h), (243, 244, 246))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 230, h), fill=(31, 41, 55))
    for i, label in enumerate(["Dashboard", "Projects", "Tokens", "Reports", "Settings"]):
        d.text((28, 90 + i * 46), label, fill=(229, 231, 235), font=_font(18))
    d.rectangle((230, 0, w, 60), fill="white")
    d.text((260, 18), "Token Optimizer Console", fill=(17, 24, 39), font=_font(22))
    d.rounded_rectangle((w - 170, 14, w - 30, 46), 8, fill=(37, 99, 235))
    d.text((w - 148, 20), "Run batch", fill="white", font=_font(17))
    for r in range(2):
        for c in range(3):
            x0, y0 = 260 + c * 330, 90 + r * 210
            d.rounded_rectangle((x0, y0, x0 + 300, y0 + 180), 12, fill="white", outline=(229, 231, 235))
            d.text((x0 + 20, y0 + 18), rng.choice(["Images", "Videos", "Saved", "Latency"]),
                   fill=(107, 114, 128), font=_font(16))
            d.text((x0 + 20, y0 + 50), f"{rng.randint(10, 999)}k", fill=(17, 24, 39), font=_font(36))
    d.rounded_rectangle((260, 530, w - 30, h - 30), 12, fill="white", outline=(229, 231, 235))
    for i in range(5):
        d.text((285, 555 + i * 40), _sentence(rng, 6), fill=(55, 65, 81), font=_font(16))
    return np.array(im)


def make_natural(w: int = 1024, h: int = 768, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), np.float32)
    t = np.linspace(0, 1, h * 6 // 10)[:, None]
    img[: h * 6 // 10] = (np.array([70, 130, 210]) * (1 - t) + np.array([190, 220, 245]) * t)[:, None, :]
    cv2.circle(img, (w * 3 // 4, h // 5), 45, (255, 236, 160), -1)
    noise = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 2.0)
    ground = np.array([70, 120, 50], np.float32) + 28 * noise[..., None]
    ys = np.arange(h)[:, None]
    hill = (h * 0.6 + 40 * np.sin(np.arange(w) / 90.0))[None, :]
    mask = ys > hill
    img[mask] = ground[mask]
    for _ in range(6):
        x, y = int(rng.integers(40, w - 40)), int(rng.integers(h * 6 // 10, h - 60))
        cv2.rectangle(img, (x - 4, y), (x + 4, y + 40), (80, 55, 30), -1)
        cv2.circle(img, (x, y - 10), 26, (35, 90, 35), -1)
    return np.clip(img, 0, 255).astype(np.uint8)


def make_dense(w: int = 768, h: int = 768, seed: int = 4) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.normal(128, 60, (h, w, 3)).astype(np.float32)
    return np.clip(cv2.GaussianBlur(noise, (0, 0), 0.8), 0, 255).astype(np.uint8)


def _editor_frame(w: int, h: int, typed: str, cursor_on: bool, mouse: tuple[int, int]) -> Image.Image:
    im = Image.new("RGB", (w, h), (30, 30, 30))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w, 34), fill=(50, 50, 52))
    d.text((14, 8), "editor.py  -  Token Optimizer", fill=(200, 200, 200), font=_font(16))
    d.rectangle((0, 34, 48, h), fill=(37, 37, 38))
    lines = typed.split("\n")
    for i, line in enumerate(lines):
        d.text((8, 50 + i * 24), f"{i + 1:>2}", fill=(110, 110, 110), font=_font(15))
        d.text((62, 50 + i * 24), line, fill=(212, 212, 170), font=_font(16))
    if cursor_on:
        last = lines[-1]
        cx = 62 + int(d.textlength(last, font=_font(16)))
        cy = 50 + (len(lines) - 1) * 24
        d.rectangle((cx, cy, cx + 2, cy + 18), fill=(230, 230, 230))
    mx, my = mouse
    d.polygon([(mx, my), (mx, my + 18), (mx + 12, my + 13)], fill="white")
    return im


def _slide_frame(w: int, h: int) -> Image.Image:
    im = Image.new("RGB", (w, h), (250, 250, 250))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w, 90), fill=(37, 99, 235))
    d.text((40, 26), "Results: tokens before vs after", fill="white", font=_font(32))
    for i, (name, v) in enumerate([("document", 0.8), ("ui", 0.7), ("natural", 0.45), ("dense", 0.05)]):
        y = 150 + i * 90
        d.text((60, y + 12), name, fill=(40, 40, 40), font=_font(20))
        d.rectangle((220, y, 220 + int(500 * v), y + 50), fill=(16, 185, 129))
    return im


def _logo(im: Image.Image) -> None:
    w = im.size[0]
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((w - 120, im.size[1] - 56, w - 16, im.size[1] - 16), 8, fill=(220, 38, 38))
    d.text((w - 106, im.size[1] - 48), "VIT-DS", fill="white", font=_font(18))


def make_screen_recording(path: str | Path, w: int = 960, h: int = 600, fps: int = 10,
                          seconds: int = 12, seed: int = 5) -> Path:
    rng = random.Random(seed)
    code = ("def allocate(budget):\n    heap = MaxHeap()\n    for region in quadtree.leaves():\n"
            "        heap.push(region.sse, region)\n    while budget and heap:\n"
            "        budget -= split(heap.pop())\n    return manifest")
    path = Path(path)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    total = fps * seconds
    typed_at = 0
    mouse = [w // 2, h // 2]
    for f in range(total):
        t = f / fps
        if 4 <= t < 7:
            im = _slide_frame(w, h)
        else:
            if f % 2 == 0 and typed_at < len(code):
                typed_at += 2
            if rng.random() < 0.3:
                mouse[0] = min(w - 20, max(60, mouse[0] + rng.randint(-40, 40)))
                mouse[1] = min(h - 30, max(40, mouse[1] + rng.randint(-25, 25)))
            im = _editor_frame(w, h, code[:typed_at], (f // 5) % 2 == 0, tuple(mouse))
        _logo(im)
        vw.write(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
    vw.release()
    return path


def build_dataset(out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, fn in [("document", make_document), ("ui", make_ui),
                     ("natural", make_natural), ("dense", make_dense)]:
        p = out / f"{name}.png"
        cv2.imwrite(str(p), cv2.cvtColor(fn(), cv2.COLOR_RGB2BGR))
        paths[name] = p
    paths["screen_rec"] = make_screen_recording(out / "screen_rec.mp4")
    return paths
