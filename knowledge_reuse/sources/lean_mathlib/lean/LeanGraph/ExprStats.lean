module

public import Lean.Expr
public import Lean.Util.PtrSet

public section

namespace LeanGraph.ExprStats

open Lean

private unsafe structure CollectState where
  visited : PtrSet Expr := mkPtrSet
  postorder : Array Expr := #[]

private unsafe def collectPostorder (expr : Expr) : StateM CollectState Unit := do
  if (← get).visited.contains expr then
    return
  modify fun state => { state with visited := state.visited.insert expr }
  match expr with
    | .app fn arg => collectPostorder fn; collectPostorder arg
    | .lam _ type body _ | .forallE _ type body _ =>
      collectPostorder type; collectPostorder body
    | .letE _ type value body _ =>
      collectPostorder type; collectPostorder value; collectPostorder body
    | .mdata _ nested | .proj _ _ nested => collectPostorder nested
    | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => pure ()
  modify fun state => { state with postorder := state.postorder.push expr }

private unsafe def cachedCount (cache : PtrMap Expr Nat) (expr : Expr) : Nat :=
  (cache.find? expr).get!

/--
Number of expression constructor occurrences under deterministic tree traversal.
The first pass marks pointers before visiting children and collects the expression DAG in
postorder. The second pass evaluates every DAG node once and memoizes its exact arbitrary-
precision subtree count. This preserves tree multiplicity without recursively re-entering
shared subgraphs.
-/
private unsafe def treeOccurrencesUnsafe (expr : Expr) : Nat :=
  let (_, state) := (collectPostorder expr).run {}
  let value := Id.run do
    let mut cache : PtrMap Expr Nat := mkPtrMap state.postorder.size
    for current in state.postorder do
      let count := match current with
        | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => 1
        | .app fn arg => 1 + cachedCount cache fn + cachedCount cache arg
        | .lam _ type body _ | .forallE _ type body _ =>
          1 + cachedCount cache type + cachedCount cache body
        | .letE _ type nested body _ =>
          1 + cachedCount cache type + cachedCount cache nested + cachedCount cache body
        | .mdata _ nested | .proj _ _ nested => 1 + cachedCount cache nested
      cache := cache.insert current count
    return cachedCount cache expr
  value

@[implemented_by treeOccurrencesUnsafe]
opaque treeOccurrences (expr : Expr) : Nat := 0

end LeanGraph.ExprStats
