import { useMemo, useState } from "react";

import type { DomainMatrixRow, DomainMetric, Overview } from "../types";

type Props = {
  overview: Overview;
  onOpenCell: (srcDomain: string, dstDomain: string) => void;
};

const algorithmLabels: Record<string, string> = {
  classification: "1 · 领域标签",
  edge_direction: "2 · 边方向",
  population: "3 · 分析总体",
  pair_unit: "4 · 去重单位",
  cell_count: "5 · 跨域累加",
  row_share: "6 · 行内份额",
  external_policy: "边界 · External",
};

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

export default function DomainExplorer({ overview, onOpenCell }: Props) {
  const domains = overview.domains.map((row) => row.domain);
  const [source, setSource] = useState(domains[0] ?? "Algebra");
  const [mode, setMode] = useState<"share" | "count">("share");

  const outgoing = useMemo(
    () =>
      overview.domain_matrix
        .filter((row) => row.src_domain === source)
        .sort((a, b) => b.dependency_pair_count - a.dependency_pair_count),
    [overview.domain_matrix, source],
  );
  const sourceMetric = overview.domains.find((row) => row.domain === source);
  const maximum = Math.max(
    ...outgoing.map((row) => (mode === "share" ? row.row_share : row.dependency_pair_count)),
    1,
  );

  return (
    <section id="domains" className="section-block">
      <div className="section-heading">
        <div>
          <p className="eyebrow">DOMAIN OPERATIONALIZATION</p>
          <h2>领域不是模型猜出来的，而是 module 路径标签</h2>
        </div>
        <p>
          它是一套可重复的 repository taxonomy，不是假设每条定理只属于一个数学主题。跨领域边仍保留，正是领域矩阵的研究对象。
        </p>
      </div>

      <div className="algorithm-grid">
        {Object.entries(algorithmLabels).map(([key, label]) => (
          <article key={key} className={key === "external_policy" ? "algorithm-boundary" : ""}>
            <span>{label}</span>
            <p>{overview.domain_algorithm[key]}</p>
          </article>
        ))}
      </div>

      <div className="domain-workbench">
        <aside>
          <p className="eyebrow">SELECT SOURCE DOMAIN</p>
          <label>
            <span>来源领域</span>
            <select value={source} onChange={(event) => setSource(event.target.value)}>
              {domains.map((domain) => (
                <option key={domain}>{domain}</option>
              ))}
            </select>
          </label>
          <div className="segmented">
            <button className={mode === "share" ? "active" : ""} onClick={() => setMode("share")}>
              row share
            </button>
            <button className={mode === "count" ? "active" : ""} onClick={() => setMode("count")}>
              pair count
            </button>
          </div>
          {sourceMetric && <DomainFacts metric={sourceMetric} />}
          <p className="microcopy">
            点击任一目标领域，可查看该 cell 发布的 3 个真实 SOURCE pair。颜色只表示本行份额，不表示数学相似度。
          </p>
        </aside>

        <div className="flow-list" aria-label={`${source} 的目标领域分布`}>
          {outgoing.map((row) => {
            const value = mode === "share" ? row.row_share : row.dependency_pair_count;
            return (
              <button key={row.dst_domain} onClick={() => onOpenCell(source, row.dst_domain)}>
                <span className="flow-rank">{row.dst_domain === source ? "SELF" : "CROSS"}</span>
                <strong>{source} → {row.dst_domain}</strong>
                <span className="flow-value">
                  {row.dependency_pair_count.toLocaleString()} pairs · {percent(row.row_share)}
                </span>
                <i style={{ width: `${Math.max(1, (value / maximum) * 100)}%` }} />
              </button>
            );
          })}
        </div>
      </div>

      <DomainMatrixTable rows={overview.domain_matrix} onOpenCell={onOpenCell} />
    </section>
  );
}

function DomainFacts({ metric }: { metric: DomainMetric }) {
  return (
    <dl className="domain-facts">
      <div>
        <dt>内部节点</dt>
        <dd>{metric.node_count.toLocaleString()}</dd>
      </div>
      <div>
        <dt>内部 outgoing pairs</dt>
        <dd>{metric.edge_count.toLocaleString()}</dd>
      </div>
      <div>
        <dt>H*ref</dt>
        <dd>{metric.reference_entropy_proxy.toFixed(3)}</dd>
      </div>
      <div>
        <dt>Gini</dt>
        <dd>{metric.gini.toFixed(3)}</dd>
      </div>
    </dl>
  );
}

function DomainMatrixTable({
  rows,
  onOpenCell,
}: {
  rows: DomainMatrixRow[];
  onOpenCell: (srcDomain: string, dstDomain: string) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = rows
    .filter((row) => `${row.src_domain} ${row.dst_domain}`.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => b.dependency_pair_count - a.dependency_pair_count)
    .slice(0, 80);
  return (
    <div className="matrix-ledger">
      <div>
        <h3>跨领域 ledger</h3>
        <p>完整保存所有非空 SOURCE cells；默认显示 pair count 最大的 80 项。</p>
      </div>
      <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="筛选领域名称…" />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>source domain</th>
              <th>target domain</th>
              <th className="numeric">unique pairs</th>
              <th className="numeric">row share</th>
              <th>局部证据</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => (
              <tr key={`${row.src_domain}:${row.dst_domain}`}>
                <td>{row.src_domain}</td>
                <td>{row.dst_domain}</td>
                <td className="numeric">{row.dependency_pair_count.toLocaleString()}</td>
                <td className="numeric">{percent(row.row_share)}</td>
                <td>
                  <button className="table-link" onClick={() => onOpenCell(row.src_domain, row.dst_domain)}>
                    查看 3 条 pair →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
