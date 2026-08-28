module

public section

namespace LeanGraph.ProbeFixture

axiom P : Prop

def D1 : Nat := 1
def D2 : Nat := D1 + 1

theorem T1 : P → P := fun h => h
theorem T2 (h : P) : P := T1 h

opaque O1 : Nat

inductive Tiny where
  | zero
  | succ (n : Tiny)

structure Box where
  value : Nat

class Tagged (α : Type) where
  tag : α → Nat

instance : Tagged Nat where
  tag n := n

private theorem privateT : D1 = 1 := rfl

theorem usesPrivate : D1 = 1 := privateT

end LeanGraph.ProbeFixture

