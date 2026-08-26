module

public import LeanGraph.ExtractModule
public import Lean.Util.Path

public section

open Lean
open LeanGraph

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

def main (args : List String) : IO UInt32 := do
  let snapshot :: moduleStrings := args | do
    IO.eprintln "usage: lean-graph-extract SNAPSHOT MODULE [MODULE ...]"
    return 2
  if moduleStrings.isEmpty then
    IO.eprintln "usage: lean-graph-extract SNAPSHOT MODULE [MODULE ...]"
    return 2
  let modules := moduleStrings.toArray.map String.toName
  try
    Lean.initSearchPath (← Lean.findSysroot)
    let imports := modules.map fun module => { module, importAll := true }
    let env ← Lean.importModules imports {}
    let results := extractModules env snapshot modules
    for index in [:modules.size] do
      results[index]!.writeJsonLines snapshot modules[index]!
    return 0
  catch error =>
    IO.eprintln s!"extraction failed for {String.intercalate ", " moduleStrings}: {error}"
    for moduleString in moduleStrings do
      IO.println (failedAudit snapshot moduleString (toString error)).compress
    return 1
