"""Tests for hashring.py.

Run with:  python test_hashring.py       (no dependencies)
       or:  python -m pytest

The hash (md5) is deterministic, so every number here is reproducible run to run
— no random seed needed.
"""

from hashring import ConsistentHashRing, NaiveModuloRing, distribution


KEYS = [f"key-{i}" for i in range(10000)]


def test_empty_ring_returns_none():
    assert ConsistentHashRing().get_node("anything") is None


def test_same_key_always_maps_to_same_node():
    ring = ConsistentHashRing(["a", "b", "c"])
    first = ring.get_node("user-42")
    for _ in range(100):
        assert ring.get_node("user-42") == first


def test_every_key_lands_on_a_real_node():
    ring = ConsistentHashRing(["a", "b", "c"])
    for k in KEYS[:500]:
        assert ring.get_node(k) in {"a", "b", "c"}


def test_removing_a_node_only_remaps_that_nodes_keys():
    """The core guarantee: removing server C must NOT move keys that were on
    A or B. Only C's keys get redistributed."""
    ring = ConsistentHashRing(["a", "b", "c"])
    before = {k: ring.get_node(k) for k in KEYS}
    ring.remove_node("c")
    for k in KEYS:
        if before[k] != "c":
            assert ring.get_node(k) == before[k], f"{k} moved but wasn't on c"
        else:
            assert ring.get_node(k) in {"a", "b"}  # c's keys went elsewhere


def test_adding_a_node_remaps_only_a_small_fraction():
    """Adding a 5th server should move roughly 1/5 of keys, not most of them."""
    ring = ConsistentHashRing([f"s{i}" for i in range(4)], replicas=200)
    before = {k: ring.get_node(k) for k in KEYS}
    ring.add_node("s4")
    moved = sum(1 for k in KEYS if ring.get_node(k) != before[k]) / len(KEYS)
    # Theoretical ideal is 20%; allow headroom for virtual-node variance.
    assert 0.10 < moved < 0.32, f"moved {moved:.1%}, expected ~20%"


def test_naive_modulo_remaps_almost_everything():
    """Contrast: naive hash % N scrambles nearly all keys when N changes."""
    ring = NaiveModuloRing([f"s{i}" for i in range(4)])
    before = {k: ring.get_node(k) for k in KEYS}
    ring.add_node("s4")
    moved = sum(1 for k in KEYS if ring.get_node(k) != before[k]) / len(KEYS)
    assert moved > 0.6, f"expected most keys to move, only {moved:.1%} did"


def test_more_virtual_nodes_improve_balance():
    """Many virtual nodes per server => more even key distribution."""
    def imbalance(replicas):
        ring = ConsistentHashRing([f"s{i}" for i in range(5)], replicas=replicas)
        counts = distribution(ring, KEYS)
        # spread between the busiest and quietest server, relative to ideal
        ideal = len(KEYS) / 5
        return (max(counts.values()) - min(counts.values())) / ideal

    assert imbalance(500) < imbalance(1), "more vnodes should balance better"


def test_node_set_tracks_changes():
    ring = ConsistentHashRing(["a", "b"])
    assert ring.nodes == {"a", "b"}
    ring.add_node("c")
    assert ring.nodes == {"a", "b", "c"}
    ring.remove_node("a")
    assert ring.nodes == {"b", "c"}


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} tests passed")
