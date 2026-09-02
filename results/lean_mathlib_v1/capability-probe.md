# Lean v4.32.1 capability probe

Overall gate: **PASS**

| Capability | Result |
|---|---|
| `environment_enumeration` | PASS |
| `declaration_kinds` | PASS |
| `type_constant_references` | PASS |
| `value_constant_references` | PASS |
| `constant_occurrence_multiplicity` | PASS |
| `module_provenance` | PASS |
| `ordinary_import_hides_values` | PASS |
| `import_all_exposes_values` | PASS |
| `import_all_supported` | PASS |
| `source_ranges_imported` | PASS |

The source-range check is observational rather than gate-failing: the specification permits a declaration-identity-preserving source indexer when imported semantic range metadata is unavailable. Ordinary imports intentionally hide values/proofs; `import all` exposes them and preserves definition/theorem/opaque kinds in this pinned toolchain.
