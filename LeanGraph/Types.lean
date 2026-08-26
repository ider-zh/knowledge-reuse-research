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
  typeConstants : Array String
  valueConstants : Option (Array String)

structure EdgeRecord where
  snapshot : String
  src : String
  dst : String
  edgeType : EdgeType

end LeanGraph

