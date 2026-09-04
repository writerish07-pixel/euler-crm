import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Users, ClipboardCheck, Truck, TrendingUp, Wallet, IndianRupee,
  AlertCircle, Landmark, CalendarDays,
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { get } from "../lib/api";
import { inr, compactInr, num, ytdCount, ytdMoney } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button } from "../components/ui";
import OwnerPriceEditor from "../components/OwnerPriceEditor";
import YardStockCard from "../components/YardStockCard";
import { useAuth } from "../context/AuthContext";

export default function Dashboard() {
  const { isOwner } = useAuth();
  const [d, setD] = useState(null);

  useEffect(() => {
    get("/dashboard").then(setD).catch(() => {});
  }, []);

  const k = d?.kpis || {};
  const mtd = d?.period?.mtd || {};
  const ytd = d?.period?.ytd || {};
  const payColors = { Cash: "#059669", UPI: "#1D4ED8", Finance: "#7C3AED", Other: "#A1A1AA" };
  const payData = Object.entries(d?.payments || {}).map(([name, value]) => ({ name, value }));

  return (
    <div data-testid="owner-dashboard">
      <PageHeader
        title="Operations Dashboard"
        subtitle={d?.lastUpdated
          ? `MTD + YTD morning board · updated ${new Date(d.lastUpdated).toLocaleTimeString("en-IN")}`
          : "MTD + YTD morning board"}
        actions={<Link to="/monthly"><Button variant="secondary" data-testid="ops-go-monthly"><CalendarDays size={14} /> Monthly Register</Button></Link>}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="ops-period-kpis">
        <StatCard label="Leads (MTD)" value={d ? num(mtd.leads ?? k.monthlyLeads) : "—"} sub={d ? ytdCount(ytd.leads ?? k.leadsYtd) : "loading"} icon={Users} />
        <StatCard label="Bookings (MTD)" value={d ? num(mtd.bookings ?? k.monthlyBookings) : "—"} sub={d ? ytdCount(ytd.bookings ?? k.bookingsYtd) : "loading"} icon={ClipboardCheck} tone="text-emerald-600" />
        <StatCard label="Deliveries (MTD)" value={d ? num(mtd.deliveries ?? k.monthlyDeliveries) : "—"} sub={d ? ytdCount(ytd.deliveries ?? k.deliveriesYtd) : "loading"} icon={Truck} tone="text-cobalt" />
        <StatCard label="Collected (MTD)" value={d ? compactInr(mtd.collected ?? k.collectedMtd ?? k.revenue) : "—"} sub={d ? ytdMoney(ytd.collected ?? k.collectedYtd) : "loading"} icon={IndianRupee} tone="text-cobalt" />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
        <StatCard label="Active Bookings" value={d ? num(k.activeBookings) : "—"} sub={d ? `${num(k.monthlyBookings)} booked MTD` : "loading"} icon={ClipboardCheck} tone="text-emerald-600" />
        <StatCard label="Total Leads" value={d ? num(k.totalLeads) : "—"} sub="live stock · not period-cut" icon={Users} />
        <StatCard label="Conversion" value={d ? `${k.conversion}%` : "—"} sub={d ? `${ytdCount(k.conversionYtd)}% · bookings ÷ MTD leads` : "bookings ÷ MTD leads"} icon={TrendingUp} tone="text-violet-600" />
        <StatCard label="Follow-ups overdue" value={d ? num(k.followupOverdue) : "—"} sub={d ? `${num(k.followupDue)} due today` : "loading"} icon={AlertCircle} tone="text-red-600" />
      </div>

      {isOwner && <OwnerPriceEditor />}

      <div className="mt-6">
        <YardStockCard />
      </div>

      {!d ? <div className="text-ink-faint text-sm mt-6">Loading dashboard…</div> : (
      <>
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
              <Row label="Finance Outstanding" value={k.financeOutstanding || 0} tone="text-violet-600" />
              {k.financeOverdueCount > 0 && (
                <Row label={`Finance Overdue (>2d, ${k.financeOverdueCount} files)`} value={k.financeOverdueAmount || 0} tone="text-red-600" />
              )}
              <div className="border-t border-line pt-3">
                <Row label="Total Outstanding" value={d.outstanding.total} tone="text-ink" bold />
              </div>
            </div>
          </Card>
          <div className="grid grid-cols-2 gap-4">
            <MiniStat label="Today Leads" value={k.todayLeads} icon={Users} />
            <MiniStat label="Pending Del." value={k.pendingDeliveries} icon={Truck} />
            <MiniStat label="Follow-ups Due" value={k.followupDue || 0} icon={ClipboardCheck} testid="kpi-followup-due" />
            <MiniStat label="Follow-ups Overdue" value={k.followupOverdue || 0} icon={AlertCircle} testid="kpi-followup-overdue" />
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
            { key: "revenue", label: "Collected", align: "right", mono: true, render: (r) => inr(r.revenue) },
          ]}
          rows={d.modelPerformance}
          rowKey="model"
        />
      </div>
      </>
      )}
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

function MiniStat({ label, value, icon: Icon, testid }) {
  return (
    <Card className="p-4" data-testid={testid}>
      <Icon size={16} className="text-ink-faint" />
      <div className="mt-2 font-heading text-xl font-extrabold text-ink tabular">{value}</div>
      <div className="text-xs text-ink-faint">{label}</div>
    </Card>
  );
}
