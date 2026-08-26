module

public import LeanGraph.Compat
public import LeanGraph.ExprStats
public import LeanGraph.Types

public section

namespace LeanGraph

open Lean
open LeanGraph.Compat

private def sortedNames (names : Array Name) : Array String :=
  names.qsort Name.quickLt |>.map (·.toString)

def extractDecl (snapshot : String) (module : Name) (info : ConstantInfo) : DeclRecord :=
  let value? := getDeclarationValue? info
  {
    snapshot
    name := info.name.toString
    module := module.toString
    kind := getDeclarationKind info
    hasValue := value?.isSome
    typeExprNodes := ExprStats.treeOccurrences info.type
    valueExprNodes := value?.map ExprStats.treeOccurrences
    typeConstants := sortedNames (getUsedConstants info.type)
    valueConstants := value?.map fun value => sortedNames (getUsedConstants value)
  }

def DeclRecord.edges (record : DeclRecord) : Array EdgeRecord :=
  let typeEdges := record.typeConstants.map fun dst =>
    { snapshot := record.snapshot, src := record.name, dst, edgeType := .type }
  let valueEdges := record.valueConstants.getD #[] |>.map fun dst =>
    { snapshot := record.snapshot, src := record.name, dst, edgeType := .value }
  typeEdges ++ valueEdges

private def optionNatJson : Option Nat → Json
  | some value => toJson value
  | none => Json.null

def DeclRecord.toJson (record : DeclRecord) : Json := Json.mkObj [
  ("record", "node"),
  ("snapshot", record.snapshot),
  ("name", record.name),
  ("module", record.module),
  ("kind", record.kind),
  ("has_value", record.hasValue),
  ("type_expr_nodes", record.typeExprNodes),
  ("value_expr_nodes", optionNatJson record.valueExprNodes),
  ("type_const_unique", record.typeConstants.size),
  ("value_const_unique", optionNatJson (record.valueConstants.map (·.size)))
]

def EdgeRecord.toJson (record : EdgeRecord) : Json := Json.mkObj [
  ("record", "edge"),
  ("snapshot", record.snapshot),
  ("src", record.src),
  ("dst", record.dst),
  ("edge_type", record.edgeType.toString),
  ("multiplicity", Json.null)
]

end LeanGraph

