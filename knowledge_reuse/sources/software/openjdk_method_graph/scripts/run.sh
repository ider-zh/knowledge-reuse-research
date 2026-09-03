#!/usr/bin/env bash
set -euo pipefail

adapter_dir="$(cd "$(dirname "$0")/.." && pwd)"
repo_root="$(cd "$adapter_dir/../../../.." && pwd)"
jdk_dir="${1:?usage: run.sh <jdk-directory> <archive-path> [workspace-directory]}"
archive_path="${2:?usage: run.sh <jdk-directory> <archive-path> [workspace-directory]}"
workspace_dir="${3:-$repo_root/data/software/openjdk_jdk_28_b13}"
classes_dir="$workspace_dir/build/classes"
raw_dir="$workspace_dir/raw"
output_dir="$workspace_dir/normalized"

mkdir -p "$classes_dir" "$raw_dir" "$output_dir"

"$adapter_dir/scripts/golden.sh" "$jdk_dir" "$workspace_dir/golden"

"$jdk_dir/bin/javac" \
  -d "$classes_dir" \
  "$adapter_dir/src/main/java/org/openjdk/callgraph/MethodGraphExtractor.java"

"$jdk_dir/bin/java" \
  -cp "$classes_dir" \
  org.openjdk.callgraph.MethodGraphExtractor \
  "$jdk_dir/jmods" "$raw_dir"

python3 "$adapter_dir/scripts/build_graph.py" \
  --jdk "$jdk_dir" \
  --raw "$raw_dir" \
  --output "$output_dir" \
  --archive "$archive_path"
