# Knowledge Reuse Research Report Generation Spec

状态：`DRAFT FOR REVIEW`  
版本：`report-spec-v2`  
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

研究报告正文必须首先满足三种角色：

| 角色 | 报告需要回答的问题 |
|---|---|
| 研究者 | 研究对象、变量、假设、统计方法与解释边界是什么？ |
| 审计者 | 研究总体、缺失、过滤和版本是否可追溯？ |
| 跨系统比较者 | 哪些指标可与其他图比较，哪些是 source-native 指标？ |

工程运行轨迹（缓存、分片、进程、重试、性能、饱和/截断实现防护、
命令清单）属于独立 machine audit 与工程文档，不进入研究报告正文。
报告只保留理解总体范围、观测覆盖和统计有效性所必需的研究证据。

报告必须做到：

- 概念设计先于统计结果；
- 每个可具体化的核心概念先用 1–2 个真实、可回查案例建立直觉；
- 事实、推断、限制和未来工作明确分层；
- 所有数字可追溯到机器可读结果；
- 所有影响研究总体或统计解释的过滤、缺失和展示降采样都显式披露；
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
- 把缓存、分片、重试、进程耗时等工程运行轨迹写成研究结论；
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

### 2.3 Veldhuizen 2005 命题对照契约

Lean/mathlib 报告必须围绕 Veldhuizen 的理论对象给出五项逐条 verdict，而不是把任意网络指标当成论文复现：

1. declaration 的复用 rank–frequency 是否重尾、尾部斜率是否接近 `1/r`；
2. 正入度 declaration 的 Top 1/5/10% 与 Gini 是否表明少数组件主导复用；
3. 来源路径领域的 rank exponent、集中度与 `H*ref` 是否不同；
4. source、statement/type Expr 与 proof/value Expr 长度对复用的条件关联方向；
5. 多 snapshot 数据能否支持“稳定核心 + 持续长尾”的纵向命题。

报告必须严格区分：

- `degree_tail_alpha`：入度概率质量尾部的幂律指数；
- `rank_exponent_beta`：`log C(r)` 对 `log r` 的负斜率，`beta≈1` 才与 Zipf `1/r` 直接对应；
- Veldhuizen 的理论 `H` 与由来源领域依赖目标份额计算的经验代理 `H*ref`；
- 论文中每次复用节省的代码量 `S(n)` 与 Lean declaration 的长度/Expr 复杂度；
- 原论文的 raw reference frequency 与本实验的 unique-consumer indegree。

`H*ref(d)` 使用统一目标领域全集进行归一化：若来源领域 `d` 指向目标领域 `b` 的唯一 consumer–target pair 份额为 `p_d(b)`，目标领域全集大小为 `D`，则

```text
H*ref(d) = -Σ_b p_d(b) log p_d(b) / log D
```

TYPE/VALUE 对同一 `(src,dst)` 的重复在此处折叠一次，使 `H*ref`、领域 Gini 与 rank-frequency 使用同一个 reuse 单位。报告必须说明它是 `Veldhuizen-style empirical proxy`，不能据此估计理论 `H` 或推出 `1-H` 的可复用代码比例。

如果只有一个 snapshot，第 5 项必须明确判为 `not testable`；如果 schema 没有稳定的 instance-role 字段，instance 分层必须显示 `not available` 而不是并入 definition 后假称已完成。

### 2.4 三层指标模型

报告必须把指标分为三层：

1. **Core comparable metrics**：node/edge count、unique indegree/outdegree、zero-degree、Gini、HHI、Top-k share、Lorenz、rank-frequency。
2. **Source-aligned metrics**：概念相近但单位不同，例如 Lean Expr nodes、Wikipedia wikitext bytes、software AST nodes。
3. **Source-native metrics**：只在特定 source 有语义，例如 Lean TYPE/VALUE、Wikipedia namespace、software call/import edge。

跨系统表格不得直接比较第 2、3 层原始数值，除非报告给出标准化定义及其局限。

### 2.5 平滑的研究逻辑链

每个主要概念和研究结论必须按同一条逻辑链展开：

