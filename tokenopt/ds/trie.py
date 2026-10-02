"""Binary trie over fixed-width integer keys with insertion counts.

Keys are (block position || perceptual hash of that block). A key that is
inserted in many frames is a recurring overlay (logo, toolbar, watermark):
something the model only needs to see once.
"""
from __future__ import annotations


class _Node:
    __slots__ = ("children", "count", "prefix_count")

    def __init__(self) -> None:
        self.children: list[_Node | None] = [None, None]
        self.count = 0          # insertions ending exactly here
        self.prefix_count = 0   # insertions passing through here


class BitTrie:
    def __init__(self, key_bits: int) -> None:
        self.key_bits = key_bits
        self.root = _Node()
        self.distinct = 0

    def _bits(self, key: int):
        for i in range(self.key_bits - 1, -1, -1):
            yield (key >> i) & 1

    def insert(self, key: int) -> int:
        node = self.root
        node.prefix_count += 1
        for b in self._bits(key):
            if node.children[b] is None:
                node.children[b] = _Node()
            node = node.children[b]
            node.prefix_count += 1
        if node.count == 0:
            self.distinct += 1
        node.count += 1
        return node.count

    def count(self, key: int) -> int:
        node = self.root
        for b in self._bits(key):
            node = node.children[b]
            if node is None:
                return 0
        return node.count

    def count_prefix(self, prefix: int, prefix_len: int) -> int:
        """Total insertions whose top `prefix_len` bits equal `prefix`."""
        node = self.root
        for i in range(prefix_len - 1, -1, -1):
            node = node.children[(prefix >> i) & 1]
            if node is None:
                return 0
        return node.prefix_count

    def frequent(self, min_count: int) -> list[tuple[int, int]]:
        """All keys inserted at least `min_count` times, pruning light subtrees."""
        out: list[tuple[int, int]] = []
        stack: list[tuple[_Node, int, int]] = [(self.root, 0, 0)]
        while stack:
            node, key, depth = stack.pop()
            if node.prefix_count < min_count:
                continue
            if depth == self.key_bits:
                if node.count >= min_count:
                    out.append((key, node.count))
                continue
            for b in (0, 1):
                child = node.children[b]
                if child is not None:
                    stack.append((child, (key << 1) | b, depth + 1))
        return sorted(out)

    def __len__(self) -> int:
        return self.distinct
