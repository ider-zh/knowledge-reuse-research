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

def getDeclarationType (info : ConstantInfo) : Expr := info.type

def getDeclarationValue? (info : ConstantInfo) : Option Expr :=
  info.value? (allowOpaque := true)

def getUsedConstants (expr : Expr) : Array Name := expr.getUsedConstants

def getSourceRange? [Monad m] [MonadEnv m] [MonadLiftT BaseIO m]
    (name : Name) : m (Option DeclarationRanges) :=
  Lean.findDeclarationRanges? name

/-- Visibility evidence available without guessing from declaration prefixes. -/
structure VisibilityInfo where
  isImported : Bool
  hasValue : Bool
  deriving Repr

def getVisibilityInfo? (env : Environment) (name : Name) : Option VisibilityInfo := do
  let info ← env.find? name
  return { isImported := env.isImportedConst name, hasValue := (getDeclarationValue? info).isSome }

end LeanGraph.Compat

