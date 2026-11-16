"""Near-duplicate search race: linear scan vs BK-tree vs multi-index hashing.

All three answer the same question the video pipeline asks for every frame:
"which stored 64-bit pHashes are within Hamming distance r of this one?"

The data imitates video signatures: a set of scene "centres" with many
near-duplicate frames scattered a few bits around each one, plus queries that
are half near-duplicates (should hit) and half unrelated frames (should miss).

Two costs are reported:
  * comparisons -- full 64-bit distance evaluations per query (machine-independent)
  * time        -- wall-clock microseconds per query on this machine
Every structure's answer is checked against linear scan, so the race only
counts a structure that returns exactly the right set.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .ds.bk_tree import BKTree  # noqa: E402
from .ds.hash_table import MultiIndexHashTable, hamming  # noqa: E402

SIZES = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000]
RADII = [0, 1, 2, 3, 4, 6, 8]
RADIUS = 4      # what video_opt uses for near-duplicates
QUERIES = 300


def _flip(h: int, k: int, rng: random.Random) -> int:
    for bit in rng.sample(range(64), k):
        h ^= 1 << bit
    return h


def make_signatures(n: int, rng: random.Random) -> list[int]:
    """n hashes in clusters of ~25: one scene centre, frames 0-6 bits away."""
    out: list[int] = []
    while len(out) < n:
        centre = rng.getrandbits(64)
        for _ in range(25):
            out.append(_flip(centre, rng.randint(0, 6), rng))
    return out[:n]


def make_queries(data: list[int], rng: random.Random) -> list[int]:
    qs = [_flip(rng.choice(data), rng.randint(0, 3), rng) for _ in range(QUERIES // 2)]
    qs += [rng.getrandbits(64) for _ in range(QUERIES - len(qs))]
    rng.shuffle(qs)
    return qs


class LinearScan:
    def __init__(self) -> None:
        self.items: list[tuple[int, int]] = []
        self.comparisons = 0

    def add(self, h: int, payload: int) -> None:
        self.items.append((h, payload))

    def query(self, h: int, max_distance: int) -> list[tuple[int, int]]:
        self.comparisons += len(self.items)
        hits = [(hamming(h, k), p) for k, p in self.items]
        return sorted((d, p) for d, p in hits if d <= max_distance)


def _build(kind: str, data: list[int], radius: int):
    s = {"linear": LinearScan, "bktree": BKTree,
         "mih": lambda: MultiIndexHashTable(max_distance=max(radius, 1))}[kind]()
    t0 = time.perf_counter()
    for i, h in enumerate(data):
        s.add(h, i)
    return s, (time.perf_counter() - t0) * 1000


def _run(data: list[int], queries: list[int], radius: int) -> dict:
    row: dict = {}
    truth = None
    for kind in ("linear", "bktree", "mih"):
        s, build_ms = _build(kind, data, radius)
        t0 = time.perf_counter()
        answers = [sorted(p for _, p in s.query(q, radius)) for q in queries]
        elapsed = time.perf_counter() - t0
        if truth is None:
            truth = answers
        row[kind] = {
            "build_ms": round(build_ms, 2),
            "query_us": round(elapsed / len(queries) * 1e6, 2),
            "comparisons": round(s.comparisons / len(queries), 1),
            "correct": answers == truth,
        }
    row["avg_hits"] = round(sum(len(a) for a in truth) / len(queries), 2)
    return row


LABELS = {"linear": "Linear scan", "bktree": "BK-tree", "mih": "Multi-index hashing"}
COLORS = {"linear": "#9aa0a6", "bktree": "#e8710a", "mih": "#1a73e8"}


def _plot_scaling(rows: list[dict], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for kind in ("linear", "bktree", "mih"):
        ns = [r["n"] for r in rows]
        axes[0].plot(ns, [r[kind]["comparisons"] for r in rows], "o-", color=COLORS[kind], label=LABELS[kind])
        axes[1].plot(ns, [r[kind]["query_us"] for r in rows], "o-", color=COLORS[kind], label=LABELS[kind])
    for ax, ylab in zip(axes, ("distance evaluations per query", "microseconds per query")):
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("stored hashes (n)")
        ax.set_ylabel(ylab)
        ax.grid(True, which="both", alpha=0.25)
    axes[0].legend()
    fig.suptitle(f"Near-duplicate search, radius {RADIUS}: work as the store grows")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_radius(rows: list[dict], n: int, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for kind in ("linear", "bktree", "mih"):
        ax.plot([r["radius"] for r in rows], [r[kind]["comparisons"] for r in rows], "o-",
                color=COLORS[kind], label=LABELS[kind])
    ax.set_yscale("log")
    ax.set_xlabel("search radius r (bits)")
    ax.set_ylabel("distance evaluations per query")
    ax.set_title(f"Cost vs radius at n = {n:,}")
    ax.grid(True, which="both", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_race(out: Path, seed: int = 7) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    scaling = []
    for n in SIZES:
        data = make_signatures(n, rng)
        row = _run(data, make_queries(data, rng), RADIUS)
        row["n"] = n
        scaling.append(row)
        print(f"  n={n:>6}: linear {row['linear']['query_us']:>8} us | "
              f"bk-tree {row['bktree']['query_us']:>8} us | mih {row['mih']['query_us']:>8} us")

    n_fixed = 20_000
    data = make_signatures(n_fixed, rng)
    queries = make_queries(data, rng)
    radius_rows = []
    for r in RADII:
        row = _run(data, queries, r)
        row["radius"] = r
        radius_rows.append(row)

    _plot_scaling(scaling, out / "race_scaling.png")
    _plot_radius(radius_rows, n_fixed, out / "race_radius.png")
    result = {"radius": RADIUS, "queries": QUERIES, "scaling": scaling,
              "radius_sweep": {"n": n_fixed, "rows": radius_rows}}
    (out / "race.json").write_text(json.dumps(result, indent=2))
    (out / "RACE.md").write_text(_report(result))
    return result


def _report(res: dict) -> str:
    lines = [
        "# Near-duplicate search race",
        "",
        f"Linear scan vs BK-tree vs multi-index hashing on clustered 64-bit pHash signatures, "
        f"radius {res['radius']}, {res['queries']} queries per point (half near-duplicates, half unrelated). "
        "Every answer is checked against linear scan.",
        "",
        "| n | linear cmp / us | BK-tree cmp / us | MIH cmp / us | all correct |",
        "|---:|---:|---:|---:|---|",
    ]
    for r in res["scaling"]:
        ok = all(r[k]["correct"] for k in ("linear", "bktree", "mih"))
        lines.append(f"| {r['n']:,} | {r['linear']['comparisons']:,} / {r['linear']['query_us']} "
                     f"| {r['bktree']['comparisons']:,} / {r['bktree']['query_us']} "
                     f"| {r['mih']['comparisons']:,} / {r['mih']['query_us']} | {'yes' if ok else 'NO'} |")
    sw = res["radius_sweep"]
    lines += ["", f"## Radius sweep at n = {sw['n']:,} (distance evaluations per query)", "",
              "| radius | linear | BK-tree | MIH | avg hits |", "|---:|---:|---:|---:|---:|"]
    for r in sw["rows"]:
        lines.append(f"| {r['radius']} | {r['linear']['comparisons']:,} | {r['bktree']['comparisons']:,} "
                     f"| {r['mih']['comparisons']:,} | {r['avg_hits']} |")
    lines += ["", "![scaling](race_scaling.png)", "", "![radius](race_radius.png)", ""]
    return "\n".join(lines)
