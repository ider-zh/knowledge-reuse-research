# Software v1 handoff

- Workstream: software / OpenJDK method graph
- State: implementation and full-corpus validation complete
- Base branch: `main`
- Owned paths: `knowledge_reuse/sources/software/`,
  `experiments/software_v1/`, `results/software_v1/openjdk_28_b13/`

## Current evidence

The official OpenJDK `28-ea+13-812` Linux x64 JMOD corpus was processed under
the frozen default-runtime semantics. The golden capability fixture passes.
The full run contains 239,765 method nodes, 859,406 resolved call-site facts,
621,105 invocation-kind-specific aggregated edges, and 15,442 explicitly
retained unresolved facts. All resolved endpoints exist, graph-core
multiplicity matches the native graph, and two independent normalization runs
produced identical SHA-256 values for all seven Parquet datasets.

## Commands

```bash
knowledge_reuse/sources/software/openjdk_method_graph/scripts/golden.sh \
  /path/to/jdk-28 /tmp/openjdk-method-graph-golden

knowledge_reuse/sources/software/openjdk_method_graph/scripts/run.sh \
  /path/to/jdk-28 \
  /path/to/openjdk-28-ea+13_linux-x64_bin.tar.gz
```

## Intentionally uncommitted artifacts

The JDK archive, unpacked JDK, raw TSV facts, and generated Parquet datasets are
large rebuildable artifacts under `vendor/` or `data/software/` and are excluded
from Git.

## Next action

Use `graph_core_nodes.parquet` and `graph_core_links.parquet` as the input to
the shared reuse analysis. If runtime-dispatch sensitivity is required, add a
separate CHA/RTA projection rather than modifying the exact-reference graph.
