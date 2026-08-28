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
  let observed := ExprStats.treeOccurrences expr
  let expected := 2 ^ (depth + 1) - 1
  if observed == expected then
    IO.println s!"exact_tree_occurrences={observed}"
    return 0
  IO.eprintln s!"expected exact tree occurrences {expected}, observed {observed}"
  return 1
