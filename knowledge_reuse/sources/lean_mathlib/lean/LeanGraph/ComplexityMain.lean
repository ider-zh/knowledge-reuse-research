module

public import LeanGraph.Compat
public import LeanGraph.ExprStats
public import Lean.Util.Path

public section

open Lean
open LeanGraph
open LeanGraph.Compat

private def optionNatJson : Option Nat → Json
  | some value => toJson value
  | none => Json.null

private def complexityJson (snapshot : String) (module : Name) (info : ConstantInfo) : Json :=
  let typeStats := ExprStats.analyze info.type
  let valueStats? := (getDeclarationValue? info).map ExprStats.analyze
  Json.mkObj [
    ("record", "complexity"),
    ("snapshot", snapshot),
    ("name", info.name.toString),
    ("module", module.toString),
    ("has_value", valueStats?.isSome),
    ("type_expr_tree_occurrences", typeStats.treeOccurrences),
    ("type_expr_unique_ptr_nodes", typeStats.uniquePtrNodes),
    ("type_expr_dag_arcs", typeStats.dagArcs),
    ("type_expr_max_depth", typeStats.maxDepth),
    ("value_expr_tree_occurrences", optionNatJson (valueStats?.map ( ·.treeOccurrences))),
    ("value_expr_unique_ptr_nodes", optionNatJson (valueStats?.map ( ·.uniquePtrNodes))),
    ("value_expr_dag_arcs", optionNatJson (valueStats?.map ( ·.dagArcs))),
    ("value_expr_max_depth", optionNatJson (valueStats?.map ( ·.maxDepth)))
  ]

private def failedAudit (snapshot module error : String) : Json := Json.mkObj [
  ("record", "audit"),
  ("snapshot", snapshot),
  ("module", module),
  ("status", "failed"),
  ("decl_count", 0),
  ("edge_count", 0),
  ("warning_count", 0),
  ("error", error)
]

private def extractModuleComplexity
    (env : Environment) (snapshot : String) (module : Name) : IO Unit := do
  let mut count : Nat := 0
  for name in listDeclarationsInModules env #[module] do
    if getDeclarationModule env name != some module then
      continue
    if let some info := env.find? name then
      IO.println (complexityJson snapshot module info).compress
      count := count + 1
  IO.println <| Json.mkObj [
    ("record", "audit"),
    ("snapshot", snapshot),
    ("module", module.toString),
    ("status", "ok"),
    ("decl_count", count),
    ("edge_count", 0),
    ("warning_count", 0),
    ("error", Json.null)
  ] |>.compress

def main (args : List String) : IO UInt32 := do
  let snapshot :: moduleStrings := args | do
    IO.eprintln "usage: lean-graph-complexity SNAPSHOT MODULE [MODULE ...]"
    return 2
  if moduleStrings.isEmpty then
    IO.eprintln "usage: lean-graph-complexity SNAPSHOT MODULE [MODULE ...]"
    return 2
  let modules := moduleStrings.toArray.map String.toName
  try
    Lean.initSearchPath (← Lean.findSysroot)
    let imports := modules.map fun module => { module, importAll := true }
    let env ← Lean.importModules imports {}
    for module in modules do
      extractModuleComplexity env snapshot module
    return 0
  catch error =>
    IO.eprintln s!"complexity extraction failed for {String.intercalate ", " moduleStrings}: {error}"
    for moduleString in moduleStrings do
      IO.println (failedAudit snapshot moduleString (toString error)).compress
    return 1
