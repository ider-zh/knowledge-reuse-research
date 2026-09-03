# OpenJDK 28+13 Java Method Graph Specification

Version: 1.0  
Status: Frozen for implementation  
Target: OpenJDK `jdk-28+13`, Linux x64 official early-access binary

## 1. Objective

Build a static, method-level call graph for the Java class libraries shipped in
the official OpenJDK 28 Early-Access build 13 binary. The graph supports direct
and transitive caller analysis, reachability, cycle detection, call-path
analysis, and source navigation.

The graph covers Java bytecode only. HotSpot C/C++, JNI implementations, build
tools, tests, demos, and benchmark code are outside scope.

## 2. Authoritative input

- Binary: `openjdk-28-ea+13_linux-x64_bin.tar.gz`
- Source identity: OpenJDK tag `jdk-28+13`
- Source commit: `6870f28fe74cbd71419bdd1d1797434366bf8114`
- Binary verification: `java -version` must report `28-ea` and build `28-ea+13`
- Class corpus: every standard `classes/**/*.class` entry in every
  `jmods/*.jmod`, excluding `classes/META-INF/**` variant overlays
- Source corpus: `lib/src.zip`, when present

The binary archive SHA-256 and all JMOD filenames are recorded in the run
manifest. Extraction must never silently substitute another JDK build.

The version-1 graph models the default JDK runtime without `--enable-preview`.
Preview overlays under `classes/META-INF/preview` can replace classes with the
same JVM identity and therefore must be built as a separate graph variant; they
must not be merged into the default graph.

## 3. Graph model

### 3.1 Node

One node represents one JVM method declaration found in the class corpus.
Included declarations are ordinary methods, constructors (`<init>`), static
initializers (`<clinit>`), interface and abstract methods, native methods,
synthetic methods, bridge methods, and compiler-generated lambda bodies.

Module, package, class, field, source file, call site, and native function are
not graph nodes. Module, package, class, and source location are method
attributes.

Canonical method key:

```text
{module}/{internal-class-name}#{method-name}{JVM-descriptor}
```

Example:

```text
java.base/java/lang/String#substring(II)Ljava/lang/String;
```

`method_id` is an unsigned 64-bit deterministic hash of `method_key`. The full
key remains authoritative; hash collisions are checked and fail the run.

### 3.2 Call-site edge

A call-site edge represents one bytecode invocation instruction in a caller
method. Direction is caller to statically referenced callee.

Supported invocation kinds:

- `STATIC` (`invokestatic`)
- `SPECIAL` (`invokespecial`)
- `VIRTUAL` (`invokevirtual`)
- `INTERFACE` (`invokeinterface`)
- `DYNAMIC` (`invokedynamic`) when a concrete method handle can be resolved

Repeated calls are retained as separate call-site records using bytecode order
and source line. No occurrence is discarded in the fact table.

### 3.3 Aggregated edge

An aggregated method edge is unique by:

```text
(caller_method_id, callee_method_id, invoke_kind)
```

It stores `callsite_count`. Graph traversal and centrality use aggregated edges;
source navigation and occurrence analysis use call-site edges.

### 3.4 Callee resolution

Normal invoke instructions target the owner, name, and descriptor encoded in
the class file. The referenced declaration may be inherited from a superclass
or interface, so resolution searches the class hierarchy when the exact owner
does not declare it.

When no declaration exists in the selected JMOD corpus, the call is retained in
`unresolved_calls` and excluded from the closed method graph. Missing targets
must not be silently dropped.

### 3.5 Dynamic invocation

For LambdaMetafactory call sites, method handles in bootstrap arguments are
recorded as resolved `DYNAMIC` calls. Other `invokedynamic` sites, including
runtime bootstrap operations without a single concrete Java target, are stored
in `unresolved_calls` with their bootstrap owner and descriptor.

### 3.6 Runtime dispatch

Version 1 produces the exact bytecode-reference graph. It does not expand a
virtual/interface invocation into every possible runtime implementation.
Class hierarchy metadata required for a future CHA projection is retained, but
`DISPATCHES_TO` is not part of the version-1 acceptance criteria. This avoids
mixing certain bytecode references with conservative runtime candidates.

## 4. Output datasets

All tabular outputs use Parquet with Zstandard compression.

### 4.1 `methods.parquet`

