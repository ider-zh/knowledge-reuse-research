import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Overview } from "../types";

const format = new Intl.NumberFormat("en-US");

export default function DomainCharts({ overview }: { overview: Overview }) {
  const chartData = useMemo(
    () =>
      overview.domains.slice(0, 12).map((row) => ({
        domain: row.domain,
        nodes: row.node_count,
        Href: Number(row.reference_entropy_proxy.toFixed(3)),
        Gini: Number(row.gini.toFixed(3)),
      })),
    [overview.domains],
  );
  return (
    <section className="section-block charts">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">DOMAIN CONTEXT</p>
          <h2>领域差异先受规模影响</h2>
        </div>
        <p>路径领域不是等大的实验组；规模、H*ref 与 Gini 必须并排阅读。</p>
      </div>
      <div className="chart-grid">
        <figure>
          <figcaption>
            <b>主要路径领域的内部节点数</b><span>Top 12 by node count</span>
          </figcaption>
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={chartData} margin={{ left: 10, right: 10, bottom: 70 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="domain" angle={-45} textAnchor="end" interval={0} fontSize={13} />
              <YAxis tickFormatter={(value) => `${Math.round(value / 1000)}k`} />
              <Tooltip formatter={(value) => format.format(Number(value))} />
              <Bar dataKey="nodes" fill="#1f6b53" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </figure>
        <figure>
          <figcaption>
            <b>H*ref 与复用 Gini</b><span>同一领域的两个不同问题</span>
          </figcaption>
          <ResponsiveContainer width="100%" height={340}>
            <BarChart data={chartData} margin={{ left: 0, right: 10, bottom: 70 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="domain" angle={-45} textAnchor="end" interval={0} fontSize={13} />
              <YAxis domain={[0, 1]} />
              <Tooltip />
              <Legend />
              <Bar dataKey="Href" fill="#c07a2b" />
              <Bar dataKey="Gini" fill="#20495f" />
            </BarChart>
          </ResponsiveContainer>
        </figure>
      </div>
    </section>
  );
}
