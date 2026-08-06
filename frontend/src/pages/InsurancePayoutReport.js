import React, { useEffect, useState } from "react";
import { ShieldCheck, TrendingUp, IndianRupee, AlertCircle } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { get } from "../lib/api";
import { inr, compactInr } from "../lib/format";
import { Card, PageHeader, StatCard, Table } from "../components/ui";

export default function InsurancePayoutReport() {
  const [d, setD] = useState(null);
  useEffect(() => { get("/reports/insurance-payout").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="text-ink-faint text-sm">Loading report…</div>;

  const chart = [...d.byMonth].reverse().map((m) => ({ month: m.key, Expected: m.expected, Received: m.received }));

  return (
    <div>
      <PageHeader title="Insurer Payout Report" subtitle="Owner · expected vs received insurer payouts by month" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Premium" value={compactInr(d.totals.premium)} icon={ShieldCheck} />
        <StatCard label="Expected Payout" value={compactInr(d.totals.expected)} icon={TrendingUp} tone="text-cobalt" />
        <StatCard label="Received Payout" value={compactInr(d.totals.received)} icon={IndianRupee} tone="text-emerald-600" />
        <StatCard label="Outstanding" value={compactInr(d.totals.outstanding)} icon={AlertCircle} tone="text-red-600" />
      </div>

      <Card className="p-5 mb-6">
        <h3 className="font-heading font-bold text-ink mb-4">Expected vs Received by Month</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#52525B" }} />
              <YAxis tickFormatter={(v) => compactInr(v)} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#A1A1AA" }} width={70} />
              <Tooltip formatter={(v) => inr(v)} cursor={{ fill: "#F4F4F5" }} contentStyle={{ borderRadius: 10, border: "1px solid #E4E4E7", fontSize: 13 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Expected" fill="#1D4ED8" radius={[6, 6, 0, 0]} maxBarSize={40} />
              <Bar dataKey="Received" fill="#059669" radius={[6, 6, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h3 className="font-heading font-bold text-ink mb-3">By Month</h3>
          <Table rowKey="key"
            columns={[
              { key: "key", label: "Month", render: (r) => <span className="font-semibold">{r.key}</span> },
              { key: "count", label: "Policies", align: "right" },
              { key: "expected", label: "Expected", align: "right", mono: true, render: (r) => inr(r.expected) },
              { key: "received", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.received)}</span> },
              { key: "outstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.outstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.outstanding)}</span> },
            ]}
            rows={d.byMonth} empty="No insurance entries yet" />
        </div>
        <div>
          <h3 className="font-heading font-bold text-ink mb-3">By Insurer</h3>
          <Table rowKey="key"
            columns={[
              { key: "key", label: "Insurer", render: (r) => <span className="font-semibold">{r.key}</span> },
              { key: "count", label: "Policies", align: "right" },
              { key: "premium", label: "Premium", align: "right", mono: true, render: (r) => inr(r.premium) },
              { key: "expected", label: "Expected", align: "right", mono: true, render: (r) => inr(r.expected) },
              { key: "outstanding", label: "Outstanding", align: "right", mono: true, render: (r) => inr(r.outstanding) },
            ]}
            rows={d.byInsurer} empty="No insurance entries yet" />
        </div>
      </div>
    </div>
  );
}
