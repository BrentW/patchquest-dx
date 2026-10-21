"""Read-only, explicit FAT8 chain inspection. Apache-2.0.

No filesystem discovery, allocation, free-space approval or disk writes.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Chain:
    clusters: tuple
    sector_counts: tuple


def agree(copies):
    """Require identical explicit FAT copies; never vote or silently repair."""
    copies = tuple(copies)
    if not copies or any(not isinstance(c, (bytes, bytearray, memoryview)) for c in copies):
        raise ValueError('expected nonempty collection of byte tables')
    copies = tuple(bytes(c) for c in copies)
    if not copies[0] or any(c != copies[0] for c in copies[1:]):
        raise ValueError('empty or disagreeing FAT copies')
    return copies[0]


def walk(table, start, *, cluster_count, sectors_per_cluster, terminal_first=0xc1):
    """Walk a caller-selected byte table with terminal-sector-count markers.

    Indices 0..cluster_count-1 are links. terminal_first denotes one occupied
    sector in the final cluster; subsequent markers denote larger counts.
    Every other byte is rejected, including unused/system markers. Geometry,
    directory selection and interpretation of flags belong to the caller.
    """
    if not isinstance(table, (bytes, bytearray, memoryview)):
        raise ValueError('expected byte table')
    table = bytes(table)
    values = (start, cluster_count, sectors_per_cluster, terminal_first)
    if any(type(v) is not int for v in values):
        raise ValueError('expected integer profile values')
    if not 0 < cluster_count <= terminal_first <= 255 or cluster_count > len(table):
        raise ValueError('invalid cluster count or terminal range')
    if not 1 <= sectors_per_cluster <= 256-terminal_first:
        raise ValueError('invalid terminal-sector count')
    if not 0 <= start < cluster_count:
        raise ValueError('start outside table profile')
    clusters, counts, seen = [], [], set()
    current = start
    while True:
        if current in seen:
            raise ValueError('cyclic allocation chain')
        seen.add(current); clusters.append(current)
        value = table[current]
        if terminal_first <= value < terminal_first + sectors_per_cluster:
            counts.append(value-terminal_first+1)
            return Chain(tuple(clusters), tuple(counts))
        if not 0 <= value < cluster_count:
            raise ValueError('invalid, unused or reserved chain entry')
        counts.append(sectors_per_cluster)
        current = value


def crosslinks(chains):
    """Report clusters shared by named chains; no owner or repair is inferred."""
    owners = {}
    for name, chain in chains.items():
        for cluster in chain.clusters:
            owners.setdefault(cluster, []).append(name)
    return {cluster: tuple(names) for cluster, names in owners.items() if len(names)>1}
