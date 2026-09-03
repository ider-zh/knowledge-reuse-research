# OpenJDK method graph adapter

This adapter builds a method-level static call graph from the Java class
libraries in the official OpenJDK 28 Early-Access build 13 binary.

## Frozen identity

- Repository: `https://github.com/openjdk/jdk`
- Tag: `jdk-28+13`
- Commit: `6870f28fe74cbd71419bdd1d1797434366bf8114`
- Runtime build: `28-ea+13-812`
- Linux x64 archive SHA-256:
  `e4a930685f551dc72f843ee83fd1ce3901edeed8db422f0f98f3e9c0e7f4ddb8`
- Graph ID: `software/openjdk/jdk-28+13/default`

## Semantics

A node is one JVM method declaration. Constructors, static initializers,
abstract methods, native methods, synthetic methods, bridge methods, and lambda
bodies are included. Module, package, and class are method attributes rather
than graph nodes.

An edge points from caller to statically referenced callee. The native graph
retains `STATIC`, `SPECIAL`, `VIRTUAL`, `INTERFACE`, and resolved `DYNAMIC`
invocation kinds. Repeated bytecode occurrences remain separate in
`call_sites.parquet` and are represented by `callsite_count` in the aggregated
graph.

The graph models the default runtime without `--enable-preview`; JMOD
`META-INF/preview` overlays are excluded to prevent duplicate JVM identities.
Native C/C++ implementations and runtime virtual-dispatch expansion are outside
this graph. Unresolved targets are retained in an audit table.

## Gates and execution

The runner executes a synthetic golden JMOD before scanning the full corpus.
The fixture asserts all five invocation categories plus constructor, native,
and abstract declarations. A failed gate stops the full run.

Prerequisites are Python 3.12+, the repository dependencies, `rg`, and the
official JDK 28+13 archive unpacked locally.

```bash
knowledge_reuse/sources/software/openjdk_method_graph/scripts/run.sh \
  /path/to/jdk-28 \
  /path/to/openjdk-28-ea+13_linux-x64_bin.tar.gz
```

By default, rebuildable outputs are written to:

```text
data/software/openjdk_jdk_28_b13/
├── golden/
├── raw/
└── normalized/
```

The normalized directory contains the source-native method/call-site tables,
the closed aggregated graph, unresolved-call audit facts, auxiliary class
hierarchy metadata, and `graph-core-v1` node/link projections.

The complete graph contract is frozen in the experiment
[`SPEC.md`](../../../../experiments/software_v1/openjdk_28_b13/SPEC.md).
