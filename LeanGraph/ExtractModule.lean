module

public import LeanGraph.ExtractDecl

public section

namespace LeanGraph

open Lean
open LeanGraph.Compat

structure ModuleExtraction where
  declarations : Array DeclRecord
  deriving Inhabited

def extractModule (env : Environment) (snapshot : String) (module : Name) : ModuleExtraction := Id.run do
  let mut declarations := #[]
  for name in listDeclarations env do
    if getDeclarationModule env name != some module then
      continue
    if let some info := env.find? name then
      let record := extractDecl env snapshot module info
      declarations := declarations.push record
  return { declarations }

def extractModules
    (env : Environment) (snapshot : String) (modules : Array Name) : Array ModuleExtraction := Id.run do
  let mut records : Array (Name × DeclRecord) := #[]
  for name in listDeclarations env do
    let some module := getDeclarationModule env name | continue
    if !modules.contains module then
      continue
    if let some info := env.find? name then
      let record := extractDecl env snapshot module info
      records := records.push (module, record)
  return modules.map fun module => {
    declarations := records.filterMap fun (declarationModule, record) =>
      if declarationModule == module then some record else none
  }

def ModuleExtraction.writeJsonLines
    (result : ModuleExtraction) (snapshot : String) (module : Name) : IO Unit := do
  for declaration in result.declarations do
    IO.println declaration.toJson.compress
  let mut edgeCount := 0
  for declaration in result.declarations do
    let edges := declaration.edges
    edgeCount := edgeCount + edges.size
    for edge in edges do
      IO.println edge.toJson.compress
  IO.println <| Json.mkObj [
    ("record", "audit"),
    ("snapshot", snapshot),
    ("module", module.toString),
    ("status", "ok"),
    ("decl_count", result.declarations.size),
    ("edge_count", edgeCount),
    ("warning_count", 0),
    ("error", Json.null)
  ] |>.compress

end LeanGraph
