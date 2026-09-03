import { useEffect, useState } from "react";

import {
  loadDomainEdges,
  loadExternalTargets,
  loadNodes,
  loadSourceEdges,
  mathlibModuleUrl,
} from "../data";
import type {
  DomainEdgeSample,
  ExplorerKind,
  ExternalTargetSample,
  NodeSample,
  SamplePayload,
  SourceEdgeSample,
} from "../types";
import { DataTable, type Column } from "./DataTable";

export type ExplorerSelection = {
  kind: ExplorerKind;
  srcDomain?: string;
  dstDomain?: string;
};

type Props = {
  selection: ExplorerSelection;
  onClose: () => void;
};

const number = (value: number | null | undefined) => value?.toLocaleString() ?? "—";
const exactInteger = (value: string) => BigInt(value).toLocaleString("en-US");

const nodeColumns: Column<NodeSample>[] = [
  { id: "name", label: "declaration", value: (row) => row.name },
  {
    id: "module",
    label: "module ↗",
    value: (row) => row.module,
    render: (row) => (
      <a href={mathlibModuleUrl(row.module)} target="_blank" rel="noreferrer">
        {row.module}
      </a>
    ),
  },
  { id: "domain", label: "领域", value: (row) => row.domain },
  { id: "kind", label: "kind", value: (row) => row.kind },
  { id: "source_degree", label: "SOURCE 直接入度", value: (row) => row.in_degree_source, align: "right" },
  { id: "source_occurrences", label: "入向 occurrence", value: (row) => row.in_occurrences_source, align: "right" },
  {
    id: "source_paths",
    label: "直接+间接路径入度",
    value: (row) => row.in_paths_source_log10,
    render: (row) => exactInteger(row.in_paths_source),
    align: "right",
  },
  { id: "cycle_boundary", label: "循环边界?", value: (row) => row.is_path_cycle_boundary },
  { id: "out_degree", label: "SOURCE 出度", value: (row) => row.out_degree_source, align: "right" },
  { id: "tokens", label: "Token", value: (row) => row.source_tokens, align: "right" },
  {
    id: "tree",
    label: "Value T",
    value: (row) => row.value_expr_tree_occurrences,
    render: (row) => number(row.value_expr_tree_occurrences),
    align: "right",
  },
  { id: "reason", label: "为何发布", value: (row) => row.sample_reason },
];

const externalColumns: Column<ExternalTargetSample>[] = [
  { id: "name", label: "external target", value: (row) => row.name },
  {
    id: "consumers",
    label: "unique consumers",
    value: (row) => row.unique_consumer_count,
    align: "right",
  },
  { id: "pairs", label: "SOURCE pairs", value: (row) => row.source_pair_count, align: "right" },
  { id: "occurrences", label: "source occurrences", value: (row) => row.source_occurrence_count, align: "right" },
  {
    id: "module_hints",
    label: "module hints",
    value: (row) => row.target_module_hints.join(" · "),
    render: (row) => {
      const shown = row.target_module_hints.slice(0, 3).join(" · ");
      const remaining = row.target_module_hint_count - Math.min(3, row.target_module_hint_count);
      return remaining > 0 ? `${shown} · 另 ${remaining} 项` : shown;
    },
  },
  { id: "reason", label: "为何发布", value: (row) => row.sample_reason },
];

const edgeColumns: Column<DomainEdgeSample>[] = [
  { id: "src", label: "consumer/source", value: (row) => row.src_name },
  { id: "src_domain", label: "来源领域", value: (row) => row.src_domain },
  { id: "multiplicity", label: "SOURCE occurrences", value: (row) => row.multiplicity, align: "right" },
  { id: "dst", label: "dependency/target", value: (row) => row.dst_name },
  { id: "dst_domain", label: "目标领域", value: (row) => row.dst_domain },
  {
    id: "src_module",
    label: "source module ↗",
    value: (row) => row.src_module,
    render: (row) => (
      <a href={mathlibModuleUrl(row.src_module)} target="_blank" rel="noreferrer">
        {row.src_module}
      </a>
    ),
  },
  { id: "src_kind", label: "src kind", value: (row) => row.src_kind },
  { id: "dst_kind", label: "dst kind", value: (row) => row.dst_kind },
];

const sourceEdgeColumns: Column<SourceEdgeSample>[] = [
  { id: "src", label: "consumer/source", value: (row) => row.src_name },
  { id: "src_domain", label: "来源领域", value: (row) => row.src_domain },
  { id: "edge_type", label: "edge type", value: (row) => row.edge_type },
  { id: "dst", label: "dependency/target", value: (row) => row.dst_name },
  { id: "dst_domain", label: "目标领域", value: (row) => row.dst_domain },
  { id: "multiplicity", label: "source occurrences", value: (row) => row.multiplicity, align: "right" },
  {
    id: "src_module",
    label: "source module ↗",
    value: (row) => row.src_module,
    render: (row) => (
      <a href={mathlibModuleUrl(row.src_module)} target="_blank" rel="noreferrer">
        {row.src_module}
      </a>
    ),
  },
  { id: "external", label: "external?", value: (row) => row.is_external_target },
  { id: "self_loop", label: "self-loop?", value: (row) => row.is_self_loop },
  { id: "reason", label: "为何发布", value: (row) => row.sample_reason },
];

