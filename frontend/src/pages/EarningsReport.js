import React, { useEffect, useState } from "react";
import { Coins, TrendingUp, ShieldCheck, Layers } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { get } from "../lib/api";
import { inr, compactInr } from "../lib/format";
import { Card, PageHeader, StatCard, Table } from "../components/ui";

export default function EarningsReport() {
  const [d, setD] = useState(null);
  useEffect(() => { get("/reports/dealer-earnings").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="text-ink-faint text-sm">Loading report…</div>;

  const chart = [...d.byMonth].reverse().map((m) => ({
    month: m.key, Margin: m.margin, Scheme: m.scheme, Insurance: m.insurance, Other: m.other,
  }));

  return (
    <div>
      <PageHeader title="Dealer Earnings Report" subtitle="Owner · monthly margin, scheme retained & insurance income" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Earnings" value={compactInr(d.totals.total)} icon={Coins} tone="text-amber-600" />
        <StatCard label="Dealer Margin" value={compactInr(d.totals.margin)} icon={TrendingUp} tone="text-cobalt" />
        <StatCard label="Scheme Retained" value={compactInr(d.totals.scheme)} icon={Layers} tone="text-emerald-600" />
        <StatCard label="Insurance Income" value={compactInr(d.totals.insurance)} icon={ShieldCheck} tone="text-violet-600" />
      </div>

      <Card className="p-5 mb-6">
        <h3 className="font-heading font-bold text-ink mb-4">Monthly Earnings Breakdown</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#52525B" }} />
              <YAxis tickFormatter={(v) => compactInr(v)} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#A1A1AA" }} width={70} />
              <Tooltip formatter={(v) => inr(v)} cursor={{ fill: "#F4F4F5" }} contentStyle={{ borderRadius: 10, border: "1px solid #E4E4E7", fontSize: 13 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Margin" stackId="a" fill="#1D4ED8" />
              <Bar dataKey="Scheme" stackId="a" fill="#059669" />
              <Bar dataKey="Insurance" stackId="a" fill="#7C3AED" />
              <Bar dataKey="Other" stackId="a" fill="#A1A1AA" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <h3 className="font-heading font-bold text-ink mb-3">By Month</h3>
      <Table rowKey="key"
        columns={[
          { key: "key", label: "Month", render: (r) => <span className="font-semibold">{r.key}</span> },
          { key: "count", label: "Deals", align: "right" },
          { key: "margin", label: "Margin", align: "right", mono: true, render: (r) => inr(r.margin) },
          { key: "scheme", label: "Scheme Retained", align: "right", mono: true, render: (r) => inr(r.scheme) },
          { key: "insurance", label: "Insurance", align: "right", mono: true, render: (r) => inr(r.insurance) },
          { key: "other", label: "Other", align: "right", mono: true, render: (r) => inr(r.other) },
          { key: "total", label: "Total", align: "right", mono: true, render: (r) => <span className="font-bold text-amber-600">{inr(r.total)}</span> },
        ]}
        rows={d.byMonth} empty="No dealer-earnings records yet" />
    </div>
  );
}
