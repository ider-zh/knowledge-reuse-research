"""Curated, data-verified cases explaining the Lean source-to-graph transformation."""

from __future__ import annotations

from typing import Any

import polars as pl

from knowledge_reuse.sources.lean_mathlib.layout import ROOT


MATHLIB_TAG = "v4.32.1"


def source_excerpt(source_file: str, start_line: int, end_line: int) -> dict[str, Any]:
    path = ROOT / "vendor" / "mathlib4" / source_file
    lines = path.read_text().splitlines()
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        raise ValueError(f"invalid source excerpt {source_file}:{start_line}-{end_line}")
    return {
        "source_file": source_file,
        "start_line": start_line,
        "end_line": end_line,
        "source_url": (
            "https://github.com/leanprover-community/mathlib4/blob/"
            f"{MATHLIB_TAG}/{source_file}#L{start_line}-L{end_line}"
        ),
        "code": "\n".join(lines[start_line - 1 : end_line]),
    }


def _node(nodes: pl.DataFrame, name: str) -> dict[str, Any]:
    selected = nodes.filter(pl.col("name") == name)
    if selected.height != 1:
        raise ValueError(f"expected exactly one node named {name}, observed {selected.height}")
    row = selected.row(0, named=True)
    return {
        "node_id": row["node_id"],
        "name": row["name"],
        "kind": row["kind"],
        "module": row["module"],
        "has_value": row["has_value"],
        "type_expr_nodes": row["type_expr_nodes"],
        "value_expr_nodes": row["value_expr_nodes"],
    }


def _edge(
    edges: pl.DataFrame,
    node_by_name: dict[str, dict[str, Any]],
    src_name: str,
    dst_name: str,
    edge_type: str,
) -> dict[str, Any]:
    src, dst = node_by_name[src_name], node_by_name[dst_name]
    selected = edges.filter(
        (pl.col("src_id") == src["node_id"])
        & (pl.col("dst_id") == dst["node_id"])
        & (pl.col("edge_type") == edge_type)
    )
    if selected.height != 1:
        raise ValueError(
            f"expected one {edge_type} edge {src_name} -> {dst_name}, observed {selected.height}"
        )
    row = selected.row(0, named=True)
    return {
        "src_id": src["node_id"],
        "src_name": src_name,
        "src_kind": src["kind"],
        "dst_id": dst["node_id"],
        "dst_name": dst_name,
        "dst_kind": dst["kind"],
        "edge_type": edge_type,
        "multiplicity": row["multiplicity"],
        "is_self_loop": src["node_id"] == dst["node_id"],
    }


