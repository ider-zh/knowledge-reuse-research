import { lazy, Suspense, useEffect, useState } from "react";

import DomainExplorer from "./components/DomainExplorer";
import Explorer, { type ExplorerSelection } from "./components/Explorer";
import GraphConstruction from "./components/GraphConstruction";
import { loadOverview } from "./data";
import type { Claim, ExplorerKind, Overview } from "./types";

const format = new Intl.NumberFormat("en-US");
const DomainCharts = lazy(() => import("./components/DomainCharts"));
const ReuseDistributionChart = lazy(() => import("./components/ReuseDistributionChart"));

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
            <a href="#distribution">Zipf 对照</a>
            <a href="#domains">领域流向</a>
            <a href="#methods">数据契约</a>
            <a href="https://github.com/ider-zh/knowledge-reuse-research" target="_blank" rel="noreferrer">GitHub ↗</a>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="hero">
          <div className="hero-copy">
            <p className="eyebrow">LEAN 4 / MATHLIB v4.32.1 · .ILEAN SOURCE GRAPH</p>
            <h1>形式化知识<br />复用观测站</h1>
            <p className="hero-dek">
              本研究把 mathlib 中的 declaration 视为节点，把 Lean 在 `.ilean` 中解析到具体目标的源码引用视为有向边。完整图用于计算复用分布；本页通过统计图与固定版本源码案例呈现证据。
            </p>
          </div>
          <aside className="concept-card">
            <p className="eyebrow">GRAPH SEMANTICS</p>
            <b>consumer declaration</b><span>→</span><b>referenced declaration</b>
            <p>每个不同源码位置贡献一次 occurrence；同一 pair 的位置数成为 multiplicity。import 关系不直接成为边。</p>
          </aside>
        </section>

        <section className="metric-grid" aria-label="图规模指标">
          <MetricCard number={metrics.internal_declarations} label="内部 declaration" detail="Environment 中的研究节点" onClick={() => open("nodes")} />
          <MetricCard number={metrics.external_targets} label="显式 external targets" detail="保留边界目标与 module hints" onClick={() => open("external")} />
          <MetricCard number={metrics.source_pairs} label="SOURCE pairs" detail="不同 consumer → target 对" onClick={() => open("source")} />
          <MetricCard number={metrics.source_occurrences} label="源码引用 occurrence" detail="不同 resolved LSP source ranges" onClick={() => open("source")} />
          <MetricCard number={metrics.repeated_pairs} label="重复引用 pairs" detail="multiplicity 大于 1" onClick={() => open("source")} />
          <MetricCard number={metrics.self_loop_pairs} label="SOURCE self-loops" detail="递归或自引用源码位置" onClick={() => open("source")} />
        </section>

        <aside className="attribution-boundary">
          <b>Declaration edge 的归属边界</b>
          <p>
            `.ilean` 中另有 {format.format(metrics.unparented_usages)} 个位置没有 parent declaration，
            {format.format(metrics.unresolved_parent_usages)} 个位置的 parent label 不在 Environment 节点集中。
            两类记录均独立保存，不进入 declaration→declaration 图。
          </p>
        </aside>

        <GraphConstruction />

        <section id="findings" className="section-block findings">
          <div className="section-heading">
            <div><p className="eyebrow">VELDHUIZEN-STYLE FINDINGS</p><h2>先给结论，再打开证据</h2></div>
            <p>每条结论给出分析总体、限制和机器证据路径。supported 表示证据支持经验命题，不表示证明了严格分布定律。</p>
          </div>
          <div className="claim-grid">
            {overview.claims.map((claim) => <ClaimCard key={claim.claim_id} claim={claim} />)}
          </div>
        </section>

        <Suspense fallback={<section className="section-block loading">正在加载 Zipf 对照图…</section>}>
          <ReuseDistributionChart />
        </Suspense>

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
            <p>网页发布可审阅的局部样本和完整总体的派生统计；每个 JSON 均记录总体数、发布数、schema 与 checksum。</p>
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
        <p>{overview.graph_schema_version} · direct resolved source references</p>
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
