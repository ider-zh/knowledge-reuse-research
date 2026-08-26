module

public import LeanGraph.ExtractDecl

public section

namespace LeanGraph

open Lean
open LeanGraph.Compat

structure ModuleExtraction where
  declarations : Array DeclRecord
  edges : Array EdgeRecord
  deriving Inhabited

def extractModule (env : Environment) (snapshot : String) (module : Name) : ModuleExtraction := Id.run do
  let mut declarations := #[]
  let mut edges := #[]
  for name in listDeclarations env do
    if getDeclarationModule env name != some module then
      continue
    if let some info := env.find? name then
      let record := extractDecl env snapshot module info
      declarations := declarations.push record
      edges := edges ++ record.edges
  return { declarations, edges }

def extractModules
    (env : Environment) (snapshot : String) (modules : Array Name) : Array ModuleExtraction := Id.run do
  let mut results := modules.map fun _ => { declarations := #[], edges := #[] }
  for name in listDeclarations env do
    let some module := getDeclarationModule env name | continue
    let some index := modules.findIdx? (· == module) | continue
    if let some info := env.find? name then
      let record := extractDecl env snapshot module info
      let current := results[index]!
      results := results.set! index {
        declarations := current.declarations.push record
        edges := current.edges ++ record.edges
      }
  return results

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
