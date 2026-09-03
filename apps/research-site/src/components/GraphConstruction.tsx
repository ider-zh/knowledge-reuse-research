import { useEffect, useMemo, useState } from "react";

import { loadConstructionCases } from "../data";
import type {
  ConstructionCase,
  ConstructionCases,
  ConstructionEdge,
  ExprBreakdownLayer,
} from "../types";

const format = new Intl.NumberFormat("en-US");
const percent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 1 });

export default function GraphConstruction() {
  const [data, setData] = useState<ConstructionCases | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"nodes" | "edges">("edges");
  const [caseId, setCaseId] = useState("edge.dfunlike");

  useEffect(() => {
    loadConstructionCases()
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const cases = mode === "nodes" ? data?.node_cases ?? [] : data?.edge_cases ?? [];
  const selected = useMemo(
    () => cases.find((item) => item.case_id === caseId) ?? cases[0],
    [caseId, cases],
  );

  const switchMode = (next: "nodes" | "edges") => {
    setMode(next);
    setCaseId(next === "nodes" ? "node.definition" : "edge.dfunlike");
  };

  return (
    <section id="construction" className="section-block construction-section">
      <div className="section-heading">
        <div><p className="eyebrow">SOURCE → SEMANTIC GRAPH</p><h2>一段 Lean 代码怎样成为节点和边</h2></div>
        <p>节点来自 Lean Environment；边来自 `.ilean` 中已经解析到全局常量的源码位置。不同位置不被折叠，聚合后成为 SOURCE multiplicity。</p>
      </div>

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="loading">正在载入源码案例…</p>}
      {data && selected && (
        <>
          <div className="construction-pipeline" aria-label="Lean 源码到研究图的五个阶段">
            {data.stages.map((stage, index) => (
              <article key={stage.stage}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <b>{stage.stage}</b>
                <p>{stage.description}</p>
              </article>
            ))}
          </div>

          <section className="expr-mechanism" aria-label=".ilean SOURCE edge 抽取机制">
            <header>
              <div><p className="eyebrow">EXTRACTION MECHANISM</p><h3>Lean 怎样把源码 identifier 写入 `.ilean` reference index</h3></div>
              <a href={data.edge_extraction.steps[0].url} target="_blank" rel="noreferrer">Lean v4.32.1 实现证据 ↗</a>
            </header>
            <p>{data.edge_extraction.mechanism}</p>
            <div className="expr-mechanism-grid">
              {data.edge_extraction.steps.map((step, index) => (
                <article key={step.step}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <h4>{step.step}</h4>
                  <code>{step.code}</code>
                  <p>{step.detail}</p>
                  <a href={step.url} target="_blank" rel="noreferrer">{step.evidence} ↗</a>
                </article>
              ))}
            </div>
            <aside><b>module 字段怎样解释？</b><p>{data.edge_extraction.module_hint}</p></aside>
          </section>

          <AttributionBoundary boundary={data.attribution_boundary} />

          <div className="construction-note">
            <b>边方向</b><span>{data.edge_direction}</span>
            <b>重复计数单位</b><span>{data.occurrence_unit}</span>
          </div>

          <div className="case-workbench">
            <aside>
              <div className="case-mode" role="group" aria-label="案例类型">
                <button className={mode === "nodes" ? "active" : ""} onClick={() => switchMode("nodes")}>NODE CASES</button>
                <button className={mode === "edges" ? "active" : ""} onClick={() => switchMode("edges")}>EDGE CASES</button>
              </div>
              <div className="case-index">
                {cases.map((item) => (
                  <button key={item.case_id} className={item.case_id === selected.case_id ? "active" : ""} onClick={() => setCaseId(item.case_id)}>
                    <small>{item.case_id}</small><b>{item.title}</b>
                  </button>
                ))}
              </div>
            </aside>

            <article className="case-detail">
              <header>
                <div><p className="eyebrow">VERIFIED MATHLIB CASE</p><h3>{selected.title}</h3><p>{selected.summary}</p></div>
                <a href={selected.source_url} target="_blank" rel="noreferrer">查看固定版本源码 ↗</a>
              </header>
              <div className="case-evidence-grid">
                <div className="source-panel">
                  <div><span>{selected.source_file}</span><span>L{selected.start_line}–L{selected.end_line}</span></div>
                  <pre><code>{selected.code}</code></pre>
                </div>
                <div className="graph-panel">
                  {selected.edges ? <EdgeDiagram edges={selected.edges} /> : <NodeDiagram item={selected} />}
                  {selected.source_locations && <SourceLocations item={selected} />}
                  {selected.aggregate && <TargetAggregate aggregate={selected.aggregate} />}
                </div>
              </div>
              {selected.interpretation && <p className="case-interpretation"><b>研究解释：</b>{selected.interpretation}</p>}
            </article>
          </div>
        </>
      )}
    </section>
  );
}

function AttributionBoundary({ boundary }: { boundary: ConstructionCases["attribution_boundary"] }) {
  const unparented = boundary.unparented;
  const unresolved = boundary.parent_not_in_environment;
  const profile = boundary.outside_declaration_profile;
  const explained = profile.variable_context_count
    + profile.categories.option_or_attribute_header
    + profile.categories.attribute_command
    + profile.categories.alias_command
    + profile.categories.namespace_syntax_or_scope_command;
  const profileRows = [
    ["variable 与多行 binder", profile.variable_context_count],
    ["set_option / attribute header", profile.categories.option_or_attribute_header],
    ["attribute command", profile.categories.attribute_command],
    ["alias command", profile.categories.alias_command],
    ["namespace、syntax 与 scope", profile.categories.namespace_syntax_or_scope_command],
    ["其他命令或多行上下文", profile.population - explained],
  ] as const;
  return (
    <section className="attribution-method" aria-labelledby="attribution-method-title">
      <header>
        <div>
          <p className="eyebrow">ENDPOINT ATTRIBUTION</p>
          <h3 id="attribution-method-title">文件能确定 module，但不能总能确定 consumer declaration</h3>
        </div>
        <p>主研究图只接受语义明确的 declaration → declaration 边；其余位置作为源码上下文证据保留。</p>
      </header>

      <div className="endpoint-flow" aria-label=".ilean 引用两端的对齐规则">
        <article>
          <span>来源端 · consumer</span>
          <b>当前 module + source range + 可选 parent label</b>
          <p>{boundary.source_endpoint}</p>
        </article>
        <i>→</i>
        <article className="edge-contract">
          <span>进入主图的条件</span>
          <b>parent ∈ Environment ∧ parent.module = .ilean.module</b>
          <p>{boundary.primary_graph_rule}</p>
        </article>
        <i>→</i>
        <article>
          <span>目标端 · dependency</span>
          <b>resolved constant name + module hint</b>
          <p>{boundary.target_endpoint}</p>
        </article>
      </div>

      <div className="attribution-ledger">
        <article>
          <header><span>parent label 缺失</span><strong>{format.format(unparented.total)}</strong></header>
          <dl>
            <div><dt>不在任何 declaration 范围</dt><dd>{format.format(unparented.outside_declaration_range)}</dd></div>
            <div><dt>唯一 Environment 范围候选</dt><dd>{format.format(unparented.unique_environment_declaration)}</dd></div>
            <div><dt>多个声明范围重叠</dt><dd>{format.format(unparented.overlapping_declaration_ranges)}</dd></div>
          </dl>
          <p>唯一范围命中是可验证的回填候选；当前主图仍只采用 `.ilean` 直接给出的 parent，不把范围邻近当作事实。</p>
        </article>
        <article>
          <header><span>parent 不在内部 Environment 节点集</span><strong>{format.format(unresolved.total)}</strong></header>
          <dl>
            <div><dt><code>example</code> 临时上下文</dt><dd>{format.format(unresolved.example_context)}</dd></div>
            <div><dt>private / eval 上下文</dt><dd>{format.format(unresolved.private_or_eval_context)}</dd></div>
            <div><dt>元编程或外部上下文</dt><dd>{format.format(unresolved.metaprogram_or_external_context)}</dd></div>
          </dl>
          <p>这些 label 描述精化上下文，并不必然对应本研究语料中的持久 declaration；把它们并入节点集会改变“复用组件”的定义。</p>
        </article>
      </div>

      <aside className="parent-module-mismatch">
        <b>parent module 不一致 · {format.format(boundary.parent_module_mismatch.total)}</b>
        <p>{boundary.parent_module_mismatch.policy}</p>
      </aside>

      <section className="outside-profile" aria-labelledby="outside-profile-title">
        <header>
          <div>
            <span>主要发现</span>
            <h4 id="outside-profile-title">声明范围外的位置主要来自共享的 variable 上下文</h4>
          </div>
          <strong>{format.format(profile.variable_context_count)}<small>{percent.format(profile.variable_context_share)}</small></strong>
        </header>
        <p>
          这些 identifier 已被 Lean 解析到确定的全局常量，但所在的 `variable` 命令服务于后续多个声明，
          自身不是持久 declaration。把一次模块级引用复制给相邻 theorem 会人为增加边和 occurrence。
        </p>
        <div className="outside-profile-bars">
          {profileRows.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <i><b style={{ width: `${(value / profile.population) * 100}%` }} /></i>
              <strong>{format.format(value)}</strong>
            </div>
          ))}
        </div>
        <small>{profile.classification_note}</small>
      </section>

      <aside className="context-policy"><b>完整性原则</b><p>{boundary.context_policy}</p></aside>

      <div className="exception-cases">
        {boundary.examples.map((example) => (
          <article key={example.title}>
            <span>{example.kind}</span>
            <h4>{example.title}</h4>
            <code>{example.code}</code>
            <p>{example.explanation}</p>
            <a href={example.url} target="_blank" rel="noreferrer">查看固定版本证据 ↗</a>
          </article>
        ))}
      </div>
    </section>
  );
}

