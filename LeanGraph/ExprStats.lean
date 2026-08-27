module

public import Lean.Expr
public import Lean.Util.PtrSet

public section

namespace LeanGraph.ExprStats

open Lean

/--
Number of expression constructor occurrences under deterministic tree traversal.
Pointer memoization preserves tree multiplicity while avoiding repeated traversal of
shared DAG subexpressions. It deliberately uses Lean's pinned `PtrMap`: structural
hashing of very large proof terms can itself dominate extraction time.
-/
private unsafe def treeOccurrencesCached
    (expr : Expr) : StateM (PtrMap Expr Nat) Nat := do
  if let some count := PtrMap.find? (← get) expr then
    return count
  let count ← match expr with
    | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => pure 1
    | .app fn arg => return 1 + (← treeOccurrencesCached fn) + (← treeOccurrencesCached arg)
    | .lam _ type body _ | .forallE _ type body _ =>
      return 1 + (← treeOccurrencesCached type) + (← treeOccurrencesCached body)
    | .letE _ type value body _ =>
      return 1 + (← treeOccurrencesCached type) + (← treeOccurrencesCached value) +
        (← treeOccurrencesCached body)
    | .mdata _ nested | .proj _ _ nested => return 1 + (← treeOccurrencesCached nested)
  modify fun cache => PtrMap.insert cache expr count
  return count

private unsafe def treeOccurrencesUnsafe (expr : Expr) : Nat :=
  treeOccurrencesCached expr |>.run' mkPtrMap

@[implemented_by treeOccurrencesUnsafe]
opaque treeOccurrences (expr : Expr) : Nat := 0

end LeanGraph.ExprStats
