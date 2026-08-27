module

public import Lean.Expr

public section

namespace LeanGraph.ExprStats

open Lean

/--
Number of expression constructor occurrences under deterministic tree traversal.
Memoization preserves tree multiplicity while avoiding repeated traversal of shared
or structurally equal DAG subexpressions.
-/
private partial def treeOccurrencesCached
    (expr : Expr) : StateM (Std.HashMap Expr Nat) Nat := do
  if let some count := (← get).get? expr then
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
  modify (·.insert expr count)
  return count

def treeOccurrences (expr : Expr) : Nat :=
  treeOccurrencesCached expr |>.run' {}

end LeanGraph.ExprStats
