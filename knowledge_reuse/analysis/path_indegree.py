"""Exact multiplicity-weighted incoming path counts with explicit cycle boundaries."""

from __future__ import annotations

import math
from collections import deque

import numpy as np
import polars as pl
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


def _log10_integer(value: int) -> float | None:
    if value == 0:
        return None
    bits = value.bit_length()
    shift = max(0, bits - 53)
    return math.log10(value >> shift) + shift * math.log10(2.0)


def weighted_incoming_path_counts(
    node_ids: pl.Series,
    edges: pl.DataFrame,
) -> pl.DataFrame:
    """Count direct and indirect incoming paths, preserving edge multiplicity.

    Every direct edge occurrence is one path. Paths arriving at a node in a
    cyclic strongly connected component are counted there but never extended.
    Direct edges whose source is cyclic are retained, but cannot seed a longer
    path. This makes the remaining propagation graph acyclic and finite.
    """

    if node_ids.n_unique() != len(node_ids):
        raise ValueError("path-count node IDs must be unique")
    required = {"src_id", "dst_id", "multiplicity"}
    if not required.issubset(edges.columns):
        raise ValueError(f"path-count edges require columns {sorted(required)}")
    if edges.filter(pl.col("multiplicity") <= 0).height:
        raise ValueError("path-count edge multiplicity must be positive")
    if edges.select("src_id", "dst_id").n_unique() != edges.height:
        raise ValueError("path-count edges must contain one row per node pair")

    sorted_ids = np.sort(node_ids.to_numpy())
    count = len(sorted_ids)
    src_native = edges["src_id"].to_numpy()
    dst_native = edges["dst_id"].to_numpy()
    src = np.searchsorted(sorted_ids, src_native)
    dst = np.searchsorted(sorted_ids, dst_native)
    if (
        np.any(src >= count)
        or np.any(dst >= count)
        or np.any(sorted_ids[src] != src_native)
        or np.any(sorted_ids[dst] != dst_native)
    ):
        raise ValueError("path-count edges must have internal source and target nodes")

    adjacency = csr_matrix(
        (np.ones(edges.height, dtype=np.uint8), (src, dst)),
        shape=(count, count),
    )
    component_count, labels = connected_components(
        adjacency, directed=True, connection="strong", return_labels=True
    )
    component_sizes = np.bincount(labels, minlength=component_count)
    cyclic = component_sizes[labels] > 1
    cyclic[src[src == dst]] = True

    multiplicities = [int(value) for value in edges["multiplicity"].to_list()]
    total_paths = [0] * count
    extendable_paths = [0] * count
    for source, target, multiplicity in zip(src, dst, multiplicities, strict=True):
        total_paths[target] += multiplicity
        if not cyclic[source] and not cyclic[target]:
            extendable_paths[target] += multiplicity

    propagating = ~cyclic[src] & ~cyclic[dst]
    indegree = np.bincount(dst[propagating], minlength=count).astype(np.int64)
    queue = deque(np.flatnonzero(~cyclic & (indegree == 0)).tolist())
    order = np.argsort(src, kind="stable")
    ordered_dst = dst[order]
    ordered_multiplicity = [multiplicities[index] for index in order]
    offsets = np.zeros(count + 1, dtype=np.int64)
    offsets[1:] = np.cumsum(np.bincount(src, minlength=count))
    processed = 0
    while queue:
        source = queue.popleft()
        processed += 1
        for position in range(offsets[source], offsets[source + 1]):
            target = ordered_dst[position]
            if cyclic[source]:
                continue
            extra = ordered_multiplicity[position] * extendable_paths[source]
            total_paths[target] += extra
            if not cyclic[target]:
                extendable_paths[target] += extra
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(int(target))
    if processed != int((~cyclic).sum()):
        raise RuntimeError("cycle-boundary propagation graph is not acyclic")

    by_native_id = {
        int(node_id): (str(value), _log10_integer(value), bool(cyclic[index]))
        for index, (node_id, value) in enumerate(zip(sorted_ids, total_paths, strict=True))
    }
    return pl.DataFrame(
        {
            "node_id": node_ids,
            "in_paths_source": [by_native_id[int(node_id)][0] for node_id in node_ids],
            "in_paths_source_log10": [
                by_native_id[int(node_id)][1] for node_id in node_ids
            ],
            "is_path_cycle_boundary": [
                by_native_id[int(node_id)][2] for node_id in node_ids
            ],
        },
        schema={
            "node_id": node_ids.dtype,
            "in_paths_source": pl.String,
            "in_paths_source_log10": pl.Float64,
            "is_path_cycle_boundary": pl.Boolean,
        },
    )
