module

public import Lean.Expr

public section

namespace LeanGraph.ExprStats

open Lean

/-- Number of expression constructor occurrences under deterministic tree traversal. -/
partial def treeOccurrences : Expr → Nat
  | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => 1
  | .app fn arg => 1 + treeOccurrences fn + treeOccurrences arg
  | .lam _ type body _ => 1 + treeOccurrences type + treeOccurrences body
  | .forallE _ type body _ => 1 + treeOccurrences type + treeOccurrences body
  | .letE _ type value body _ =>
      1 + treeOccurrences type + treeOccurrences value + treeOccurrences body
  | .mdata _ expr => 1 + treeOccurrences expr
  | .proj _ _ expr => 1 + treeOccurrences expr

end LeanGraph.ExprStats

