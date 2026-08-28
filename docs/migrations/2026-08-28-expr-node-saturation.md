# Withdrawal of expression-size saturation

The temporary saturation design was rejected because bounded observations are not
valid research measurements. No saturated record is accepted in the formal Lean v1
dataset.

The exact implementation now uses two passes:

1. pre-mark every expression pointer and collect the DAG in postorder;
2. evaluate each DAG node once, caching its exact arbitrary-precision tree count.

This fixes the recursive re-entry problem without changing metric semantics. Shards
produced by the temporary saturation implementation are invalidated and rebuilt.
The raw schema therefore remains unchanged and contains no saturation fields.
