module

public import Lean.DeclarationRange
public import Lean.Util.FoldConsts

public section

namespace LeanGraph.Compat

open Lean

/-- Deterministically list all declarations visible in an environment. -/
def listDeclarations (env : Environment) : Array Name :=
  env.constants.toList.map (·.1) |>.toArray.qsort Name.quickLt

def getDeclarationName (info : ConstantInfo) : Name := info.name

def getDeclarationKind : ConstantInfo → String
  | .axiomInfo _ => "axiom"
  | .defnInfo _ => "definition"
  | .thmInfo _ => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _ => "quotient"
  | .inductInfo _ => "inductive"
  | .ctorInfo _ => "constructor"
  | .recInfo _ => "recursor"

def getDeclarationModule (env : Environment) (name : Name) : Option Name := do
  let idx ← env.getModuleIdxFor? name
  env.header.moduleNames[idx.toNat]?

private def sortUniqueNames (names : Array Name) : Array Name := Id.run do
  let sorted := names.qsort Name.quickLt
  let mut result := #[]
  let mut previous : Option Name := none
  for name in sorted do
    if previous != some name then
      result := result.push name
      previous := some name
  return result

/--
List declarations owned by the requested modules without scanning every declaration in the
import closure. `moduleData` is indexed by `ModuleIdx`; include `extraConstNames` so generated
auxiliary declarations retain the same provenance coverage as `getModuleIdxFor?`.
-/
def listDeclarationsInModules (env : Environment) (modules : Array Name) : Array Name := Id.run do
  let mut names := #[]
  for module in modules do
    let some moduleIdx := env.getModuleIdx? module | continue
    let some data := env.header.moduleData[moduleIdx]? | continue
    names := names ++ data.constNames
    names := names ++ data.extraConstNames
  return sortUniqueNames names

def getDeclarationType (info : ConstantInfo) : Expr := info.type

def getDeclarationValue? (info : ConstantInfo) : Option Expr :=
  info.value? (allowOpaque := true)

def getUsedConstants (expr : Expr) : Array Name := expr.getUsedConstants

def getSourceRange? [Monad m] [MonadEnv m] [MonadLiftT BaseIO m]
    (name : Name) : m (Option DeclarationRanges) :=
  Lean.findDeclarationRanges? name

/-- Read persisted declaration ranges directly from an imported module. -/
def getSourceRangeFromEnv? (env : Environment) (name : Name) : Option DeclarationRanges :=
  Lean.declRangeExt.find? (level := .exported) env name <|>
    Lean.declRangeExt.find? (level := .server) env name <|>
    Lean.declRangeExt.find? (level := .private) env name

/-- Visibility evidence available without guessing from declaration prefixes. -/
structure VisibilityInfo where
  isImported : Bool
  hasValue : Bool
  deriving Repr

def getVisibilityInfo? (env : Environment) (name : Name) : Option VisibilityInfo := do
  let info ← env.find? name
  return { isImported := env.isImportedConst name, hasValue := (getDeclarationValue? info).isSome }

end LeanGraph.Compat
