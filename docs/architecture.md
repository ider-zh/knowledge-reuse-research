# Multi-source architecture

This repository is a research monorepo for measuring knowledge reuse in several
directed graph systems. A source adapter owns extraction and source-specific
normalization. Shared analysis owns metrics meaningful across systems. An
experiment binds one source snapshot to configuration, hypotheses, and results.

## Boundaries

    external source
        ↓
    knowledge_reuse/sources/<source>/    native identity and semantics
        ↓
    schemas/core/graph-core-v1.*         common node/link contract
        ↓
    knowledge_reuse/analysis/            shared metrics and reports
        ↓
    experiments/<experiment_id>/         hypotheses and run notes
    apps/research-site/                   compact public evidence and static UI
        ↓
    data/<source>/<snapshot>/            large rebuildable facts
    results/<experiment_id>/runs/<run>/  compact auditable run results

All sources, including Lean/mathlib, use source/snapshot-namespaced data and
experiment-namespaced results. Raw facts may be relocated as an atomic corpus,
but their bytes and content checksums must not change during a structural
migration.

Smoke, full, and later robustness runs have separate result directories. They
must never share mutable `metrics/`, `tables/`, `report/`, or run-manifest paths.
Experiment-level evidence such as capability probes, golden gates, inventory,
and shard plans remains directly under `results/<experiment_id>/`.

## Packages

- knowledge_reuse.analysis: source-neutral metrics, fitting, and reports.
- knowledge_reuse.sources.lean_mathlib: Lean extractor sources, commands,
  ingestion, normalization, source-specific SQL, and reporting.
- knowledge_reuse.sources.wikipedia: Wikipedia page/link adapter.
- knowledge_reuse.sources.software: repository/call/dependency graph adapter.

Source packages own their operational code. Root-level commands stay thin and
dispatch into a source package; source-specific scripts, SQL, fixtures, and
schemas must not be added to shared root directories.

The research site is a presentation boundary, not another analysis engine. A
source-owned exporter may publish small, checksummed JSON under
`apps/research-site/public/datasets/<experiment>/<snapshot>/`. These files must
state the full population count, the published sample count, and the sampling
rule. The browser must not recompute headline findings or receive the complete
raw/normalized graph.

## Cross-system invariants

Every adapter emits deterministic node IDs, preserves native identifiers, uses
consumer/source → dependency/target edge direction, records missing/external
targets explicitly, and publishes completeness/audit data. Source-specific
columns may coexist beside the core projection.

Cross-system analyses consume only the core projection and state when a measure
is not comparable. Lean proof Expr size, Wikipedia wikitext bytes, and software
AST size remain clearly labeled native units.

## Dependency rule

Source adapters may depend on shared contracts and utilities. Shared analysis
must not import a source adapter. Experiments may depend on both. This one-way
rule prevents source-specific assumptions leaking into other systems.