function NodeDegreeGuide({ rows }: { rows: NodeSample[] }) {
  const example = rows.find((row) => row.name === "DFunLike.coe");

  return (
    <aside className="degree-guide" aria-labelledby="degree-guide-title">
      <header>
        <p className="eyebrow">DIRECT DEGREE, OCCURRENCES &amp; PATHS</p>
        <h3 id="degree-guide-title">直接复用、源码次数与传递路径是三个不同统计量</h3>
      </header>
      <div className="degree-guide-grid">
        <article>
          <b>SOURCE pair · A → B</b>
          <p>只要 `.ilean` 在 A 的源码范围中把 identifier 解析为 B，就存在一个直接 pair。这里不增加间接依赖。</p>
        </article>
        <article>
          <b>直接入度</b>
          <p>引用 B 的不同 declaration A 的数量。一个 A 无论出现 B 一次还是十次，都只为 B 的直接入度贡献 1。</p>
        </article>
        <article>
          <b>入向 occurrence</b>
          <p>所有 A→B pair 的 multiplicity 之和，即解析到 B 的不同源码位置数。self-loop 单独保留，但不计作“被其他声明复用”。</p>
        </article>
        <article>
          <b>直接+间接路径入度</b>
          <p>计算所有终止于 B 的 SOURCE 路径，并把 edge multiplicity 当作平行路径数。路径到达循环 SCC 后停止，不穿过循环继续传播；结果保留为任意精度整数。</p>
        </article>
      </div>
      {example && (
        <p className="degree-example">
          <b>表中算例 · DFunLike.coe：</b>
          直接入度 {number(example.in_degree_source)}，入向 occurrence {number(example.in_occurrences_source)}，
          直接+间接路径入度 {exactInteger(example.in_paths_source)}。路径指标回答依赖链可沿多少条不同路线到达该节点，不等于独立 consumer 数，也不代表实际执行次数。
        </p>
      )}
    </aside>
  );
}

export default function Explorer({ selection, onClose }: Props) {
  const [payload, setPayload] = useState<SamplePayload<unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPayload(null);
    setError(null);
    if (!selection.kind) return;
    let active = true;
    const loader =
      selection.kind === "nodes"
        ? loadNodes
        : selection.kind === "external"
          ? loadExternalTargets
          : selection.kind === "source"
            ? loadSourceEdges
            : loadDomainEdges;
    loader()
      .then((value) => {
        if (active) setPayload(value as SamplePayload<unknown>);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      active = false;
    };
  }, [selection]);

  if (!selection.kind) return null;
  const titles = {
    nodes: "内部 declaration · 公开目的性样本",
    external: "显式外部目标 · 高复用头部样本",
    source: "SOURCE pairs · 重复引用与 self-loop 样本",
    edges: "领域 SOURCE pairs · 每格真实样本",
  };
  const filteredEdges =
    selection.kind === "edges" && payload
      ? (payload.rows as DomainEdgeSample[]).filter(
          (row) =>
            (!selection.srcDomain || row.src_domain === selection.srcDomain) &&
            (!selection.dstDomain || row.dst_domain === selection.dstDomain),
        )
      : [];

  return (
    <div className="explorer-backdrop" role="dialog" aria-modal="true">
      <section className="explorer-panel">
        <header>
          <div>
            <p className="eyebrow">PUBLIC SAMPLE EXPLORER</p>
            <h2>{titles[selection.kind]}</h2>
          </div>
          <button className="close-button" onClick={onClose} aria-label="关闭数据浏览器">
            ×
          </button>
        </header>
        {payload && (
          <div className="sample-contract">
            <strong>总体 {payload.population_count.toLocaleString()}</strong>
            <span>站点发布 {payload.published_count.toLocaleString()} 条解释性样本</span>
            {payload.internal_population_count != null && (
              <span>领域矩阵内部总体 {payload.internal_population_count.toLocaleString()}</span>
            )}
            <span>样本不能替代总体估计</span>
          </div>
        )}
        {!payload && !error && <p className="loading">正在按需加载小型公开数据…</p>}
        {error && <p className="error">{error}</p>}
        {payload && selection.kind === "nodes" && (
          <>
            <NodeDegreeGuide rows={payload.rows as NodeSample[]} />
            <DataTable
              rows={payload.rows as NodeSample[]}
              columns={nodeColumns}
              initialSort="source_degree"
            />
          </>
        )}
        {payload && selection.kind === "external" && (
          <DataTable
            rows={payload.rows as ExternalTargetSample[]}
            columns={externalColumns}
            initialSort="consumers"
          />
        )}
        {payload && selection.kind === "source" && (
          <DataTable
            rows={payload.rows as SourceEdgeSample[]}
            columns={sourceEdgeColumns}
            initialSort="multiplicity"
          />
        )}
        {payload && selection.kind === "edges" && (
          <>
            {(selection.srcDomain || selection.dstDomain) && (
              <p className="active-filter">
                当前 cell：{selection.srcDomain ?? "全部来源"} → {selection.dstDomain ?? "全部目标"}，
                发布 {filteredEdges.length} 个确定性样本。
              </p>
            )}
            <DataTable
              rows={filteredEdges.length || selection.srcDomain || selection.dstDomain ? filteredEdges : (payload.rows as DomainEdgeSample[])}
              columns={edgeColumns}
              initialSort="src_domain"
              initialDescending={false}
            />
          </>
        )}
      </section>
    </div>
  );
}
