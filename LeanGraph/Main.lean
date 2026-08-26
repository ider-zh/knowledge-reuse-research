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
  let [snapshot, moduleString] := args | do
    IO.eprintln "usage: lean-graph-extract SNAPSHOT MODULE"
    return 2
  try
    Lean.initSearchPath (← Lean.findSysroot)
    let module := moduleString.toName
    let env ← Lean.importModules #[{ module, importAll := true }] {}
    let result := extractModule env snapshot module
    result.writeJsonLines snapshot module
    return 0
  catch error =>
    IO.eprintln s!"extraction failed for {moduleString}: {error}"
    IO.println (failedAudit snapshot moduleString (toString error)).compress
    return 1
