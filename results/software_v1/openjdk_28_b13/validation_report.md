# OpenJDK 28+13 Method Graph Validation Report

Generated: 2026-09-03T07:29:22.384168+00:00

## Result

PASS

## Corpus

- JMODs: 65
- Classes: 27,262
- Methods: 239,765
- Raw invocation facts: 874,848
- Resolved call sites: 859,406
- Unresolved call sites: 15,442
- Aggregated method edges: 621,105

## Integrity checks

- Resolved endpoints exist: True
- Aggregated counts equal resolved call sites: True
- Graph-core projection matches native graph: True
- Native/abstract methods incorrectly containing code: 0
- Method ID collisions: 0
- All five invocation kinds present: True
- Constructors: 30,297
- Static initializers: 5,925
- Native methods: 1,727
- Abstract methods: 18,002
- Resolved call sites with source lines: 859,406 / 859,406

## Reproducibility

An independent second normalization run produced identical SHA-256 values for
all seven native and graph-core Parquet datasets.

## Invocation kinds

{
  "DYNAMIC": 9785,
  "INTERFACE": 104741,
  "SPECIAL": 144539,
  "STATIC": 139786,
  "VIRTUAL": 460555
}

## Resolution modes

{
  "BOOTSTRAP_HANDLE": 9785,
  "EXACT": 769208,
  "INHERITED": 79647,
  "SIGNATURE_POLYMORPHIC": 766
}

## Unresolved reasons

{
  "TARGET_NOT_IN_CORPUS": 2005,
  "UNRESOLVED_DYNAMIC": 13437
}

## Deterministic samples

{
  "DYNAMIC": {
    "caller": "java.base/com/sun/crypto/provider/DESKey#<init>([BI)V",
    "callee": "java.base/com/sun/crypto/provider/DESKey#lambda$new$0([B)V",
    "source_line": 87
  },
  "INTERFACE": {
    "caller": "java.base/com/sun/crypto/provider/AESCipher#checkKeySize(Ljava/security/Key;I)V",
    "callee": "java.base/java/security/Key#getEncoded()[B",
    "source_line": 147
  },
  "SPECIAL": {
    "caller": "java.base/com/sun/crypto/provider/AEADBufferedStream#<init>(I)V",
    "callee": "java.base/java/io/ByteArrayOutputStream#<init>(I)V",
    "source_line": 50
  },
  "STATIC": {
    "caller": "java.base/com/sun/crypto/provider/AEADBufferedStream#checkCapacity(I)V",
    "callee": "java.base/jdk/internal/util/ArraysSupport#newLength(III)I",
    "source_line": 73
  },
  "VIRTUAL": {
    "caller": "java.base/com/sun/crypto/provider/AEADBufferedStream#write(Ljava/nio/ByteBuffer;)V",
    "callee": "java.base/java/nio/Buffer#position()I",
    "source_line": 83
  }
}

## Scope limitation

This is the exact Java bytecode-reference graph. Native implementations,
reflection assembled at runtime, and runtime virtual dispatch expansion are not
included.
