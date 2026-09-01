import { useEffect, useState } from "react";

import {
  loadDomainEdges,
  loadExternalTargets,
  loadNodes,
  loadTypedEdges,
  mathlibModuleUrl,
} from "../data";
import type {
  DomainEdgeSample,
  ExplorerKind,
  ExternalTargetSample,
  NodeSample,
  SamplePayload,
  TypedEdgeSample,
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
  { id: "in_degree_all", label: "ALL 入度", value: (row) => row.in_degree_all, align: "right" },
  { id: "type", label: "TYPE 入度", value: (row) => row.in_degree_type, align: "right" },
  { id: "value", label: "VALUE 入度", value: (row) => row.in_degree_value, align: "right" },
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
  { id: "typed", label: "typed edges", value: (row) => row.typed_edge_count, align: "right" },
  { id: "type", label: "TYPE", value: (row) => row.type_edge_count, align: "right" },
  { id: "value", label: "VALUE", value: (row) => row.value_edge_count, align: "right" },
  { id: "reason", label: "为何发布", value: (row) => row.sample_reason },
];

const edgeColumns: Column<DomainEdgeSample>[] = [
  { id: "src", label: "consumer/source", value: (row) => row.src_name },
  { id: "src_domain", label: "来源领域", value: (row) => row.src_domain },
  { id: "types", label: "TYPE / VALUE", value: (row) => row.edge_types },
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

const typedEdgeColumns: Column<TypedEdgeSample>[] = [
  { id: "src", label: "consumer/source", value: (row) => row.src_name },
  { id: "src_domain", label: "来源领域", value: (row) => row.src_domain },
  { id: "edge_type", label: "edge type", value: (row) => row.edge_type },
  { id: "dst", label: "dependency/target", value: (row) => row.dst_name },
  { id: "dst_domain", label: "目标领域", value: (row) => row.dst_domain },
  { id: "multiplicity", label: "raw multiplicity", value: (row) => row.multiplicity, align: "right" },
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
  { id: "reason", label: "为何发布", value: (row) => row.sample_reason },
];

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
          : selection.kind === "typed"
            ? loadTypedEdges
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
    typed: "唯一 typed edges · 分层真实样本",
    edges: "领域 dependency pairs · 每格真实样本",
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
          <DataTable
            rows={payload.rows as NodeSample[]}
            columns={nodeColumns}
            initialSort="in_degree_all"
          />
        )}
        {payload && selection.kind === "external" && (
          <DataTable
            rows={payload.rows as ExternalTargetSample[]}
            columns={externalColumns}
            initialSort="consumers"
          />
        )}
        {payload && selection.kind === "typed" && (
          <DataTable
            rows={payload.rows as TypedEdgeSample[]}
            columns={typedEdgeColumns}
            initialSort="src_domain"
            initialDescending={false}
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
