"""Local web server for the Token Optimizer UI (standard library only).

    .venv/bin/python web/server.py [port]   -> http://localhost:8420

Static files come from web/, figures from results/, and a small JSON API runs
the real optimizer on samples or uploaded files.
"""
from __future__ import annotations

import base64
import json
import math
import mimetypes
import sys
import tempfile
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tokenopt.adapters.claude import build_payload  # noqa: E402
from tokenopt.image_opt import load_image, optimize_image, render_leaves, uniform_at_budget  # noqa: E402
from tokenopt.metrics import psnr, ssim  # noqa: E402
from tokenopt.synth import build_dataset  # noqa: E402
from tokenopt.video_opt import optimize_video, read_video  # noqa: E402


def quadtree_overlay(img: np.ndarray, leaves, patch: int) -> np.ndarray:
    """Dark-theme overlay: darkened image, orange = single-patch detail, cyan = merged leaf."""
    out = (img.astype(np.float32) * 0.42).astype(np.uint8)
    for leaf in leaves:
        color = (255, 107, 53) if leaf.patches == 1 else (103, 232, 249)
        cv2.rectangle(out, (leaf.x, leaf.y), (leaf.x + leaf.w - 1, leaf.y + leaf.h - 1), color, 1)
    return out

WEB = ROOT / "web"
RESULTS = ROOT / "results"
SYNTH = ROOT / "data" / "synthetic"
MAX_SIDE = 1568
MAX_UPLOAD = 60 * 1024 * 1024
CURVE_FRACTIONS = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75]
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

_uploads: "OrderedDict[str, dict]" = OrderedDict()  # id -> {"name", "kind", "image"|"path"}


def _remember(entry: dict) -> str:
    uid = uuid.uuid4().hex[:12]
    _uploads[uid] = entry
    while len(_uploads) > 12:
        _, old = _uploads.popitem(last=False)
        if old.get("tmp"):
            Path(old["path"]).unlink(missing_ok=True)
    return uid


def _db(x: float) -> float | None:
    return None if math.isinf(x) else round(x, 2)


