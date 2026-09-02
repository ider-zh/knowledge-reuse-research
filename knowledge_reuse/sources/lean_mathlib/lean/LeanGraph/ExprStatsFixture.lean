module

public import LeanGraph.ExprStats

public section

open Lean
open LeanGraph

private def sharedExpr : Nat → Expr → Expr
  | 0, expr => expr
  | depth + 1, expr => sharedExpr depth (.app expr expr)

def main : IO UInt32 := do
  let depth := 80
  let expr := sharedExpr depth (.const `Nat [])
  let observed := ExprStats.analyze expr
  let observedConstants := ExprStats.constantOccurrences expr
  let expected := 2 ^ (depth + 1) - 1
  let expectedConstants := #[(`Nat, 2 ^ depth)]
  let expectedStats : ExprStats.Complexity := {
    treeOccurrences := expected
    uniquePtrNodes := depth + 1
    dagArcs := 2 * depth
    maxDepth := depth + 1
  }
  if observed == expectedStats && observedConstants == expectedConstants then
    IO.println s!"tree_occurrences={observed.treeOccurrences} unique_ptr_nodes={observed.uniquePtrNodes} dag_arcs={observed.dagArcs} max_depth={observed.maxDepth} nat_occurrences={observedConstants[0]!.2}"
    return 0
  IO.eprintln s!"expected {repr expectedStats} and {repr expectedConstants}, observed {repr observed} and {repr observedConstants}"
  return 1
