module

public import Lean.Expr
public import Lean.Util.PtrSet

public section

namespace LeanGraph.ExprStats

open Lean

structure Count where
  value : Nat
  saturated : Bool
  deriving Inhabited, Repr

private def maxCount : Nat := 18446744073709551615
private def maxCacheMisses : Nat := 100000

private unsafe structure State where
  cache : PtrMap Expr Count := mkPtrMap
  cacheMisses : Nat := 0

private unsafe abbrev CountM := StateM State

private def finishCount (total : Nat) (alreadySaturated : Bool) : Count :=
  if alreadySaturated || total > maxCount then
    { value := maxCount, saturated := true }
  else
    { value := total, saturated := false }

private def unaryCount (nested : Count) : Count :=
  finishCount (1 + nested.value) nested.saturated

private def binaryCount (left right : Count) : Count :=
  finishCount (1 + left.value + right.value) (left.saturated || right.saturated)

private def ternaryCount (first second third : Count) : Count :=
  finishCount (1 + first.value + second.value + third.value)
    (first.saturated || second.saturated || third.saturated)

/--
Number of expression constructor occurrences under deterministic tree traversal.
Pointer memoization preserves tree multiplicity while avoiding repeated traversal of
shared DAG subexpressions. Counts saturate explicitly at `UInt64.max`, matching the
raw ingestion type and preventing exponentially shared proof DAGs from creating
unbounded bignums. A fixed cache-miss budget also bounds pathological expression
representations; saturation is explicit in the output. It deliberately uses Lean's
pinned `PtrMap`: structural hashing of very large proof terms can itself dominate
extraction time.
-/
private unsafe def treeOccurrencesCached
    (expr : Expr) : CountM Count := do
  if let some count := PtrMap.find? (← get).cache expr then
    return count
  if (← get).cacheMisses >= maxCacheMisses then
    return { value := maxCount, saturated := true }
  modify fun state => { state with cacheMisses := state.cacheMisses + 1 }
  let count ← match expr with
    | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ =>
      pure { value := 1, saturated := false }
    | .app fn arg => return binaryCount (← treeOccurrencesCached fn) (← treeOccurrencesCached arg)
    | .lam _ type body _ | .forallE _ type body _ =>
      return binaryCount (← treeOccurrencesCached type) (← treeOccurrencesCached body)
    | .letE _ type value body _ =>
      return ternaryCount (← treeOccurrencesCached type) (← treeOccurrencesCached value)
        (← treeOccurrencesCached body)
    | .mdata _ nested | .proj _ _ nested => return unaryCount (← treeOccurrencesCached nested)
  modify fun state => { state with cache := PtrMap.insert state.cache expr count }
  return count

private unsafe def treeOccurrencesUnsafe (expr : Expr) : Count :=
  treeOccurrencesCached expr |>.run' {}

@[implemented_by treeOccurrencesUnsafe]
opaque treeOccurrences (expr : Expr) : Count := { value := 0, saturated := false }

end LeanGraph.ExprStats
