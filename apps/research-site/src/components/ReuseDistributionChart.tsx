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

import { loadRankFrequency } from "../data";
import type { RankFrequencyDistribution } from "../types";

const format = new Intl.NumberFormat("en-US");

export default function ReuseDistributionChart() {
  const [data, setData] = useState<RankFrequencyDistribution | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [population, setPopulation] = useState("all_declarations");

  useEffect(() => {
    loadRankFrequency()
      .then(setData)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const selected = useMemo(
    () => data?.series.find((series) => series.population === population) ?? data?.series[0],
    [data, population],
  );

  return (
    <section id="distribution" className="section-block distribution-section">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">RANK–FREQUENCY / ZIPF COMPARISON</p>
          <h2>复用分布是否接近 1/r？</h2>
        </div>
        <p>
          横轴是复用排名 r，纵轴 C(r) 是 `.ilean` SOURCE 图中直接引用目标的不同 consumer declaration 数。两轴均为对数刻度；若经验曲线与 Zipf 参考线平行，指数 β 接近 1。
        </p>
      </div>

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="loading">正在载入完整图的压缩分布曲线…</p>}
      {data && selected && (
        <div className="distribution-workbench">
          <div className="distribution-tabs" role="group" aria-label="选择声明总体">
            {data.series.map((series) => (
              <button
                key={series.population}
                className={series.population === selected.population ? "active" : ""}
                onClick={() => setPopulation(series.population)}
              >
                {series.label}
              </button>
            ))}
          </div>

          <div className="distribution-summary">
            <article><span>βrank</span><strong>{selected.beta_rank.toFixed(3)}</strong><p>β=1 才与严格 1/r 平行</p></article>
            <article><span>拟合 R²</span><strong>{selected.r_squared.toFixed(3)}</strong><p>仅描述所选高复用区间的线性贴合</p></article>
            <article><span>拟合观测</span><strong>{format.format(selected.tail_n)}</strong><p>入度至少为 xmin={format.format(selected.xmin)}</p></article>
            <article><span>正入度总体</span><strong>{format.format(selected.positive_n)}</strong><p>self-loop 不计作被其他声明复用</p></article>
          </div>

          <figure className="distribution-chart">
            <figcaption>
              <b>{selected.label} 的经验 rank–frequency</b>
              <span>经验散点/连线、拟合 β 线与 Zipf 1/r 参考线</span>
            </figcaption>
            <ResponsiveContainer width="100%" height={500}>
              <ComposedChart data={selected.points} margin={{ top: 24, right: 34, bottom: 36, left: 24 }}>
                <CartesianGrid strokeDasharray="3 5" />
                <XAxis
                  type="number"
                  dataKey="rank"
                  scale="log"
                  domain={[1, "dataMax"]}
                  allowDataOverflow
                  tickFormatter={compactTick}
                  label={{ value: "rank r（log）", position: "insideBottom", offset: -18, fontSize: 14 }}
                  tick={{ fontSize: 13 }}
                />
                <YAxis
                  type="number"
                  scale="log"
                  domain={[1, "auto"]}
                  allowDataOverflow
                  tickFormatter={compactTick}
                  label={{ value: "C(r) direct SOURCE consumers（log）", angle: -90, position: "insideLeft", fontSize: 14 }}
                  tick={{ fontSize: 13 }}
                />
                <Tooltip
                  formatter={(value, name) => [format.format(Number(value)), legendName(String(name))]}
                  labelFormatter={(rank) => `rank ${format.format(Number(rank))}`}
                  contentStyle={{ fontSize: 14 }}
                />
                <Legend verticalAlign="top" formatter={(value) => legendName(String(value))} wrapperStyle={{ fontSize: 14 }} />
                <Scatter
                  name="empirical_degree"
                  dataKey="empirical_degree"
                  fill="#1f6b53"
                  line={{ stroke: "#1f6b53", strokeWidth: 2 }}
                  shape="circle"
                />
                <Line name="fitted_degree" dataKey="fitted_degree" stroke="#c07a2b" strokeWidth={3} dot={false} connectNulls={false} />
                <Line name="zipf_degree" dataKey="zipf_degree" stroke="#9d493d" strokeWidth={2} strokeDasharray="8 6" dot={false} connectNulls={false} />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="chart-method">
              {selected.display_sampling} 参考线定义为 {data.reference_definition}。网页只压缩显示曲线点；β 拟合来自完整总体。
            </p>
          </figure>

          <div className="distribution-reading">
            <b>如何读这张图</b>
            <p>曲线跨越多个数量级，说明复用高度不均匀。β&gt;1 表示曲线比 1/r 下降更快；β&lt;1 表示下降更慢。接近并不等于统计上证明严格 Zipf。</p>
          </div>
        </div>
      )}
    </section>
  );
}

function compactTick(value: number) {
  if (value >= 1_000_000) return `${value / 1_000_000}m`;
  if (value >= 1_000) return `${value / 1_000}k`;
  return String(value);
}

function legendName(value: string) {
  if (value === "empirical_degree") return "经验 C(r)";
  if (value === "fitted_degree") return "尾部拟合 r^-β";
  if (value === "zipf_degree") return "Zipf 参考 1/r";
  return value;
}
