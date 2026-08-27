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
        ↓
    data/<source>/<snapshot>/            large rebuildable facts
    results/<experiment_id>/             compact auditable results

The pinned Lean experiment predates namespaced data. Its existing
"data/raw/<snapshot>" and "results/*" paths remain supported until its v1 report
is complete, so checksum resume is not invalidated by this reorganization. New
sources use namespaced paths from their first run.

## Packages

- knowledge_reuse.analysis: source-neutral metrics, fitting, and reports.
- knowledge_reuse.sources.lean_mathlib: Lean ingestion and normalization.
- knowledge_reuse.sources.wikipedia: Wikipedia page/link adapter.
- knowledge_reuse.sources.software: repository/call/dependency graph adapter.
- pipeline: compatibility entry points for original Lean v1 commands. New
  implementation code must not be added here.
- LeanGraph: pinned Lean semantic extractor. It remains at repository root
  because its module namespace and accepted experiment contract require it.

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
