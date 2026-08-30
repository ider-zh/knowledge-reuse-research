# Knowledge Reuse Research Report Generation Spec

状态：`DRAFT FOR REVIEW`  
版本：`report-spec-v1`  
适用范围：Lean/mathlib、Wikipedia、open-source software 及后续知识复用图实验  
规范来源：项目多源架构、Lean/mathlib 实验 Notion spec、各实验 machine-readable results

## 0. 本文档如何使用

这是一份报告生成规范，不是实验结果，也不是 HTML 设计稿。它用于：

1. 约束报告生成器消费什么数据、如何组织证据、允许得出什么结论；
2. 让不同数据源的报告具有相同的研究骨架，同时保留 source-specific 语义；
3. 让研究者在实现前评估报告内容、阅读顺序和验收标准；
4. 让测试能够判断报告是否完整、可追溯、未隐藏失败或缺失数据。

本规范通过评审前，不应继续以当前 HTML 的版式作为默认设计依据。

### 0.1 规范依据

- [Lean 4 / mathlib Reuse Graph Experiment（Notion）](https://app.notion.com/p/3c8812cd4d2881278c81c0202ae95ca3)
- [`docs/architecture.md`](architecture.md)
- 研究者提供的 Lean 形式化知识概念设计（本轮只读取，不修改）
- `schemas/core/` 与各 experiment 的 machine-readable result contracts

## 1. 目标与非目标

### 1.1 目标

报告必须同时满足四种角色：

| 角色 | 报告需要回答的问题 |
|---|---|
| 研究者 | 研究对象、变量、假设、统计方法与解释边界是什么？ |
| 审计者 | 图是否完整？是否截断？失败、缺失、过滤和版本是否可追溯？ |
| 工程者 | 数据从哪里来？如何重建？报告是否只消费版本化 compact artifacts？ |
| 跨系统比较者 | 哪些指标可与其他图比较，哪些是 source-native 指标？ |

报告必须做到：

- 概念设计先于统计结果；
- 事实、推断、限制和未来工作明确分层；
- 所有数字可追溯到机器可读结果；
- 所有过滤、缺失、降采样和失败都显式披露；
- 普通目录版与 standalone HTML 在离线环境中可读；
- 不依赖 notebook、远程数据库、CDN、远程 JavaScript 或远程字体。

### 1.2 非目标

报告生成器不得：

- 在 Jinja/HTML 模板中重新完成全量研究计算；
- 从图形外观直接宣称幂律、Zipf、因果关系或理论熵；
- 用 `0`、空数组或省略章节伪装缺失数据；
- 为减小 HTML 而截断统计输入；
- 把 source-specific 单位伪装成跨系统等价量；
- 修改 raw、normalized graph 或实验参数；
- 把交互效果置于静态可读性和审计性之上。

## 2. 通用研究模式

每个知识复用实验都映射到以下通用对象：

```text
Source snapshot
  └─ Corpus / population
      ├─ Nodes: 可复用知识单元
      ├─ Typed directed edges: consumer → dependency
      ├─ Native complexity variables
      ├─ Reuse and dependency metrics
      ├─ Group/domain labels
      └─ Audit and completeness evidence
```

### 2.1 通用图定义

对固定 source snapshot 定义：

```text
G = (V, E)
u → v means: u consumes, cites, calls, imports, links to, or semantically depends on v
```

边方向在所有 source 中固定为 `consumer/source → dependency/target`。因此：

- `indegree(v)` 表示 v 被多少节点直接复用；
- `outdegree(u)` 表示 u 的直接依赖负担；
- 主复用指标使用 unique source nodes，而不是同一 source 内的重复 occurrence；
- occurrence/multiplicity 若可获得，作为独立变量，不得与 unique reuse 混用。

### 2.2 通用研究问题

每个 source report 至少回答：

| ID | 通用问题 | 最小证据 |
|---|---|---|
| RQ-A | 复用是否集中或呈重尾？ | degree、CCDF、rank-frequency、Gini、Top-k share、模型比较 |
| RQ-B | 节点长度/复杂度与复用有何关系？ | coverage、Spearman、分箱曲线、count regression + CI |
| RQ-C | 不同 group/domain 是否异质？ | 分组规模、集中度、tail、dependency matrix、entropy proxy |
| RQ-D | 不同边语义或节点类型是否具有不同规律？ | typed views、kind/type 子图与稳健性比较 |
| RQ-E | 哪些结果可跨系统比较？ | core metric 与 native metric 的明确映射及不可比说明 |

### 2.3 三层指标模型

报告必须把指标分为三层：

1. **Core comparable metrics**：node/edge count、unique indegree/outdegree、zero-degree、Gini、HHI、Top-k share、Lorenz、rank-frequency。
2. **Source-aligned metrics**：概念相近但单位不同，例如 Lean Expr nodes、Wikipedia wikitext bytes、software AST nodes。
3. **Source-native metrics**：只在特定 source 有语义，例如 Lean TYPE/VALUE、Wikipedia namespace、software call/import edge。

跨系统表格不得直接比较第 2、3 层原始数值，除非报告给出标准化定义及其局限。

## 3. 证据与结论契约

### 3.1 证据层级

报告中的重要句子必须属于以下类型之一：

| 类型 | 定义 | 示例 |
|---|---|---|
| `fact` | manifest、audit 或确定性聚合直接给出的事实 | “8,264/8,264 模块成功” |
| `supported` | 预先定义方法和质量门禁支持的统计结论 | “复用高度集中，Gini=…” |
| `exploratory` | 观察性、快照特定或多重比较中的发现 | “某领域表现出更高集中度” |
| `inconclusive` | 现有证据不能区分假设或缺少必要检验 | “尚不能确认纯幂律” |
| `not_available` | 指标未实现、输入不可用或不适用 | “multiplicity 在 v1 不可用” |

禁止只用颜色表达证据等级；标签必须出现在文本或可访问属性中。

### 3.2 Claim registry

报告生成前必须存在机器可读 claim registry，建议为
`results/<experiment>/runs/<run>/report/claims.json`：

```json
{
  "schema_version": "report-claims-v1",
  "claims": [
    {
      "claim_id": "completeness.full_corpus",
      "status": "fact",
      "text": "All configured modules were extracted successfully.",
      "evidence": [
        "metrics/data_quality.json#/extraction_completeness",
        "metrics/data_quality.json#/module_status_counts"
      ],
      "scope": "configured corpus",
      "caveat": "Configured exclusions are outside the population."
    }
  ]
}
```

HTML 中每条 headline finding 必须对应一个 `claim_id`。文字可本地化，但数值、status、scope 与 evidence 不得脱离 registry 单独维护。

### 3.3 禁止性结论

除非存在额外设计和证据，报告不得声称：

- indegree 等于知识质量、数学重要性或人类意图；
- 相关或回归系数是因果效应；
- log-log 图近似直线即证明 Zipf/power law；
- 经验 entropy proxy 等于理论 entropy；
- configured corpus 的 100% 等于整个上游生态的 100%；
- 可视化降采样后的点数是统计样本量。

## 4. 输入产物契约

### 4.1 报告只消费 compact results

报告生成器默认只能读取：

```text
results/<experiment_id>/runs/<run_kind>/
├── run-manifest.json
├── metrics/
│   ├── summary.json
│   ├── data_quality.json
│   ├── node_metrics.parquet
│   ├── powerlaw_fits.parquet
│   ├── regressions.parquet
│   ├── domain_metrics.parquet
│   └── view_metrics.parquet
├── tables/
│   ├── top_reuse.csv
│   ├── domain_matrix.parquet
│   └── ...
└── report/
```

允许在 report generation 中进行的操作：formatting、排序、选择已计算行、有限聚合用于展示、确定性可视化降采样。

不允许的操作：重新读取 raw graph 拟合模型、在模板层定义新总体、改变缺失值、用 HTML 逻辑覆盖 audit 结论。

### 4.2 必需 provenance

每个报告必须绑定：

- `source_id`、`snapshot_id`、`experiment_id`、`run_kind`；
- upstream version/revision；
- extractor/normalizer/analyzer/report generator revision；
- config hash 与 raw manifest hash；
- schema versions；
- started/finished time、worker count 和运行环境；
- 每个输入 compact artifact 的 checksum；
- 报告输出 checksum 与 byte size。

若任何绑定缺失，报告第一屏状态必须为 `AUDIT INCOMPLETE`，不得显示“完整实验”。

### 4.3 Null、zero 与 not-applicable

三者必须区分：

| 状态 | 含义 | 展示 |
|---|---|---|
| `0` | 已测量且值为零 | `0` |
| `null` | 应可测量但当前缺失 | `—`，并报告 coverage |
| `not_applicable` | 对该 node/source 没有定义 | `N/A`，说明原因 |

绘图不得调用 `fill_null(0)`。每个涉及 nullable metric 的图表必须显示有效样本量 `n_valid` 与总体 `n_total`。

## 5. 报告信息架构

所有 source report 使用相同一级章节顺序。source adapter 可增加三级小节，但不得删除必需章节；不适用时保留章节并解释 `not_available/not_applicable`。

### 1. 封面与执行摘要

第一屏必须包含：

- source、snapshot、experiment、run kind；
- `COMPLETE / INCOMPLETE / AUDIT INCOMPLETE`；
- extracted/expected corpus units；
- internal nodes、external nodes、typed unique edges；
- 3–8 条 headline findings，每条带 evidence status；
- 明确说明是否存在截断、失败、partial、过滤或未实现指标。

### 2. 概念设计与研究对象

- 什么是 knowledge unit；
- 为什么选择该节点粒度；
- 什么构成直接复用；
- 边方向；
- reuse、dependency、complexity、domain 的操作化定义；
- 与人类意图、使用频率、质量或重要性的区别。

### 3. 研究问题与假设

- RQ-A 至 RQ-E；
- 每个 RQ 的总体、变量、视图、方法和判断标准；
- exploratory analysis 与 confirmatory analysis 分开。

### 4. Corpus 与 Snapshot

- include/exclude 规则；
- snapshot/version；
- corpus inventory；
- exclusion count 与理由；
- configured corpus 与外部 universe 的边界。

### 5. 图构建语义

- source-native 节点和边；
- typed graph views；
- unique edge 与 multiplicity；
- internal/external target；
- identity 与 deterministic ID；
- extraction、normalization 和 deduplication 的高层流程。

### 6. 完整性与数据质量

- expected/extracted/ok/partial/failed/excluded；
- dangling、duplicate、null、coverage、checksum；
- capability/golden/fixture 证据；
- 失败是否影响总体；
- “完整”的精确定义。

本章节必须直接回答：**是否构建了研究契约下的完整图？是否存在截断？**

### 7. 节点复杂度与长度

- 每个变量的定义、单位、算法、coverage；
- tree occurrence 与 unique DAG node 的区别；
- source length 与 elaborated/native structure 的区别；
- 缺失机制；
- 未实现的建议变量。

### 8. Graph Overview

- node/edge counts；
- node kind/type distribution；
- edge type distribution；
- zero indegree/outdegree/isolated/self-loop；
- degree summary、CCDF 和 rank-frequency。

### 9. Reuse concentration

- Top 1/5/10% share；
- Gini、HHI、Lorenz；
- top reusable nodes；
- 集中度不等同于重要性的解释。

### 10. Heavy-tail model comparison

- population、n、positive n、tail n；
- xmin、alpha、KS；
- goodness-of-fit/bootstrap status；
- power law vs lognormal/truncated comparisons；
- supported 与 rejected/inconclusive 模型；
- 不能只展示拟合线。

### 11. Length/complexity vs reuse

- nullable coverage；
- scatter/density 或 hexbin；
- log-binned median 与 quantiles；
- Spearman；
- Negative Binomial 或有解释的替代 count model；
- controls、effect size、95% CI、diagnostics；
- observational caveat。

### 12. Node-kind 与 edge-semantics 分析

- 主要 node types；
- 主要 source→target type 组合；
- typed graph views；
- 不同机制不能混合解释。

### 13. Domain/group 分析

- taxonomy 定义；
- node/edge/reuse scale；
- group dependency matrix；
- internal dependency share；
- diversity 与 entropy proxy；
- per-group tail/concentration；
- taxonomy 局限。

### 14. Robustness checks

- full vs user-facing/no-generated；
- edge type views；
- node type views；
- major filtering choices；
- unique edge vs multiplicity（若可用）；
- 结论是否跨视图保持。

### 15. 跨系统解释

- core projection 映射；
- 可比较指标；
- 不可直接比较的 native units；
- source-specific 自动化机制；
- 与参考理论工作的 conceptual replication/extension 边界。

### 16. 结论、限制与下一实验

- 按 RQ 回答，而不是重复图表；
- 最强证据与最大不确定性；
- 不可推出的结论；
- 下一步应由当前证据缺口驱动。

### 17. Reproducibility appendix

- manifest；
- schema 与配置链接；
- commands；
- fit diagnostics；
- failures/warnings；
- checksums；
- benchmark；
- machine-readable artifact index。

## 6. 图表与表格规范

### 6.1 每张图的必需元素

每张图必须有：

- 唯一 figure ID 和可引用标题；
- x/y 轴名称、单位和 transform；
- `n_total`、`n_valid`、population、graph view；
- 数据是完整、过滤还是仅视觉降采样；
- caption 至少回答“图支持什么”和“图不支持什么”；
- 静态 fallback；
- 颜色之外的可辨识方式；
- SVG `<title>`/ARIA label 或等价可访问文本。

### 6.2 降采样

可视化降采样必须：

- 只发生在 render layer；
- 确定性；
- 保留端点和尾部；
- 在 caption 标注展示点数与统计样本量；
- 不改变表格、模型、相关、quantile 或 claim registry。

禁止使用“前 N 行”作为默认散点采样，因为节点排序可能与 source/domain 相关。建议使用固定 seed hash sampling、分层采样或按坐标排序后的确定性等距采样。

### 6.3 表格

- 列名使用研究术语而不是内部变量名，必要时括号给出 schema column；
- 数值包含单位、合理精度与千位分隔；
- p-value 与 effect size 同时出现；
- `null` 显示为 `—`，`not_applicable` 显示为 `N/A`；
- 长表默认给出主表与可下载完整表链接；
- 排序规则必须写在 caption 或表头说明中。

### 6.4 Mandatory figures

每个 graph report 至少包含：

1. node type counts；
2. edge type counts；
3. indegree CCDF；
4. rank-frequency；
5. tail-fit/model diagnostic；
6. native source length vs reuse；
7. native structural complexity vs reuse；
8. binned complexity vs reuse；
9. Lorenz curve；
10. top group/domain scale；
11. group→group dependency heatmap；
12. group entropy/diversity proxy；
13. per-group concentration/tail；
14. robustness comparison。

若某图不适用，报告保留位置并给出 `not_available` 原因，不能换成无关图充数。

## 7. HTML 与生成器要求

### 7.1 输出

```text
results/<experiment_id>/runs/<run_kind>/report/
├── index.html
├── report_standalone.html
├── assets/
├── claims.json
└── artifact-index.json
```

- `index.html` 只能引用相对路径本地 assets；
- `report_standalone.html` 必须单文件离线打开；
- 禁止 CDN、远程 JS、远程字体、远程数据库；
- 禁用 JavaScript 后，全部 headline findings、关键图表和关键表格仍可读取。

### 7.2 确定性

相同输入 checksums 和 generator revision 必须产生相同正文、图形和表格。若生成时间导致 byte hash 变化，时间字段必须从 deterministic report body 分离，或明确排除出稳定性断言。

### 7.3 性能与体积

- generator 不得读取 raw shards；
- 全量报告生成应有 wall time、peak RSS 和 output bytes 记录；
- standalone 目标体积不超过 2 MiB；超过 10 MiB 必须失败，除非 experiment config 有书面例外；
- 体积优化不得减少统计总体或删除审计内容。

### 7.4 报告配置

建议每个实验提供 `report.toml`：

```toml
schema_version = "report-spec-v1"
language = "zh-CN"
audience = ["researcher", "auditor", "engineer"]
source_id = "lean_mathlib"
experiment_id = "lean_mathlib_v1"
run_kind = "full"
claim_registry = "report/claims.json"
standalone_target_bytes = 2097152
standalone_max_bytes = 10485760

[display_sampling]
method = "stable_hash_stratified"
seed = "report-spec-v1"
max_scatter_points = 2000
max_line_points = 1000
```

配置只能影响 presentation，不得改变实验 population 或分析参数。

## 8. Lean/mathlib 专用要求

本节覆盖 Lean/mathlib 特有语义；未覆盖部分继承通用规范。

### 8.1 Snapshot 与 corpus

正式 v1 报告必须显示：

- mathlib tag `v4.32.1`；
- 完整 40-character mathlib commit SHA；
- 从 checkout `lean-toolchain` 实际读取的 Lean toolchain；
- extractor commit；
- `Mathlib/**/*.lean` include 规则；
- Archive、tests、benchmarks、Counterexamples 等配置化 exclusions；
- expected/extracted/excluded module counts。

“100% 完整”只能写成“configured corpus 100%”，不得扩展为所有 Lean package 或所有 mathlib 历史内容。

### 8.2 Lean 节点

主要内部节点是 elaborated Environment 中的 declarations。报告至少分开：

- theorem；
- definition；
- instance（若 schema/kind 能稳定识别）；
- inductive；
- constructor；
- recursor；
- opaque/axiom；
- generated/internal declarations。

完整图保留 generated/internal nodes。面向用户的近似图只能作为 derived robustness view，不能覆盖底图。

### 8.3 Lean 边

边方向固定：

```text
consumer declaration → referenced declaration
```

必须分别报告：

- `TYPE`：target constant 出现在 elaborated type/statement；
- `VALUE`：target constant 出现在 proof/definition body；
- `ALL`：TYPE 与 VALUE 的 union；
- theorem→theorem、theorem→definition、definition→definition 等派生视图。

主 edge table 是唯一 `(src, dst, edge_type)`。如果同一 Expr 中 occurrence multiplicity 未稳定实现，则必须为 null，并在正文和 robustness 中显示 `not_available`。

### 8.4 Proof visibility

报告必须记录：

- pinned API capability probe 是否通过；
- `import all`/private scope 方案；
- theorem `has_value` coverage；
- golden fixture 中 proof/value edge exact comparison；
- 任何 unavailable proof body 或 failed module。

禁止把 unavailable proof body 当作空 VALUE edge set。theorem value coverage 不完整时，第一屏必须为 `INCOMPLETE`。

### 8.5 Lean 长度与复杂度

v1 必需变量：

| 变量 | 定义 | 缺失规则 |
|---|---|---|
| `source_bytes` | declaration source range 对应字节数 | 无可靠 range 时 null |
| `source_lines` | source range 行数 | 无可靠 range 时 null |
| `source_tokens` | source range 的 deterministic token count | 无可靠 range 时 null |
| `type_expr_nodes` | elaborated type 的 Expr tree occurrences | 所有内部 declaration 必须有值 |
| `value_expr_nodes` | proof/definition body 的 Expr tree occurrences | 无 value 时 null |
| `type_const_unique` | type 中唯一 referenced constants 数 | 必须有值 |
| `value_const_unique` | value 中唯一 referenced constants 数 | 无 value 时 null |

Expr 计数报告必须说明当前算法：

1. 对共享 Expr DAG 使用 pointer-identity visited set 收集 postorder；
2. 每个 unique Expr pointer 的 subtree count 只计算一次并缓存；
3. 父节点按每个 child occurrence 累加缓存值，恢复 tree-occurrence multiplicity；
4. 使用 Lean 任意精度 `Nat`，没有 saturation cap；
5. cache 消除重复计算，不等于删除共享子表达式的贡献。

算法复杂度应报告为：对单个 Expr，pointer collection 约为 `O(U + A)`，cached recurrence 约为 `O(U + A)`；其中 U 为唯一 Expr 对象数，A 为 DAG child arcs。`Nat` 加法成本还依赖结果位宽。

当前 v1 没有以下变量时，必须显示 `not_available`，不得从现有计数推断：

- maximum Expr depth；
- unique pointer-node count；
- constant occurrence multiplicity。

### 8.6 Lean 完整图与“不截断”声明

只有以下条件同时成立，报告才可显示 `完整图构建成功`：

- capability probe passed；
- golden exact node/typed-edge fixture passed；
- expected modules = extracted modules；
- 所有配置内 module status = `ok`；
- theorem value coverage = 100%；
- dangling internal src/dst = 0；
- duplicate normalized typed edges = 0；
- deterministic sample rerun passed；
- shard merge order independence passed；
- extractor 没有 node/edge/depth/time cap；
- 没有 saturation、silent fallback 或 partial-as-empty。

报告还必须显示：

- internal declaration count；
- explicit external/prelude target count；
- TYPE/VALUE/ALL unique edge counts；
- self-loop count；
- source-range coverage；
- no-value declaration count；
- configured exclusions。

### 8.7 Lean 必需统计分析

Lean report 至少包含：

- ALL、TYPE、VALUE degree distributions；
- theorem-only、definition-only；
- theorem→theorem、theorem→definition、definition→definition（数据可用时）；
- Gini、HHI、Top 1/5/10%、Lorenz；
- power law vs lognormal，条件允许时加入 truncated power law；
- bootstrap goodness-of-fit status；
- `source_bytes`、`type_expr_nodes`、`value_expr_nodes` 的 Spearman；
- 每个长度变量的 Negative Binomial regression，控制 kind + domain；
- coefficient、effect size、95% CI、p-value、n；
- major domains 的 node/edge/reuse、dependency matrix、Gini、tail 与 `H*ref`；
- ALL 与 NO_GENERATED 等视图的稳健性比较。

### 8.8 Lean 专用解释边界

报告必须明确：

- elaborated dependency 不等于源码中人眼可见的 citation；
- theorem→theorem 最接近 premise reuse，但仍可能包含自动化产生的 proof-term 依赖；
- typeclass、coercion、simp 与 generated declarations 会影响边；
- declaration indegree 不等于定理质量或数学深度；
- module path taxonomy 是可复现代理，不是严格数学本体；
- `H*ref` 是 empirical operational proxy，且 `H*ref ≠ theoretical H`；
- 模型比较未支持时，不得宣称 Zipf law。

## 9. Source-specific 扩展模板

Wikipedia 与 software 报告继承相同章节和证据契约，仅替换 native semantics。

| 概念 | Lean/mathlib | Wikipedia | Software |
|---|---|---|---|
| node | declaration | page/article | function/module/package/repository（实验需固定一种） |
| edge | TYPE/VALUE constant reference | hyperlink/citation | call/import/dependency |
| source length | declaration range bytes/tokens | wikitext/prose bytes/tokens | source/AST bytes/tokens |
| structural complexity | Expr tree occurrences | section/template/link structure | AST/cyclomatic/call structure |
| domain/group | Mathlib top-level path | namespace/category/topic | language/ecosystem/repository layer |
| automation caveat | elaborator/typeclass/simp | templates/bots/redirects | generated code/framework/monorepo |

任何新 source 在生成正式报告前必须提交自己的 source-specific appendix，说明 identity、edge semantics、external target、completeness unit、native complexity 与主要偏差来源。

## 10. 自动验收标准

### 10.1 Contract tests

报告测试至少断言：

- 17 个必需章节均存在且顺序正确；
- 第一屏包含 snapshot、run、完整性与图规模；
- 每条 headline claim 有 registry entry 和 evidence path；
- 所有 evidence path 存在并绑定 checksum；
- required figures 均有 title、axes、population、n、caption；
- nullable metric 图中不存在 null→0 转换；
- standalone 中不存在 remote URL dependency；
- HTML 在禁用 JS 时保留关键内容；
- input checksum 不变时重复生成 byte-identical；
- standalone size 未超过配置 hard limit；
- run kind 与所有 compact results 一致；
- failed/partial/completeness 不会被模板条件隐藏。

### 10.2 Semantic tests

- edge direction在正文、图例和指标定义中一致；
- reuse 使用 target indegree；
- unique edge 与 multiplicity 未混淆；
- sample size 是统计总体，不是绘图点数；
- heavy-tail 结论读取 model comparison 与 bootstrap status；
- entropy proxy 有 proxy 标签；
- regression 同时报告 effect size 与 CI；
- source-native complexity 单位不被标成 cross-source equivalent。

### 10.3 Lean acceptance additions

- 报告中的 module/node/edge counts 与 full `data_quality.json`/`summary.json` 一致；
- theorem value coverage 与 proof visibility 结论一致；
- TYPE、VALUE 和 ALL 数量一致性通过；
- source metric coverage 显示 null rate；
- tree-occurrence 算法描述与 `ExprStats.lean` fixture 一致；
- 报告出现“缓存不等于截断”及未实现复杂度变量；
- `--force` 只控制是否重建有效 cache，不改变 graph semantics 或 analysis population。

## 11. 人工评审量表

研究者可对每项打 0–3 分：

| 维度 | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 概念清晰度 | 不知道图表示什么 | 有定义但混乱 | 基本清晰 | 无需代码背景即可准确理解 |
| 完整性透明度 | 看不出是否失败/截断 | 信息藏在附录 | 首屏可见 | 首屏结论可追溯到 audit |
| 证据严谨性 | 图代替检验 | 有统计但过度结论 | 结论基本匹配证据 | claim/status/evidence 全绑定 |
| 复杂度解释 | 单一“长度” | 多变量但算法不清 | 算法与 coverage 清楚 | tree/DAG/null/单位全部区分 |
| 可读性 | 数据堆叠 | 能读但难导航 | 结构清楚 | 概念→证据→解释自然连贯 |
| 跨系统复用 | 完全 source-specific | 只有口号 | core/native 分层 | 新 source 可直接按契约接入 |
| 可复现性 | 无版本/命令 | 部分 manifest | 可重建 | checksum、claims、artifacts 可审计 |
| 视觉可信度 | 图无单位/样本 | caption 重复标题 | 信息基本完整 | 每图说明支持与不支持什么 |

建议验收门槛：每项至少 2 分，总分至少 20/24；“完整性透明度”“证据严谨性”“可复现性”必须达到 3 分。

## 12. 评审后实施顺序

规范确认后，按以下独立阶段实施，每阶段单独验证和提交：

1. 定义 `report.toml`、claim registry 和 artifact index schema；
2. 把通用 evidence/formatting/render helpers 移入 shared analysis；
3. 实现 Lean source-specific report adapter；
4. 增加 contract、semantic、determinism 和 offline tests；
5. 从现有 full compact artifacts 重建 Lean report；
6. 人工按第 11 节评分；
7. 冻结 `report-spec-v1`；
8. Wikipedia/software 按相同契约增加 source-specific appendix。

在第 1 步之前，不修改 Lean graph、实验 population、`--force` 或已有 raw/derived data。

## 13. 本轮需要研究者评估的决定

请重点确认：

1. 17 章顺序是否符合“概念先行、证据随后”的阅读方式；
2. 是否接受 claim registry 作为所有 headline conclusions 的唯一来源；
3. 是否接受 standalone 2 MiB 目标、10 MiB hard limit；
4. 是否要求首版就新增 maximum Expr depth 与 unique pointer-node count，或继续标为 v2 指标；
5. 是否需要在单个 Lean report 中加入 Wikipedia/software 的实际对比数据，还是只保留跨系统方法映射；
6. 报告默认语言是否固定为中文，机器字段与统计术语保留英文。

---

本规范不改变任何实验结果。它定义下一版 report generator 应遵循的研究、证据、展示与验收契约。
