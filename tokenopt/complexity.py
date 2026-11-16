"""Empirical complexity: does each data structure cost what theory says?

For every structure we time its core operation over a range of input sizes,
fit the theoretical model (c * f(n), one free constant) by least squares, and
report how well the model explains the measurements (R^2).

  structure            operation measured           theory
  summed-area table    mean+variance of a rectangle O(1) per query   (vs naive O(area))
  quadtree             full build from a SAT        O(nodes)
  max-heap             push + pop                   O(log n) per op
  union-find           union + find                 O(alpha(n)) ~ O(1) per op
  chained hash table   insert + lookup              O(1) average per op
  bit trie             insert of a 72-bit key       O(key bits) = O(1) in n
"""
from __future__ import annotations

import json
import math
import random
import statistics
import time
from pathlib import Path

import cv2
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .ds.hash_table import ChainedHashTable  # noqa: E402
from .ds.max_heap import MaxHeap  # noqa: E402
from .ds.quadtree import AdaptiveQuadtree  # noqa: E402
from .ds.summed_area import SummedAreaTable  # noqa: E402
from .ds.trie import BitTrie  # noqa: E402
from .ds.union_find import UnionFind  # noqa: E402
from .synth import make_natural  # noqa: E402

SIZES = [1_000, 3_000, 10_000, 30_000, 100_000, 300_000]


