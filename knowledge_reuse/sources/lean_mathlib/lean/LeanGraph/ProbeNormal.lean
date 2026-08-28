module

public meta import LeanGraph.Compat
public import LeanGraph.ProbeFixture
public meta import Lean.Elab.Command

open Lean
open LeanGraph.Compat

private meta def report (name : Name) : Elab.Command.CommandElabM Unit := do
  let env ← getEnv
  let some info := env.find? name | throwError "missing declaration {name}"
  let module? := getDeclarationModule env name
  let range? ← getSourceRange? name
  logInfo m!"PROBE name={name} kind={getDeclarationKind info} module={module?} \
    hasValue={(getDeclarationValue? info).isSome} typeConsts={getUsedConstants info.type} \
    valueConsts={(getDeclarationValue? info).map getUsedConstants} hasRange={range?.isSome}"

run_cmd do
  for name in [`LeanGraph.ProbeFixture.P, `LeanGraph.ProbeFixture.D2,
      `LeanGraph.ProbeFixture.T2, `LeanGraph.ProbeFixture.Tiny,
      `LeanGraph.ProbeFixture.Tiny.zero, `LeanGraph.ProbeFixture.O1] do
    report name
