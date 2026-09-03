"""Export compact public evidence for the Lean source-reference graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import tomllib
from typing import Any

import polars as pl

from knowledge_reuse.sources.lean_mathlib.construction_cases import build_construction_cases
from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    ROOT,
    normalized_root,
    run_results_root,
    source_graph_normalized_root,
)
from knowledge_reuse.sources.lean_mathlib.source_graph_metrics import metrics_root


NODE_COLUMNS = [
    "name",
    "module",
    "domain",
    "kind",
    "has_value",
    "source_tokens",
    "type_expr_unique_ptr_nodes",
    "value_expr_unique_ptr_nodes",
    "value_expr_tree_occurrences",
    "in_degree_source",
    "in_occurrences_source",
    "in_paths_source",
    "in_paths_source_log10",
    "is_path_cycle_boundary",
    "out_degree_source",
    "out_occurrences_source",
]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def public_node_sample(nodes: pl.DataFrame) -> pl.DataFrame:
    selected = []
    for reason, frame in (
        (
            "SOURCE 复用入度前 120",
            nodes.sort("in_degree_source", "name", descending=[True, False]).head(120),
        ),
        (
            "每个路径领域 SOURCE 复用入度前 5",
            nodes.sort("domain", "in_degree_source", "name", descending=[False, True, False])
            .group_by("domain", maintain_order=True)
            .head(5),
        ),
        (
            "直接+间接 SOURCE 路径数前 60",
            nodes.filter(pl.col("in_paths_source_log10").is_not_null())
            .sort("in_paths_source_log10", "name", descending=[True, False])
            .head(60),
        ),
        (
            "Value Expr 展开复杂度前 60（辅助节点属性）",
            nodes.drop_nulls("value_expr_tree_occurrences")
            .sort("value_expr_tree_occurrences", "name", descending=[True, False])
            .head(60),
        ),
        (
            "固定方法案例：DFunLike.coe",
            nodes.filter(pl.col("name") == "DFunLike.coe"),
        ),
    ):
        selected.append(
            frame.select("node_id", *NODE_COLUMNS).with_columns(
                pl.lit(reason).alias("sample_reason")
            )
        )
    return (
        pl.concat(selected)
        .group_by("node_id")
        .agg(
            *[pl.col(column).first() for column in NODE_COLUMNS],
            pl.col("sample_reason").unique().sort().str.join("；"),
        )
        .sort("in_degree_source", "name", descending=[True, False])
    )


def external_target_sample(
    edges: pl.DataFrame, external_nodes: pl.DataFrame, limit: int = 200
) -> pl.DataFrame:
    return (
        edges.join(
            external_nodes.select(
                "node_id", "name", "target_module_hints", "target_module_hint_count"
            ),
            left_on="dst_id",
            right_on="node_id",
            how="inner",
        )
        .group_by("dst_id", "name", "target_module_hints", "target_module_hint_count")
        .agg(
            pl.col("src_id").n_unique().alias("unique_consumer_count"),
            pl.len().alias("source_pair_count"),
            pl.col("multiplicity").sum().alias("source_occurrence_count"),
        )
        .sort("unique_consumer_count", "name", descending=[True, False])
        .head(limit)
        .with_columns(
            pl.lit(f"外部目标按 SOURCE unique consumers 排名前 {limit}").alias(
                "sample_reason"
            )
        )
    )


def target_identities(nodes: pl.DataFrame, external_nodes: pl.DataFrame) -> pl.DataFrame:
    return pl.concat(
        [
            nodes.select("node_id", "name", "module", "domain", "kind"),
            external_nodes.select("node_id", "name").with_columns(
                pl.lit(None, dtype=pl.String).alias("module"),
                pl.lit("EXTERNAL").alias("domain"),
                pl.lit("external").alias("kind"),
            ),
        ]
    )


def enrich_edges(
    edges: pl.DataFrame, nodes: pl.DataFrame, external_nodes: pl.DataFrame
) -> pl.DataFrame:
    identities = nodes.select("node_id", "name", "module", "domain", "kind")
    targets = target_identities(nodes, external_nodes)
    return (
        edges.join(
            identities.rename(
                {
                    "node_id": "src_id",
                    "name": "src_name",
                    "module": "src_module",
                    "domain": "src_domain",
                    "kind": "src_kind",
                }
            ),
            on="src_id",
            how="inner",
        )
        .join(
            targets.rename(
                {
                    "node_id": "dst_id",
                    "name": "dst_name",
                    "module": "dst_module",
                    "domain": "dst_domain",
                    "kind": "dst_kind",
                }
            ),
            on="dst_id",
            how="inner",
        )
    )


def domain_edge_sample(
    edges: pl.DataFrame,
    nodes: pl.DataFrame,
    external_nodes: pl.DataFrame,
    per_cell: int = 3,
) -> pl.DataFrame:
    return (
        enrich_edges(edges, nodes, external_nodes)
        .filter(pl.col("dst_domain") != "EXTERNAL")
        .sort("src_domain", "dst_domain", "src_name", "dst_name")
        .with_columns(
            pl.int_range(pl.len()).over("src_domain", "dst_domain").alias("cell_rank")
        )
        .filter(pl.col("cell_rank") < per_cell)
        .with_columns(
            (pl.col("src_domain") != pl.col("dst_domain")).alias("is_cross_domain"),
            pl.lit(
                f"每个非空 source-domain → target-domain cell 按完整名称取前 {per_cell} 个 SOURCE pair"
            ).alias("sample_reason"),
        )
    )


def source_edge_sample(
    edges: pl.DataFrame,
    nodes: pl.DataFrame,
    external_nodes: pl.DataFrame,
    per_group: int = 4,
) -> pl.DataFrame:
    return (
        enrich_edges(edges, nodes, external_nodes)
        .with_columns(
            (pl.col("dst_domain") == "EXTERNAL").alias("is_external_target"),
            (pl.col("src_id") == pl.col("dst_id")).alias("is_self_loop"),
        )
        .sort(
            "is_self_loop",
            "is_external_target",
            "multiplicity",
            "src_name",
            "dst_name",
            descending=[False, False, True, False, False],
        )
        .with_columns(
            pl.int_range(pl.len())
            .over("is_self_loop", "is_external_target")
            .alias("group_rank")
        )
        .filter(pl.col("group_rank") < per_group)
        .with_columns(
            pl.lit(
                f"按 self-loop × external 分组展示 multiplicity 最高的 {per_group} 个 SOURCE pair"
            ).alias("sample_reason")
        )
    )


def logarithmic_ranks(population_size: int, limit: int = 280) -> list[int]:
    if population_size < 1:
        return []
    if population_size <= limit:
        return list(range(1, population_size + 1))
    return sorted(
        {
            1,
            population_size,
            *(
                round(math.exp(math.log(population_size) * index / (limit - 1)))
                for index in range(limit)
            ),
        }
    )


def rank_frequency_distribution(
    nodes: pl.DataFrame, rank_fits: pl.DataFrame, snapshot: str
) -> dict[str, Any]:
    populations = (
        ("all_declarations", "全部 declaration", None),
        ("kind:theorem", "theorem", "theorem"),
        ("kind:definition", "definition", "definition"),
    )
    series = []
    for population, label, kind in populations:
        selected = nodes if kind is None else nodes.filter(pl.col("kind") == kind)
        degrees = (
            selected.filter(pl.col("in_degree_source") > 0)
            .sort("in_degree_source", descending=True)["in_degree_source"]
            .to_list()
        )
        fit_rows = rank_fits.filter(pl.col("population") == population)
        if fit_rows.height != 1:
            raise ValueError(f"expected one source rank-frequency fit for {population}")
        fit = fit_rows.row(0, named=True)
        if fit["status"] != "ok":
            raise ValueError(f"source rank-frequency fit unavailable for {population}")
        beta = float(fit["beta_rank"])
        intercept = float(fit["intercept"])
        tail_n = int(fit["tail_n"])
        display_ranks = sorted({*logarithmic_ranks(len(degrees)), tail_n})
        points = [
            {
                "rank": rank,
                "empirical_degree": degrees[rank - 1],
                "fitted_degree": (
                    math.exp(intercept) * rank ** (-beta) if rank <= tail_n else None
                ),
                "zipf_degree": math.exp(intercept) / rank if rank <= tail_n else None,
            }
            for rank in display_ranks
        ]
        series.append(
            {
                "population": population,
                "label": label,
                "positive_n": len(degrees),
                "tail_n": tail_n,
                "xmin": fit["xmin"],
                "beta_rank": beta,
                "r_squared": fit["r_squared"],
                "display_sampling": (
                    f"完整排序的 {len(degrees):,} 个正 SOURCE 入度节点中按对数间隔显示 "
                    f"{len(points):,} 个 rank；拟合使用全部 {tail_n:,} 个尾部观测。"
                ),
                "points": points,
            }
        )
    return {
        "schema_version": "research-site-source-rank-frequency-v1",
        "snapshot_id": snapshot,
        "reuse_unit": "distinct direct non-self consumer declarations in `.ilean` SOURCE graph",
        "rank_definition": "positive SOURCE indegree sorted descending; rank 1 is most reused",
        "reference_definition": "Zipf reference C(r)=exp(fitted intercept)/r",
        "series": series,
    }


def source_url(source_file: str, line: int) -> str:
    return f"https://github.com/leanprover-community/mathlib4/blob/v4.32.1/{source_file}#L{line}"


def source_excerpt(source_file: str, zero_based_line: int, radius: int = 3) -> tuple[int, int, str]:
    lines = (ROOT / "vendor" / "mathlib4" / source_file).read_text().splitlines()
    start = max(0, zero_based_line - radius)
    end = min(len(lines), zero_based_line + radius + 1)
    return start + 1, end, "\n".join(lines[start:end])


def probable_variable_continuation(lines: list[str], line_index: int) -> bool:
    """Recognize a multiline binder whose nearest command head is `variable`."""

    for previous in range(line_index - 1, max(-1, line_index - 16), -1):
        text = lines[previous].strip()
        if not text or text.startswith(("--", "/-")):
            continue
        if text.startswith(("variable ", "variables ")):
            return True
        if text.startswith(
            (
                "set_option ", "omit ", "include ", "section ", "namespace ",
                "open ", "attribute ", "alias ", "def ", "theorem ", "lemma ",
                "instance ", "example ", "structure ", "class ", "inductive ",
                "abbrev ", "opaque ", "@[", "local ",
            )
        ):
            return False
    return False


def attribution_boundary(
    unparented_usages: pl.DataFrame,
    unresolved_parent_usages: pl.DataFrame,
    environment_names: set[str],
    ilean_root: pathlib.Path,
    source_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Audit which source-side `.ilean` locations can name a declaration."""

    source_root = source_root or ilean_root.parents[3]
    range_counts = {
        "outside_declaration_range": 0,
        "unique_declaration_range": 0,
        "unique_environment_declaration": 0,
        "overlapping_declaration_ranges": 0,
    }
    outside_context_counts = {
        "explicit_variable": 0,
        "probable_variable_continuation": 0,
        "option_or_attribute_header": 0,
        "attribute_command": 0,
        "alias_command": 0,
        "namespace_syntax_or_scope_command": 0,
        "other_command_or_continuation": 0,
    }
    for frame in unparented_usages.sort("module").partition_by("module", maintain_order=True):
        module = frame.item(0, "module")
        path = ilean_root.joinpath(*module.split(".")).with_suffix(".ilean")
        payload = json.loads(path.read_text())
        declarations = [
            (name, (bounds[0], bounds[1]), (bounds[2], bounds[3]))
            for name, bounds in payload.get("decls", {}).items()
            if isinstance(bounds, list)
            and len(bounds) >= 4
            and all(isinstance(value, int) for value in bounds[:4])
        ]
        source_path = source_root.joinpath(*module.split(".")).with_suffix(".lean")
        source_lines = source_path.read_text().splitlines()
        for row in frame.iter_rows(named=True):
            start = (row["start_line"], row["start_character"])
            end = (row["end_line"], row["end_character"])
            containing = [
                name
                for name, decl_start, decl_end in declarations
                if decl_start <= start and end <= decl_end
            ]
            if not containing:
                range_counts["outside_declaration_range"] += 1
                line_index = row["start_line"]
                text = source_lines[line_index].strip()
                if text.startswith(("variable ", "variables ")):
                    category = "explicit_variable"
                elif text.startswith(("[", "{", "(", "⦃")) and probable_variable_continuation(
                    source_lines, line_index
                ):
                    category = "probable_variable_continuation"
                elif text.startswith(("set_option ", "@[")):
                    category = "option_or_attribute_header"
                elif text.startswith("attribute "):
                    category = "attribute_command"
                elif text.startswith("alias "):
                    category = "alias_command"
                elif text.startswith(
                    (
                        "open ", "namespace ", "section ", "end ", "export ",
                        "notation", "infix", "prefix", "postfix", "macro", "syntax",
                        "scoped", "include ", "omit ", "local ", "universe ",
                    )
                ):
                    category = "namespace_syntax_or_scope_command"
                else:
                    category = "other_command_or_continuation"
                outside_context_counts[category] += 1
            elif len(containing) == 1:
                range_counts["unique_declaration_range"] += 1
                if containing[0] in environment_names:
                    range_counts["unique_environment_declaration"] += 1
            else:
                range_counts["overlapping_declaration_ranges"] += 1

    parent = pl.col("parent_decl")
    is_example = parent.str.contains("_example")
    example_count = unresolved_parent_usages.filter(is_example).height
    private_count = unresolved_parent_usages.filter(
        parent.str.starts_with("_private.") & ~is_example
    ).height
    other_count = unresolved_parent_usages.height - example_count - private_count
    variable_context_count = (
        outside_context_counts["explicit_variable"]
        + outside_context_counts["probable_variable_continuation"]
    )
    return {
        "primary_graph_rule": (
            "只有 `.ilean` 已解析目标且 parent label 对应持久 Environment declaration "
            "的位置，才进入 declaration reuse 主图。"
        ),
        "target_endpoint": (
            "constant reference key 提供目标 declaration 名与 module hint；不在内部语料中的"
            "目标仍保留为显式 external declaration 节点。"
        ),
        "source_endpoint": (
            "文件路径只能确定引用所在 module，不能保证存在 consumer declaration。来源端必须有"
            " parent declaration label，或经过单独验证的唯一 declaration 范围归属。"
        ),
        "unparented": {"total": unparented_usages.height, **range_counts},
        "outside_declaration_profile": {
            "population": range_counts["outside_declaration_range"],
            "variable_context_count": variable_context_count,
            "variable_context_share": (
                variable_context_count / range_counts["outside_declaration_range"]
                if range_counts["outside_declaration_range"]
                else 0.0
            ),
            "classification_note": (
                "显式 variable 按当前行命令头直接识别；多行 binder 根据向前最多 15 行的最近命令头"
                "归为高可信近似，其余类别按当前源码行前缀划分。"
            ),
            "categories": outside_context_counts,
        },
        "parent_not_in_environment": {
            "total": unresolved_parent_usages.height,
            "example_context": example_count,
            "private_or_eval_context": private_count,
            "metaprogram_or_external_context": other_count,
        },
        "context_policy": (
            "没有可靠持久 declaration 来源的位置继续作为 source-context 记录保存。完整源码引用层"
            "可以将其表示为 SourceContextNode；它们不会被伪造成 declaration 节点，也不进入复用指标。"
        ),
        "examples": [
            {
                "kind": "模块级命令",
                "title": "section variable 有所属 module，但没有 consumer declaration",
                "code": "variable {G H : Type*} [Add G] [Add H]",
                "explanation": (
                    "两个 Add 引用都位于全部 declaration 范围之外。将其分配给相邻 theorem，"
                    "会产生 Lean 并未记录的边。"
                ),
                "url": source_url("Mathlib/Algebra/AddConstMap/Basic.lean", 318),
            },
            {
                "kind": "临时上下文",
                "title": "example 会被精化，但不会持久化为 Environment 节点",
                "code": "example (l : AList β) : True := by induction l <;> trivial",
                "explanation": (
                    "`.ilean` 可以把上下文标为 AList._example；declaration 语料则只包含持久的 "
                    "Environment declarations。"
                ),
                "url": source_url("Mathlib/Data/List/AList.lean", 337),
            },
            {
                "kind": "元编程命令",
                "title": "to_additive 在新 declaration 正文之外关联已有常量",
                "code": "attribute [to_additive existing] Inv Mul HMul instHMul Div HDiv instHDiv",
                "explanation": (
                    "该命令记录 resolved constants，但它本身不是具有 declaration 来源端的"
                    "可复用数学声明。"
                ),
                "url": source_url("Mathlib/Tactic/ToAdditive.lean", 25),
            },
            {
                "kind": "范围歧义",
                "title": "生成或嵌套 declaration 可能共享源码范围",
                "code": "usage range ⊆ outer declaration range ∩ generated declaration range",
                "explanation": (
                    "仅凭范围包含会得到多个候选。该位置可以审计，但 declaration 图不能按距离"
                    "擅自选择其中一个。"
                ),
                "url": "https://github.com/leanprover/lean4/blob/v4.32.1/src/lean/Lean/Server/References.lean#L205-L217",
            },
        ],
    }


