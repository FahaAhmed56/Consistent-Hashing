#!/usr/bin/env python3
"""Consistent hashing — how distributed systems decide which server holds a key.

THE PROBLEM. You have N servers and millions of keys (cache entries, user
records, files). You need a rule that maps each key to a server. The obvious
rule is `server = hash(key) % N`. It works... until N changes. Add or remove
one server and almost EVERY key suddenly maps somewhere new, so your whole
cache is cold and data has to move en masse. That's a catastrophe at scale.

THE FIX. Consistent hashing places both servers and keys on an imaginary
circle (a "ring"). A key belongs to the first server found walking clockwise
from the key's position. Now adding or removing a server only disturbs the keys
in one arc of the ring — about 1/N of them — instead of nearly all of them.
This is how Cassandra, DynamoDB, many CDNs, and sharded caches spread data.

VIRTUAL NODES. One point per server gives lumpy, unfair distribution. So each
server is placed at MANY points around the ring (its "virtual nodes"), which
evens out the load. That one trick is what makes consistent hashing practical.

CLI:
    python hashring.py demo    # prove the minimal-remapping property with numbers
"""

import argparse
import bisect
import hashlib
from collections import Counter


def _hash(value):
    """A stable 128-bit hash as an int. md5 is used for its even spread, not
    for security — consistent hashing just needs a well-distributed hash."""
    return int(hashlib.md5(str(value).encode("utf-8")).hexdigest(), 16)


class ConsistentHashRing:
    """A hash ring with virtual nodes.

    `replicas` is how many points each server occupies on the ring. More points
    = more even distribution (at a little memory cost). 100-200 is typical.
    """

    def __init__(self, nodes=None, replicas=150):
        self.replicas = replicas
        self._ring = {}          # ring position (int) -> server name
        self._sorted = []        # sorted ring positions, for fast lookup
        self._nodes = set()
        for node in nodes or []:
            self.add_node(node)

    def _vnode_key(self, node, i):
        # Each server gets `replicas` distinct positions, one per index.
        return f"{node}#{i}"

    def add_node(self, node):
        """Add a server: scatter its virtual nodes around the ring."""
        if node in self._nodes:
            return
        self._nodes.add(node)
        for i in range(self.replicas):
            pos = _hash(self._vnode_key(node, i))
            self._ring[pos] = node
        self._rebuild()

    def remove_node(self, node):
        """Remove a server: delete all its virtual nodes from the ring."""
        if node not in self._nodes:
            return
        self._nodes.discard(node)
        for i in range(self.replicas):
            pos = _hash(self._vnode_key(node, i))
            self._ring.pop(pos, None)
        self._rebuild()

    def _rebuild(self):
        self._sorted = sorted(self._ring)

    def get_node(self, key):
        """Which server owns this key? The first one clockwise on the ring."""
        if not self._ring:
            return None
        h = _hash(key)
        # Find the first ring position >= the key's position...
        idx = bisect.bisect_right(self._sorted, h)
        # ...wrapping back to the start of the ring if we ran off the end.
        if idx == len(self._sorted):
            idx = 0
        return self._ring[self._sorted[idx]]

    @property
    def nodes(self):
        return set(self._nodes)


class NaiveModuloRing:
    """The simple, broken-at-scale approach, for comparison: hash(key) % N."""

    def __init__(self, nodes=None):
        self._nodes = list(nodes or [])

    def add_node(self, node):
        if node not in self._nodes:
            self._nodes.append(node)

    def remove_node(self, node):
        if node in self._nodes:
            self._nodes.remove(node)

    def get_node(self, key):
        if not self._nodes:
            return None
        return self._nodes[_hash(key) % len(self._nodes)]

    @property
    def nodes(self):
        return set(self._nodes)


# ---------------------------------------------------------------------------
# Helpers for the demo / analysis.
# ---------------------------------------------------------------------------
def distribution(ring, keys):
    """Count how many keys land on each server."""
    counts = Counter(ring.get_node(k) for k in keys)
    return counts


def fraction_remapped(ring_factory, mutate, keys):
    """Map all keys, apply a change (add/remove a node), and return the fraction
    of keys that ended up on a different server."""
    ring = ring_factory()
    before = {k: ring.get_node(k) for k in keys}
    mutate(ring)
    moved = sum(1 for k in keys if ring.get_node(k) != before[k])
    return moved / len(keys)


# ---------------------------------------------------------------------------
# Demo.
# ---------------------------------------------------------------------------
def cmd_demo(args):
    keys = [f"key-{i}" for i in range(args.keys)]
    start_nodes = [f"server-{i}" for i in range(args.nodes)]

    print(f"{args.keys:,} keys across {args.nodes} servers.\n")

    # --- 1) Distribution balance with virtual nodes ---
    ring = ConsistentHashRing(start_nodes, replicas=args.replicas)
    dist = distribution(ring, keys)
    print(f"Key distribution (consistent hashing, {args.replicas} vnodes/server):")
    ideal = args.keys / args.nodes
    for node in sorted(dist):
        pct = dist[node] / args.keys * 100
        print(f"  {node:<12} {dist[node]:>7,}  ({pct:4.1f}%)")
    spread = (max(dist.values()) - min(dist.values())) / ideal * 100
    print(f"  ideal per server: {ideal:,.0f}   max-min spread: {spread:.1f}% of ideal\n")

    # --- 2) The headline: what happens when you ADD a server ---
    def add_one(r):
        r.add_node(f"server-{args.nodes}")

    ch_moved = fraction_remapped(
        lambda: ConsistentHashRing(start_nodes, replicas=args.replicas),
        add_one, keys)
    naive_moved = fraction_remapped(
        lambda: NaiveModuloRing(start_nodes), add_one, keys)

    print(f"Adding one server ({args.nodes} -> {args.nodes + 1}):")
    print(f"  consistent hashing remapped : {ch_moved * 100:5.1f}% of keys")
    print(f"  naive hash % N remapped     : {naive_moved * 100:5.1f}% of keys")
    print(f"  theoretical best (1/(N+1))  : {100 / (args.nodes + 1):5.1f}%\n")

    # --- 3) And when you REMOVE a server ---
    def remove_one(r):
        r.remove_node("server-0")

    ch_rm = fraction_remapped(
        lambda: ConsistentHashRing(start_nodes, replicas=args.replicas),
        remove_one, keys)
    naive_rm = fraction_remapped(
        lambda: NaiveModuloRing(start_nodes), remove_one, keys)

    print(f"Removing one server ({args.nodes} -> {args.nodes - 1}):")
    print(f"  consistent hashing remapped : {ch_rm * 100:5.1f}% of keys")
    print(f"  naive hash % N remapped     : {naive_rm * 100:5.1f}% of keys")
    print("\nThat gap is the whole point: consistent hashing moves only the keys")
    print("it must, so adding/removing a server doesn't cold-start your cache.")


def main():
    parser = argparse.ArgumentParser(description="Consistent hashing from scratch.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo", help="measure the minimal-remapping property")
    p.add_argument("--keys", type=int, default=100000)
    p.add_argument("--nodes", type=int, default=4)
    p.add_argument("--replicas", type=int, default=150)
    p.set_defaults(func=cmd_demo)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
