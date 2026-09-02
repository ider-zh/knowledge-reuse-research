import { lazy, Suspense, useEffect, useState } from "react";

import DomainExplorer from "./components/DomainExplorer";
import Explorer, { type ExplorerSelection } from "./components/Explorer";
import GraphConstruction from "./components/GraphConstruction";
import { loadOverview } from "./data";
import type { Claim, ExplorerKind, Overview } from "./types";

const format = new Intl.NumberFormat("en-US");
const DomainCharts = lazy(() => import("./components/DomainCharts"));

function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explorer, setExplorer] = useState<ExplorerSelection>({ kind: null });

  useEffect(() => {
    loadOverview()
      .then(setOverview)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  if (error) return <main className="fatal"><h1>站点数据加载失败</h1><p>{error}</p></main>;
  if (!overview) return <main className="fatal"><p className="eyebrow">LOADING RESEARCH SNAPSHOT</p><h1>正在装载 compact evidence…</h1></main>;

  const open = (kind: ExplorerKind) => setExplorer({ kind });
  const metrics = overview.headline_metrics;

  return (
    <>
      <header className="site-header">
        <nav>
          <a className="wordmark" href="#top">KR / OBSERVATORY</a>
          <div>
            <a href="#findings">研究结论</a>
            <a href="#construction">图的构建</a>
            <a href="#domains">领域流向</a>
            <a href="#methods">数据契约</a>
            <a href="https://github.com/ider-zh/knowledge-reuse-research" target="_blank" rel="noreferrer">GitHub ↗</a>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">LEAN 4 / MATHLIB v4.32.1 · FULL GRAPH</p>
            <h1>形式化知识<br />复用观测站</h1>
            <p className="hero-dek">
              不把 2,400 万条边下载到浏览器。总体结论来自完整图；站点只发布带选择规则、可追溯到源码的局部证据。
            </p>
          </div>
          <aside className="concept-card">
            <p className="eyebrow">GRAPH SEMANTICS</p>
            <b>consumer declaration</b><span>→</span><b>referenced declaration</b>
            <p>边来自精化后的证明与类型表达式；import 只负责装载环境。</p>
          </aside>
        </section>

        <section className="metric-grid" aria-label="图规模指标">
          <MetricCard number={metrics.internal_declarations} label="内部 declaration" detail="配置语料内的完整节点" onClick={() => open("nodes")} />
          <MetricCard number={metrics.external_targets} label="显式 external targets" detail="保留边界依赖，不伪造领域" onClick={() => open("external")} />
          <MetricCard number={metrics.typed_edges} label="唯一 typed edges" detail="TYPE 与 VALUE 分开计数" onClick={() => open("typed")} />
          <MetricCard number={metrics.unique_dependency_pairs} label="ALL dependency pairs" detail="TYPE/VALUE 对同一 pair 折叠" onClick={() => open("edges")} />
          <MetricCard
            number={metrics.constant_occurrences}
            label="展开 Expr tree 常量次数"
            detail={`精确值 ${format.format(metrics.constant_occurrences)}；不是运行时调用量`}
            onClick={() => open("typed")}
          />
        </section>

        <GraphConstruction />

        <section id="findings" className="section-block findings">
          <div className="section-heading">
            <div><p className="eyebrow">VELDHUIZEN-STYLE FINDINGS</p><h2>先给结论，再打开证据</h2></div>
            <p>每条结论保留 scope、caveat 和机器证据路径。supported 不等于证明，exploratory 不等于无价值。</p>
          </div>
          <div className="claim-grid">
            {overview.claims.map((claim) => <ClaimCard key={claim.claim_id} claim={claim} />)}
          </div>
        </section>

        <Suspense fallback={<section className="section-block loading">正在加载领域图表…</section>}>
          <DomainCharts overview={overview} />
        </Suspense>
        <DomainExplorer
          overview={overview}
          onOpenCell={(srcDomain, dstDomain) => setExplorer({ kind: "edges", srcDomain, dstDomain })}
        />

        <section id="methods" className="section-block methods">
          <div className="section-heading">
            <div><p className="eyebrow">PUBLICATION CONTRACT</p><h2>完整计算，有限发布</h2></div>
            <p>网页是证据入口，不是原始数据仓库。每个公开 JSON 都有 population count、published count、schema 和 checksum。</p>
          </div>
          <div className="method-grid">
            {Object.entries(overview.sampling_policy).map(([key, value]) => (
              <article key={key}><span>{key.replaceAll("_", " ")}</span><p>{value}</p></article>
            ))}
          </div>
          <div className="scope-equation">
            <span>完整 normalized graph</span><b>→</b><span>完整 derived metrics</span><b>→</b><span>目的性 public samples</span><b>→</b><span>静态站点</span>
          </div>
        </section>
      </main>

      <footer>
        <p>Knowledge Reuse Research · snapshot {overview.snapshot_id}</p>
        <p>Cloudflare-ready static build · no browser access to full raw graph</p>
      </footer>

      <Explorer selection={explorer} onClose={() => setExplorer({ kind: null })} />
    </>
  );
}

function MetricCard({ number, label, detail, onClick }: { number: number; label: string; detail: string; onClick: () => void }) {
  const compact = number >= 1_000_000_000_000;
  const displayNumber = compact ? `${(number / 1_000_000_000_000).toFixed(3)} 万亿` : format.format(number);
  return (
    <button className="metric-card" onClick={onClick}>
      <span className="metric-link">OPEN SAMPLE TABLE ↗</span>
      <strong className={compact ? "compact" : ""} title={format.format(number)}>{displayNumber}</strong>
      <b>{label}</b>
      <small>{detail}</small>
    </button>
  );
}

function ClaimCard({ claim }: { claim: Claim }) {
  return (
    <article className={`claim-card ${claim.status}`}>
      <header><span>{claim.status}</span><code>{claim.claim_id}</code></header>
      <p className="claim-text">{claim.text}</p>
      <details><summary>范围、限制与证据</summary><p><b>Scope</b> {claim.scope}</p><p><b>Caveat</b> {claim.caveat}</p><p><b>Evidence</b> {claim.evidence.join(" · ")}</p></details>
    </article>
  );
}

export default App;