function NodeDiagram({ item }: { item: ConstructionCase }) {
  return (
    <div className="node-output">
      <p className="diagram-label">ENVIRONMENT DECLARATIONS</p>
      {item.nodes?.map((node) => (
        <article key={node.node_id}>
          <span className={`kind-badge ${node.kind}`}>{node.kind}</span>
          <h4>{node.name}</h4>
          <dl>
            <div><dt>node id</dt><dd>{format.format(node.node_id)}</dd></div>
            <div><dt>type Expr</dt><dd>{format.format(node.type_expr_nodes)}</dd></div>
            <div><dt>value Expr</dt><dd>{node.value_expr_nodes === null ? "null" : format.format(node.value_expr_nodes)}</dd></div>
          </dl>
        </article>
      ))}
      {item.expr_breakdown && (
        <section className="expr-breakdown" aria-label="Set 的具体 Expr 构造">
          <header>
            <div><span>EXACT EXPR BREAKDOWN</span><h5>3 和 5 具体由哪些 Expr 构造组成？</h5></div>
            <small>{item.expr_breakdown.verification}</small>
          </header>
          <div className="expr-layer-grid">
            <ExprLayer title="TYPE EXPR · 3 nodes" layer={item.expr_breakdown.type_expr} />
            <ExprLayer title="VALUE EXPR · 5 nodes" layer={item.expr_breakdown.value_expr} />
          </div>
          <p>{item.expr_breakdown.notation}</p>
          <section className="expr-evidence-chain" aria-label="Sort 解释的证据链">
            <header><span>EVIDENCE CHAIN</span><h6>为什么可以把这些 `.sort` 解释为 Type 和 Prop？</h6></header>
            <ol>
              {item.expr_breakdown.evidence.map((evidence, index) => (
                <li key={evidence.kind}>
                  <i>{index + 1}</i>
                  <div>
                    <span>{evidence.supports}</span>
                    <a href={evidence.url} target="_blank" rel="noreferrer">{evidence.title} ↗</a>
                    <p>{evidence.detail}</p>
                    {evidence.code && <code>{evidence.code}</code>}
                  </div>
                </li>
              ))}
              <li className="observed-evidence">
                <i>{item.expr_breakdown.evidence.length + 1}</i>
                <div>
                  <span>本案例观测</span>
                  <b>Set 的 raw ConstantInfo</b>
                  <p>TYPE 与 VALUE 面板逐项显示 `.sort (u+1)` 和 `.sort 0`；这些值由固定 Lean 环境直接读取。</p>
                </div>
              </li>
            </ol>
            <p><b>推理：</b>{item.expr_breakdown.inference}</p>
          </section>
        </section>
      )}
      <aside className="node-schema-guide" aria-label="节点字段定义">
        <h5>这些字段怎样理解？</h5>
        <dl>
          <div>
            <dt>kind</dt>
            <dd>Lean 环境记录的声明类别，例如 definition、theorem 或 constructor。</dd>
          </div>
          <div>
            <dt>node id</dt>
            <dd>该快照规范化图中的稳定整数标识；它用于连接边，不表示顺序或复杂度。</dd>
          </div>
          <div>
            <dt>type Expr</dt>
            <dd>声明的类型或命题经 Lean 精化后形成的内部表达式。数值是概念展开 Expr tree 中的构造节点出现次数。</dd>
          </div>
          <div>
            <dt>value Expr</dt>
            <dd>定义体或证明项经精化后的内部表达式，采用同一计数方法；null 表示该 value 不可观测，不表示复杂度为零。</dd>
          </div>
        </dl>
        <p>因此，Set 的 type Expr=3、value Expr=5，表示它的精化类型树含 3 个表达式构造出现，定义体树含 5 个；两者都不是源码 Token 数或依赖边数。</p>
      </aside>
    </div>
  );
}