```text
研究问题
  → 概念定义
  → 1–2 个真实、可核验的具体例子
  → 操作化变量与单位
  → 提取/计算算法
  → 单例证据记录
  → 总体统计或模型结果
  → 结论等级
  → 反例、限制或不可推出的结论
```

不得从抽象定义直接跳到全局统计图，也不得先展示相关系数，再在后文补充变量定义。读者在看到总体结果之前，必须已经能用一个真实节点和一条真实边解释该指标如何产生。

章节之间必须使用短的过渡段说明因果顺序，而不是仅靠编号相邻。例如：

> 上一节定义了 node 和 TYPE/VALUE edge，并用两个真实声明验证了边方向。本节据此把每个 target 收到的唯一 source 数定义为 reuse indegree，再从单节点计数扩展到全库分布。

每个核心分析区块使用以下最小叙事单元：

1. **Definition**：一句话和必要公式；
2. **Concrete case**：来自当前 snapshot 的真实对象；
3. **Computation**：输入字段、算法、复杂度与缺失规则；
4. **Population result**：完整总体上的图、表或模型；
5. **Interpretation**：支持什么、不支持什么。

### 2.6 高中阶段读者可理解性契约

报告不得把“术语已经出现在表头”当作“概念已经解释”。正文以没有接触
Lean、图论或统计建模，但具备高中代数和比例知识的读者为最低解释基线：

- source-specific 术语（如 elaboration、declaration、Expr、TYPE/VALUE）
  首次出现时先用日常语言解释，再给正式名称；若术语由 source 定义，还必须
  链接 source 的官方语言参考、源码定义或版本固定文档；
- 图论术语（有向边、入度、出度、CCDF、rank-frequency）先用 3–5 个节点
  的可手算例子解释计数方向；
- 集中度指标至少给出“完全均匀”和“全部集中于一个节点”两个边界例子；
- 每个缩写（DAG、CCDF、HHI、GLM、CI）首次出现时写出全称或中文含义；
- 每个统计方法先回答“它比较什么、数值范围怎样读、为什么在这里使用”，
  然后才展示结果；
- 首次给出符号或统计量（如 `β`、Gini、`H*ref`、`xmin`、KS）时，必须在
  数字之前直接给出定义、取值/方向怎样读及适用总体；不得要求读者向后寻找上下文；
- `log1p`、percentile、coefficient、confidence interval、p value、control
  等词必须给出一句无需统计课程背景的解释；
- 章节结尾应说明上一节的结果为什么导向下一节，不能只依赖目录编号；
- 真实总体数字与教学用 toy example 必须明确区分，避免读者把手算例子
  误当实验数据。

数学定义不能被比喻替代；推荐顺序是“日常类比 → 正式定义 → 手算例子 →
真实数据 → 解释边界”。

## 3. 证据与结论契约

### 3.1 证据层级

报告中的重要句子必须属于以下类型之一：

| 类型 | 定义 | 示例 |
|---|---|---|
| `fact` | manifest、audit 或确定性聚合直接给出的事实 | “8,264/8,264 模块成功” |
| `supported` | 预先定义方法和质量门禁支持的统计结论 | “复用高度集中，Gini=…” |
| `exploratory` | 观察性、快照特定或多重比较中的发现 | “某领域表现出更高集中度” |
| `inconclusive` | 现有证据不能区分假设或缺少必要检验 | “尚不能确认纯幂律” |
| `not_available` | 指标未实现、输入不可用或不适用 | “该快照没有可验证的 occurrence 数据” |

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

### 3.4 Example / exemplar evidence contract

报告中的例子不是装饰性文案，而是最小可审计证据。每个真实例子必须绑定 machine-readable exemplar record，建议输出：

```text
results/<experiment_id>/runs/<run_kind>/report/examples.json
results/<experiment_id>/runs/<run_kind>/tables/report_examples.parquet
```

最小记录结构：

