"""Array-backed binary max-heap, implemented by hand (no heapq).

Used to rank quadtree regions by saliency (squared error) so a fixed token
budget is always spent on the region that currently loses the most detail.
Ties are broken FIFO so results are deterministic.
"""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class MaxHeap(Generic[T]):
    def __init__(self) -> None:
        self._a: list[tuple[float, int, T]] = []
        self._seq = 0

    def __len__(self) -> int:
        return len(self._a)

    def _above(self, i: int, j: int) -> bool:
        """True if entry i should sit above entry j."""
        pi, si, _ = self._a[i]
        pj, sj, _ = self._a[j]
        return pi > pj or (pi == pj and si < sj)

    def _swap(self, i: int, j: int) -> None:
        self._a[i], self._a[j] = self._a[j], self._a[i]

    def push(self, priority: float, item: T) -> None:
        self._a.append((priority, self._seq, item))
        self._seq += 1
        i = len(self._a) - 1
        while i > 0:
            parent = (i - 1) // 2
            if not self._above(i, parent):
                break
            self._swap(i, parent)
            i = parent

    def peek(self) -> tuple[float, T]:
        if not self._a:
            raise IndexError("peek from empty heap")
        p, _, item = self._a[0]
        return p, item

    def pop(self) -> tuple[float, T]:
        if not self._a:
            raise IndexError("pop from empty heap")
        top = self._a[0]
        last = self._a.pop()
        if self._a:
            self._a[0] = last
            i, n = 0, len(self._a)
            while True:
                l, r, best = 2 * i + 1, 2 * i + 2, i
                if l < n and self._above(l, best):
                    best = l
                if r < n and self._above(r, best):
                    best = r
                if best == i:
                    break
                self._swap(i, best)
                i = best
        return top[0], top[2]
