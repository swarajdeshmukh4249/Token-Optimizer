"""BK-tree (Burkhard-Keller tree) for near-duplicate search under Hamming distance.

Each node stores one hash; its children are keyed by their distance to that node.
Hamming distance is a metric, so the triangle inequality bounds the search: when
looking for everything within radius r of a query q, and q is at distance d from
a node, only the children whose edge label k satisfies |k - d| <= r can hold a
match. Every other subtree is skipped without being visited.

Children live in a fixed array of 65 slots (distances 0..64 for 64-bit hashes),
so following an edge is O(1). Insert walks one root-to-leaf path: O(depth).
Query cost depends on the radius and on how clustered the data is: small radii
on clustered data prune most of the tree; large radii degrade toward a full scan.

Counts every distance evaluation in `comparisons`, so the cost can be compared
with linear scan and multi-index hashing independently of machine speed.
"""
from __future__ import annotations

from typing import Any

from .hash_table import hamming


class _Node:
    __slots__ = ("key", "payloads", "children")

    def __init__(self, key: int, payload: Any, bits: int) -> None:
        self.key = key
        self.payloads = [payload]
        self.children: list[_Node | None] = [None] * (bits + 1)


class BKTree:
    def __init__(self, bits: int = 64) -> None:
        self.bits = bits
        self._root: _Node | None = None
        self._count = 0
        self.comparisons = 0  # distance evaluations made by queries

    def add(self, h: int, payload: Any) -> None:
        self._count += 1
        if self._root is None:
            self._root = _Node(h, payload, self.bits)
            return
        node = self._root
        while True:
            d = hamming(h, node.key)
            if d == 0:  # identical hash: keep it in the same node
                node.payloads.append(payload)
                return
            child = node.children[d]
            if child is None:
                node.children[d] = _Node(h, payload, self.bits)
                return
            node = child

    def query(self, h: int, max_distance: int) -> list[tuple[int, Any]]:
        """(distance, payload) for every stored hash within max_distance, nearest first."""
        hits: list[tuple[int, Any]] = []
        if self._root is None:
            return hits
        stack = [self._root]
        while stack:
            node = stack.pop()
            d = hamming(h, node.key)
            self.comparisons += 1
            if d <= max_distance:
                hits.extend((d, p) for p in node.payloads)
            lo, hi = max(1, d - max_distance), min(self.bits, d + max_distance)
            for k in range(lo, hi + 1):
                child = node.children[k]
                if child is not None:
                    stack.append(child)
        hits.sort(key=lambda t: t[0])
        return hits

    def depth(self) -> int:
        if self._root is None:
            return 0
        best, stack = 0, [(self._root, 1)]
        while stack:
            node, lvl = stack.pop()
            best = max(best, lvl)
            stack.extend((c, lvl + 1) for c in node.children if c is not None)
        return best

    def __len__(self) -> int:
        return self._count
