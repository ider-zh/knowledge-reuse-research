module

public import LeanGraph.ExtractDecl

public section

namespace LeanGraph

open Lean
open LeanGraph.Compat

structure ModuleExtraction where
  declarations : Array DeclRecord
  edges : Array EdgeRecord

def extractModule (env : Environment) (snapshot : String) (module : Name) : ModuleExtraction := Id.run do
  let mut declarations := #[]
  let mut edges := #[]
  for name in listDeclarations env do
    if getDeclarationModule env name != some module then
      continue
    if let some info := env.find? name then
      let record := extractDecl snapshot module info
      declarations := declarations.push record
      edges := edges ++ record.edges
  return { declarations, edges }

def ModuleExtraction.writeJsonLines
    (result : ModuleExtraction) (snapshot : String) (module : Name) : IO Unit := do
  for declaration in result.declarations do
    IO.println declaration.toJson.compress
  for edge in result.edges do
    IO.println edge.toJson.compress
  IO.println <| Json.mkObj [
    ("record", "audit"),
    ("snapshot", snapshot),
    ("module", module.toString),
    ("status", "ok"),
    ("decl_count", result.declarations.size),
    ("edge_count", result.edges.size),
    ("warning_count", 0),
    ("error", Json.null)
  ] |>.compress

end LeanGraph

