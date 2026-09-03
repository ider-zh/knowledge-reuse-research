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

import { loadPathRankComparison } from "../data";
import type { PathRankComparison as PathRankData } from "../types";

const integer = new Intl.NumberFormat("en-US");

export default function PathRankComparison() {
  const [data, setData] = useState<PathRankData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rangeId, setRangeId] = useState("all_positive");

  useEffect(() => {
    loadPathRankComparison()
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const selected = useMemo(
    () => data?.ranges.find((range) => range.range_id === rangeId) ?? data?.ranges[0],
    [data, rangeId],
  );

  if (error) return <section id="path-distribution" className="section-block"><p className="error">{error}</p></section>;
  if (!data || !selected) return <section id="path-distribution" className="section-block loading">正在载入路径分布证据…</section>;

  const zipf = selected.models.zipf;
  const prime = selected.models.reciprocal_prime;
  const improvement = 100 * (zipf.fixed_rmse_log10 - prime.fixed_rmse_log10) / zipf.fixed_rmse_log10;

  return (
    <section id="path-distribution" className="section-block path-rank-section">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">OCCURRENCE-WEIGHTED PATH RANKS</p>
          <h2>路径组合曲线不像 Zipf，也不像素数倒数曲线</h2>
        </div>
        <p>
          将每个节点的 occurrence 加权路径数由大到小排列。该数把不同依赖路线与每层重复源码位置相乘，描述图中的路径组合规模；它不是引用该节点的独立 declaration 数，也不是工作量。
        </p>
      </div>

      <div className="path-rank-workbench">
        <div className="distribution-tabs" role="group" aria-label="选择路径排名分析范围">
          {data.ranges.map((range) => (
            <button
              key={range.range_id}
              className={range.range_id === selected.range_id ? "active" : ""}
              onClick={() => setRangeId(range.range_id)}
            >
              {range.range_id === "all_positive" ? "全部正路径节点" : "路径数最高 1%"}
            </button>
          ))}
        </div>

        <div className="distribution-summary path-rank-summary">
          <article><span>分析节点</span><strong>{integer.format(selected.observation_count)}</strong><p>零路径节点不进入 rank 曲线</p></article>
          <article><span>经验 βrank</span><strong>{zipf.free_exponent_beta.toFixed(3)}</strong><p>β=1 才具有 Zipf 的 1/r 斜率</p></article>
          <article><span>Zipf 固定形状</span><strong>{zipf.fixed_r_squared_log10.toFixed(3)}</strong><p>log₁₀ 空间 R²；RMSE={zipf.fixed_rmse_log10.toFixed(3)} decades</p></article>
          <article><span>素数倒数固定形状</span><strong>{prime.fixed_r_squared_log10.toFixed(3)}</strong><p>log₁₀ 空间 R²；RMSE={prime.fixed_rmse_log10.toFixed(3)} decades</p></article>
        </div>

        <figure className="distribution-chart path-rank-chart">
          <figcaption>
            <b>节点路径数的 rank–frequency 曲线</b>
            <span>横纵轴均已取 log₁₀；参考曲线分别独立拟合一个垂直截距</span>
          </figcaption>
          <ResponsiveContainer width="100%" height={520}>
            <ComposedChart data={selected.points} margin={{ top: 24, right: 34, bottom: 42, left: 32 }}>
              <CartesianGrid strokeDasharray="3 5" />
              <XAxis
                type="number"
                dataKey="log10_rank"
                domain={[0, "dataMax"]}
                tickFormatter={(value) => Number(value).toFixed(1)}
                label={{ value: "log₁₀(rank r)", position: "insideBottom", offset: -22, fontSize: 14 }}
                tick={{ fontSize: 14 }}
              />
              <YAxis
                type="number"
                domain={[Math.floor(selected.minimum_log10), Math.ceil(selected.maximum_log10)]}
                tickFormatter={(value) => Number(value).toFixed(0)}
                label={{ value: "log₁₀(occurrence 加权路径数)", angle: -90, position: "insideLeft", fontSize: 14 }}
                tick={{ fontSize: 14 }}
              />
              <Tooltip
                formatter={(value, name) => [Number(value).toFixed(3), pathLegend(String(name))]}
                labelFormatter={(_, payload) => payload?.[0] ? `rank ${integer.format(payload[0].payload.rank)}` : ""}
                contentStyle={{ fontSize: 14 }}
              />
              <Legend verticalAlign="top" formatter={(value) => pathLegend(String(value))} wrapperStyle={{ fontSize: 14 }} />
              <Scatter name="empirical_log10" dataKey="empirical_log10" fill="#1f6b53" line={{ stroke: "#1f6b53", strokeWidth: 2 }} shape="circle" />
              <Line name="zipf_log10" dataKey="zipf_log10" stroke="#9d493d" strokeWidth={3} dot={false} />
              <Line name="reciprocal_prime_log10" dataKey="reciprocal_prime_log10" stroke="#c07a2b" strokeWidth={3} strokeDasharray="9 5" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <p className="chart-method">
            完整范围含 {integer.format(selected.observation_count)} 个观测，图中按对数间隔发布 {integer.format(selected.display_point_count)} 个 rank。RMSE 的单位是 decade：相差 1 decade 即相差一个数量级。固定模板均只拟合截距，因此 R² 与 RMSE 可以直接比较。
          </p>
        </figure>

        <div className="path-rank-methods">
          <article><span>01 · 排名对象</span><p>对完整内部图中路径数大于零的节点按精确路径数降序排列；计算使用保存的 log₁₀ 值，避免大整数转为浮点数时溢出。</p></article>
          <article><span>02 · Zipf 模板</span><p><code>P(r)=10ᵃ/r</code>。只用最小二乘拟合截距 a；另放开指数得到经验 β，用于检查其与 β=1 的距离。</p></article>
          <article><span>03 · 素数模板</span><p><code>P(r)=10ᵃ/pᵣ</code>，其中 pᵣ 是实际第 r 个素数。由素数定理 pᵣ∼r ln r，它近似按 1/(r ln r) 下降；取倒数后才可与下降的 rank 曲线比较。</p></article>
        </div>

        <aside className="path-rank-conclusion">
          <b>结论</b>
          <p>
            在当前范围内，经验 rank 指数 β={zipf.free_exponent_beta.toFixed(3)}，明显偏离 Zipf 的 β=1。
            素数倒数模板的 RMSE 比 Zipf 低 {Math.abs(improvement).toFixed(1)}%，但两者固定形状的 R² 分别只有 {zipf.fixed_r_squared_log10.toFixed(3)} 与 {prime.fixed_r_squared_log10.toFixed(3)}。
            因而素数模板至多是数值上略近的负对照，不能据此主张路径分布服从素数规律；高路径值主要反映长依赖链中的分叉与汇合组合。
          </p>
        </aside>

        <p className="path-rank-references">
          方法背景：<a href={data.references.zipf_reuse} target="_blank" rel="noreferrer">Veldhuizen 的复用与 Zipf 命题 ↗</a>
          <span> · </span>
          <a href={data.references.nth_prime_asymptotic} target="_blank" rel="noreferrer">NIST DLMF：pᵣ ∼ r ln r ↗</a>
        </p>
      </div>
    </section>
  );
}

function pathLegend(value: string) {
  if (value === "empirical_log10") return "经验路径曲线";
  if (value === "zipf_log10") return "Zipf A/r";
  if (value === "reciprocal_prime_log10") return "素数倒数 A/pᵣ";
  return value;
}
