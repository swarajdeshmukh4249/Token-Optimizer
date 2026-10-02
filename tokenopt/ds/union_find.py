"""Disjoint-set union with path compression and union by rank.

Used to (a) cluster video frames into scenes and (b) merge adjacent
high-detail patches into connected regions for the provider adapter.
"""
from __future__ import annotations


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n
        self.components = n

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        self.components -= 1
        return True

    def connected(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)

    def groups(self) -> list[list[int]]:
        """Members of each set, ordered by smallest member."""
        by_root: dict[int, list[int]] = {}
        for i in range(len(self.parent)):
            by_root.setdefault(self.find(i), []).append(i)
        return sorted(by_root.values(), key=lambda g: g[0])