```json
{
  "example_id": "edge.value.theorem_to_theorem.01",
  "snapshot_id": "...",
  "concept": "VALUE edge and theorem reuse",
  "selection_rule": "stable_hash among non-generated theorem→theorem VALUE edges",
  "node_ids": [123, 456],
  "native_ids": ["Source.name", "Target.name"],
  "edge_type": "VALUE",
  "metrics": {
    "target_in_degree_value": 42
  },
  "evidence": [
    "normalized/edges.parquet#src_id=123,dst_id=456,edge_type=VALUE",
    "normalized/nodes.parquet#node_id=123",
    "normalized/nodes.parquet#node_id=456"
  ],
  "source_locator": "source-native stable locator",
  "explanation": "Why this record illustrates the concept.",
  "caveat": "What this one case cannot establish."
}
```

每个 exemplar 必须满足：

- 来自本次报告绑定的同一 snapshot 和 run population；
- native ID、node ID、edge type 与展示指标能回查到 normalized/compact artifacts；
- selection rule 可复现，禁止仅凭作者偏好挑选；
- 不因名称熟悉或结果极端而假装“有代表性”；
- caption 明确它是解释概念、典型案例、边界案例还是反例；
- 单个案例不能作为总体结论证据，必须随后连接 population result；
- source snippet 若展示，必须记录准确 locator、版本与长度限制；
- synthetic fixture 只能解释算法正确性，必须标为 `synthetic_fixture`，不能冒充真实语料案例。

选择策略至少同时覆盖：

1. **直观例子**：名称和关系较容易理解；
2. **不同语义例子**：例如不同 edge type 或 node kind；
3. **工作量边界**：small、median、p99/high-complexity；
4. **缺失/不适用例子**：解释 null 为什么不是 zero；
5. **反例或对照**：提醒读者单例不能代表总体规律。

真实例子默认每个核心概念 1–2 个。超过 2 个时应放入 case-study 表格或 appendix，避免正文被案例列表淹没。

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
│   ├── report_examples.parquet
│   └── ...
└── report/
    └── examples.json
