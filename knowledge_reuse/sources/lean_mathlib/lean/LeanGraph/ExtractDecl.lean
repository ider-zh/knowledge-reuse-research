module

public import LeanGraph.Compat
public import LeanGraph.ExprStats
public import LeanGraph.Types

public section

namespace LeanGraph

open Lean
open LeanGraph.Compat

private def deterministicOccurrences
    (occurrences : Array (Name × Nat)) : Array (String × Nat) :=
  occurrences.map fun (name, count) => (name.toString, count)

def extractDecl (env : Environment) (snapshot : String) (module : Name)
    (info : ConstantInfo) : DeclRecord :=
  let value? := getDeclarationValue? info
  let range? := getSourceRangeFromEnv? env info.name |>.map (·.range)
  {
    snapshot
    name := info.name.toString
    module := module.toString
    kind := getDeclarationKind info
    hasValue := value?.isSome
    typeExprNodes := ExprStats.treeOccurrences info.type
    valueExprNodes := value?.map ExprStats.treeOccurrences
    typeConstants := deterministicOccurrences (ExprStats.constantOccurrences info.type)
    valueConstants := value?.map fun value =>
      deterministicOccurrences (ExprStats.constantOccurrences value)
    sourceStartLine := range?.map (·.pos.line)
    sourceStartColumn := range?.map (·.pos.column)
    sourceEndLine := range?.map (·.endPos.line)
    sourceEndColumn := range?.map (·.endPos.column)
  }

def DeclRecord.edges (record : DeclRecord) : Array EdgeRecord :=
  let typeEdges := record.typeConstants.map fun (dst, multiplicity) =>
    { snapshot := record.snapshot, src := record.name, dst, edgeType := .type, multiplicity }
  let valueEdges := record.valueConstants.getD #[] |>.map fun (dst, multiplicity) =>
    { snapshot := record.snapshot, src := record.name, dst, edgeType := .value, multiplicity }
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
  ("value_const_unique", optionNatJson (record.valueConstants.map (·.size))),
  ("source_start_line", optionNatJson record.sourceStartLine),
  ("source_start_column", optionNatJson record.sourceStartColumn),
  ("source_end_line", optionNatJson record.sourceEndLine),
  ("source_end_column", optionNatJson record.sourceEndColumn)
]

def EdgeRecord.toJson (record : EdgeRecord) : Json := Json.mkObj [
  ("record", "edge"),
  ("snapshot", record.snapshot),
  ("src", record.src),
  ("dst", record.dst),
  ("edge_type", record.edgeType.toString),
  ("multiplicity", record.multiplicity)
]

end LeanGraph
