"""Agent-screenshot compression: what a computer-use agent pays per turn.

A computer-use agent sends a full screenshot every turn and keeps all earlier
screenshots in its context, so turn k re-reads k images. Most consecutive
screenshots differ only by a cursor, a hover state or a few typed characters.

This module scripts a 20-turn session in a synthetic web app (dashboard ->
projects -> "new project" modal -> create -> back) and encodes it *causally*:
turn k is encoded with optimize_video(frames[:k+1]), so every decision (scene,
duplicate, delta, static overlay) uses only screenshots the agent already has.
No future frame ever influences what is sent at turn k.

Two numbers are reported against sending the full 16 px patch grid each turn:
  * screenshot tokens  -- tokens added by each new turn
  * context tokens     -- tokens the model reads across the whole session,
                          sum over turns of (all screenshots so far); this is
                          the quadratic cost agents actually pay.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image, ImageDraw

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .cost import grid_tokens  # noqa: E402
from .synth import _font  # noqa: E402
from .video_opt import optimize_video  # noqa: E402

W, H = 1280, 800
PATCH = 16
PROJECTS = [("Search ranking", "Active", "12.4k"), ("Docs assistant", "Active", "8.1k"),
            ("Invoice OCR", "Paused", "2.3k"), ("Support triage", "Active", "19.7k"),
            ("Video tagging", "Draft", "0"), ("Code review bot", "Active", "5.6k"),
            ("Churn model", "Paused", "1.1k"), ("Image captions", "Active", "7.9k")]
ROLE_COLOURS = {"key": "#1a73e8", "delta": "#34a853", "duplicate": "#bdc1c6"}

# ---------------------------------------------------------------- drawing ----


def _chrome(d: ImageDraw.ImageDraw, url: str) -> None:
    d.rectangle((0, 0, W, 76), fill=(222, 225, 230))
    d.rounded_rectangle((12, 8, 260, 36), 8, fill=(255, 255, 255))
    d.text((26, 14), "Acme Console", fill=(60, 64, 67), font=_font(14))
    d.rounded_rectangle((90, 42, W - 24, 70), 14, fill=(255, 255, 255))
    d.text((110, 48), url, fill=(60, 64, 67), font=_font(15))
    for i, x in enumerate((24, 46, 68)):
        d.ellipse((x - 6, 50, x + 6, 62), fill=(150 + i * 20, 150, 150))


def _sidebar(d: ImageDraw.ImageDraw, active: str, hover: str | None = None) -> None:
    d.rectangle((0, 76, 220, H), fill=(32, 33, 36))
    d.text((24, 98), "ACME", fill=(255, 255, 255), font=_font(22))
    for i, name in enumerate(("Dashboard", "Projects", "Usage", "Billing", "Settings")):
        y = 150 + i * 44
        if name == active:
            d.rounded_rectangle((12, y - 8, 208, y + 28), 8, fill=(26, 115, 232))
        elif name == hover:
            d.rounded_rectangle((12, y - 8, 208, y + 28), 8, fill=(60, 64, 67))
        d.text((32, y), name, fill=(232, 234, 237), font=_font(17))


def _cursor(d: ImageDraw.ImageDraw, x: int, y: int) -> None:
    d.polygon([(x, y), (x, y + 20), (x + 6, y + 15), (x + 14, y + 15)], fill=(0, 0, 0),
              outline=(255, 255, 255))


def _dashboard(d: ImageDraw.ImageDraw) -> None:
    d.text((252, 100), "Dashboard", fill=(32, 33, 36), font=_font(28))
    for i, (label, value) in enumerate((("Requests today", "48,213"), ("Tokens / week", "3.2M"),
                                        ("Active projects", "5"), ("Spend", "$412"))):
        x = 252 + i * 250
        d.rounded_rectangle((x, 150, x + 230, 260), 12, fill=(255, 255, 255), outline=(218, 220, 224))
        d.text((x + 18, 166), label, fill=(95, 99, 104), font=_font(15))
        d.text((x + 18, 200), value, fill=(32, 33, 36), font=_font(30))
    d.rounded_rectangle((252, 290, W - 32, H - 32), 12, fill=(255, 255, 255), outline=(218, 220, 224))
    d.text((272, 306), "Requests per hour", fill=(95, 99, 104), font=_font(15))
    rng = np.random.default_rng(5)
    vals = 200 + np.cumsum(rng.normal(0, 18, 60))
    xs = np.linspace(280, W - 60, 60)
    ys = (H - 60) - (vals - vals.min()) / (np.ptp(vals) + 1e-9) * 360
    d.line(list(zip(xs.tolist(), ys.tolist())), fill=(26, 115, 232), width=3)


def _projects(d: ImageDraw.ImageDraw, rows: list[tuple[str, str, str]], hover_new: bool,
              hover_row: int | None = None, checked: int | None = None) -> None:
    d.text((252, 100), "Projects", fill=(32, 33, 36), font=_font(28))
    d.rounded_rectangle((W - 220, 96, W - 32, 136), 8,
                        fill=(23, 78, 166) if hover_new else (26, 115, 232))
    d.text((W - 196, 106), "+ New project", fill=(255, 255, 255), font=_font(17))
    d.rounded_rectangle((252, 156, W - 32, H - 32), 12, fill=(255, 255, 255), outline=(218, 220, 224))
    for j, head in enumerate(("Name", "Status", "Tokens / week")):
        d.text((300 + j * 300, 172), head, fill=(95, 99, 104), font=_font(15))
    for i, (name, status, toks) in enumerate(rows):
        y = 208 + i * 52
        if i == hover_row:
            d.rectangle((253, y - 10, W - 33, y + 38), fill=(241, 243, 244))
        d.rectangle((268, y + 4, 284, y + 20), outline=(95, 99, 104), width=2)
        if i == checked:
            d.rectangle((268, y + 4, 284, y + 20), fill=(26, 115, 232))
        d.text((300, y), name, fill=(32, 33, 36), font=_font(17))
        colour = {"Active": (30, 142, 62), "Paused": (227, 116, 0)}.get(status, (95, 99, 104))
        d.text((600, y), status, fill=colour, font=_font(17))
        d.text((900, y), toks, fill=(32, 33, 36), font=_font(17))
        d.line((268, y + 40, W - 48, y + 40), fill=(232, 234, 237))


def _modal(im: Image.Image, name: str, focused: bool, dropdown_open: bool, plan: str | None,
           hover_create: bool) -> Image.Image:
    dark = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.45)
    d = ImageDraw.Draw(dark)
    x0, y0 = W // 2 - 260, 190
    d.rounded_rectangle((x0, y0, x0 + 520, y0 + 380), 14, fill=(255, 255, 255))
    d.text((x0 + 28, y0 + 24), "New project", fill=(32, 33, 36), font=_font(24))
    d.text((x0 + 28, y0 + 78), "Name", fill=(95, 99, 104), font=_font(15))
    d.rounded_rectangle((x0 + 28, y0 + 100, x0 + 492, y0 + 142), 8, fill=(255, 255, 255),
                        outline=(26, 115, 232) if focused else (218, 220, 224), width=2)
    d.text((x0 + 42, y0 + 111), name, fill=(32, 33, 36), font=_font(17))
    if focused:
        cx = x0 + 42 + int(d.textlength(name, font=_font(17)))
        d.rectangle((cx + 1, y0 + 110, cx + 3, y0 + 132), fill=(32, 33, 36))
    d.text((x0 + 28, y0 + 164), "Weekly token budget", fill=(95, 99, 104), font=_font(15))
    d.rounded_rectangle((x0 + 28, y0 + 186, x0 + 492, y0 + 228), 8, fill=(255, 255, 255),
                        outline=(218, 220, 224), width=2)
    d.text((x0 + 42, y0 + 197), plan or "Choose a budget", fill=(32, 33, 36) if plan else (154, 160, 166),
           font=_font(17))
    d.rounded_rectangle((x0 + 360, y0 + 310, x0 + 492, y0 + 352), 8,
                        fill=(23, 78, 166) if hover_create else (26, 115, 232))
    d.text((x0 + 398, y0 + 320), "Create", fill=(255, 255, 255), font=_font(17))
    if dropdown_open:
        d.rounded_rectangle((x0 + 28, y0 + 232, x0 + 492, y0 + 372), 8, fill=(255, 255, 255),
                            outline=(218, 220, 224), width=2)
        for i, opt in enumerate(("100k / week", "1M / week", "10M / week")):
            d.text((x0 + 42, y0 + 246 + i * 42), opt, fill=(32, 33, 36), font=_font(17))
    return dark


def _toast(d: ImageDraw.ImageDraw, text: str) -> None:
    d.rounded_rectangle((W // 2 - 200, H - 92, W // 2 + 200, H - 44), 10, fill=(32, 33, 36))
    d.text((W // 2 - 176, H - 79), text, fill=(255, 255, 255), font=_font(16))


def _screen(page: str, mouse: tuple[int, int], **kw) -> np.ndarray:
    im = Image.new("RGB", (W, H), (248, 249, 250))
    d = ImageDraw.Draw(im)
    _chrome(d, f"console.acme.dev/{page}")
    _sidebar(d, "Dashboard" if page == "dashboard" else "Projects", kw.get("hover_nav"))
    if page == "dashboard":
        _dashboard(d)
    else:
        _projects(d, kw.get("rows", PROJECTS), kw.get("hover_new", False),
                  kw.get("hover_row"), kw.get("checked"))
    if "modal" in kw:
        im = _modal(im, **kw["modal"])
        d = ImageDraw.Draw(im)
    if kw.get("toast"):
        _toast(d, kw["toast"])
    _cursor(d, *mouse)
    return np.asarray(im)


def make_session() -> list[tuple[str, np.ndarray]]:
    """Twenty (action, screenshot) turns of a scripted agent task."""
    new_rows = PROJECTS[:7] + [("Agent demo", "Draft", "0")]
    m = dict(name="", focused=False, dropdown_open=False, plan=None, hover_create=False)
    cx, cy = W // 2, 190  # modal origin helpers
    turns = [
        ("observe dashboard", _screen("dashboard", (700, 420))),
        ("move to Projects", _screen("dashboard", (90, 200), hover_nav="Projects")),
        ("click Projects", _screen("projects", (90, 200))),
        ("wait for page", _screen("projects", (90, 200))),
        ("hover + New project", _screen("projects", (W - 120, 116), hover_new=True)),
        ("click + New project", _screen("projects", (W - 120, 116), modal=dict(m))),
        ("click name field", _screen("projects", (cx - 100, cy + 120), modal={**m, "focused": True})),
        ("type 'Agent'", _screen("projects", (cx - 100, cy + 120),
                                 modal={**m, "focused": True, "name": "Agent"})),
        ("type ' demo'", _screen("projects", (cx - 100, cy + 120),
                                 modal={**m, "focused": True, "name": "Agent demo"})),
        ("open budget dropdown", _screen("projects", (cx, cy + 206),
                                         modal={**m, "name": "Agent demo", "dropdown_open": True})),
        ("pick 1M / week", _screen("projects", (cx - 120, cy + 296),
                                   modal={**m, "name": "Agent demo", "plan": "1M / week"})),
        ("click Create", _screen("projects", (cx + 160, cy + 330), rows=new_rows,
                                 toast="Project 'Agent demo' created")),
        ("wait", _screen("projects", (cx + 160, cy + 330), rows=new_rows)),
        ("check new row", _screen("projects", (276, 208 + 7 * 52 + 12), rows=new_rows, checked=7)),
        ("back to Dashboard", _screen("dashboard", (90, 156))),
        ("confirm dashboard", _screen("dashboard", (90, 156))),
        ("open Projects again", _screen("projects", (90, 200), rows=new_rows)),
        ("hover new row", _screen("projects", (700, 208 + 7 * 52 + 12), rows=new_rows, hover_row=7)),
        ("wait", _screen("projects", (700, 208 + 7 * 52 + 12), rows=new_rows, hover_row=7)),
        ("report success", _screen("projects", (700, 208 + 7 * 52 + 12), rows=new_rows, hover_row=7)),
    ]
    return turns


# --------------------------------------------------------------- encoding ----


def encode_causal(frames: list[np.ndarray]) -> list[dict]:
    """Encode turn k from frames[:k+1] only; return the per-turn decision."""
    out = []
    for k in range(len(frames)):
        res = optimize_video(frames[:k + 1], patch=PATCH)
        rec = res.frames[-1]
        out.append({"role": rec.role, "ref": rec.ref, "tokens": rec.tokens,
                    "psnr": rec.psnr, "regions": rec.regions, "recon": res.recon[-1]})
    return out


def run_agent(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    session = make_session()
    frames = [f for _, f in session]
    enc = encode_causal(frames)
    base = grid_tokens(W, H, PATCH)

    turns, run_b, run_o, ctx_b, ctx_o = [], 0, 0, 0, 0
    for k, ((action, _), e) in enumerate(zip(session, enc)):
        run_b += base
        run_o += e["tokens"]
        ctx_b += run_b
        ctx_o += run_o
        turns.append({"turn": k + 1, "action": action, "role": e["role"], "ref": e["ref"],
                      "baseline_tokens": base, "tokens": e["tokens"],
                      "psnr": round(float(e["psnr"]), 2) if np.isfinite(e["psnr"]) else None,
                      "context_baseline": ctx_b, "context_optimized": ctx_o})

    roles = {r: sum(t["role"] == r for t in turns) for r in ROLE_COLOURS}
    psnrs = [t["psnr"] for t in turns if t["psnr"] is not None]
    summary = {
        "turns": len(turns), "resolution": [W, H], "patch": PATCH,
        "screenshot_tokens_baseline": run_b, "screenshot_tokens_optimized": run_o,
        "screenshot_reduction": round(1 - run_o / run_b, 4),
        "context_tokens_baseline": ctx_b, "context_tokens_optimized": ctx_o,
        "context_reduction": round(1 - ctx_o / ctx_b, 4),
        "roles": roles, "min_psnr": min(psnrs) if psnrs else None,
    }
    result = {"summary": summary, "turns": turns}

    _plot_turns(turns, out / "agent_turns.png")
    _filmstrip(session, enc, out / "agent_filmstrip.png")
    (out / "agent.json").write_text(json.dumps(result, indent=2))
    (out / "AGENT.md").write_text(_report(result))
    return result


# ---------------------------------------------------------------- figures ----


def _plot_turns(turns: list[dict], path: Path) -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.4))
    ks = [t["turn"] for t in turns]
    from matplotlib.patches import Patch
    a.bar(ks, [t["baseline_tokens"] for t in turns], color="#e8eaed")
    a.bar(ks, [t["tokens"] for t in turns], color=[ROLE_COLOURS[t["role"]] for t in turns])
    handles = [Patch(color="#e8eaed", label="full screenshot")]
    handles += [Patch(color=c, label=f"optimized: {r}") for r, c in ROLE_COLOURS.items()]
    a.set_xlabel("agent turn")
    a.set_ylabel("tokens added this turn")
    a.set_title("Tokens per screenshot")
    a.set_xticks(ks)
    a.legend(handles=handles, fontsize=8)
    b.plot(ks, [t["context_baseline"] for t in turns], "o-", color="#9aa0a6", label="full screenshots")
    b.plot(ks, [t["context_optimized"] for t in turns], "o-", color="#1a73e8", label="optimized")
    b.set_xlabel("agent turn")
    b.set_ylabel("cumulative tokens read by the model")
    b.set_title("Context cost over the session")
    b.set_xticks(ks)
    b.grid(alpha=0.25)
    b.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _filmstrip(session, enc, path: Path, cols: int = 5, tw: int = 320) -> None:
    th = int(tw * H / W)
    rows = (len(session) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 40) + 8), (255, 255, 255))
    sd = ImageDraw.Draw(sheet)
    s = tw / W
    for k, ((action, frame), e) in enumerate(zip(session, enc)):
        im = Image.fromarray(frame).convert("RGB")
        if e["role"] == "duplicate":
            im = Image.blend(im, Image.new("RGB", im.size, (200, 200, 200)), 0.6)
        im = im.resize((tw, th), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        colour = ROLE_COLOURS[e["role"]]
        if e["role"] == "delta":
            for r in e["regions"]:
                d.rectangle((r["x"] * s, r["y"] * s, (r["x"] + r["w"]) * s, (r["y"] + r["h"]) * s),
                            outline=colour)
        x, y = 8 + (k % cols) * (tw + 8), 8 + (k // cols) * (th + 40)
        sheet.paste(im, (x, y))
        sd.rectangle((x, y, x + tw - 1, y + th - 1), outline=colour, width=3)
        sd.text((x, y + th + 4), f"{k + 1}. {action}", fill=(32, 33, 36), font=_font(13))
        sd.text((x, y + th + 21), f"{e['role']}  {e['tokens']} tokens", fill=colour, font=_font(12))
    sheet.save(path)


def _report(res: dict) -> str:
    s = res["summary"]
    lines = [
        "# Agent-screenshot compression",
        "",
        f"A scripted {s['turns']}-turn computer-use session at {s['resolution'][0]}x{s['resolution'][1]}, "
        f"encoded causally (turn k sees only screenshots 1..k). Baseline: the full {s['patch']} px patch grid "
        f"({res['turns'][0]['baseline_tokens']:,} tokens) every turn.",
        "",
        "| metric | full screenshots | optimized | reduction |",
        "|---|---:|---:|---:|",
        f"| screenshot tokens | {s['screenshot_tokens_baseline']:,} | {s['screenshot_tokens_optimized']:,} "
        f"| {s['screenshot_reduction']:.1%} |",
        f"| context tokens read (all turns) | {s['context_tokens_baseline']:,} | "
        f"{s['context_tokens_optimized']:,} | {s['context_reduction']:.1%} |",
        "",
        f"Turn roles: {s['roles']['key']} key, {s['roles']['delta']} delta, "
        f"{s['roles']['duplicate']} duplicate. Lowest reconstruction PSNR: {s['min_psnr']} dB.",
        "",
        "Context tokens assume the agent keeps every screenshot in its history, so turn k re-reads all k "
        "images; this is why the saving compounds.",
        "",
        "| turn | action | role | tokens | PSNR dB |",
        "|---:|---|---|---:|---:|",
    ]
    for t in res["turns"]:
        lines.append(f"| {t['turn']} | {t['action']} | {t['role']} | {t['tokens']:,} | {t['psnr']} |")
    lines += ["", "![turns](agent_turns.png)", "", "![filmstrip](agent_filmstrip.png)", "",
              "Limitation: each turn is re-encoded from its own prefix, so the reference canvas a delta "
              "builds on is the one that prefix reconstructs, which can differ slightly from what an "
              "earlier turn actually sent when overlay detection changes as history grows.", ""]
    return "\n".join(lines)