```

允许在 report generation 中进行的操作：formatting、排序、选择已计算行、有限聚合用于展示、确定性可视化降采样。

不允许的操作：重新读取 raw graph 拟合模型、在模板层定义新总体、改变缺失值、用 HTML 逻辑覆盖 audit 结论。

### 4.2 必需 provenance

每个报告必须绑定：

- `source_id`、`snapshot_id`、`experiment_id`、`run_kind`；
- upstream version/revision；
- extractor/normalizer/analyzer/report generator revision；工作树非 clean 时可用精确
  source/binary SHA-256 绑定实现，但不得用当前 revision 倒推历史未记录的 extractor；
- config hash 与 raw manifest hash；
- schema versions；
- 研究报告正文绑定 source/snapshot/schema/revision/checksum；started/finished
  time、worker count 和运行环境保存在 machine audit，可由证据索引回查；
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
- 明确 configured corpus、覆盖率、影响研究解释的过滤或未实现指标；
  工程运行轨迹链接到 machine audit，不进入 headline findings。

### 2. 概念设计与研究对象

- 什么是 knowledge unit；
- 为什么选择该节点粒度；
- 什么构成直接复用；
- 边方向；
- reuse、dependency、complexity、domain 的操作化定义；
- 与人类意图、使用频率、质量或重要性的区别。

本章必须先给出 1–2 个真实 node，再给出 1–2 条真实 typed edge。例子需要同时展示 native name、node kind、source/module、边方向和“为何这构成复用”，让没有 source-specific 或图研究背景的读者也能手工判断关系。

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

本章必须用一条真实 edge 逐步展示：source native object → extractor record → normalized IDs → typed edge → target indegree 增加 1。另给一条不同 edge semantic 的对照案例，避免读者把所有边理解为同一种引用。

### 6. 研究范围与观测完整性

- expected/extracted/ok/partial/failed/excluded；
- dangling、duplicate、null 与 coverage；
- 影响统计总体的 missing/failed/excluded 状态；
- “完整”的精确定义。

本章节必须直接回答：**报告覆盖哪个固定总体、观测到多少、哪些值为
null，以及缺失如何进入或退出分析？** 工程上的截断防护、缓存实现与
运行事故只在 machine audit 中记录。

### 7. 节点复杂度与长度

- 每个变量的定义、单位、算法、coverage；
- Token 指标必须给出可执行的精确定义，并用一行高中生可手算的源码
  展示分词结果；若它不是 source lexer 的精确 token，必须称为代理量；
- tree occurrence 与 unique DAG node 的区别；
- 至少分别报告 unique DAG nodes U、DAG arcs A、maximum depth D、expanded
  tree occurrences T、expansion factor T/U 和 unique constant breadth；
- source length 与 elaborated/native structure 的区别；
- `value=null` 的判定规则，以及 null 对 node 保留、incoming reuse、TYPE
  edge、VALUE edge 和 value-complexity 样本的不同影响。

本章至少展示四种工作量案例：small、median、p99/high-complexity 和 null/not-applicable。每个案例列出输入对象、关键结构、算法访问的 unique objects/arcs（若可用）、输出值和所处总体分位数。算法讲解必须包含一个可手算的小例子和一个真实高工作量例子。解释止于研究定义、递推式、时间/空间复杂度和指标含义；不得以 cache、streaming、sharding 或运行事故组织正文叙事。

### 8. Graph Overview

- node/edge counts；
- node kind/type distribution；
- edge type distribution；
- zero indegree/outdegree/isolated/self-loop；
- degree summary、CCDF 和 rank-frequency。

从前述单条边自然过渡到单节点 indegree，再扩展到全体 degree distribution。正文至少手工展开一个 target 的 2–5 条 incoming edge 样例，说明 unique consumers 如何去重；若完整 incoming list 很长，仅展示确定性选取的少量边并链接完整 compact table。

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
- 若模型使用 `log1p(x)`，所谓“翻倍效应”必须注明参考值 `x`，并使用
  `log1p(2x)-log1p(x)` 计算；不得把它写成与 baseline 无关的常数；
- observational caveat。

在相关和回归之前，必须并列展示两个真实节点案例：长度/复杂度相近但 reuse 不同，或 reuse 相近但复杂度不同。该对照用于建立直觉和暴露混杂，不得用两个案例替代总体模型。

### 12. Node-kind 与 edge-semantics 分析

- 主要 node types；
- 主要 source→target type 组合；
- typed graph views；
- 不同机制不能混合解释。

每个进入 headline comparison 的主要 edge semantic 至少有一个真实例子。若某个组合没有边或数量太少，显示实际 count 和 `not_available/inconclusive`，不得用 synthetic edge 补位。

### 13. Domain/group 分析

- taxonomy 定义；
- node/edge/reuse scale；
- group dependency matrix；
- internal dependency share；
- diversity 与 entropy proxy；
- per-group tail/concentration；
- taxonomy 局限。

至少用两条跨 group/domain 的真实边解释 dependency matrix 的一个 cell 如何累加，并与一条 group 内部边对照。

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

主 edge table 的存储键是唯一 `(src, dst, edge_type)`，并以正整数
`multiplicity` 保存 target constant 在 source 的对应 elaborated Expr tree 中出现的准确次数。
无权复用广度使用不同 source 的数量；加权引用强度使用 `multiplicity` 之和。两种统计必须
并列命名，不得把同一 source 内的重复出现解释为多个独立 consumer。

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

没有以下变量时，必须显示 `not_available`，不得从其他计数推断：

- maximum Expr depth；
- unique pointer-node count；

`constant occurrence multiplicity` 采用与 Expr tree occurrence 相同的 DAG 动态规划语义：先按
pointer identity 收集唯一 DAG 节点，再从根向子节点传播 root-to-node path count；每个 `.const`
节点按其路径权重累加。该算法在不展开共享子树的情况下保留每个使用位置，时间约为
`O(U + A + K)`，其中 `K` 是唯一 DAG 中 constant nodes 的数量，整数加法成本仍取决于位宽。

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

### 8.9 Lean 真实案例集

Lean 正文必须包含一个由 full normalized graph 生成的最小案例集。案例不能只来自 golden fixture；fixture 用于验证 extractor，而真实案例用于帮助读者理解研究语义。

| 概念 | 最少案例 | 报告必须展示 |
|---|---:|---|
| declaration node | 2 | 一个有 value 的 definition/theorem；一个无 value 或不同 kind 的 declaration |
| TYPE edge | 1 | source/target type 的相关片段、constant reference、方向、两个 node kind |
| VALUE edge | 1 | proof/definition body 的相关片段、constant reference、方向、两个 node kind |
| reuse indegree | 1 target + 2–5 consumers | 每条 incoming edge 如何使 unique consumer count 增加，重复 typed edge 如何去重 |
| source/type/value complexity | 至少 4 | small、median、p99/high、null/not-applicable |
| cache algorithm | 2 | 可手算的小 Expr/DAG；真实 high-workload declaration |
| domain matrix | 3 edges | 两条跨领域边与一条领域内边 |

固定 `mathlib-v4.32.1` full graph 中已经验证存在、可作为首版候选的关系包括：

```text
constantCoeff_xInTermsOfW --VALUE--> map_pow
padicValRat.of_nat         --TYPE-->  padicValNat
```

第一条用于解释 theorem proof/value 对 theorem 的复用；第二条用于解释 theorem statement/type 对 definition 的依赖。生成器仍必须在当前输入 artifacts 中重新验证它们，写入 node IDs、module、kind、edge type 和 checksum。若候选在未来 snapshot 不存在，必须依据版本化 selection rule 选择替代案例并记录替换原因，禁止静默保留旧文字。

节点与 value/null 对照的首版候选：

- `Set`：definition，可用于展示一个结构较小但高复用的真实节点；
- `CategoryTheory.Category`：inductive，可用于解释 `has_value=false` 时 `value_expr_nodes=null`，而不是零；
- `Semiring.toNonAssocSemiring`：definition，可同时展示 type 与 value complexity；
- `CategoryTheory.Limits.colimitLimitToLimitColimit_surjective`：真实 high-workload theorem，用于说明 tree-occurrence 值可能远大于可见源码，以及 cache 为什么必要。

上述名称是 snapshot-specific exemplar candidates，不是跨版本 contract。报告中出现的具体数值必须从本次 `node_metrics`/normalized records 读取，不能写死在模板。

#### 8.9.1 Expr 缓存算法的可视化例子

报告必须用一个小型结构图解释共享子表达式：

```text
        parent
        /    \
     shared  shared
        |
       leaf