def build_construction_cases(nodes: pl.DataFrame, edges: pl.DataFrame) -> dict[str, Any]:
    required_names = {
        "Set",
        "CategoryTheory.Category",
        "CategoryTheory.Category.mk",
        "List.Ico",
        "List.Ico.mem",
        "padicValNat",
        "padicValRat.of_nat",
        "map_pow",
        "constantCoeff_xInTermsOfW",
        "Computation.run",
    }
    node_by_name = {name: _node(nodes, name) for name in sorted(required_names)}
    set_expr_breakdown = {
        "verification": "Lean v4.32.1 environment ConstantInfo for `Set`",
        "type_expr": {
            "surface": "(α : Type u) → Type u",
            "raw": ".forallE α (.sort (u+1)) (.sort (u+1))",
            "nodes": [
                {
                    "index": 1,
                    "depth": 0,
                    "constructor": ".forallE α",
                    "meaning": "根节点：接收类型参数 α 的函数类型",
                },
                {
                    "index": 2,
                    "depth": 1,
                    "constructor": ".sort (u+1)",
                    "meaning": "参数 α 的类型 Type u",
                },
                {
                    "index": 3,
                    "depth": 1,
                    "constructor": ".sort (u+1)",
                    "meaning": "Set α 的结果类型 Type u",
                },
            ],
        },
        "value_expr": {
            "surface": "fun (α : Type u) => α → Prop",
            "raw": ".lam α (.sort (u+1)) (.forallE _ (.bvar 0) (.sort 0))",
            "nodes": [
                {
                    "index": 1,
                    "depth": 0,
                    "constructor": ".lam α",
                    "meaning": "根节点：以类型 α 为参数的函数",
                },
                {
                    "index": 2,
                    "depth": 1,
                    "constructor": ".sort (u+1)",
                    "meaning": "参数 α 的类型 Type u",
                },
                {
                    "index": 3,
                    "depth": 1,
                    "constructor": ".forallE _",
                    "meaning": "函数类型 α → Prop",
                },
                {
                    "index": 4,
                    "depth": 2,
                    "constructor": ".bvar 0",
                    "meaning": "引用最近绑定的参数 α",
                },
                {
                    "index": 5,
                    "depth": 2,
                    "constructor": ".sort 0",
                    "meaning": "Prop 的内部表示",
                },
            ],
        },
        "notation": "Lean 内部以 Sort (u+1) 表示 Type u，以 Sort 0 表示 Prop。",
        "evidence": [
            {
                "kind": "language_reference",
                "title": "Lean Language Reference · Universes",
                "url": "https://lean-lang.org/doc/reference/latest/The-Type-System/Universes/",
                "supports": "语言层定义",
                "detail": (
                    "官方参考说明 Type u 是 Sort (u+1) 的缩写，Prop 是 Sort 0 的缩写。"
                ),
                "code": None,
            },
            {
                "kind": "pinned_parser_source",
                "title": "Lean v4.32.1 · Lean/Parser/Term.lean L134–L144",
                "url": (
                    "https://github.com/leanprover/lean4/blob/v4.32.1/"
                    "src/lean/Lean/Parser/Term.lean#L134-L144"
                ),
                "supports": "固定版本语法定义",
                "detail": "parser 源码注释直接记录 Type u 与 Prop 的 Sort 等价关系。",
                "code": "Type u ≡ Sort (u + 1)\nProp ≡ Sort 0",
            },
            {
                "kind": "pinned_elaborator_source",
                "title": "Lean v4.32.1 · Lean/Elab/BuiltinTerm.lean L21–L34",
                "url": (
                    "https://github.com/leanprover/lean4/blob/v4.32.1/"
                    "src/lean/Lean/Elab/BuiltinTerm.lean#L21-L34"
                ),
                "supports": "固定版本执行规则",
                "detail": (
                    "elabProp 构造 level zero 的 Sort；elabTypeStx 对给定 universe level "
                    "先取 successor，再构造 Sort。"
                ),
                "code": (
                    "elabProp     → mkSort Level.zero\n"
                    "elabTypeStx → mkSort (mkLevelSucc u)"
                ),
            },
        ],
        "inference": (
            "前两项给出语言定义与 v4.32.1 的精化实现；本案例 raw ConstantInfo 中的 "
            ".sort (u+1) 和 .sort 0 是同一规则的实际输出。因此这里不是从显示文本跳到解释，"
            "而是用固定版本规则解释固定版本观测。"
        ),
    }
    if len(set_expr_breakdown["type_expr"]["nodes"]) != node_by_name["Set"]["type_expr_nodes"]:
        raise ValueError("Set type Expr breakdown disagrees with extracted node count")
    if len(set_expr_breakdown["value_expr"]["nodes"]) != node_by_name["Set"]["value_expr_nodes"]:
        raise ValueError("Set value Expr breakdown disagrees with extracted node count")

    node_cases = [
        {
            "case_id": "node.definition",
            "title": "一个 definition 形成一个命名节点",
            "summary": "`def Set` 在环境中登记为 definition；其 type 与 value 分别成为可分析对象。",
            **source_excerpt("Mathlib/Data/Set/Defs.lean", 49, 50),
            "nodes": [node_by_name["Set"]],
            "expr_breakdown": set_expr_breakdown,
        },
        {
            "case_id": "node.inductive-constructor",
            "title": "一段 class 源码产生不同 kind 的节点",
            "summary": "Lean 将 class 编译为归纳声明，并为构造方式登记 constructor；二者是不同节点。",
            **source_excerpt("Mathlib/CategoryTheory/Category/Basic.lean", 233, 242),
            "nodes": [
                node_by_name["CategoryTheory.Category"],
                node_by_name["CategoryTheory.Category.mk"],
            ],
        },
        {
            "case_id": "node.theorem",
            "title": "theorem 的命题和证明共同属于一个节点",
            "summary": "`List.Ico.mem` 的 type 是区间成员关系命题，value 是 `by` 后精化得到的证明项。",
            **source_excerpt("Mathlib/Data/List/Intervals.lean", 60, 63),
            "nodes": [node_by_name["List.Ico.mem"]],
        },
    ]

    edge_cases = [
        {
            "case_id": "edge.type-value",
            "title": "同一依赖可同时进入 TYPE 与 VALUE 层",
            "summary": "`padicValNat` 出现在命题中，也进入精化后的证明；两种语义分别保存。",
            **source_excerpt("Mathlib/NumberTheory/Padics/PadicVal/Basic.lean", 163, 165),
            "edges": [
                _edge(edges, node_by_name, "padicValRat.of_nat", "padicValNat", "TYPE"),
                _edge(edges, node_by_name, "padicValRat.of_nat", "padicValNat", "VALUE"),
            ],
            "interpretation": (
                "TYPE multiplicity 描述 target 在命题 Expr tree 中的出现次数；VALUE multiplicity "
                "描述它在证明 Expr tree 中的出现次数。二者不是 import 边。"
            ),
        },
        {
            "case_id": "edge.repeated",
            "title": "重复引用由 multiplicity 保留",
            "summary": "`map_pow` 在该证明的精化 VALUE Expr tree 中出现三次，因此边权为 3。",
            **source_excerpt(
                "Mathlib/RingTheory/WittVector/WittPolynomial.lean", 203, 214
            ),
            "edges": [
                _edge(
                    edges,
                    node_by_name,
                    "constantCoeff_xInTermsOfW",
                    "map_pow",
                    "VALUE",
                )
            ],
            "interpretation": (
                "源码中肉眼可见的名字次数不必等于精化 Expr 的 constant occurrence；隐式参数、"
                "类型类与证明项结构均属于可复现的语义表示。"
            ),
        },
        {
            "case_id": "edge.self-loop",
            "title": "递归定义产生 self-loop",
            "summary": "`Computation.run` 的定义体直接再次引用自身，因此形成 VALUE 自环。",
            **source_excerpt("Mathlib/Data/Seq/Computation.lean", 97, 103),
            "edges": [
                _edge(edges, node_by_name, "Computation.run", "Computation.run", "VALUE")
            ],
            "interpretation": (
                "自环是递归计算依赖的真实语义边；研究复用广度时应与‘被其他 declaration 使用’"
                "分开报告。"
            ),
        },
        {
            "case_id": "edge.same-pair-weighted",
            "title": "唯一 consumer 与引用强度是两个层级",
            "summary": "`List.Ico.mem` 对 `List.Ico` 贡献一个 consumer，但 TYPE 与 VALUE 各有独立权重。",
            **source_excerpt("Mathlib/Data/List/Intervals.lean", 60, 63),
            "edges": [
                _edge(edges, node_by_name, "List.Ico.mem", "List.Ico", "TYPE"),
                _edge(edges, node_by_name, "List.Ico.mem", "List.Ico", "VALUE"),
            ],
            "interpretation": (
                "ALL reuse breadth 将该 source-target pair 计为一个 consumer；occurrence intensity "
                "则保留 TYPE 与 VALUE multiplicity 的信息。"
            ),
        },
    ]

    return {
        "schema_version": "lean-graph-construction-cases-v1",
        "snapshot_id": "mathlib-v4.32.1",
        "edge_direction": "consumer declaration → referenced declaration",
        "occurrence_unit": "constant occurrences in the expanded elaborated Expr tree",
        "expr_extraction": {
            "mechanism": "Lean Environment → ConstantInfo → Expr constructor traversal",
            "source_text_role": (
                "Lean 自己负责解析和精化源码；本抽取器不搜索源码字符串。源码 range 只用于定位案例与计算独立的 source-length 指标。"
            ),
            "steps": [
                {
                    "step": "读取环境声明",
                    "code": "env.find? name → ConstantInfo",
                    "detail": "module 导入后，Lean Environment 保存已经精化的命名声明。",
                    "evidence": "LeanGraph/ExtractModule.lean L29–L35",
                    "url": (
                        "https://github.com/ider-zh/knowledge-reuse-research/blob/main/"
                        "knowledge_reuse/sources/lean_mathlib/lean/LeanGraph/ExtractModule.lean#L29-L35"
                    ),
                },
                {
                    "step": "分离 TYPE 与 VALUE",
                    "code": "info.type / info.value? (allowOpaque := true)",
                    "detail": "TYPE 读取声明类型或命题；VALUE 读取可观测的定义体或证明项。",
                    "evidence": "LeanGraph/ExtractDecl.lean L18–L32",
                    "url": (
                        "https://github.com/ider-zh/knowledge-reuse-research/blob/main/"
                        "knowledge_reuse/sources/lean_mathlib/lean/LeanGraph/ExtractDecl.lean#L18-L32"
                    ),
                },
                {
                    "step": "遍历 Expr 数据结构",
                    "code": ".app / .lam / .forallE / .letE / .proj / …",
                    "detail": "按 Lean Expr constructor 访问子表达式；不是把 Expr pretty-print 后再数文字。",
                    "evidence": "LeanGraph/ExprStats.lean L31–L43",
                    "url": (
                        "https://github.com/ider-zh/knowledge-reuse-research/blob/main/"
                        "knowledge_reuse/sources/lean_mathlib/lean/LeanGraph/ExprStats.lean#L31-L43"
                    ),
                },
                {
                    "step": "识别 declaration 依赖",
                    "code": ".const targetName universes → count[targetName] += weight",
                    "detail": "只有命名常量 constructor 形成目标 declaration；变量、Sort 与 literal 不形成依赖边。",
                    "evidence": "LeanGraph/ExprStats.lean L119–L143",
                    "url": (
                        "https://github.com/ider-zh/knowledge-reuse-research/blob/main/"
                        "knowledge_reuse/sources/lean_mathlib/lean/LeanGraph/ExprStats.lean#L119-L143"
                    ),
                },
            ],
            "cache": (
                "先用 PtrSet 只访问每个共享 Expr 指针一次，再按 root-to-node path weight 恢复展开树中的重复出现次数；缓存减少扫描工作量，但不把重复引用去掉。"
            ),
            "official_expr_url": (
                "https://github.com/leanprover/lean4/blob/v4.32.1/"
                "src/lean/Lean/Expr.lean#L290-L402"
            ),
        },
        "stages": [
            {
                "stage": "Lean source",
                "description": "源码定义 declaration；import 只决定环境中哪些名字可见。",
            },
            {
                "stage": "Environment declaration",
                "description": "读取完整名称、kind、type，以及可获得时的 value/proof。",
            },
            {
                "stage": "Elaborated Expr",
                "description": "分别遍历 TYPE 与 VALUE Expr，而不是搜索源码字符串。",
            },
            {
                "stage": "Weighted typed edge",
                "description": "每个唯一 (src,dst,edge_type) 保存正整数 multiplicity。",
            },
            {
                "stage": "Research views",
                "description": "unique consumers 衡量复用广度；multiplicity 之和衡量引用强度。",
            },
        ],
        "node_cases": node_cases,
        "edge_cases": edge_cases,
    }
