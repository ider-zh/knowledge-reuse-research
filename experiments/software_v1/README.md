# software_v1

The first pinned software experiment is the Java class-library method graph for
OpenJDK `jdk-28+13` at commit
`6870f28fe74cbd71419bdd1d1797434366bf8114`.

The frozen graph semantics and acceptance criteria are in
[`openjdk_28_b13/SPEC.md`](openjdk_28_b13/SPEC.md). Compact extraction evidence
is retained under `results/software_v1/openjdk_28_b13/`; large native and
graph-core Parquet tables are rebuildable data and remain under
`data/software/openjdk_jdk_28_b13/`.

This experiment uses JVM method declarations as nodes and bytecode invocation
references as caller-to-callee edges. Unresolved calls remain explicit, and
runtime dispatch candidates are not mixed with exact bytecode references.