```

若 `shared` 被两个 child position 引用：

- pointer traversal 只展开 `shared` 一次；
- cache 只计算 `count(shared)` 一次；
- `count(parent)` 仍两次累加 `count(shared)`；
- 因此缓存减少计算工作量，但 tree-occurrence 结果没有截断。

这个小图可以是 `synthetic_fixture`，但旁边必须连接一个真实 mathlib high-workload declaration，展示其 name、kind、module、`type_expr_nodes`、`value_expr_nodes`、source coverage 和总体分位数。synthetic fixture 证明 recurrence 易于理解；真实 declaration 证明该算法处理的是实际研究负载。

#### 8.9.2 不同工作量算法例子

报告不能笼统写“算法是 O(n)”。至少区分：

| 阶段 | 工作量单位 | 例子要求 | 需要报告的性能量 |
|---|---|---|---|
| module extraction | modules、environment loading、declarations | 一个小 module 与一个声明密集 module | wall time、decl/s、edge/s、RSS |
| Expr complexity | unique Expr pointers U、child arcs A、tree count 位宽 | small 与 high-workload declaration | U/A（若已测量）或明确 not available、tree count、duration |
| edge normalization | raw typed edges、unique typed edges | 有重复候选与去重后结果 | input/output rows、dedup ratio、wall time、RSS |
| graph aggregation | nodes、edges、groups | smoke 与 full | scanned rows、wall time、peak RSS |
| model fitting | positive n、tail n、candidate xmin | 小 population 与 all declarations | n、tail n、duration、status |
| HTML rendering | figure points、table rows、output bytes | full statistics 与 display sample | statistical n、rendered n、wall time、bytes |

若某阶段没有 per-case timing 或 U/A 指标，必须标记 `not_available`，不能用总 pipeline wall time 代替局部算法复杂度。

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
- `examples.json` 与 `report_examples.parquet` 存在，且 snapshot/run 与报告一致；
- 每个 exemplar 的 native ID、node ID、edge 与 metrics 可在证据路径中解析；
- 每个核心概念都有规定数量的真实例子；
- synthetic fixture 与 real corpus example 有显式不同标签；
- 案例选择规则确定性，未来 snapshot 的替换有记录；
- 单例文字之后存在对应 population result，不以案例代替总体证据。

### 10.2 Semantic tests

- edge direction在正文、图例和指标定义中一致；
- reuse 使用 target indegree；
- unique edge 与 multiplicity 未混淆；
- sample size 是统计总体，不是绘图点数；
- heavy-tail 结论读取 model comparison 与 bootstrap status；
- entropy proxy 有 proxy 标签；
- regression 同时报告 effect size 与 CI；
- source-native complexity 单位不被标成 cross-source equivalent；
- 每个主要区块遵循 definition → concrete case → computation → population result → interpretation；
- 章节过渡明确说明前一层证据如何支持下一层分析；
- 案例 caption 同时说明它解释什么以及不能证明什么。

### 10.3 Lean acceptance additions

- 报告中的 module/node/edge counts 与 full `data_quality.json`/`summary.json` 一致；
- theorem value coverage 与 proof visibility 结论一致；
- TYPE、VALUE 和 ALL 数量一致性通过；
- source metric coverage 显示 null rate；
- tree-occurrence 算法描述与 `ExprStats.lean` fixture 一致；
- machine audit/测试验证 cache 命中不改变 graph semantics 或 analysis population；
  cache、重试、force 等工程运行轨迹不进入研究正文；
- TYPE 与 VALUE 各有至少一个从 full graph 验证的真实 edge 案例；
- 至少一个无 value 的 declaration 用于解释 `null ≠ 0`；
- Expr cache 同时有手算 DAG 和真实 high-workload declaration；
- 正文解释 Expr 递推算法与渐进复杂度，但不展示 extraction/cache/retry/rendering
  等工程 workload tracking；这些信息仅保留在 machine audit。

## 11. 人工评审量表

研究者可对每项打 0–3 分：

| 维度 | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 概念清晰度 | 不知道图表示什么 | 有定义但混乱 | 基本清晰 | 无需代码背景即可准确理解 |
| 完整性透明度 | 看不出是否失败/截断 | 信息藏在附录 | 首屏可见 | 首屏结论可追溯到 audit |
| 证据严谨性 | 图代替检验 | 有统计但过度结论 | 结论基本匹配证据 | claim/status/evidence 全绑定 |
| 例子可核验性 | 无例子或虚构例子 | 例子真实但无法回查 | 例子有基本证据路径 | 真实案例、选择规则、artifact 与总体结果全部连接 |
| 复杂度解释 | 单一“长度” | 多变量但算法不清 | 算法与 coverage 清楚 | tree/DAG/null/单位全部区分 |
| 可读性 | 数据堆叠 | 能读但难导航 | 结构清楚 | 概念→证据→解释自然连贯 |
| 跨系统复用 | 完全 source-specific | 只有口号 | core/native 分层 | 新 source 可直接按契约接入 |
| 可复现性 | 无版本/命令 | 部分 manifest | 可重建 | checksum、claims、artifacts 可审计 |
| 视觉可信度 | 图无单位/样本 | caption 重复标题 | 信息基本完整 | 每图说明支持与不支持什么 |

建议验收门槛：每项至少 2 分，总分至少 23/27；“完整性透明度”“证据严谨性”“例子可核验性”“可复现性”必须达到 3 分。

## 12. 评审后实施顺序

规范确认后，按以下独立阶段实施，每阶段单独验证和提交：

1. 定义 `report.toml`、claim registry、exemplar registry 和 artifact index schema；
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
7. 是否接受“真实案例由确定性规则选择、snapshot-specific 候选只作为首版起点”，而不把案例名称永久写死在跨版本模板中。

---

本规范不改变任何实验结果。它定义下一版 report generator 应遵循的研究、证据、展示与验收契约。
