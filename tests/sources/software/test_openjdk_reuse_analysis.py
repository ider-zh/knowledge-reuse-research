from pathlib import Path

import polars as pl

from knowledge_reuse.sources.software.openjdk_method_graph.scripts.analyze_reuse import main


def test_analysis_writes_direct_and_indirect_metrics(tmp_path: Path, monkeypatch) -> None:
    node_count = 21
    nodes = pl.DataFrame(
        {
            "graph_id": ["fixture"] * node_count,
            "node_id": pl.Series(range(node_count), dtype=pl.UInt64),
            "native_id": [f"n{index}" for index in range(node_count)],
            "label": [f"n{index}" for index in range(node_count)],
            "node_type": ["method"] * node_count,
            "domain": ["fixture"] * node_count,
            "is_generated": [False] * node_count,
            "size_source": pl.Series([None] * node_count, dtype=pl.UInt64),
            "size_semantic": pl.Series([None] * node_count, dtype=pl.UInt64),
        }
    )
    edge_count = node_count - 1
    links = pl.DataFrame(
        {
            "graph_id": ["fixture"] * edge_count,
            "src_id": pl.Series(range(edge_count), dtype=pl.UInt64),
            "dst_id": pl.Series(range(1, node_count), dtype=pl.UInt64),
            "relation": ["CALLS"] * edge_count,
            "multiplicity": pl.Series([2, 3, *([1] * (edge_count - 2))], dtype=pl.UInt64),
        }
    )
    node_path = tmp_path / "nodes.parquet"
    link_path = tmp_path / "links.parquet"
    output = tmp_path / "output"
    nodes.write_parquet(node_path)
    links.write_parquet(link_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "analyze_reuse.py",
            "--nodes",
            str(node_path),
            "--links",
            str(link_path),
            "--output",
            str(output),
        ],
    )

    main()

    result = pl.read_parquet(output / "node_incoming_paths.parquet")
    row = result.filter(pl.col("node_id") == 2).row(0, named=True)
    assert row["direct_call_occurrences"] == 3
    assert row["indirect_incoming_paths"] == "6"
    assert row["in_paths_source"] == "9"
