import React, { useEffect, useState } from "react";
import {
  Users, ClipboardCheck, Truck, TrendingUp, Wallet, IndianRupee,
  AlertCircle, Landmark, Banknote, Smartphone,
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { get } from "../lib/api";
import { inr, compactInr, num } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge } from "../components/ui";

export default function Dashboard() {
  const [d, setD] = useState(null);

  useEffect(() => {
    get("/dashboard").then(setD).catch(() => {});
  }, []);

  if (!d) return <div className="text-ink-faint text-sm">Loading dashboard…</div>;

  const k = d.kpis;
  const payColors = { Cash: "#059669", UPI: "#1D4ED8", Finance: "#7C3AED", Other: "#A1A1AA" };
  const payData = Object.entries(d.payments).map(([name, value]) => ({ name, value }));

  return (
    <div>
      <PageHeader
        title="Operations Dashboard"
        subtitle={`Live pipeline snapshot · updated ${new Date(d.lastUpdated).toLocaleTimeString("en-IN")}`}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Active Bookings" value={num(k.activeBookings)} sub={`${k.monthlyBookings} new this month`} icon={ClipboardCheck} tone="text-emerald-600" />
        <StatCard label="Total Leads" value={num(k.totalLeads)} sub={`${k.monthlyLeads} new this month`} icon={Users} />
        <StatCard label="Conversion" value={`${k.conversion}%`} sub="bookings ÷ monthly leads" icon={TrendingUp} tone="text-violet-600" />
        <StatCard label="Revenue (MTD)" value={compactInr(k.revenue)} sub="payments this month" icon={IndianRupee} tone="text-cobalt" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-heading font-bold text-ink">Payments by Mode <span className="text-ink-faint font-sans font-normal text-sm">(this month)</span></h3>
            <Wallet size={18} className="text-ink-faint" />
          </div>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={payData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#52525B" }} />
                <YAxis tickFormatter={(v) => compactInr(v)} tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "#A1A1AA" }} width={70} />
                <Tooltip formatter={(v) => inr(v)} cursor={{ fill: "#F4F4F5" }} contentStyle={{ borderRadius: 10, border: "1px solid #E4E4E7", fontSize: 13 }} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]} maxBarSize={72}>
                  {payData.map((e) => <Cell key={e.name} fill={payColors[e.name]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center gap-2 mb-3">
              <AlertCircle size={16} className="text-amber-500" />
              <h3 className="font-heading font-bold text-ink text-sm">Outstanding</h3>
            </div>
            <div className="space-y-3">
              <Row label="Customer Outstanding" value={d.outstanding.customer} tone="text-red-600" />
              <Row label="Company Outstanding (OEM)" value={d.outstanding.company} tone="text-amber-600" />
              <div className="border-t border-line pt-3">
                <Row label="Total Outstanding" value={d.outstanding.total} tone="text-ink" bold />
              </div>
            </div>
          </Card>
          <div className="grid grid-cols-2 gap-4">
            <MiniStat label="Today Leads" value={k.todayLeads} icon={Users} />
            <MiniStat label="Pending Del." value={k.pendingDeliveries} icon={Truck} />
          </div>
        </div>
      </div>

      <div className="mt-6">
        <h3 className="font-heading font-bold text-ink mb-3">Model Performance</h3>
        <Table
          columns={[
            { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
            { key: "leads", label: "Leads", align: "right" },
            { key: "bookings", label: "Bookings", align: "right" },
            { key: "deliveries", label: "Deliveries", align: "right" },
            { key: "pending", label: "Pending", align: "right", render: (r) => r.pending ? <Badge tone="bg-amber-50 text-amber-700 ring-amber-600/20">{r.pending}</Badge> : "—" },
            { key: "conv", label: "Book Conv %", align: "right", render: (r) => `${r.leads ? Math.round((r.bookings / r.leads) * 100) : 0}%` },
            { key: "customerOs", label: "Customer OS", align: "right", mono: true, render: (r) => inr(r.customerOs) },
            { key: "revenue", label: "Revenue", align: "right", mono: true, render: (r) => inr(r.revenue) },
          ]}
          rows={d.modelPerformance}
          rowKey="model"
        />
      </div>
    </div>
  );
}

function Row({ label, value, tone, bold }) {
  return (
    <div className="flex items-center justify-between">
      <span className={`text-sm ${bold ? "font-semibold text-ink" : "text-ink-soft"}`}>{label}</span>
      <span className={`font-mono tabular text-sm ${bold ? "font-bold" : "font-medium"} ${tone}`}>{inr(value)}</span>
    </div>
  );
}

function MiniStat({ label, value, icon: Icon }) {
  return (
    <Card className="p-4">
      <Icon size={16} className="text-ink-faint" />
      <div className="mt-2 font-heading text-xl font-extrabold text-ink tabular">{value}</div>
      <div className="text-xs text-ink-faint">{label}</div>
    </Card>
  );
}