def _png(img: np.ndarray, max_w: int | None = None) -> str:
    if max_w and img.shape[1] > max_w:
        s = max_w / img.shape[1]
        img = cv2.resize(img, (max_w, round(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


def _jpg(img: np.ndarray, max_w: int = 560) -> str:
    if img.shape[1] > max_w:
        s = max_w / img.shape[1]
        img = cv2.resize(img, (max_w, round(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def ensure_samples() -> dict[str, Path]:
    names = ["document", "ui", "natural", "dense"]
    if not all((SYNTH / f"{n}.png").exists() for n in names) or not (SYNTH / "screen_rec.mp4").exists():
        build_dataset(SYNTH)
    out = {n: SYNTH / f"{n}.png" for n in names}
    out["screen_rec"] = SYNTH / "screen_rec.mp4"
    return out


def _source(body: dict) -> dict:
    if body.get("sample"):
        path = ensure_samples().get(body["sample"])
        if path is None:
            raise ValueError("unknown sample")
        kind = "video" if path.suffix in VIDEO_EXT else "image"
        return {"name": body["sample"], "kind": kind, "path": str(path),
                "image": load_image(path, MAX_SIDE) if kind == "image" else None}
    entry = _uploads.get(body.get("id", ""))
    if entry is None:
        raise ValueError("upload expired - please upload the file again")
    return entry


def analyze_image(body: dict) -> dict:
    src = _source(body)
    if src["kind"] != "image":
        raise ValueError("this file is a video - switch to video mode")
    img = src["image"]
    patch = int(body.get("patch", 16))
    thr = float(body.get("var_threshold", 40))
    ratio = body.get("budget_ratio")
    ratio = float(ratio) if ratio not in (None, "", False) else None

    res = optimize_image(img, patch=patch, var_threshold=thr, budget_ratio=ratio)
    rec = render_leaves(img, res.leaves, patch)
    uni, uni_tokens = uniform_at_budget(img, res.tokens, patch)
    pay = build_payload(res)

    buckets = {"1": 0, "2-4": 0, "5-16": 0, "17-64": 0, "65+": 0}
    for leaf in res.leaves:
        p = leaf.patches
        key = "1" if p == 1 else "2-4" if p <= 4 else "5-16" if p <= 16 else "17-64" if p <= 64 else "65+"
        buckets[key] += 1

    curve = []
    if body.get("curve", True):
        for frac in CURVE_FRACTIONS:
            r = optimize_image(img, patch=patch, budget_ratio=frac, var_threshold=0.0)
            u, _ = uniform_at_budget(img, r.tokens, patch)
            curve.append({"frac": frac,
                          "adaptive": min(psnr(img, render_leaves(img, r.leaves, patch)), 60.0),
                          "uniform": min(psnr(img, u), 60.0)})

    h, w = img.shape[:2]
    return {
        "name": src["name"], "width": w, "height": h, "patch": patch,
        "grid": [res.grid_w, res.grid_h],
        "baseline": res.baseline_tokens, "tokens": res.tokens,
        "reduction": round(100 * res.reduction, 2), "ms": round(res.elapsed_ms, 1),
        "budget": res.budget,
        "psnr": _db(psnr(img, rec)), "ssim": round(ssim(img, rec), 4),
        "uniform_tokens": uni_tokens,
        "uniform_psnr": _db(psnr(img, uni)), "uniform_ssim": round(ssim(img, uni), 4),
        "leaf_sizes": buckets,
        "curve": curve,
        "claude": {"full": pay.full_tokens_est, "optimized": pay.payload_tokens_est,
                   "fallback": pay.used_fallback, "crops": len(pay.crops),
                   "preview_psnr": _db(psnr(img, pay.preview))},
        "images": {
            "original": _png(img, 1100),
            "overlay": _png(quadtree_overlay(img, res.leaves, patch), 1100),
            "adaptive": _png(rec, 1100),
            "uniform": _png(uni, 1100),
        },
    }


def analyze_video(body: dict) -> dict:
    src = _source(body)
    if src["kind"] != "video":
        raise ValueError("this file is an image - switch to image mode")
    fps = float(body.get("fps", 2.0))
    patch = int(body.get("patch", 16))
    thr = float(body.get("var_threshold", 40))
    frames, times = read_video(src["path"], sample_fps=fps)
    if not frames:
        raise ValueError("could not decode any frames")
    frames, times = frames[:240], times[:240]
    res = optimize_video(frames, times, patch=patch, var_threshold=thr)
    keyframes = []
    for s, group in enumerate(res.scenes[:6]):
        i = group[0]
        keyframes.append({"index": i, "scene": s, "t": round(res.frames[i].t, 2),
                          "tokens": res.frames[i].tokens, "frames_in_scene": len(group),
                          "original": _jpg(frames[i]), "seen": _jpg(res.recon[i])})
    psnrs = [f.psnr for f in res.frames if not math.isinf(f.psnr)]
    return {
        "name": src["name"], "width": res.width, "height": res.height, "fps": fps,
        "baseline": res.baseline_tokens, "tokens": res.tokens,
        "per_frame_baseline": res.baseline_tokens // len(res.frames),
        "reduction": round(100 * (1 - res.tokens / res.baseline_tokens), 2),
        "ms": round(res.elapsed_ms, 1),
        "scenes": len(res.scenes), "overlays": len(res.overlays),
        "mean_psnr": round(sum(psnrs) / len(psnrs), 2) if psnrs else None,
        "min_psnr": round(min(psnrs), 2) if psnrs else None,
        "roles": {r: sum(f.role == r for f in res.frames) for r in ("key", "delta", "duplicate")},
        "frames": [{"i": f.index, "t": round(f.t, 2), "role": f.role, "tokens": f.tokens,
                    "scene": f.scene, "ref": f.ref, "psnr": _db(f.psnr),
                    "overlay_reused": f.overlay_reused} for f in res.frames],
        "keyframes": keyframes,
    }


def handle_upload(body: dict) -> dict:
    name = Path(body.get("name", "upload")).name
    raw = base64.b64decode(body["data"].split(",", 1)[-1])
    if len(raw) > MAX_UPLOAD:
        raise ValueError("file too large (60 MB max)")
    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXT or body.get("type", "").startswith("video/"):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext or ".mp4")
        tmp.write(raw)
        tmp.close()
        cap = cv2.VideoCapture(tmp.name)
        ok = cap.isOpened() and cap.read()[0]
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if not ok:
            Path(tmp.name).unlink(missing_ok=True)
            raise ValueError("could not decode that video")
        uid = _remember({"name": Path(name).stem, "kind": "video", "path": tmp.name, "tmp": True})
        return {"id": uid, "name": Path(name).stem, "kind": "video", "width": w, "height": h}
    arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("could not decode that image")
    img = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        s = MAX_SIDE / max(h, w)
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    uid = _remember({"name": Path(name).stem, "kind": "image", "image": img})
    return {"id": uid, "name": Path(name).stem, "kind": "image",
            "width": img.shape[1], "height": img.shape[0]}


def list_samples() -> list[dict]:
    paths = ensure_samples()
    labels = {"document": "Document page", "ui": "UI screenshot", "natural": "Natural scene",
              "dense": "Dense texture", "screen_rec": "Screen recording"}
    out = []
    for name, p in paths.items():
        kind = "video" if p.suffix in VIDEO_EXT else "image"
        thumb = None
        if kind == "image":
            thumb = _jpg(load_image(p), 320)
        else:
            cap = cv2.VideoCapture(str(p))
            ok, bgr = cap.read()
            cap.release()
            if ok:
                thumb = _jpg(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), 320)
        out.append({"name": name, "label": labels.get(name, name), "kind": kind, "thumb": thumb})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, payload: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _static(self, base: Path, rel: str) -> None:
        target = (base / rel).resolve()
        if not str(target).startswith(str(base.resolve())) or not target.is_file():
            self._json(404, {"error": "not found"})
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".js":
            ctype = "text/javascript"
        data = target.read_bytes()
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):  # browsers need byte ranges to seek inside <video>
            start_s, _, end_s = rng[6:].split(",")[0].partition("-")
            size = len(data)
            start = int(start_s) if start_s else max(0, size - int(end_s))
            end = min(int(end_s), size - 1) if start_s and end_s else size - 1
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            chunk = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            self.wfile.write(chunk)
            return
        self._send(200, data, ctype)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/samples":
                return self._json(200, list_samples())
            if path == "/api/results":
                f = RESULTS / "results.json"
                rows = json.loads(f.read_text()) if f.exists() else []
                # Python writes inf as `Infinity`, which browsers' JSON.parse rejects.
                rows = [{k: (None if isinstance(v, float) and math.isinf(v) else v) for k, v in r.items()}
                        for r in rows]
                return self._json(200, rows)
            if path.startswith("/results/"):
                return self._static(RESULTS, path[len("/results/"):])
            return self._static(WEB, "index.html" if path in ("/", "") else path.lstrip("/"))
        except Exception as e:  # surface errors to the UI instead of dropping the connection
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_UPLOAD * 4 // 3 + 4096:
                return self._json(413, {"error": "file too large (60 MB max)"})
            body = json.loads(self.rfile.read(length) or b"{}")
            routes = {"/api/upload": handle_upload, "/api/image": analyze_image, "/api/video": analyze_video}
            fn = routes.get(self.path)
            if fn is None:
                return self._json(404, {"error": "not found"})
            return self._json(200, fn(body))
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": f"{type(e).__name__}: {e}"})


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    ensure_samples()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Token Optimizer UI -> http://localhost:{port}   (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