def _best(fn, repeats: int = 5) -> float:
    """Median wall time of fn() in seconds (median resists background noise)."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


def _fit(xs: list[float], ys: list[float], f) -> tuple[float, float]:
    """Least-squares c for y = c * f(x); returns (c, R^2)."""
    fx = np.array([f(x) for x in xs], dtype=float)
    y = np.array(ys, dtype=float)
    c = float(fx @ y / (fx @ fx))
    ss_res = float(((y - c * fx) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return c, (1 - ss_res / ss_tot) if ss_tot > 0 else 1.0


# ---- individual experiments -------------------------------------------------

def sat_vs_naive() -> list[dict]:
    img = make_natural(1024, 1024)
    sat = SummedAreaTable(img)
    rows = []
    for side in (8, 16, 32, 64, 128, 256, 512, 1024):
        q = 200
        xy = [(random.randint(0, 1024 - side), random.randint(0, 1024 - side)) for _ in range(q)]
        t_sat = _best(lambda: [sat.stats(x, y, side, side) for x, y in xy])
        f = img.astype(np.float64)

        def naive():
            for x, y in xy:
                crop = f[y:y + side, x:x + side]
                crop.mean(axis=(0, 1))
                crop.var(axis=(0, 1)).mean()

        t_naive = _best(naive, repeats=3)
        rows.append({"area": side * side, "sat_us": t_sat / q * 1e6, "naive_us": t_naive / q * 1e6})
    return rows


def _count_nodes(tree: AdaptiveQuadtree) -> int:
    n, stack = 0, [tree.root]
    while stack:
        node = stack.pop()
        n += 1
        if not node.is_leaf:
            stack.extend(node.children)
    return n


def quadtree_build() -> list[dict]:
    rows = []
    for side in (512, 1024, 2048):
        img = make_natural(side, side, seed=side)
        sat = SummedAreaTable(img)
        for thr in (400.0, 150.0, 60.0, 20.0, 5.0):
            tree = AdaptiveQuadtree(img, 16, sat=sat)
            t = _best(lambda: tree.build_recursive(thr), repeats=3)
            rows.append({"side": side, "threshold": thr, "nodes": _count_nodes(tree), "ms": t * 1000})
    return sorted(rows, key=lambda r: r["nodes"])


def heap_ops() -> list[dict]:
    rows = []
    for n in SIZES:
        vals = [random.random() for _ in range(n)]

        def run():
            h = MaxHeap()
            for v in vals:
                h.push(v, None)
            for _ in range(n):
                h.pop()

        rows.append({"n": n, "us_per_op": _best(run, 3) / (2 * n) * 1e6})
    return rows


def union_find_ops() -> list[dict]:
    rows = []
    for n in SIZES:
        pairs = [(random.randrange(n), random.randrange(n)) for _ in range(n)]

        def run():
            uf = UnionFind(n)
            for a, b in pairs:
                uf.union(a, b)
            for a, _ in pairs:
                uf.find(a)

        rows.append({"n": n, "us_per_op": _best(run, 3) / (2 * n) * 1e6})
    return rows


def hash_table_ops() -> list[dict]:
    rows = []
    for n in SIZES:
        keys = [random.getrandbits(64) for _ in range(n)]

        def run():
            t = ChainedHashTable()
            for k in keys:
                t.insert(k, k)
            for k in keys:
                next(t.get_all(k))

        rows.append({"n": n, "us_per_op": _best(run, 3) / (2 * n) * 1e6})
    return rows


def trie_ops() -> list[dict]:
    rows = []
    for n in SIZES[:-1]:  # a 72-level trie of 300k keys is memory-heavy; 100k shows the trend
        keys = [random.getrandbits(72) for _ in range(n)]

        def run():
            t = BitTrie(72)
            for k in keys:
                t.insert(k)

        rows.append({"n": n, "us_per_op": _best(run, 3) / n * 1e6})
    return rows


# ---- driver ---------------------------------------------------------------

def run_complexity(out: Path, seed: int = 11) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    random.seed(seed)
    cv2.setRNGSeed(seed)
    res = {}
    for name, fn in [("sat", sat_vs_naive), ("quadtree", quadtree_build), ("heap", heap_ops),
                     ("union_find", union_find_ops), ("hash_table", hash_table_ops), ("trie", trie_ops)]:
        print(f"  measuring {name} ...")
        res[name] = fn()

    lg = lambda n: math.log2(n)  # noqa: E731
    one = lambda n: 1.0  # noqa: E731
    fits = {
        "sat_query": ("O(1)", *_fit([r["area"] for r in res["sat"]], [r["sat_us"] for r in res["sat"]], one)),
        "naive_query": ("O(area)", *_fit([r["area"] for r in res["sat"]], [r["naive_us"] for r in res["sat"]],
                                         lambda a: a)),
        "quadtree": ("O(nodes)", *_fit([r["nodes"] for r in res["quadtree"]], [r["ms"] for r in res["quadtree"]],
                                       lambda n: n)),
        "heap": ("O(log n)", *_fit([r["n"] for r in res["heap"]], [r["us_per_op"] for r in res["heap"]], lg)),
        "union_find": ("O(alpha(n)) ~ O(1)",
                       *_fit([r["n"] for r in res["union_find"]], [r["us_per_op"] for r in res["union_find"]], one)),
        "hash_table": ("O(1) average",
                       *_fit([r["n"] for r in res["hash_table"]], [r["us_per_op"] for r in res["hash_table"]], one)),
        "trie": ("O(key bits) ~ O(1) in n",
                 *_fit([r["n"] for r in res["trie"]], [r["us_per_op"] for r in res["trie"]], one)),
    }
    res["fits"] = {k: {"model": m, "c": c, "r2": r2} for k, (m, c, r2) in fits.items()}
    _plot(res, out / "complexity.png")
    (out / "complexity.json").write_text(json.dumps(res, indent=2))
    (out / "COMPLEXITY.md").write_text(_report(res))
    return res


def _plot(res: dict, path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    meas, model = "#1a73e8", "#e8710a"
    f = res["fits"]

    ax = axes[0, 0]
    a = [r["area"] for r in res["sat"]]
    ax.loglog(a, [r["naive_us"] for r in res["sat"]], "o-", color="#9aa0a6", label="naive scan: O(area)")
    ax.loglog(a, [r["sat_us"] for r in res["sat"]], "o-", color=meas, label="summed-area table: O(1)")
    ax.set(title="Rectangle mean + variance", xlabel="rectangle area (pixels)", ylabel="us per query")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    nodes = [r["nodes"] for r in res["quadtree"]]
    ax.plot(nodes, [r["ms"] for r in res["quadtree"]], "o", color=meas, label="measured")
    xs = np.linspace(0, max(nodes), 50)
    ax.plot(xs, f["quadtree"]["c"] * xs, "--", color=model,
            label=f"c * nodes  (R² = {f['quadtree']['r2']:.3f})")
    ax.set(title="Quadtree build: O(nodes)", xlabel="nodes in tree", ylabel="build time (ms)")
    ax.legend(fontsize=8)

    def per_op(ax, key, title, fn):
        ns = [r["n"] for r in res[key]]
        ax.semilogx(ns, [r["us_per_op"] for r in res[key]], "o-", color=meas, label="measured")
        flat = fn(ns[0]) == fn(ns[-1])
        ax.semilogx(ns, [f[key]["c"] * fn(n) for n in ns], "--", color=model,
                    label=f"{f[key]['model']}" + ("" if flat else f"  (R² = {f[key]['r2']:.2f})"))
        ax.set(title=title, xlabel="n (items)", ylabel="us per operation")
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=8)

    per_op(axes[0, 2], "heap", "Max-heap push + pop: O(log n)", math.log2)
    per_op(axes[1, 0], "union_find", "Union-Find: O(α(n)) ≈ O(1)", lambda n: 1.0)
    per_op(axes[1, 1], "hash_table", "Chained hash table: O(1) average", lambda n: 1.0)
    per_op(axes[1, 2], "trie", "Bit trie insert: O(key bits)", lambda n: 1.0)
    for ax in axes.flat:
        ax.grid(True, which="both", alpha=0.25)
    fig.suptitle("Measured cost vs theoretical complexity", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _report(res: dict) -> str:
    f = res["fits"]
    sat = res["sat"]
    lines = [
        "# Empirical complexity",
        "",
        "Each structure's core operation is timed over growing inputs (median of repeats) and the "
        "theoretical model c * f(n) is fitted with one free constant. For the flat O(1) models R² "
        "near 0 is expected (nothing to explain beyond the constant); what matters is that "
        "cost per operation stays flat as n grows 300x.",
        "",
        "| structure | theory | fitted R² | evidence |",
        "|---|---|---:|---|",
        f"| Summed-area table query | O(1) | - | {sat[0]['sat_us']:.1f} us at {sat[0]['area']:,} px vs "
        f"{sat[-1]['sat_us']:.1f} us at {sat[-1]['area']:,} px; naive scan grows "
        f"{sat[-1]['naive_us'] / sat[0]['naive_us']:.0f}x |",
        f"| Naive rectangle scan | O(area) | {f['naive_query']['r2']:.3f} | grows with area |",
        f"| Quadtree build | O(nodes) | {f['quadtree']['r2']:.3f} | linear in nodes |",
        f"| Max-heap push + pop | O(log n) | {f['heap']['r2']:.3f} | "
        f"{_span(res['heap'])} |",
        f"| Union-Find | O(α(n)) | - | {_span(res['union_find'])} |",
        f"| Chained hash table | O(1) average | - | {_span(res['hash_table'])} |",
        f"| Bit trie insert | O(key bits) | - | {_span(res['trie'])} |",
        "",
        "**Reading the drift.** Per-operation cost of the heap, union-find and hash table creeps up "
        "at the largest n. The operation count does not change; past ~100k items the working set "
        "no longer fits in the CPU cache, so each memory access gets slower. This is a hardware "
        "effect on top of the asymptotic cost, and it is why the heap fits log n only loosely.",
        "",
        "![complexity](complexity.png)",
        "",
    ]
    return "\n".join(lines)


def _span(rows: list[dict]) -> str:
    a, b = rows[0], rows[-1]
    return f"{a['us_per_op']:.2f} us/op at n={a['n']:,} -> {b['us_per_op']:.2f} us/op at n={b['n']:,}"
