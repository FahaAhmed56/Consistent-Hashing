# Consistent Hashing

The algorithm that decides **which server holds which key** in a distributed
system — built from scratch in pure Python, with a demo that *proves* why it
beats the naive approach.

Consistent hashing is how Cassandra, DynamoDB, many CDNs, and sharded caches
(like Memcached clusters) spread data across servers. It's one of the most
common distributed-systems / system-design interview topics.

Pure standard library — **nothing to install**.

## The problem it solves

You have N servers and millions of keys, and you need a rule mapping each key to
a server. The obvious rule is:

```
server = hash(key) % N
```

It works perfectly — until N changes. Add or remove a single server and the `% N`
changes for almost *every* key, so nearly all your data has to move at once:
caches go cold, databases thrash, everything grinds. At scale that's an outage.

**Consistent hashing** fixes this. Picture a circle. Each server is placed at
several points around it, and each key is placed at its own point. A key belongs
to the first server you meet walking clockwise. Now adding or removing a server
only disturbs the keys in one arc — about **1/N** of them — not all of them.

## See the proof

```bash
python hashring.py demo
```

```
Adding one server (4 -> 5):
  consistent hashing remapped :  17.2% of keys
  naive hash % N remapped     :  80.1% of keys
  theoretical best (1/(N+1))  :  20.0%
```

Same 100,000 keys, same change. Consistent hashing moves ~1/5 of them (close to
the theoretical ideal); naive hashing moves 4 out of 5. That gap is the entire
reason the algorithm exists.

## Virtual nodes (the trick that makes it practical)

If each server sat at just *one* point on the ring, the arcs between servers
would be wildly uneven and some servers would get far more keys than others. So
each server is scattered across **many** points — its "virtual nodes." With ~150
virtual nodes per server, the demo spreads 100k keys across 4 servers to within
~19% of a perfect split. More virtual nodes = smoother balance.

## Use it in code

```python
from hashring import ConsistentHashRing

ring = ConsistentHashRing(["cache-1", "cache-2", "cache-3"], replicas=150)

server = ring.get_node("user:12345")   # always the same server for this key
ring.add_node("cache-4")               # only ~1/4 of keys move
ring.remove_node("cache-1")            # only cache-1's keys move
```

## Run the tests

```bash
python test_hashring.py       # no dependencies
# or, with pytest:
python -m pytest
```

They verify the properties that matter: a key always maps to the same server,
removing a server moves *only* that server's keys (never anyone else's), adding
a server remaps only ~1/N, naive modulo remaps most keys, and more virtual nodes
improve balance.

## How it's built

- `_hash` — a stable, well-spread hash (md5 → int)
- `ConsistentHashRing.add_node` / `remove_node` — scatter/remove virtual nodes
- `ConsistentHashRing.get_node` — binary search (`bisect`) to the next point
  clockwise, O(log n) per lookup
- `NaiveModuloRing` — the `hash % N` version, for the side-by-side
- `cmd_demo` — measures remapping and distribution on 100k keys

## Ideas for later

- **Replication**: return the next *k* distinct servers clockwise, so each key
  lives on more than one server (how real datastores survive a node dying)
- **Weighted nodes**: give bigger servers more virtual nodes
- Plot the ring and the key distribution
- Bound the lookup with a jump-consistent-hash variant