function ExprLayer({ title, layer }: { title: string; layer: ExprBreakdownLayer }) {
  return (
    <article>
      <span>{title}</span>
      <b>{layer.surface}</b>
      <code>{layer.raw}</code>
      <ol>
        {layer.nodes.map((node) => (
          <li key={node.index} className={`expr-depth-${node.depth}`}>
            <i>{node.index}</i><code>{node.constructor}</code><p>{node.meaning}</p>
          </li>
        ))}
      </ol>
    </article>
  );
}

function EdgeDiagram({ edges }: { edges: ConstructionEdge[] }) {
  const first = edges[0];
  const selfLoop = edges.every((edge) => edge.is_self_loop);
  return (
    <div className="edge-output">
      <svg viewBox="0 0 780 270" role="img" aria-label={`${first.src_name} 到 ${first.dst_name} 的 SOURCE 边`}>
        <defs>
          <marker id="arrow-source" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#1f6b53" /></marker>
        </defs>
        {selfLoop ? (
          <>
            <rect x="220" y="105" width="340" height="90" rx="10" className="graph-node" />
            <text x="390" y="145" textAnchor="middle" className="node-name">{shortName(first.src_name)}</text>
            <text x="390" y="170" textAnchor="middle" className="node-kind">{first.src_kind}</text>
            <path d="M485 106 C610 8 655 210 555 176" className="edge-source" markerEnd="url(#arrow-source)" />
            <text x="610" y="70" textAnchor="middle" className="edge-label source">SOURCE × {first.multiplicity}</text>
          </>
        ) : (
          <>
            <rect x="35" y="92" width="280" height="94" rx="10" className="graph-node source" />
            <rect x="465" y="92" width="280" height="94" rx="10" className="graph-node target" />
            <text x="175" y="133" textAnchor="middle" className="node-name">{shortName(first.src_name)}</text>
            <text x="175" y="160" textAnchor="middle" className="node-kind">consumer · {first.src_kind}</text>
            <text x="605" y="133" textAnchor="middle" className="node-name">{shortName(first.dst_name)}</text>
            <text x="605" y="160" textAnchor="middle" className="node-kind">dependency · {first.dst_kind}</text>
            {edges.map((edge, index) => {
              const y = edges.length === 1 ? 139 : index === 0 ? 116 : 162;
              return (
                <g key={`${edge.edge_type}-${edge.dst_id}`}>
                  <path d={`M315 ${y} C365 ${y - 22} 415 ${y - 22} 465 ${y}`} className="edge-source" markerEnd="url(#arrow-source)" />
                  <text x="390" y={y - 23} textAnchor="middle" className="edge-label source">SOURCE × {edge.multiplicity}</text>
                </g>
              );
            })}
          </>
        )}
      </svg>
      <div className="edge-ledger">
        {edges.map((edge) => <span key={`${edge.edge_type}-${edge.dst_id}`} className="source"><b>{edge.edge_type}</b> source occurrences {format.format(edge.multiplicity)}</span>)}
      </div>
    </div>
  );
}

