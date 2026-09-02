module

public meta import LeanGraph.Compat
public meta import LeanGraph.ExprStats
import all LeanGraph.ProbeFixture
public meta import Lean.Elab.Command

open Lean
open LeanGraph.Compat
open LeanGraph

private meta def report (name : Name) : Elab.Command.CommandElabM Unit := do
  let env ← getEnv
  let some info := env.find? name | throwError "missing declaration {name}"
  let module? := getDeclarationModule env name
  let range? ← getSourceRange? name
  logInfo m!"PROBE_ALL name={name} kind={getDeclarationKind info} module={module?} \
    hasValue={(getDeclarationValue? info).isSome} typeConsts={getUsedConstants info.type} \
    valueConsts={(getDeclarationValue? info).map getUsedConstants} \
    typeOccurrences={ExprStats.constantOccurrences info.type} \
    valueOccurrences={(getDeclarationValue? info).map ExprStats.constantOccurrences} \
    hasRange={range?.isSome}"

run_cmd do
  let env ← getEnv
  let fixtureDecls := (listDeclarations env).filter fun name =>
    getDeclarationModule env name == some `LeanGraph.ProbeFixture
  logInfo m!"PROBE_ALL_DECLS count={fixtureDecls.size} names={fixtureDecls}"
  for name in [`LeanGraph.ProbeFixture.P, `LeanGraph.ProbeFixture.D2,
      `LeanGraph.ProbeFixture.T1,
      `LeanGraph.ProbeFixture.T2, `LeanGraph.ProbeFixture.Tiny,
      `LeanGraph.ProbeFixture.Tiny.zero, `LeanGraph.ProbeFixture.O1,
      `LeanGraph.ProbeFixture.usesPrivate] do
    report name
