import random

import numpy as np
import pytest

from tokenopt.ds.hash_table import ChainedHashTable, MultiIndexHashTable, hamming
from tokenopt.ds.max_heap import MaxHeap
from tokenopt.ds.quadtree import AdaptiveQuadtree
from tokenopt.ds.summed_area import SummedAreaTable
from tokenopt.ds.trie import BitTrie
from tokenopt.ds.union_find import UnionFind


def test_max_heap_pops_in_descending_order():
    rng = random.Random(0)
    values = [rng.random() for _ in range(500)]
    h = MaxHeap()
    for v in values:
        h.push(v, v)
    assert [h.pop()[1] for _ in range(len(values))] == sorted(values, reverse=True)
    with pytest.raises(IndexError):
        h.pop()


def test_max_heap_ties_are_fifo():
    h = MaxHeap()
    for name in "abc":
        h.push(1.0, name)
    assert [h.pop()[1] for _ in range(3)] == ["a", "b", "c"]


def test_union_find_groups_and_counts():
    uf = UnionFind(6)
    uf.union(0, 1)
    uf.union(1, 2)
    uf.union(4, 5)
    assert uf.components == 3
    assert uf.groups() == [[0, 1, 2], [3], [4, 5]]
    assert uf.connected(0, 2) and not uf.connected(2, 3)
    assert not uf.union(0, 2)


def test_bit_trie_counts_prefixes_and_frequent_keys():
    t = BitTrie(8)
    for k in [5, 5, 5, 7, 200]:
        t.insert(k)
    assert t.count(5) == 3 and t.count(6) == 0
    assert len(t) == 3
    assert t.count_prefix(0, 1) == 4  # keys < 128
    assert t.frequent(2) == [(5, 3)]


def test_chained_hash_table_survives_resizing():
    t = ChainedHashTable(capacity=4)
    for i in range(1000):
        t.insert(i % 250, i)
    assert len(t) == 1000
    assert sorted(t.get_all(7)) == [7, 257, 507, 757]


def test_multi_index_hash_finds_every_near_duplicate():
    rng = random.Random(1)
    stored = [rng.getrandbits(64) for _ in range(300)]
    index = MultiIndexHashTable(max_distance=4)
    for i, h in enumerate(stored):
        index.add(h, i)
    for _ in range(200):
        base = rng.choice(stored)
        q = base
        for bit in rng.sample(range(64), rng.randint(0, 4)):
            q ^= 1 << bit
        brute = sorted(i for i, h in enumerate(stored) if hamming(q, h) <= 4)
        assert sorted(p for _, p in index.query(q)) == brute


def test_summed_area_table_matches_numpy():
    rng = np.random.default_rng(2)
    img = rng.integers(0, 256, (37, 53, 3)).astype(np.uint8)
    sat = SummedAreaTable(img)
    for _ in range(50):
        x, y = rng.integers(0, 50), rng.integers(0, 34)
        w, h = rng.integers(1, 53 - x + 1), rng.integers(1, 37 - y + 1)
        region = img[y:y + h, x:x + w].astype(np.float64)
        mean, var = sat.stats(x, y, w, h)
        assert np.allclose(mean, region.reshape(-1, 3).mean(0))
        assert var == pytest.approx(region.reshape(-1, 3).var(0).mean(), abs=1e-6)


def _image():
    img = np.full((200, 300, 3), 240, np.uint8)
    rng = np.random.default_rng(3)
    img[40:90, 50:170] = rng.integers(0, 256, (50, 120, 3))
    return img


def _coverage(leaves, shape):
    cover = np.zeros(shape[:2], int)
    for l in leaves:
        cover[l.y:l.y + l.h, l.x:l.x + l.w] += 1
    return cover


def test_quadtree_leaves_tile_the_image_exactly():
    img = _image()
    leaves = AdaptiveQuadtree(img, 16).build_recursive(40.0)
    assert (_coverage(leaves, img.shape) == 1).all()


def test_quadtree_full_split_equals_uniform_baseline():
    img = _image()
    tree = AdaptiveQuadtree(img, 16)
    assert len(tree.build_recursive(-1.0)) == tree.baseline_tokens == 13 * 19


def test_heap_builder_matches_recursive_when_unconstrained():
    img = _image()
    a = AdaptiveQuadtree(img, 16).build_recursive(40.0)
    b = AdaptiveQuadtree(img, 16).build_budgeted(10 ** 9, 40.0)
    key = lambda l: (l.gx, l.gy, l.gw, l.gh)
    assert sorted(map(key, a)) == sorted(map(key, b))


@pytest.mark.parametrize("budget", [1, 10, 37, 100])
def test_heap_builder_respects_budget_and_still_tiles(budget):
    img = _image()
    leaves = AdaptiveQuadtree(img, 16).build_budgeted(budget)
    assert len(leaves) <= budget
    assert (_coverage(leaves, img.shape) == 1).all()