function SourceLocations({ item }: { item: ConstructionCase }) {
  return (
    <section className="source-locations">
      <header><b>RESOLVED SOURCE LOCATIONS</b><span>展示 {item.published_location_count} / {item.edges?.[0].multiplicity}</span></header>
      <ol>
        {item.source_locations?.map((location) => (
          <li key={`${location.line}:${location.start_character}:${location.end_character}`}>
            <code>L{location.line}:{location.start_character}–{location.end_character}</code>
          </li>
        ))}
      </ol>
    </section>
  );
}

function TargetAggregate({ aggregate }: { aggregate: NonNullable<ConstructionCase["aggregate"]> }) {
  return (
    <dl className="target-aggregate">
      <div><dt>目标总 occurrence</dt><dd>{format.format(aggregate.target_source_occurrences)}</dd></div>
      <div><dt>直接 consumers</dt><dd>{format.format(aggregate.target_unique_consumers)}</dd></div>
      <div><dt>来源 modules</dt><dd>{format.format(aggregate.source_modules)}</dd></div>
      <div><dt>独立保存的 private context</dt><dd>{format.format(aggregate.excluded_private_context_locations)}</dd></div>
    </dl>
  );
}

function shortName(name: string) {
  return name.length > 25 ? `${name.slice(0, 22)}…` : name;
}
