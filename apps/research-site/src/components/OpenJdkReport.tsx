import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Bar,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { loadOpenJdkReuseReport, loadReuseTheoremReport } from "../data";
import type { OpenJdkMetricSample, OpenJdkReuseReport, ReuseTheoremReport } from "../types";

const integer = new Intl.NumberFormat("en-US");
const exact = (value: string) => BigInt(value).toLocaleString("en-US");

export default function OpenJdkReport() {
  const [data, setData] = useState<OpenJdkReuseReport | null>(null);
  const [theorems, setTheorems] = useState<ReuseTheoremReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rangeId, setRangeId] = useState<"all_positive" | "top_1pct">("all_positive");
  const [sampleKey, setSampleKey] = useState<SampleKey | null>(null);

  useEffect(() => {
    Promise.all([loadOpenJdkReuseReport(), loadReuseTheoremReport()])
      .then(([reuse, theoremTests]) => { setData(reuse); setTheorems(theoremTests); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const selected = useMemo(
    () => data?.rank_shape.ranges.find((range) => range.range_id === rangeId),
    [data, rangeId],
  );

  if (error) return <main className="fatal"><h1>OpenJDK 报告加载失败</h1><p>{error}</p></main>;
  if (!data || !selected || !theorems) return <main className="fatal"><p className="eyebrow">LOADING OPENJDK REPORT</p><h1>正在装载方法调用图统计…</h1></main>;

  const zipf = selected.models.zipf;
  const prime = selected.models.reciprocal_prime;
  const paperRange = data.paper_reuse.rank_shape.ranges[0];
  const paperZipf = paperRange.models.zipf;
  const paperErrorFactor = 10 ** paperZipf.fixed_rmse_log10;
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
            <a href="#paper-reuse">论文口径</a>
            <a href="#theorem-tests">理论检验</a>
            <a href="#rank-shape">路径口径</a>
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
              以 JVM method declaration 为节点，以已解析的字节码调用位置为边。本报告先按 Veldhuizen 的论文口径统计方法收到的静态引用次数，再与保留重复调用位置的直接+间接路径入度对照。
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
            <div><p className="eyebrow">FINDINGS</p><h2>直接引用近似 Zipf，路径组合不是</h2></div>
            <p>结论来自同一批 {integer.format(data.population.nodes)} 个方法节点。两种曲线的差异来自计算定义，而不是语料变化。</p>
          </div>
          <div className="claim-grid software-claims">
            <article className="claim-card supported">
              <header><span>supported</span><code>SOFT-REUSE-ZIPF-01</code></header>
              <p className="claim-text">按论文的静态引用计数口径，经验 β={paperZipf.free_exponent_beta.toFixed(3)}，接近 Zipf 的 β=1。</p>
              <p className="claim-detail">固定 1/r 模板达到 R²={paperZipf.fixed_r_squared_log10.toFixed(3)}、RMSE={paperZipf.fixed_rmse_log10.toFixed(3)} decades。</p>
            </article>
            <article className="claim-card inconclusive">
              <header><span>rejected fit</span><code>SOFT-ZIPF-01</code></header>
              <p className="claim-text">完整正值总体的经验 rank 指数 β={data.rank_shape.ranges[0].models.zipf.free_exponent_beta.toFixed(3)}，远高于 Zipf 的 β=1。</p>
              <p className="claim-detail">固定 1/r 模板在 log₁₀ 空间的 R² 为 {data.rank_shape.ranges[0].models.zipf.fixed_r_squared_log10.toFixed(3)}。</p>
            </article>
            <article className="claim-card exploratory">
              <header><span>metric boundary</span><code>SOFT-COMPARE-01</code></header>
              <p className="claim-text">最大路径入度为 {exact(data.path_counts.maximum)}；路径组合与论文中的直接引用次数回答不同问题。</p>
              <p className="claim-detail">直接引用衡量静态复用；路径入度放大上游分叉与汇合，不能互换为“number of uses”。</p>
            </article>
          </div>
        </section>

        <section id="paper-reuse" className="section-block">
          <div className="section-heading compact">
            <div><p className="eyebrow">VELDHUIZEN 2005 · REUSE AND ZIPF'S LAW</p><h2>按论文“静态引用次数”重画</h2></div>
            <p>论文遍历 Unix 安装中的可执行文件与 shared objects，统计每个库子程序被引用多少次，按次数降序排列，并在双对数坐标上与 <code>c·n⁻¹</code> 比较。这里逐项映射到 JDK 方法与已解析字节码调用点。</p>
          </div>
          <div className="path-rank-workbench paper-reuse-workbench">
            <div className="distribution-summary path-rank-summary">
              <article><span>被引用方法</span><strong>{integer.format(data.paper_reuse.population.referenced_methods)}</strong><p>零引用方法不进入 log–log 曲线</p></article>
              <article><span>静态引用</span><strong>{integer.format(data.paper_reuse.population.references)}</strong><p>重复 bytecode call site 分别计数</p></article>
              <article><span>经验 βrank</span><strong>{paperZipf.free_exponent_beta.toFixed(3)}</strong><p>接近论文 Zipf 基准 β=1</p></article>
              <article><span>Zipf R² / RMSE</span><strong>{paperZipf.fixed_r_squared_log10.toFixed(3)}</strong><p>{paperZipf.fixed_rmse_log10.toFixed(3)} decades ≈ {paperErrorFactor.toFixed(2)}×</p></article>
            </div>
            <section className="paper-logic" aria-labelledby="paper-logic-title">
              <header>
                <div><p className="eyebrow">THEORY → OBSERVATION</p><h3 id="paper-logic-title">论文为什么会预期一条 Zipf 曲线</h3></div>
                <p>这不是“先画 rank chart 再猜规律”。论文先把软件库理解为对程序的压缩，再从组件标识成本建立约束，最后用 Unix 软件语料检查真实复用频率是否接近 <code>1/n</code>。</p>
              </header>
              <div className="paper-theory-chain">
                <article><span>01 · 压缩视角</span><p>程序来自某个问题域；库把重复代码替换为组件引用。问题域熵 <code>H</code> 越低，可复用的理论空间越大，最多约有 <code>1−H</code> 的代码可由库提供。</p></article>
                <article><span>02 · 标识成本</span><p>组件按使用频率排序。要唯一解码第 <code>n</code> 个组件，其自分隔标识至少需要约 <code>log⁺n</code> bits；库越大，长尾组件越贵。</p></article>
                <article><span>03 · 编码预算</span><p>令 <code>λ(n)</code> 为单位压缩程序中第 n 个组件的期望引用数。所有引用必须装进程序，因此 <code>Σ λ(n)log⁺n ≤ 1</code>，并导出渐近上界 <code>λ(n) ≺ 1/(n log n log⁺n)</code>。</p></article>
                <article><span>04 · 经验假说</span><p>论文进一步主张：库在“少写代码”的选择压力下接近最大熵配置，于是实际 rank–frequency 可能呈 <code>λ(n)≈c/n</code>。Figure 1 检查的是曲线形状，并不单独证明这个形成机制。</p></article>
              </div>
            </section>
            <div className="paper-procedure-heading">
              <div><p className="eyebrow">EMPIRICAL PROCEDURE</p><h3>论文如何从二进制得到 Figure 1</h3></div>
              <p>下列四步是论文的实证计算流程；右侧 JDK 图严格复用“组件—静态引用—降序 rank—双对数比较”这条主线。</p>
            </div>
            <div className="paper-method-map" aria-label="论文方法到 OpenJDK 的计算映射">
              <article><span>01 · 扫描语料</span><p>论文定位系统中的 executable objects 与 shared objects；Linux 还解码 PLT/GOT，并把 x86 指令纳入组件总体。</p></article>
              <article><span>02 · 解析静态引用</span><p>用 <code>nm</code>、<code>objdump</code> 或反汇编恢复 relocatable symbol / subroutine reference。这里对应已解析的 bytecode invocation call site。</p></article>
              <article><span>03 · 按组件计数</span><p>对每个组件汇总直接引用：<code>U(v)=Σ multiplicity(u,v)</code>。不做传递闭包，也不引入本报告的路径入度。</p></article>
              <article><span>04 · 排名并比较</span><p>按 U(v) 降序得到 rank n；在双对数坐标画 <code>(n,U)</code>，再与斜率 −1 的虚线族 <code>c/n</code> 比较。</p></article>
            </div>
            <div className="paper-corpus-ledger table-scroll">
              <table><thead><tr><th>论文语料</th><th className="numeric">object files</th><th className="numeric">components</th><th>读取方式与边界</th></tr></thead><tbody>
                <tr><td>Linux / SuSE</td><td className="numeric">12,136</td><td className="numeric">455,716</td><td>反汇编 executable objects；解码 PLT/GOT；包含 x86 指令与约五十万 subroutines。</td></tr>
                <tr><td>SunOS</td><td className="numeric">23,774</td><td className="numeric">110,306</td><td>shared objects 的 relocatable symbols；未含机器指令，绘图从 rank 50 开始。</td></tr>
                <tr><td>Mac OS X</td><td className="numeric">2,334</td><td className="numeric">37,677</td><td>shared objects 的 relocatable symbols；未含机器指令，绘图从 rank 50 开始。</td></tr>
              </tbody></table>
            </div>
            <div className="paper-figure-comparison">
              <figure className="paper-original-figure">
                <figcaption><b>论文 Figure 1 · 三套 Unix 软件语料</b><span>原图：组件使用频率与 <code>c·n⁻¹</code> 虚线族</span></figcaption>
                <a href={data.references.paper} target="_blank" rel="noreferrer"><img src="/papers/cs-0508023/figure-1.png" alt="Veldhuizen 论文 Figure 1：Linux、SunOS 与 Mac OS X 的组件使用频率 rank-frequency 双对数图" /></a>
                <p className="chart-method">原图给出视觉上的 Zipf-like 证据，没有报告 β、R² 或 RMSE。尾部的台阶来自大量只被少量引用的 subroutines。</p>
              </figure>
              <figure className="distribution-chart path-rank-chart paper-jdk-figure">
                <figcaption><b>OpenJDK 28+13 · method 复现</b><span>同为静态直接引用、降序 rank 与双对数坐标</span></figcaption>
                <ResponsiveContainer width="100%" height={440}>
                  <ComposedChart data={paperRange.points} margin={{ top: 24, right: 24, bottom: 42, left: 24 }}>
                    <CartesianGrid strokeDasharray="3 5" />
                    <XAxis type="number" dataKey="log10_rank" domain={[0, "dataMax"]} tickFormatter={(v) => `10^${Number(v).toFixed(0)}`} label={{ value: "方法复用排名 n（log₁₀）", position: "insideBottom", offset: -22, fontSize: 13 }} />
                    <YAxis type="number" domain={[Math.floor(paperRange.minimum_log10), Math.ceil(paperRange.maximum_log10)]} tickFormatter={(v) => `10^${Number(v).toFixed(0)}`} label={{ value: "静态引用次数 U（log₁₀）", angle: -90, position: "insideLeft", fontSize: 13 }} />
                    <Tooltip formatter={(value, name) => [Number(value).toFixed(3), legend(String(name))]} labelFormatter={(_, payload) => payload?.[0] ? `rank ${integer.format(payload[0].payload.rank)}` : ""} />
                    <Legend verticalAlign="top" formatter={(value) => legend(String(value))} />
                    <Scatter name="paper_empirical_log10" dataKey="empirical_log10" fill="#1f6b53" line={{ stroke: "#1f6b53", strokeWidth: 2 }} shape="circle" />
                    <Line name="paper_zipf_log10" dataKey="zipf_log10" stroke="#9d493d" strokeWidth={3} strokeDasharray="9 5" dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
                <p className="chart-method">固定 Zipf 线只拟合垂直幅度 c。本研究另算 β={paperZipf.free_exponent_beta.toFixed(3)}、R²={paperZipf.fixed_r_squared_log10.toFixed(3)}、RMSE={paperZipf.fixed_rmse_log10.toFixed(3)} decades；{integer.format(data.paper_reuse.population.singleton_methods)} 个单次引用方法形成尾部台阶。</p>
              </figure>
            </div>
            <div className="paper-comparison-ledger table-scroll">
              <table><thead><tr><th>比较项</th><th>论文 Figure 1</th><th>OpenJDK 图</th><th>解释</th></tr></thead><tbody>
                <tr><td>component</td><td>library subroutine；Linux 另含 x86 instruction</td><td>JVM method declaration</td><td>JDK 单位更窄，避免把指令与方法混为同类组件。</td></tr>
                <tr><td>use</td><td>目标文件中的静态 reference</td><td>已解析 bytecode invocation call site</td><td>两者都不是运行时执行频率；重复静态位置分别计数。</td></tr>
                <tr><td>rank 起点</td><td>Linux 从 1；SunOS/Mac 从 50</td><td>从 1</td><td>JDK 没有“遗漏高频机器指令”的对应缺口，不需要 offset。</td></tr>
                <tr><td>结论强度</td><td>三套曲线与 <code>c/n</code> 视觉对照</td><td>同口径曲线 + β/R²/RMSE</td><td>两图都支持形状近似；都不能仅凭曲线证明最大熵因果机制。</td></tr>
              </tbody></table>
            </div>
            <aside className="paper-scope-note">
              <b>可比边界</b>
              <p>论文的 Linux 数据还包含 x86 指令，SunOS 与 Mac OS X 因遗漏这类高频组件而从 n=50 起排 rank。本 JDK 曲线的组件单位始终是 method，不存在对应的“遗漏指令”层，因此从 n=1 开始且不作 offset。这里比较静态引用分布的形状，不比较运行时执行频率，也不声称复现论文三套 Unix 原始数据。</p>
            </aside>
            <section className="paper-prime-conclusion" aria-labelledby="paper-prime-title">
              <header>
                <div><p className="eyebrow">PAPER CONCLUSION · PRIME ANALOGIES</p><h3 id="paper-prime-title">论文使用了素数概念，但没有建立新的素数分布</h3></div>
                <p>素数在论文中承担理论类比与研究启发的作用，不是软件复用频率的直接生成机制。</p>
              </header>
              <div className="prime-analogy-grid">
                <article><span>01</span><p><b>素数无限多</b><i>↔</i>有用软件组件可能无限多</p></article>
                <article><span>02</span><p><b>素数作为整数因子的频率</b><i>↔</i>组件在程序中的复用频率</p></article>
                <article><span>03</span><p><b>第 n 个素数的大小</b><i>↔</i>第 n 个组件的规模</p></article>
                <article><span>04</span><p><b>整数所含素因子的数量</b><i>↔</i>程序使用的组件数量</p></article>
              </div>
              <aside>
                <span>论文真正拟合和讨论的组件复用分布</span>
                <strong>λ(n) ≈ c / n</strong>
                <p>这是 Zipf-like 复用分布。因而，本报告路径章节中的 <code>1/pᵣ</code> 只能作为额外的负对照，不能表述为论文提出的软件复用模型。</p>
              </aside>
            </section>
            <section className="paper-conclusion-comparison" aria-labelledby="paper-comparison-title">
              <header>
                <div><p className="eyebrow">PAPER CONCLUSIONS × OPENJDK EVIDENCE</p><h3 id="paper-comparison-title">论文结论与 JDK 统计的比较</h3></div>
                <p>JDK 调用图能直接检验“组件引用频率的形状”，但不能仅凭一次静态快照识别最大熵机制、估计问题域熵 H，或证明无限性命题。</p>
              </header>
              <div className="table-scroll">
                <table>
                  <thead><tr><th>论文结论</th><th>JDK 统计结果</th><th>判断</th></tr></thead>
                  <tbody>
                    <tr>
                      <td>组件按使用频率排序后呈 <code>λ(n)≈c/n</code> 的 Zipf-like 曲线。</td>
                      <td>{integer.format(data.paper_reuse.population.referenced_methods)} 个被引用方法的 β={paperZipf.free_exponent_beta.toFixed(3)}；固定 <code>1/r</code> 的 R²={paperZipf.fixed_r_squared_log10.toFixed(3)}、RMSE={paperZipf.fixed_rmse_log10.toFixed(3)} decades。</td>
                      <td><span className="evidence-status supported">支持</span></td>
                    </tr>
                    <tr>
                      <td>程序员追求更短的代码，使库朝最大熵配置演化；Zipf 曲线是这种压力的结果。</td>
                      <td>JDK 数据复现了曲线形状，但单次观察性快照不能区分最大熵、API 设计惯例、代码生成或其他形成机制。</td>
                      <td><span className="evidence-status bounded">形状一致，机制未验证</span></td>
                    </tr>
                    <tr>
                      <td>问题域熵参数 H 限制复用潜力：最多约 <code>1−H</code> 的代码可来自库；H 越低，越可能出现强复用。</td>
                      <td>调用引用数不包含“未压缩程序大小”、组件带来的代码节省或问题域程序分布，不能从当前 graph 反推 H。</td>
                      <td><span className="evidence-status untested">不可由本数据检验</span></td>
                    </tr>
                    <tr>
                      <td>任何有限库都不完备；随着问题域扩展，总会存在更多能缩短程序的有用组件。</td>
                      <td>package 留出实验在 5/5 个折发现正净节省 opcode macro；跨版本比较从 JDK 17 到 28 观察到 method 净增 {integer.format(theorems.phase_5_cross_version.delta.net_methods)}，且保留 caller 已调用新增组件。</td>
                      <td><span className="evidence-status bounded">有限支持；无限性未证明</span></td>
                    </tr>
                    <tr>
                      <td>组件规模、使用次数与标识成本受理论界限约束；程序使用的组件数量可能呈 Erdős–Kac 式正态行为。</td>
                      <td>以 classfile 为 program 并按大小分层后，cross-class 组件数 skew={theorems.phase_3_erdos_kac.scopes.cross_class.skewness.toFixed(3)}、Q–Q R²={theorems.phase_3_erdos_kac.scopes.cross_class.qq_r_squared.toFixed(3)}，未通过预注册正态判据；use–size Spearman ρ={theorems.phase_4_component_size.spearman_log_use_vs_log_size.toFixed(3)}。</td>
                      <td><span className="evidence-status bounded">正态近似不支持；界限仅代理检验</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <aside><b>综合结论</b><p>OpenJDK 结果支持“库组件的静态引用频率近似 Zipf”；跨版本增长和留出净节省为有限库不完备提供了探索性、有限证据；条件组件数则不支持本次操作化下的 Erdős–Kac 正态近似。它们仍不构成对无限性、最大熵机制或 Kolmogorov complexity 命题的证明。路径入度 β={data.rank_shape.ranges[0].models.zipf.free_exponent_beta.toFixed(3)} 说明指标定义也会显著改变分布。</p></aside>
            </section>
            <p className="path-rank-references">论文原文：<a href={data.references.paper} target="_blank" rel="noreferrer">Veldhuizen, 2005, arXiv:cs/0508023v3 ↗</a></p>
          </div>
        </section>

        <TheoryTests data={theorems} />

        <section id="rank-shape" className="section-block">
          <div className="section-heading compact">
            <div><p className="eyebrow">PATH METRIC · SEPARATE ANALYSIS</p><h2>路径入度、Zipf 与素数倒数</h2></div>
            <p>这一节保留原先的结构性路径指标，但不再把它称为论文的 reuse count。节点按精确的直接+间接路径数降序排列；每个固定模板只拟合一个垂直截距。</p>
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

function TheoryTests({ data }: { data: ReuseTheoremReport }) {
  const normality = data.phase_3_erdos_kac.scopes.cross_class;
  const qq = normality.qq_points.map((point) => ({
    ...point,
    normal_reference: point.normal_quantile,
  }));
  const component = data.phase_4_component_size;
  const componentPoints = component.binned_points.map((point) => ({
    log_rank: Math.log10(point.rank_geometric_mean),
    log_uses: Math.log10(point.median_uses),
    log_size: Math.log10(point.median_bytecode_length),
  }));
  const mdl = data.phase_4_mdl_incompleteness;
  const versions = data.phase_5_cross_version;
  const older = versions.snapshots[0];
  const newer = versions.snapshots[1];

  return <section id="theorem-tests" className="section-block theorem-tests">
    <div className="section-heading">
      <div><p className="eyebrow">PAPER CLAIMS · JDK OBSERVABLES</p><h2>从论文命题到可观测的 JDK 指标</h2></div>
      <p>Figure 1 只检验复用频率的形状。论文还讨论“每个程序使用多少组件”“有限库是否仍遗漏有用组件”，以及组件规模与标识成本的关系。下面先把抽象命题翻译为 JDK 字节码中可计算的代理量，再报告证据边界。</p>
    </div>

    <section className="claim-test-map" aria-labelledby="claim-test-map-title">
      <header><div><p className="eyebrow">OPERATIONALIZATION</p><h3 id="claim-test-map-title">三个检验分别在问什么</h3></div><p>这些不是论文原始 Unix 数据的复算，而是用同一组理论命题组织 OpenJDK 证据。代理量与原命题不等价，所以每项都保留“能说明什么 / 不能说明什么”。</p></header>
      <div>
        <article><span>组件数是否近似正态</span><p><b>论文类比：</b>整数的素因子数近似正态，因此一个程序使用的库组件数也可能呈 Erdős–Kac 式形状。</p><p><b>JDK 代理：</b>把一个 classfile 当作 program，计数其引用的不同外部 method；按 classfile size 的 20 个分位层标准化后做 Q–Q 检查。</p></article>
        <article><span>有限方法词汇是否不完备</span><p><b>论文命题：</b>对足够丰富的问题域，任何有限库之外仍可能存在能缩短程序的有用组件。</p><p><b>JDK 代理：</b>只在训练 package 中发现重复 opcode 片段，再到未见 package 检查：扣除定义、引用与引用 class 成本后是否仍净省 bytes。</p></article>
        <article><span>新组件是否持续出现并被采用</span><p><b>论文命题：</b>问题域扩展会继续产生有用组件。</p><p><b>JDK 代理：</b>比较官方 JDK 17 与 28 二进制快照，观察 method 增减，并检查旧版本已存在的 caller 是否开始引用新增 method。</p></article>
      </div>
      <aside><b>为什么没有直接复刻论文 Figure 4</b><p>Figure 4 以独立 executable/RPM 作为 program，并研究“软件规模—不同库子程序数”及其饱和区间。本分析只有 JMOD 内的 classfile 单元，也没有论文原始逐程序数据，因此采用条件 Q–Q 代理；它能反驳当前操作化下的正态形状，但不能改写论文原数据的结论。</p></aside>
    </section>

    <div className="theorem-verdicts">
      <article className="claim-card inconclusive"><header><span>不支持</span><code>COMPONENT-COUNT</code></header><p className="claim-text">条件化后的组件数不符合预注册正态形状。</p><p>cross-class：skew={normality.skewness.toFixed(3)}、excess kurtosis={normality.excess_kurtosis.toFixed(3)}、Q–Q R²={normality.qq_r_squared.toFixed(3)}；三个阈值均未通过。</p></article>
      <article className="claim-card exploratory"><header><span>探索性支持</span><code>HELD-OUT-MDL</code></header><p className="claim-text">5/5 个 package 留出折均发现正净节省 opcode macro。</p><p>{integer.format(mdl.eligible_method_count)} 个候选方法；各折最佳值的中位数为 {integer.format(mdl.median_best_heldout_net_savings_bytes)} bytes。尚未验证 operand、stack contract 与 verifier-safe rewriting。</p></article>
      <article className="claim-card supported"><header><span>有限支持</span><code>CROSS-VERSION</code></header><p className="claim-text">JDK 17→28 的方法词汇净增 {integer.format(versions.delta.net_methods)}。</p><p>新增 {integer.format(versions.delta.added_methods)}、移除 {integer.format(versions.delta.removed_methods)}；保留 caller 对 {integer.format(versions.new_component_adoption.added_methods_referenced_from_retained_callers)} 个新增 callee 产生调用。</p></article>
    </div>

    <div className="theorem-chart-grid">
      <figure className="distribution-chart">
        <figcaption><b>条件组件数 Q–Q</b><span>classfile 作为 program；按大小 20 分位分层标准化</span></figcaption>
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={qq} margin={{ top: 18, right: 24, bottom: 34, left: 18 }}>
            <CartesianGrid strokeDasharray="3 5" />
            <XAxis type="number" dataKey="normal_quantile" label={{ value: "标准正态分位数", position: "insideBottom", offset: -18 }} />
            <YAxis type="number" dataKey="observed_z" label={{ value: "观测 z", angle: -90, position: "insideLeft" }} />
            <Tooltip formatter={(value) => Number(value).toFixed(3)} />
            <Scatter dataKey="observed_z" name="观测" fill="#20495f" />
            <Line dataKey="normal_reference" name="理想正态" stroke="#9d493d" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="chart-method">组件数定义为每个 classfile 引用的不同外部 method。结果右偏且厚尾；cross-package 与 cross-module 的偏离更大，因此本快照不支持 Erdős–Kac 式正态近似。</p>
      </figure>

      <figure className="distribution-chart">
        <figcaption><b>组件使用次数与规模</b><span>STATIC/SPECIAL 精确目标；对数 rank bins</span></figcaption>
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={componentPoints} margin={{ top: 18, right: 24, bottom: 34, left: 18 }}>
            <CartesianGrid strokeDasharray="3 5" />
            <XAxis type="number" dataKey="log_rank" label={{ value: "log₁₀(use rank)", position: "insideBottom", offset: -18 }} />
            <YAxis type="number" label={{ value: "log₁₀(value)", angle: -90, position: "insideLeft" }} />
            <Tooltip formatter={(value) => Number(value).toFixed(3)} />
            <Legend />
            <Line dataKey="log_uses" name="median uses" stroke="#1f6b53" dot={false} />
            <Line dataKey="log_size" name="median bytecode size" stroke="#c07a2b" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="chart-method">use 与 Code 大小几乎无单调关系（Spearman ρ={component.spearman_log_use_vs_log_size.toFixed(3)}）。{(100 * component.gross_savings_meets_log2_rank_fraction).toFixed(1)}% 满足粗略 savings ≥ log₂(rank) 下界，但 JVM 实际标识经 class-local constant pool 编码，不能把该比例解释成理论证明。</p>
      </figure>

      <figure className="distribution-chart">
        <figcaption><b>package 留出净节省</b><span>每折最佳 opcode macro；已扣定义、引用与引用 class 成本</span></figcaption>
        <ResponsiveContainer width="100%" height={330}>
          <ComposedChart data={mdl.folds} margin={{ top: 18, right: 24, bottom: 34, left: 18 }}>
            <CartesianGrid strokeDasharray="3 5" />
            <XAxis dataKey="fold" label={{ value: "held-out fold", position: "insideBottom", offset: -18 }} />
            <YAxis label={{ value: "net bytes", angle: -90, position: "insideLeft" }} />
            <Tooltip formatter={(value) => integer.format(Number(value))} />
            <Bar dataKey="best_heldout_net_savings_bytes" name="best net savings" fill="#1f6b53" />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="chart-method">这是反例搜索：若训练数据发现的片段在未见 package 仍带来正净节省，则现有 method vocabulary 对这个代理编码并不完备。结论仅为探索性，不能自动提升为合法 Java API。</p>
      </figure>

      <article className="version-comparison">
        <header><p className="eyebrow">CROSS-VERSION · LONGITUDINAL</p><h3>{older.label} → {newer.label}</h3></header>
        <dl>
          <div><dt>methods</dt><dd>{integer.format(older.methods)} → {integer.format(newer.methods)} <b>+{versions.delta.methods_percent.toFixed(2)}%</b></dd></div>
          <div><dt>bytecode</dt><dd>{integer.format(older.bytecode_bytes)} → {integer.format(newer.bytecode_bytes)} <b>+{versions.delta.bytecode_bytes_percent.toFixed(2)}%</b></dd></div>
          <div><dt>reuse β</dt><dd>{older.reuse_rank_beta.toFixed(3)} → {newer.reuse_rank_beta.toFixed(3)}</dd></div>
          <div><dt>新增采用</dt><dd>{integer.format(versions.new_component_adoption.retained_caller_calls_to_added_methods)} retained-caller call sites</dd></div>
        </dl>
        <p>两个官方二进制快照同时显示总体扩展与 Zipf-like 稳定性，但仍不足以把有限增长外推为“组件供给无限”。gross savings proxy 为 {integer.format(versions.new_component_adoption.gross_savings_proxy_bytes)} bytes，属于静态上界而非因果节省。</p>
      </article>
    </div>

    <aside className="paper-scope-note"><b>为这些检验补充的数据</b><p>抽取器为每个 method 保存 Code byte length、instruction count、max stack/locals、控制流与异常处理标记，并为每个 class 保存 classfile size 与 constant-pool entries；调用图节点与边的既有定义不变。</p></aside>
  </section>;
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
  if (value === "paper_empirical_log10") return "OpenJDK 静态引用";
  if (value === "paper_zipf_log10") return "论文基准 c/n";
  if (value === "empirical_log10") return "经验路径曲线";
  if (value === "zipf_log10") return "Zipf A/r";
  if (value === "reciprocal_prime_log10") return "素数倒数 A/pᵣ";
  return value;
}
