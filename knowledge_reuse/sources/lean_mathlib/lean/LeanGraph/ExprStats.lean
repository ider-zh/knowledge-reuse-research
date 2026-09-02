module

public import Lean.Expr
public import Lean.Util.PtrSet

public section

namespace LeanGraph.ExprStats

open Lean

/--
Four complementary measurements of one elaborated Lean expression.

`uniquePtrNodes` and `dagArcs` describe the expression as it is stored with sharing.
`maxDepth` is the longest root-to-leaf path, counting both endpoints.
`treeOccurrences` describes the hypothetical tree obtained by expanding every shared
reference at every use site.
-/
structure Complexity where
  treeOccurrences : Nat
  uniquePtrNodes : Nat
  dagArcs : Nat
  maxDepth : Nat
  deriving BEq, Repr

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

private def childArcCount : Expr → Nat
  | .app .. | .lam .. | .forallE .. => 2
  | .letE .. => 3
  | .mdata .. | .proj .. => 1
  | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => 0

/--
Number of expression constructor occurrences under deterministic tree traversal.
The first pass marks pointers before visiting children and collects the expression DAG in
postorder. The second pass evaluates every DAG node once and memoizes its exact arbitrary-
precision subtree count. This preserves tree multiplicity without recursively re-entering
shared subgraphs.
-/
private unsafe def analyzeUnsafe (expr : Expr) : Complexity :=
  let (_, state) := (collectPostorder expr).run {}
  Id.run do
    let mut countCache : PtrMap Expr Nat := mkPtrMap state.postorder.size
    let mut depthCache : PtrMap Expr Nat := mkPtrMap state.postorder.size
    let mut arcs := 0
    for current in state.postorder do
      let count := match current with
        | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => 1
        | .app fn arg => 1 + cachedCount countCache fn + cachedCount countCache arg
        | .lam _ type body _ | .forallE _ type body _ =>
          1 + cachedCount countCache type + cachedCount countCache body
        | .letE _ type nested body _ =>
          1 + cachedCount countCache type + cachedCount countCache nested +
            cachedCount countCache body
        | .mdata _ nested | .proj _ _ nested => 1 + cachedCount countCache nested
      let depth := match current with
        | .bvar _ | .fvar _ | .mvar _ | .sort _ | .const .. | .lit _ => 1
        | .app fn arg => 1 + max (cachedCount depthCache fn) (cachedCount depthCache arg)
        | .lam _ type body _ | .forallE _ type body _ =>
          1 + max (cachedCount depthCache type) (cachedCount depthCache body)
        | .letE _ type nested body _ =>
          1 + max (cachedCount depthCache type)
            (max (cachedCount depthCache nested) (cachedCount depthCache body))
        | .mdata _ nested | .proj _ _ nested => 1 + cachedCount depthCache nested
      countCache := countCache.insert current count
      depthCache := depthCache.insert current depth
      arcs := arcs + childArcCount current
    return {
      treeOccurrences := cachedCount countCache expr
      uniquePtrNodes := state.postorder.size
      dagArcs := arcs
      maxDepth := cachedCount depthCache expr
    }

@[implemented_by analyzeUnsafe]
opaque analyze (expr : Expr) : Complexity := {
  treeOccurrences := 0
  uniquePtrNodes := 0
  dagArcs := 0
  maxDepth := 0
}

def treeOccurrences (expr : Expr) : Nat := (analyze expr).treeOccurrences

/-- Add one expanded-tree occurrence weight to an expression DAG node. -/
private unsafe def addOccurrenceWeight
    (weights : PtrMap Expr Nat) (expr : Expr) (weight : Nat) : PtrMap Expr Nat :=
  weights.insert expr ((weights.find? expr).getD 0 + weight)

/--
Count named constants in the tree obtained by expanding the expression DAG.

The traversal visits each pointer-distinct Expr node once.  A forward dynamic-programming
pass propagates the number of root-to-node paths, so a shared subtree contributes once for
every use site without recursively expanding it.  Results are deterministic and retain
arbitrary-precision occurrence counts.
-/
private unsafe def constantOccurrencesUnsafe (expr : Expr) : Array (Name × Nat) :=
  let (_, state) := (collectPostorder expr).run {}
  Id.run do
    let mut weights : PtrMap Expr Nat := mkPtrMap state.postorder.size
    let mut counts : Std.HashMap Name Nat := {}
    weights := weights.insert expr 1
    for current in state.postorder.reverse do
      let weight := (weights.find? current).getD 0
      match current with
        | .app fn arg =>
          weights := addOccurrenceWeight weights fn weight
          weights := addOccurrenceWeight weights arg weight
        | .lam _ type body _ | .forallE _ type body _ =>
          weights := addOccurrenceWeight weights type weight
          weights := addOccurrenceWeight weights body weight
        | .letE _ type value body _ =>
          weights := addOccurrenceWeight weights type weight
          weights := addOccurrenceWeight weights value weight
          weights := addOccurrenceWeight weights body weight
        | .mdata _ nested | .proj _ _ nested =>
          weights := addOccurrenceWeight weights nested weight
        | .const name _ =>
          counts := counts.alter name fun previous => some (previous.getD 0 + weight)
        | .bvar _ | .fvar _ | .mvar _ | .sort _ | .lit _ => pure ()
    return counts.toArray.qsort fun left right => Name.quickLt left.1 right.1

@[implemented_by constantOccurrencesUnsafe]
opaque constantOccurrences (expr : Expr) : Array (Name × Nat) := #[]

end LeanGraph.ExprStats