def build_source_edge_case(
    case_id: str,
    title: str,
    summary: str,
    src_name: str,
    dst_name: str,
    nodes: pl.DataFrame,
    external_nodes: pl.DataFrame,
    edges: pl.DataFrame,
    usages: pl.DataFrame,
    aggregate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identities = target_identities(nodes, external_nodes)
    src = identities.filter(pl.col("name") == src_name).row(0, named=True)
    dst = identities.filter(pl.col("name") == dst_name).row(0, named=True)
    edge = edges.filter(
        (pl.col("src_id") == src["node_id"]) & (pl.col("dst_id") == dst["node_id"])
    ).row(0, named=True)
    locations = usages.filter(
        (pl.col("src_id") == src["node_id"]) & (pl.col("dst_id") == dst["node_id"])
    ).sort("start_line", "start_character")
    source_file = nodes.filter(pl.col("node_id") == src["node_id"]).item(0, "source_file")
    first_line = int(locations.item(0, "start_line"))
    start_line, end_line, code = source_excerpt(source_file, first_line)
    location_rows = [
        {
            "line": int(row["start_line"]) + 1,
            "start_character": int(row["start_character"]),
            "end_character": int(row["end_character"]),
        }
        for row in locations.head(10).iter_rows(named=True)
    ]
    return {
        "case_id": case_id,
        "title": title,
        "summary": summary,
        "source_file": source_file,
        "start_line": start_line,
        "end_line": end_line,
        "source_url": source_url(source_file, first_line + 1),
        "code": code,
        "edges": [
            {
                "src_id": src["node_id"],
                "src_name": src["name"],
                "src_kind": src["kind"],
                "dst_id": dst["node_id"],
                "dst_name": dst["name"],
                "dst_kind": dst["kind"],
                "edge_type": "SOURCE",
                "multiplicity": edge["multiplicity"],
                "is_self_loop": src["node_id"] == dst["node_id"],
            }
        ],
        "source_locations": location_rows,
        "published_location_count": len(location_rows),
        "aggregate": aggregate,
        "interpretation": (
            "每个不同源码位置贡献一次 occurrence；相同 source-target 的位置聚合为 "
            "multiplicity。网页最多展示前 10 个位置，边权来自完整位置集合。"
        ),
    }


def construction_cases(
    snapshot: str,
    nodes: pl.DataFrame,
    external_nodes: pl.DataFrame,
    edges: pl.DataFrame,
    usages: pl.DataFrame,
    unparented_usages: pl.DataFrame,
    unresolved_parent_usages: pl.DataFrame,
) -> dict[str, Any]:
    old_root = normalized_root(snapshot, "full")
    old_nodes = pl.read_parquet(old_root / "nodes.parquet")
    old_edges = pl.read_parquet(old_root / "edges.parquet")
    old = build_construction_cases(old_nodes, old_edges)
    source_ids = dict(nodes.select("name", "node_id").iter_rows())
    for case in old["node_cases"]:
        for node in case.get("nodes", []):
            node["node_id"] = source_ids[node["name"]]

    dfunlike_id = nodes.filter(pl.col("name") == "DFunLike.coe").item(0, "node_id")
    dfunlike_edges = edges.filter(pl.col("dst_id") == dfunlike_id)
    dfunlike_usages = usages.filter(pl.col("dst_id") == dfunlike_id)
    dfunlike_unresolved = unresolved_parent_usages.filter(
        pl.col("target_decl") == "DFunLike.coe"
    )
    cases = [
        build_source_edge_case(
            "edge.dfunlike",
            "DFunLike.coe：局部 pair 与完整目标入度",
            "局部 pair 展示同一 consumer 中两个源码位置；目标汇总来自完整 `.ilean` 图。",
            "AlgEquiv.instFunLike",
            "DFunLike.coe",
            nodes,
            external_nodes,
            edges,
            usages,
            {
                "target_source_occurrences": int(dfunlike_edges["multiplicity"].sum()),
                "target_unique_consumers": dfunlike_edges["src_id"].n_unique(),
                "source_modules": dfunlike_usages["module"].n_unique(),
                "excluded_private_context_locations": dfunlike_unresolved.height,
            },
        ),
        build_source_edge_case(
            "edge.repeated",
            "同一 declaration pair 的 71 个源码位置",
            "一个 theorem 在其源码范围内多次引用同一 definition；位置不折叠为一条无权边。",
            "Algebra.FormallySmooth.of_surjective_of_ker_eq_map_of_flat",
            "Algebra.Extension.Ring",
            nodes,
            external_nodes,
            edges,
            usages,
        ),
        build_source_edge_case(
            "edge.self-loop",
            "递归声明形成 SOURCE self-loop",
            "声明正文中的递归名称由 `.ilean` 解析回该声明自身，因而保留 self-loop。",
            "CategoryTheory.FreeMonoidalCategory.HomEquiv",
            "CategoryTheory.FreeMonoidalCategory.HomEquiv",
            nodes,
            external_nodes,
            edges,
            usages,
        ),
    ]
    return {
        "schema_version": "lean-source-construction-cases-v2",
        "snapshot_id": snapshot,
        "edge_direction": "consumer declaration → resolved target declaration",
        "occurrence_unit": "one distinct `.ilean` resolved LSP source range",
        "edge_extraction": {
            "mechanism": (
                "Lean writes resolved identifier references and their source ranges from elaborator "
                "InfoTrees into `.ilean`; the graph reads constant references with parent declaration labels."
            ),
            "steps": [
                {
                    "step": "收集精化信息",
                    "code": "findReferences text trees",
                    "detail": "Lean 遍历 InfoTree，只保留具有源码 range 的原始 identifier 信息。",
                    "evidence": "Lean References.lean · findReferences",
                    "url": "https://github.com/leanprover/lean4/blob/v4.32.1/src/lean/Lean/Server/References.lean#L257-L268",
                },
                {
                    "step": "解析全局常量",
                    "code": "Expr.const n → RefIdent.const module name",
                    "detail": "精化后的常量名称成为目标；局部 free variable 不成为 declaration target。",
                    "evidence": "Lean References.lean · identOf",
                    "url": "https://github.com/leanprover/lean4/blob/v4.32.1/src/lean/Lean/Server/References.lean#L231-L255",
                },
                {
                    "step": "写入 .ilean",
                    "code": "Ilean { module, references, decls }",
                    "detail": "编译前端把 reference index 以 JSON 形式写入版本 5 `.ilean` 文件。",
                    "evidence": "Lean Frontend.lean · ilean writer",
                    "url": "https://github.com/leanprover/lean4/blob/v4.32.1/src/lean/Lean/Elab/Frontend.lean#L357-L368",
                },
                {
                    "step": "聚合 SOURCE edge",
                    "code": "GROUP BY (parent_decl, target_decl)",
                    "detail": "不同 source ranges 全部保留；pair 的 multiplicity 等于其位置数。",
                    "evidence": "项目 schema · lean-source-graph-v1",
                    "url": "https://github.com/ider-zh/knowledge-reuse-research/blob/main/schemas/lean_mathlib/lean-source-graph-v1.md",
                },
            ],
            "module_hint": (
                "`.ilean` constant key 的 module 字段通常来自 Environment module index；索引缺失时 "
                "Lean 回退到当前模块，因此它只是 hint，不参与 node identity。"
            ),
        },
        "attribution_boundary": attribution_boundary(
            unparented_usages,
            unresolved_parent_usages,
            set(nodes["name"].to_list()),
            ROOT / "vendor" / "mathlib4" / ".lake" / "build" / "lib" / "lean",
        ),
        "stages": [
            {"stage": "Lean source", "description": "声明与证明源码提供 identifier 的实际位置。"},
            {"stage": "Elaborator InfoTree", "description": "Lean 把表面语法解析为带目标名称的精化信息。"},
            {"stage": ".ilean reference index", "description": "保存 resolved constant、父声明和 LSP range。"},
            {"stage": "SOURCE multigraph", "description": "同一 pair 的不同位置保留为 multiplicity。"},
            {"stage": "Research metrics", "description": "直接入度衡量复用广度，occurrence 衡量源码引用次数。"},
        ],
        "node_cases": old["node_cases"],
        "edge_cases": cases,
    }


def claims(
    summary: dict[str, Any],
    ranks: pl.DataFrame,
    powerlaw_fits: pl.DataFrame,
    domains: pl.DataFrame,
) -> list[dict[str, Any]]:
    rank = {row["population"]: row for row in ranks.iter_rows(named=True)}
    powerlaw = {
        row["population"]: row for row in powerlaw_fits.iter_rows(named=True)
    }
    concentration = summary["reuse_concentration"]
    domain = {row["domain"]: row for row in domains.iter_rows(named=True)}
    return [
        {
            "claim_id": "veldhuizen.rank_frequency",
            "status": "supported",
            "text": (
                "`.ilean` 直接复用呈宽尾 rank–frequency，但不支持严格 Zipf 1/r："
                f"全体尾部 β={rank['all_declarations']['beta_rank']:.3f}，theorem "
                f"β={rank['kind:theorem']['beta_rank']:.3f}，definition "
                f"β={rank['kind:definition']['beta_rank']:.3f}。"
            ),
            "scope": (
                "直接、非 self-loop、不同 consumer declaration 的 SOURCE 入度；"
                f"全体拟合尾部 n={rank['all_declarations']['tail_n']:,}，"
                f"xmin={rank['all_declarations']['xmin']:.0f}。"
            ),
            "caveat": (
                "β<1 表示比 1/r 下降更慢；高 R² 是描述性贴合。全体尾部的纯 power law "
                f"相对 lognormal 的归一化对数似然比为 "
                f"{powerlaw['all_declarations']['powerlaw_vs_lognormal_r']:.3f}（负值偏向 lognormal），"
                "因此不能宣称严格 power law。"
            ),
            "evidence": [
                "source_graph_metrics/rank_frequency_fits.parquet",
                "source_graph_metrics/powerlaw_fits.parquet",
            ],
        },
        {
            "claim_id": "veldhuizen.concentration",
            "status": "supported",
            "text": (
                f"在 {summary['positive_reused_target_count']:,} 个正入度 declaration 中，"
                f"Top 1/5/10% 承接 {concentration['top_1pct_share']:.1%}/"
                f"{concentration['top_5pct_share']:.1%}/"
                f"{concentration['top_10pct_share']:.1%} 的 unique-consumer 复用，"
                f"Gini={concentration['gini']:.3f}。"
            ),
            "scope": "正 SOURCE 入度的内部 declaration；self-loop 不计作被其他声明复用。",
            "caveat": "unique-consumer breadth 与同一 consumer 内出现多少次是两个不同指标。",
            "evidence": ["source_graph_metrics/summary.json#/reuse_concentration"],
        },
        {
            "claim_id": "veldhuizen.domain_heterogeneity",
            "status": "exploratory",
            "text": (
                "路径领域呈现不同引用分布："
                f"Algebra H*ref={domain['Algebra']['reference_entropy_proxy']:.3f}, "
                f"Gini={domain['Algebra']['gini']:.3f}；NumberTheory "
                f"H*ref={domain['NumberTheory']['reference_entropy_proxy']:.3f}, "
                f"Gini={domain['NumberTheory']['gini']:.3f}。"
            ),
            "scope": "两端均为内部 declaration 的直接 SOURCE pairs，按 source module 路径领域分组。",
            "caveat": "领域是 repository taxonomy；H*ref 是经验代理，不是 Veldhuizen 理论 H。",
            "evidence": ["source_graph_metrics/domain_metrics.parquet"],
        },
        {
            "claim_id": "source.occurrence_semantics",
            "status": "fact",
            "text": (
                f"{summary['source_pair_count']:,} 个 SOURCE pairs 对应 "
                f"{summary['source_occurrence_count']:,} 个源码位置；"
                f"{summary['repeated_pair_count']:,} 个 pair 的 multiplicity 大于 1。"
            ),
            "scope": "能够映射为 Environment declaration → resolved target 的 `.ilean` locations。",
            "caveat": "这是源码 identifier 引用，不是运行时调用次数，也不是 Expr DAG 展开路径数。",
            "evidence": ["runs/full/source-graph-summary.json"],
        },
    ]


def export_site(output: pathlib.Path, run_kind: str = "full") -> dict[str, Any]:
    config = tomllib.loads(CONFIG_PATH.read_text())
    snapshot = config["snapshot_id"]
    graph_root = source_graph_normalized_root(snapshot, run_kind)
    derived_root = metrics_root(run_kind)
    output.mkdir(parents=True, exist_ok=True)

    summary = json.loads((derived_root / "summary.json").read_text())
    source_nodes = pl.read_parquet(derived_root / "node_metrics.parquet")
    legacy_metrics = pl.read_parquet(run_results_root(run_kind) / "metrics/node_metrics.parquet")
    nodes = source_nodes.join(
        legacy_metrics.select(
            "name",
            "type_expr_unique_ptr_nodes",
            "value_expr_unique_ptr_nodes",
            "value_expr_tree_occurrences",
        ),
        on="name",
        how="left",
        validate="1:1",
    )
    edges = pl.read_parquet(graph_root / "edges.parquet")
    usages = pl.read_parquet(graph_root / "usages.parquet")
    unresolved_parent_usages = pl.read_parquet(
        graph_root / "unresolved_parent_usages.parquet"
    )
    unparented_usages = pl.read_parquet(graph_root / "unparented_usages.parquet")
    external_nodes = pl.read_parquet(graph_root / "external_nodes.parquet")
    domains = pl.read_parquet(derived_root / "domain_metrics.parquet").sort(
        "node_count", descending=True
    )
    domain_matrix = pl.read_parquet(derived_root / "domain_matrix.parquet").sort(
        "src_domain", "dependency_pair_count", "dst_domain", descending=[False, True, False]
    )
    rank_fits = pl.read_parquet(derived_root / "rank_frequency_fits.parquet")
    powerlaw_fits = pl.read_parquet(derived_root / "powerlaw_fits.parquet")

    node_sample = public_node_sample(nodes)
    external_sample = external_target_sample(edges, external_nodes)
    edge_sample = domain_edge_sample(edges, source_nodes, external_nodes)
    source_sample = source_edge_sample(edges, source_nodes, external_nodes)
    construction = construction_cases(
        snapshot,
        source_nodes,
        external_nodes,
        edges,
        usages,
        unparented_usages,
        unresolved_parent_usages,
    )
    rank_frequency = rank_frequency_distribution(nodes, rank_fits, snapshot)
    report_claims = claims(summary, rank_fits, powerlaw_fits, domains)

    files = {
        "overview.json": {
            "schema_version": "research-site-source-overview-v1",
            "graph_schema_version": "lean-source-graph-v1",
            "snapshot_id": snapshot,
            "run_kind": run_kind,
            "headline_metrics": {
                "internal_declarations": summary["internal_declaration_count"],
                "external_targets": summary["external_target_count"],
                "source_pairs": summary["source_pair_count"],
                "source_occurrences": summary["source_occurrence_count"],
                "repeated_pairs": summary["repeated_pair_count"],
                "self_loop_pairs": summary["self_loop_pair_count"],
                "unparented_usages": summary["unparented_usage_count"],
                "unresolved_parent_usages": summary["unresolved_parent_usage_count"],
            },
            "path_indegree": summary["path_indegree"],
            "domain_algorithm": {
                "classification": "Mathlib.X... → X；非 Mathlib module → 第一段",
                "edge_direction": "consumer/source domain → resolved target domain",
                "population": "两端均为 Environment 内部 declaration 的直接 SOURCE pairs；排除 self-loop",
                "pair_unit": "一个不同 (src_id,dst_id)；同一 pair 的多个源码位置不重复增加 pair count",
                "cell_count": "按 (src_domain,dst_domain) 分组计算 SOURCE pair 数",
                "row_share": "cell pair count / 同一 src_domain 发出的全部内部 SOURCE pairs",
                "external_policy": "external target 没有可靠 domain，不进入领域矩阵；其全部 module hints 单独保留",
            },
            "sampling_policy": {
                "nodes": "目的性样本：SOURCE 复用头部、各领域头部与 Expr 复杂度极值；不是随机代表性样本",
                "external_targets": "按 SOURCE unique consumer count 取前 200",
                "domain_edges": "每个非空领域 cell 按完整 source/target 名取前 3 个 SOURCE pair",
                "source_edges": "按 self-loop × external 分组发布 multiplicity 最高的 4 个 pair",
                "warning": "局部表用于解释和核查；Zipf、集中度与领域结论来自完整 source graph metrics",
            },
            "claims": report_claims,
            "domains": domains.to_dicts(),
            "domain_matrix": domain_matrix.to_dicts(),
        },
        "nodes.json": {
            "schema_version": "research-site-source-node-sample-v1",
            "population_count": summary["internal_declaration_count"],
            "published_count": node_sample.height,
            "rows": node_sample.to_dicts(),
        },
        "external-targets.json": {
            "schema_version": "research-site-source-external-sample-v1",
            "population_count": summary["external_target_count"],
            "published_count": external_sample.height,
            "rows": external_sample.to_dicts(),
        },
        "domain-edge-samples.json": {
            "schema_version": "research-site-source-domain-edge-sample-v1",
            "population_count": summary["source_pair_count"],
            "internal_population_count": int(domain_matrix["dependency_pair_count"].sum()),
            "published_count": edge_sample.height,
            "rows": edge_sample.to_dicts(),
        },
        "source-edge-samples.json": {
            "schema_version": "research-site-source-edge-sample-v1",
            "population_count": summary["source_pair_count"],
            "published_count": source_sample.height,
            "rows": source_sample.to_dicts(),
        },
        "construction-cases.json": construction,
        "reuse-rank-frequency.json": rank_frequency,
    }
    legacy_path = output / "typed-edge-samples.json"
    if legacy_path.exists():
        legacy_path.unlink()
    for name, payload in files.items():
        write_json(output / name, payload)

    manifest = {
        "schema_version": "research-site-data-manifest-v2",
        "source_id": "lean_mathlib",
        "experiment_id": "lean_mathlib_v1",
        "graph_schema_version": "lean-source-graph-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "files": {
            name: {"bytes": (output / name).stat().st_size, "sha256": sha256(output / name)}
            for name in files
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path(
            "apps/research-site/public/datasets/lean_mathlib_v1/mathlib-v4.32.1"
        ),
    )
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    manifest = export_site(args.output, "smoke" if args.smoke else "full")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
