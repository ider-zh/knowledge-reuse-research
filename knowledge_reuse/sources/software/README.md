# Open-source software adapter

Software adapters own repository snapshots, language parsing and resolution,
native graph semantics, unresolved-target audits, and the projection into
`graph-core-v1`.

## Implemented adapters

- [`openjdk_method_graph/`](openjdk_method_graph/): method-level Java class
  library call graph for the pinned OpenJDK `jdk-28+13` snapshot. It extracts
  declarations and invocation sites from JMOD bytecode, preserves repeated
  call sites, resolves inherited and signature-polymorphic targets, retains
  unresolved/dynamic calls explicitly, and emits native plus graph-core
  Parquet tables.

Large inputs and generated tables belong under
`data/software/<snapshot>/`. They are reproducible outputs and are not committed.
