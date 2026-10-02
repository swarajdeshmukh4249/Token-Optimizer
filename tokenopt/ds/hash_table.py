"""Hash tables for perceptual-hash signatures.

ChainedHashTable  -- a multimap with separate chaining and load-factor resizing.
MultiIndexHashTable -- near-duplicate search over 64-bit hashes. The hash is cut
    into m disjoint bands, each band indexed in its own ChainedHashTable. By the
    pigeonhole principle, two hashes within Hamming distance < m agree exactly on
    at least one band, so probing m buckets finds *every* near-duplicate without
    scanning the whole store (multi-index hashing, Norouzi et al. 2012).
"""
from __future__ import annotations

from typing import Any, Iterator

_GOLDEN = 0x9E3779B97F4A7C15
_MASK64 = (1 << 64) - 1


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class _Entry:
    __slots__ = ("key", "value", "next")

    def __init__(self, key: int, value: Any, nxt: "_Entry | None") -> None:
        self.key, self.value, self.next = key, value, nxt


class ChainedHashTable:
    def __init__(self, capacity: int = 64, max_load: float = 0.75) -> None:
        self._buckets: list[_Entry | None] = [None] * capacity
        self._size = 0
        self.max_load = max_load

    def _index(self, key: int, n: int) -> int:
        # Fibonacci (multiplicative) hashing: spreads small/structured ints well.
        return ((key * _GOLDEN) & _MASK64) % n

    def insert(self, key: int, value: Any) -> None:
        if (self._size + 1) / len(self._buckets) > self.max_load:
            self._resize(len(self._buckets) * 2)
        i = self._index(key, len(self._buckets))
        self._buckets[i] = _Entry(key, value, self._buckets[i])
        self._size += 1

    def get_all(self, key: int) -> Iterator[Any]:
        node = self._buckets[self._index(key, len(self._buckets))]
        while node is not None:
            if node.key == key:
                yield node.value
            node = node.next

    def _resize(self, capacity: int) -> None:
        old = self._buckets
        self._buckets = [None] * capacity
        for head in old:
            node = head
            while node is not None:
                nxt = node.next
                i = self._index(node.key, capacity)
                node.next = self._buckets[i]
                self._buckets[i] = node
                node = nxt

    def __len__(self) -> int:
        return self._size

    def max_chain(self) -> int:
        best = 0
        for head in self._buckets:
            n, node = 0, head
            while node is not None:
                n, node = n + 1, node.next
            best = max(best, n)
        return best


class MultiIndexHashTable:
    def __init__(self, max_distance: int = 4, bits: int = 64) -> None:
        self.max_distance = max_distance
        self.bits = bits
        m = max_distance + 1
        self._bounds = [(i * bits // m, (i + 1) * bits // m) for i in range(m)]
        self._tables = [ChainedHashTable() for _ in range(m)]
        self._count = 0

    def _bands(self, h: int) -> list[int]:
        return [(h >> lo) & ((1 << (hi - lo)) - 1) for lo, hi in self._bounds]

    def add(self, h: int, payload: Any) -> None:
        entry = (h, payload)  # one shared tuple, so duplicates across bands dedupe by id
        for table, band in zip(self._tables, self._bands(h)):
            table.insert(band, entry)
        self._count += 1

    def query(self, h: int, max_distance: int | None = None) -> list[tuple[int, Any]]:
        """(distance, payload) for every stored hash within max_distance, nearest first."""
        d = self.max_distance if max_distance is None else max_distance
        if d > self.max_distance:
            raise ValueError("query radius exceeds the radius the index guarantees")
        seen: set[int] = set()
        hits: list[tuple[int, Any]] = []
        for table, band in zip(self._tables, self._bands(h)):
            for entry in table.get_all(band):
                if id(entry) in seen:
                    continue
                seen.add(id(entry))
                dist = hamming(h, entry[0])
                if dist <= d:
                    hits.append((dist, entry[1]))
        hits.sort(key=lambda t: t[0])
        return hits

    def __len__(self) -> int:
        return self._count
