module

public import Lean.Data.Json

public section

namespace LeanGraph

inductive EdgeType where
  | type
  | value
  deriving BEq, Repr

def EdgeType.toString : EdgeType → String
  | .type => "TYPE"
  | .value => "VALUE"

structure DeclRecord where
  snapshot : String
  name : String
  module : String
  kind : String
  hasValue : Bool
  typeExprNodes : Nat
  valueExprNodes : Option Nat
  typeConstants : Array (String × Nat)
  valueConstants : Option (Array (String × Nat))
  sourceStartLine : Option Nat
  sourceStartColumn : Option Nat
  sourceEndLine : Option Nat
  sourceEndColumn : Option Nat

structure EdgeRecord where
  snapshot : String
  src : String
  dst : String
  edgeType : EdgeType
  multiplicity : Nat

end LeanGraph
