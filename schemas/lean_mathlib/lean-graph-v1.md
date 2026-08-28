# Lean graph schema v1

Raw records are self-describing JSON objects written as immutable JSONL.zst.
The normalized graph uses deterministic node IDs assigned by sorting canonical
fully-qualified declaration names within a snapshot.

An edge `src -> dst` means that the source declaration semantically depends on
the target. `TYPE` references come from the elaborated declaration type;
`VALUE` references come from an accessible elaborated value/proof body. Missing
values remain null and are audited; they are never represented as zero edges.

Normalized node, edge, module, and external-node columns follow sections 10–12
of the experiment specification. Generated/internal nodes are retained in raw
and canonical data and filtered only through explicit analytical views.

