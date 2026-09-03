import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { loadOpenJdkReuseReport } from "../data";
import type { OpenJdkMetricSample, OpenJdkReuseReport } from "../types";

const integer = new Intl.NumberFormat("en-US");
const exact = (value: string) => BigInt(value).toLocaleString("en-US");

export default function OpenJdkReport() {
  const [data, setData] = useState<OpenJdkReuseReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rangeId, setRangeId] = useState<"all_positive" | "top_1pct">("all_positive");
  const [sampleKey, setSampleKey] = useState<SampleKey | null>(null);

  useEffect(() => {
    loadOpenJdkReuseReport()
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const selected = useMemo(
    () => data?.rank_shape.ranges.find((range) => range.range_id === rangeId),
    [data, rangeId],
  );

  if (error) return <main className="fatal"><h1>OpenJDK 报告加载失败</h1><p>{error}</p></main>;
  if (!data || !selected) return <main className="fatal"><p className="eyebrow">LOADING OPENJDK REPORT</p><h1>正在装载方法调用图统计…</h1></main>;

  const zipf = selected.models.zipf;
  const prime = selected.models.reciprocal_prime;
  const primeImprovement = 100 * (zipf.fixed_rmse_log10 - prime.fixed_rmse_log10) / zipf.fixed_rmse_log10;
  const rankTenfoldDrop = 10 ** zipf.free_exponent_beta;
  const zipfErrorFactor = 10 ** zipf.fixed_rmse_log10;
  const primeErrorFactor = 10 ** prime.fixed_rmse_log10;
  const freeErrorFactor = 10 ** zipf.free_rmse_log10;

  return (
    <>
      <header className="site-header">
        <nav>
          <a className="wordmark" href="/openjdk/">KR / SOFTWARE</a>
          <div>
            <a className="report-switch" href="/">Lean 报告</a>
            <a href="#construction">抽取示例</a>
            <a href="#findings">主要发现</a>
            <a href="#rank-shape">分布比较</a>
            <a href="#top-methods">高路径节点</a>
            <a href="#method">方法</a>
            <a href="https://github.com/ider-zh/knowledge-reuse-research" target="_blank" rel="noreferrer">GitHub ↗</a>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="hero software-hero">
          <div className="hero-copy">
            <p className="eyebrow">OPENJDK 28+13 / METHOD CALL GRAPH</p>
            <h1>Java 类库<br />方法复用分布</h1>
            <p className="hero-dek">
              以 JVM method declaration 为节点，以已解析的字节码调用位置为边。本报告统计每个方法的直接调用入度，以及保留重复调用位置的直接+间接路径入度；路径到达循环边界即停止。
            </p>
          </div>
          <aside className="concept-card">
            <p className="eyebrow">PATH METRIC</p>
            <b>caller method</b><span>→</span><b>callee method</b>
            <p><code>P(v)=Σ m(u,v)×(1+P*(u))</code>。m 是调用位置数；P* 在循环 SCC 上为零，防止递归产生无限 walk。</p>
          </aside>
        </section>

        <section className="metric-grid" aria-label="OpenJDK 方法图规模">
          <ReportMetric value={data.population.nodes} label="方法节点" detail="完整 JMOD Java 字节码总体" onClick={() => setSampleKey("method_nodes")} />
          <ReportMetric value={data.population.links} label="调用 pair" detail="不同 caller → callee" onClick={() => setSampleKey("call_pairs")} />
          <ReportMetric value={data.population.call_occurrences} label="调用 occurrence" detail="multiplicity 加权边总数" onClick={() => setSampleKey("call_occurrences")} />
          <ReportMetric value={data.population.positive_path_nodes} label="正路径入度节点" detail="进入 rank 曲线的总体" onClick={() => setSampleKey("positive_path_nodes")} />
          <ReportMetric value={data.population.zero_path_nodes} label="零路径入度节点" detail="完整总体中保留但无法取对数" onClick={() => setSampleKey("zero_path_nodes")} />
          <ReportMetric value={data.population.cycle_boundary_nodes} label="循环边界节点" detail="到达后停止继续传播" onClick={() => setSampleKey("cycle_boundary_nodes")} />
        </section>

        <section id="construction" className="section-block extraction-section">
          <div className="section-heading">
            <div><p className="eyebrow">CLASSFILE → GRAPH</p><h2>Node 与 Edge 抽取示例</h2></div>
            <p>示例来自本次固定 OpenJDK 语料。Java 源码用于阅读和行号核对；节点与边的身份来自 JMOD 中的 classfile declaration 和 invoke instruction。</p>
          </div>
          <div className="extraction-grid">
            <ExtractionCase title="Node：String.substring" label="METHOD DECLARATION" path={data.extraction_examples.node.source_path} lines={data.extraction_examples.node.source_lines} source={data.extraction_examples.node.source_excerpt} highlightLines={[data.extraction_examples.node.source_lines[0]]}>
              <dl className="extraction-fields">
                {Object.entries(data.extraction_examples.node.classfile_fields).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}
              </dl>
              <div className="extraction-output"><span>输出 method node</span><code>{data.extraction_examples.node.output.method_key}</code><small>node_id {data.extraction_examples.node.output.node_id}</small></div>
            </ExtractionCase>
            <ExtractionCase title="Edge：checkCapacity → newLength" label="INVOKE INSTRUCTION" path={data.extraction_examples.edge.source_path} lines={data.extraction_examples.edge.source_lines} source={data.extraction_examples.edge.source_excerpt} highlightLines={[data.extraction_examples.edge.bytecode_reference.source_line]}>
              <dl className="extraction-fields">
                <div><dt>opcode kind</dt><dd>{data.extraction_examples.edge.bytecode_reference.invoke_kind}</dd></div>
                <div><dt>source line</dt><dd>{data.extraction_examples.edge.bytecode_reference.source_line}</dd></div>
                <div><dt>declared target</dt><dd>{data.extraction_examples.edge.bytecode_reference.declared_owner}#{data.extraction_examples.edge.bytecode_reference.declared_name}{data.extraction_examples.edge.bytecode_reference.declared_descriptor}</dd></div>
                <div><dt>resolution</dt><dd>{data.extraction_examples.edge.bytecode_reference.resolution}</dd></div>
              </dl>
              <div className="extraction-output"><span>输出 method edge</span><code>{data.extraction_examples.edge.output.caller_method_key}<b> → </b>{data.extraction_examples.edge.output.callee_method_key}</code><small>{data.extraction_examples.edge.output.invoke_kind} · multiplicity {data.extraction_examples.edge.output.multiplicity}</small></div>
            </ExtractionCase>
          </div>
          <div className="invocation-examples">
            <header><div><p className="eyebrow">FIVE INVOCATION KINDS</p><h3>其他调用类型的真实记录</h3></div><p>每类展示一个确定性样例；DYNAMIC 仅在 bootstrap method handle 能解析到具体方法时进入闭合图。</p></header>
            <div className="table-scroll"><table><thead><tr><th>kind</th><th>caller</th><th>callee</th><th>line</th><th>resolution</th></tr></thead><tbody>
              {data.samples.call_occurrences.map((row) => <tr key={row.invoke_kind}><td><b>{row.invoke_kind}</b></td><td><code>{row.caller}</code></td><td><code>{row.callee}</code></td><td className="numeric">{row.source_line}</td><td>{row.resolution}</td></tr>)}
            </tbody></table></div>
          </div>
        </section>

        <section id="findings" className="section-block findings">
          <div className="section-heading">
            <div><p className="eyebrow">FINDINGS</p><h2>路径复用高度集中，但不服从 Zipf</h2></div>
            <p>结论来自全部 {integer.format(data.population.nodes)} 个方法节点。零入度节点保留在总体统计中；只有正路径值可进入双对数 rank 曲线。</p>
          </div>
          <div className="claim-grid software-claims">
            <article className="claim-card supported">
              <header><span>supported</span><code>SOFT-PATH-01</code></header>
              <p className="claim-text">最大直接+间接路径入度为 {exact(data.path_counts.maximum)}，路径组合跨越约 {data.path_counts.maximum_log10.toFixed(1)} 个十进数量级。</p>
              <p className="claim-detail">路径数衡量依赖路线的分叉与汇合，不等于独立 caller 数或运行时调用频率。</p>
            </article>
            <article className="claim-card inconclusive">
              <header><span>rejected fit</span><code>SOFT-ZIPF-01</code></header>
              <p className="claim-text">完整正值总体的经验 rank 指数 β={data.rank_shape.ranges[0].models.zipf.free_exponent_beta.toFixed(3)}，远高于 Zipf 的 β=1。</p>
              <p className="claim-detail">固定 1/r 模板在 log₁₀ 空间的 R² 为 {data.rank_shape.ranges[0].models.zipf.fixed_r_squared_log10.toFixed(3)}。</p>
            </article>
            <article className="claim-card exploratory">
              <header><span>negative control</span><code>SOFT-PRIME-01</code></header>
              <p className="claim-text">1/pᵣ 比 1/r 的固定形状误差低 {primeImprovement.toFixed(1)}%，但仍不是充分拟合。</p>
              <p className="claim-detail">素数倒数只是可下降的参考曲线；较小 RMSE 不能推出生成机制与素数有关。</p>
            </article>
          </div>
        </section>

        <section id="rank-shape" className="section-block">
          <div className="section-heading compact">
            <div><p className="eyebrow">RANK–FREQUENCY COMPARISON</p><h2>全部路径入度、Zipf 与素数倒数</h2></div>
            <p>节点按精确的直接+间接路径数降序排列。经验值和参考线都在 log₁₀ 空间比较；每个固定模板只拟合一个垂直截距。</p>
          </div>
          <div className="path-rank-workbench">
            <div className="distribution-tabs" role="group" aria-label="选择比较范围">
              {data.rank_shape.ranges.map((range) => (
                <button key={range.range_id} className={range.range_id === rangeId ? "active" : ""} onClick={() => setRangeId(range.range_id)}>
                  {range.range_id === "all_positive" ? "全部正路径节点" : "路径数最高 1%"}
                </button>
              ))}
            </div>
            <div className="distribution-summary path-rank-summary">
              <article><span>分析节点</span><strong>{integer.format(selected.observation_count)}</strong><p>基于完整总体拟合</p></article>
              <article><span>经验 βrank</span><strong>{zipf.free_exponent_beta.toFixed(3)}</strong><p>Zipf 固定指数为 1</p></article>
              <article><span>Zipf R² / RMSE</span><strong>{zipf.fixed_r_squared_log10.toFixed(3)}</strong><p>{zipf.fixed_rmse_log10.toFixed(3)} decades</p></article>
              <article><span>素数倒数 R² / RMSE</span><strong>{prime.fixed_r_squared_log10.toFixed(3)}</strong><p>{prime.fixed_rmse_log10.toFixed(3)} decades</p></article>
            </div>
            <div className="parameter-guide">
              <header>
                <div><p className="eyebrow">PARAMETER INTERPRETATION</p><h3>这些数值如何理解</h3></div>
                <p>所有拟合都在同一批节点的 log₁₀(rank)–log₁₀(path count) 空间完成，因此本范围内的 R² 与 RMSE 可以直接比较。</p>
              </header>
              <div className="parameter-grid">
                <article>
                  <span>βrank = {zipf.free_exponent_beta.toFixed(3)}</span>
                  <p>自由指数模型为 <code>P(r)=A/r<sup>β</sup></code>。rank 增加 10 倍时，路径入度约缩小 <b>{integer.format(Math.round(rankTenfoldDrop))} 倍</b>。β 越大，头部之后下降越快。</p>
                </article>
                <article>
                  <span>Zipf 固定指数 = 1</span>
                  <p>Zipf 是预先规定的 <code>P(r)=A/r</code>，只有幅度 A 可拟合；rank 增加 10 倍时数值只下降 10 倍。经验 β 与 1 相距很大，因此“幂律形状”不等于“Zipf 定律”。</p>
                </article>
                <article>
                  <span>R²：{zipf.fixed_r_squared_log10.toFixed(3)} vs {prime.fixed_r_squared_log10.toFixed(3)}</span>
                  <p>在 log₁₀ 空间，Zipf 与素数倒数分别解释约 <b>{(100 * zipf.fixed_r_squared_log10).toFixed(1)}%</b> 和 <b>{(100 * prime.fixed_r_squared_log10).toFixed(1)}%</b> 的变化。越接近 1 越好；这里两者都只解释约一半。</p>
                </article>
                <article>
                  <span>RMSE：{zipf.fixed_rmse_log10.toFixed(3)} vs {prime.fixed_rmse_log10.toFixed(3)} decades</span>
                  <p>1 decade 等于 10 倍。两项误差的量级分别相当于约 <b>{zipfErrorFactor.toFixed(1)} 倍</b> 和 <b>{primeErrorFactor.toFixed(1)} 倍</b>；越小越好，误差可发生在预测值上方或下方。</p>
                </article>
              </div>
              <aside>
                <b>综合判断</b>
                <p>放开指数后，经验模型的 R²={zipf.free_r_squared_log10.toFixed(3)}、RMSE={zipf.free_rmse_log10.toFixed(3)} decades（约 {freeErrorFactor.toFixed(1)} 倍）。因此数据接近一个陡峭的 rank 幂律，但不接近指数固定为 1 的 Zipf；1/pᵣ 只是比 1/r 略陡，所以数值上稍好，不能据此推断质数规律。</p>
              </aside>
            </div>
            <figure className="distribution-chart path-rank-chart">
              <figcaption><b>方法路径入度 rank–frequency</b><span>网页按 log-rank 抽样显示；拟合使用全部观测</span></figcaption>
              <ResponsiveContainer width="100%" height={520}>
                <ComposedChart data={selected.points} margin={{ top: 24, right: 34, bottom: 42, left: 32 }}>
                  <CartesianGrid strokeDasharray="3 5" />
                  <XAxis type="number" dataKey="log10_rank" domain={[0, "dataMax"]} tickFormatter={(v) => Number(v).toFixed(1)} label={{ value: "log₁₀(rank r)", position: "insideBottom", offset: -22, fontSize: 14 }} />
                  <YAxis type="number" domain={[Math.floor(selected.minimum_log10), Math.ceil(selected.maximum_log10)]} tickFormatter={(v) => Number(v).toFixed(0)} label={{ value: "log₁₀(直接+间接路径入度)", angle: -90, position: "insideLeft", fontSize: 14 }} />
                  <Tooltip formatter={(value, name) => [Number(value).toFixed(3), legend(String(name))]} labelFormatter={(_, payload) => payload?.[0] ? `rank ${integer.format(payload[0].payload.rank)}` : ""} />
                  <Legend verticalAlign="top" formatter={(value) => legend(String(value))} />
                  <Scatter name="empirical_log10" dataKey="empirical_log10" fill="#20495f" line={{ stroke: "#20495f", strokeWidth: 2 }} shape="circle" />
                  <Line name="zipf_log10" dataKey="zipf_log10" stroke="#9d493d" strokeWidth={3} dot={false} />
                  <Line name="reciprocal_prime_log10" dataKey="reciprocal_prime_log10" stroke="#c07a2b" strokeWidth={3} strokeDasharray="9 5" dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
              <p className="chart-method">第 r 个素数 pᵣ 随 r 增长，不能直接与下降的 rank 曲线比较，因此使用 1/pᵣ。由 pᵣ≈r ln r，它比 1/r 略陡，但当前经验曲线的 β≈{zipf.free_exponent_beta.toFixed(2)}，仍明显更陡。</p>
            </figure>
          </div>
        </section>

        <section id="top-methods" className="section-block">
          <div className="section-heading compact">
            <div><p className="eyebrow">METHOD LEDGER</p><h2>路径入度最高的方法</h2></div>
            <p>直接 occurrence 是入边 multiplicity 之和；间接路径保留每条上游路线及沿途重复调用位置的组合。</p>
          </div>
          <div className="method-ledger table-scroll">
            <table>
              <thead><tr><th>rank</th><th>method</th><th>module</th><th className="numeric">直接 caller pair</th><th className="numeric">直接 occurrence</th><th className="numeric">间接路径</th><th className="numeric">全部路径</th></tr></thead>
              <tbody>{data.top_nodes.slice(0, 30).map((row) => (
                <tr key={row.node_id}>
                  <td className="numeric">{row.rank}</td><td><code>{row.label}</code></td><td>{row.module}</td>
                  <td className="numeric">{integer.format(row.direct_unique_callers)}</td>
                  <td className="numeric">{integer.format(row.direct_call_occurrences)}</td>
                  <td className="numeric">{exact(row.indirect_incoming_paths)}</td>
                  <td className="numeric"><b>{exact(row.all_incoming_paths)}</b></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <aside className="path-rank-conclusion method-observation">
            <b>关键观察</b>
            <p>排名第一的解析器辅助方法只有 {data.top_nodes[0].direct_unique_callers} 个直接 caller pair，却累积了 {exact(data.top_nodes[0].all_incoming_paths)} 条路径。这说明路径入度会放大生成式解析代码中的分叉组合；它适合识别结构性汇聚点，不宜解释为实际使用次数。</p>
          </aside>
        </section>

        <section id="method" className="section-block methods">
          <div className="section-heading">
            <div><p className="eyebrow">METHOD &amp; BOUNDARY</p><h2>精确计数与循环终止规则</h2></div>
            <p>所有节点均输出到可重建的 Parquet 指标表；网页仅发布完整总体统计、拟合曲线的确定性显示点和前 100 个高路径节点。</p>
          </div>
          <div className="method-grid">
            <article><span>01 · direct pair</span><p>每个不同 caller→callee 记一次，忽略同一 pair 的重复调用位置。</p></article>
            <article><span>02 · occurrence</span><p>对 multiplicity 求和，每个重复字节码调用位置都保留为一条直接路径选择。</p></article>
            <article><span>03 · indirect path</span><p>沿非循环节点传播；经过多条边时 multiplicity 相乘，不同路线相加。</p></article>
            <article><span>04 · cycle boundary</span><p>到达循环 SCC 时计入该次到达，但不再从 SCC 继续扩展；self-loop 同样终止。</p></article>
          </div>
          <p className="path-rank-references">参考：<a href={data.references.zipf} target="_blank" rel="noreferrer">Zipf’s law ↗</a><span> · </span><a href={data.references.nth_prime} target="_blank" rel="noreferrer">NIST DLMF：素数渐近性质 ↗</a></p>
        </section>
      </main>
      <footer><p>Knowledge Reuse Research · {data.snapshot_id}</p><p>exact bytecode-reference graph · cycle-bounded paths</p></footer>
      {sampleKey && <SampleExplorer data={data} sampleKey={sampleKey} onClose={() => setSampleKey(null)} />}
    </>
  );
}

type SampleKey = keyof OpenJdkReuseReport["samples"];

function ReportMetric({ value, label, detail, onClick }: { value: number; label: string; detail: string; onClick: () => void }) {
  return <button className="metric-card" onClick={onClick}><span className="metric-link">OPEN SAMPLE TABLE ↗</span><strong>{integer.format(value)}</strong><b>{label}</b><small>{detail}</small></button>;
}

function ExtractionCase({ title, label, path, lines, source, highlightLines, children }: { title: string; label: string; path: string; lines: [number, number]; source: string; highlightLines: number[]; children: React.ReactNode }) {
  return <article className="extraction-case">
    <header><div><p className="eyebrow">{label}</p><h3>{title}</h3></div><small>{path}<br />L{lines[0]}–{lines[1]}</small></header>
    <pre className="source-code" aria-label={`${title} 源代码`}>
      {source.split("\n").map((text, index) => {
        const line = lines[0] + index;
        return <span key={line} className={highlightLines.includes(line) ? "highlight" : ""}><i>{line}</i><code>{text || " "}</code></span>;
      })}
    </pre>
    {children}
  </article>;
}

function SampleExplorer({ data, sampleKey, onClose }: { data: OpenJdkReuseReport; sampleKey: SampleKey; onClose: () => void }) {
  const titles: Record<SampleKey, string> = {
    method_nodes: "方法节点样例",
    call_pairs: "调用 pair 样例",
    call_occurrences: "调用 occurrence 样例",
    positive_path_nodes: "正路径入度节点样例",
    zero_path_nodes: "零路径入度节点样例",
    cycle_boundary_nodes: "循环边界节点样例",
  };
  const metricRows = sampleKey === "positive_path_nodes" || sampleKey === "zero_path_nodes" || sampleKey === "cycle_boundary_nodes"
    ? data.samples[sampleKey] as OpenJdkMetricSample[]
    : null;
  return <div className="explorer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="explorer-panel sample-explorer" role="dialog" aria-modal="true" aria-labelledby="sample-title">
      <header><div><p className="eyebrow">FULL-POPULATION SAMPLE</p><h2 id="sample-title">{titles[sampleKey]}</h2></div><button className="close-button" onClick={onClose} aria-label="关闭样例">×</button></header>
      <p className="sample-contract">这些记录来自完整分析输出，用于解释统计单位，不用于估算总体。</p>
      {sampleKey === "method_nodes" && <div className="table-scroll"><table><thead><tr><th>method key</th><th>flags</th><th>source</th><th className="numeric">直接 occurrence</th><th className="numeric">全部路径</th></tr></thead><tbody>{data.samples.method_nodes.map((row) => <tr key={row.node_id}><td><code>{row.method_key}</code></td><td>{row.flags.join(", ")}</td><td>{row.source_file}{row.first_line ? `:${row.first_line}–${row.last_line}` : ""}</td><td className="numeric">{integer.format(row.direct_call_occurrences)}</td><td className="numeric">{exact(row.all_incoming_paths)}</td></tr>)}</tbody></table></div>}
      {sampleKey === "call_pairs" && <div className="table-scroll"><table><thead><tr><th>caller</th><th>callee</th><th>relation</th><th className="numeric">multiplicity</th></tr></thead><tbody>{data.samples.call_pairs.map((row, index) => <tr key={index}><td><code>{row.caller}</code></td><td><code>{row.callee}</code></td><td>{row.relation}</td><td className="numeric">{integer.format(row.multiplicity)}</td></tr>)}</tbody></table></div>}
      {sampleKey === "call_occurrences" && <div className="table-scroll"><table><thead><tr><th>kind</th><th>caller</th><th>callee</th><th>line</th><th>resolution</th></tr></thead><tbody>{data.samples.call_occurrences.map((row) => <tr key={row.invoke_kind}><td><b>{row.invoke_kind}</b></td><td><code>{row.caller}</code></td><td><code>{row.callee}</code></td><td className="numeric">{row.source_line}</td><td>{row.resolution}</td></tr>)}</tbody></table></div>}
      {metricRows && <div className="table-scroll"><table><thead><tr><th>method</th><th>module</th><th className="numeric">caller pair</th><th className="numeric">直接 occurrence</th><th className="numeric">间接路径</th><th className="numeric">全部路径</th></tr></thead><tbody>{metricRows.map((row) => <tr key={row.node_id}><td><code>{row.label}</code></td><td>{row.module}</td><td className="numeric">{integer.format(row.direct_unique_callers)}</td><td className="numeric">{integer.format(row.direct_call_occurrences)}</td><td className="numeric">{exact(row.indirect_incoming_paths)}</td><td className="numeric"><b>{exact(row.all_incoming_paths)}</b></td></tr>)}</tbody></table></div>}
    </section>
  </div>;
}

function legend(value: string) {
  if (value === "empirical_log10") return "经验路径曲线";
  if (value === "zipf_log10") return "Zipf A/r";
  if (value === "reciprocal_prime_log10") return "素数倒数 A/pᵣ";
  return value;
}
