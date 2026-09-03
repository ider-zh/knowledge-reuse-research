#!/usr/bin/env bash
set -euo pipefail

adapter_dir="$(cd "$(dirname "$0")/.." && pwd)"
jdk_dir="${1:?usage: golden.sh <jdk-directory> <work-directory>}"
work_dir="${2:?usage: golden.sh <jdk-directory> <work-directory>}"
extractor_classes="$work_dir/extractor-classes"
module_classes="$work_dir/module-classes"
jmods_dir="$work_dir/jmods"
raw_dir="$work_dir/raw"

mkdir -p "$extractor_classes" "$module_classes" "$jmods_dir" "$raw_dir"

"$jdk_dir/bin/javac" -d "$extractor_classes" \
  "$adapter_dir/src/main/java/org/openjdk/callgraph/MethodGraphExtractor.java"

"$jdk_dir/bin/javac" --module-source-path "$adapter_dir/fixtures/src" \
  -d "$module_classes" --module software.fixture

rm -f "$jmods_dir/software.fixture.jmod"
"$jdk_dir/bin/jmod" create \
  --class-path "$module_classes/software.fixture" \
  "$jmods_dir/software.fixture.jmod"

"$jdk_dir/bin/java" -cp "$extractor_classes" \
  org.openjdk.callgraph.MethodGraphExtractor "$jmods_dir" "$raw_dir"

rg -F $'software.fixture\tfixture\tfixture/GoldenCalls\texercise' \
  "$raw_dir/methods_raw.tsv" >/dev/null
rg -F $'INTERFACE' "$raw_dir/calls_raw.tsv" >/dev/null
rg -F $'STATIC' "$raw_dir/calls_raw.tsv" >/dev/null
rg -F $'SPECIAL' "$raw_dir/calls_raw.tsv" >/dev/null
rg -F $'VIRTUAL' "$raw_dir/calls_raw.tsv" >/dev/null
rg -F $'DYNAMIC' "$raw_dir/calls_raw.tsv" >/dev/null
rg -F $'nativeCall\t()V\t256' "$raw_dir/methods_raw.tsv" >/dev/null
rg -F $'abstractCall\t()V\t1024' "$raw_dir/methods_raw.tsv" >/dev/null

echo "golden fixture: PASS"