| Field | Type | Meaning |
| --- | --- | --- |
| `method_id` | UINT64 | Deterministic identifier |
| `method_key` | STRING | Canonical method key |
| `module_name` | STRING | JDK module |
| `package_name` | STRING | Java package |
| `class_name` | STRING | Binary class name |
| `method_name` | STRING | JVM method name |
| `descriptor` | STRING | JVM method descriptor |
| `access_flags` | INT32 | Class-file access mask |
| `source_file` | STRING? | Source filename attribute |
| `first_line` | INT32? | Minimum line in method body |
| `last_line` | INT32? | Maximum line in method body |
| `is_constructor` | BOOLEAN | Name is `<init>` |
| `is_static_init` | BOOLEAN | Name is `<clinit>` |
| `is_static` | BOOLEAN | Static access flag |
| `is_abstract` | BOOLEAN | Abstract access flag |
| `is_native` | BOOLEAN | Native access flag |
| `is_synthetic` | BOOLEAN | Synthetic access flag |
| `is_bridge` | BOOLEAN | Bridge access flag |
| `has_code` | BOOLEAN | Has a Code attribute |

### 4.2 `call_sites.parquet`

| Field | Type | Meaning |
| --- | --- | --- |
| `caller_method_id` | UINT64 | Caller |
| `callee_method_id` | UINT64 | Resolved callee |
| `invoke_kind` | STRING | Invocation category |
| `instruction_ordinal` | INT32 | Invocation order in caller |
| `source_line` | INT32? | Current line number |
| `declared_owner` | STRING | Owner in constant pool |
| `declared_name` | STRING | Referenced method name |
| `declared_descriptor` | STRING | Referenced descriptor |
| `resolution` | STRING | `EXACT`, `INHERITED`, or `BOOTSTRAP_HANDLE` |

### 4.3 `method_edges.parquet`

| Field | Type | Meaning |
| --- | --- | --- |
| `caller_method_id` | UINT64 | Caller |
| `callee_method_id` | UINT64 | Callee |
| `invoke_kind` | STRING | Invocation category |
| `callsite_count` | UINT32 | Number of call sites |

### 4.4 Supporting outputs

- `classes.parquet`: non-graph class hierarchy metadata
- `unresolved_calls.parquet`: retained unresolved invocation facts
- `graph_core_nodes.parquet`: `graph-core-v1` portable method projection
- `graph_core_links.parquet`: `graph-core-v1` caller-to-callee projection
- `graph_manifest.json`: input identity, checksums, counts, tool version, time
- `validation_report.md`: acceptance results and limitations

## 5. Pipeline and checkpoints

1. Download archive to a resumable cache.
2. Verify archive SHA-256 and JDK version.
3. Inventory JMODs and write the input manifest checkpoint.
4. Extract/scan each JMOD independently; write one raw partition per module.
5. Merge method declarations and verify method-key uniqueness.
6. Resolve call targets and retain unresolved records.
7. Produce aggregated edges and Parquet outputs atomically.
8. Run acceptance checks and publish the validation report.

A completed module partition is immutable and may be reused after interruption
only when its JMOD checksum and extractor version match.

## 6. Acceptance criteria

The build succeeds only when all conditions hold:

1. JDK reports `28-ea+13`.
2. Every discovered JMOD is scanned or explicitly reported as failed.
3. Every standard, non-overlay method declaration has a unique `method_key`.
4. Every resolved call-site endpoint exists in `methods.parquet`.
5. `sum(method_edges.callsite_count) == count(call_sites)`.
6. The graph-core projection has the same node population and call-site
   multiplicity as the native graph.
7. Native and abstract methods exist as nodes and have `has_code=false`.
8. Constructors and static initializers are present when found in bytecode.
9. Unresolved invocation count and reasons are reported, never hidden.
10. Re-running against identical inputs produces identical method IDs and graph
   counts.
11. Manual samples include static, special, virtual, interface, constructor,
    lambda, abstract, and native cases.

## 7. Known limitations

- This is a static bytecode-reference graph, not a runtime trace.
- Reflection, method handles assembled at runtime, service loading, and native
  callbacks cannot be resolved completely.
- Virtual/interface calls point to their bytecode-declared target; runtime
  implementations require a separate CHA/RTA projection.
- Source line tables may omit exact columns and may be absent in some generated
  classes.
- Calls beyond Java bytecode terminate at native method nodes.

## 8. Deliverables

- This specification
- Reproducible extractor source and run scripts
- Version-locked input manifest
- Parquet graph datasets
- Validation report with counts, failures, and limitations
