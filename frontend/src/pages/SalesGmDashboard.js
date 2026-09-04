import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Users, ClipboardCheck, Truck, TrendingUp, AlertCircle, Landmark,
  Ban, IndianRupee, Percent, ClipboardList, Warehouse, Trophy, CalendarDays,
} from "lucide-react";
import { toast } from "sonner";
import { get } from "../lib/api";
import { compactInr, inr, num, ytdCount } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button } from "../components/ui";
import YardStockCard from "../components/YardStockCard";

/** Showroom-wide sales board — all executives, deal desk, no money posting. */
export default function SalesGmDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => {
    get("/sales-gm/dashboard").then(setD).catch(() => toast.error("Could not load Sales GM dashboard"));
  }, []);

  if (!d) return <div className="text-ink-faint text-sm">Loading Sales GM dashboard…</div>;
  const k = d.kpis || {};
  const scope = d.scope || {};

  return (
    <div data-testid="sales-gm-dashboard">
      <PageHeader
        title="Sales GM Dashboard"
        subtitle={`${scope.note || "Showroom-wide sales"} · MTD + YTD · updated ${d.lastUpdated ? new Date(d.lastUpdated).toLocaleTimeString("en-IN") : "—"}`}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="gm-period-kpis">
        <StatCard label="Leads (MTD)" value={num(k.leadsMtd)} sub={ytdCount(k.leadsYtd)} icon={Users} />
        <StatCard label="Bookings (MTD)" value={num(k.bookingsMtd)} sub={`${ytdCount(k.bookingsYtd)} · ${k.activeBookings || 0} active`} icon={ClipboardCheck} tone="text-emerald-600" />
        <StatCard label="Deliveries (MTD)" value={num(k.deliveriesMtd)} sub={`${ytdCount(k.deliveriesYtd)} · ${k.pendingDeliveries || 0} pending`} icon={Truck} tone="text-cobalt" />
        <StatCard label="Lead → Book" value={`${k.leadToBookPct || 0}%`}
          sub={`YTD ${k.leadToBookPctYtd || 0}% · Book → Del ${k.bookToDeliverPct || 0}%`} icon={TrendingUp} tone="text-violet-600" />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
        <StatCard label="Follow-ups overdue" value={num(k.followupOverdue)} sub={`${k.followupDue || 0} due today`} icon={AlertCircle} tone="text-red-600" />
        <StatCard label="Finance overdue" value={num(k.financeOverdueCount)}
          sub={compactInr(k.financeOverdueAmount)} icon={Landmark} tone="text-violet-600" />
        <StatCard label="Cancellations (MTD)" value={num(k.cancellationsMtd)} sub={`${ytdCount(k.cancellationsYtd)} · ${k.lostCount || 0} lost`} icon={Ban} tone="text-amber-700" />
        <StatCard label="Customer OS" value={compactInr(k.customerOutstanding)}
          sub={`Scheme use ${k.schemeUseRate || 0}%`} icon={IndianRupee} tone="text-red-600" />
      </div>

      <div className="flex flex-wrap gap-2 mt-5">
        <Link to="/monthly"><Button variant="secondary" data-testid="gm-go-monthly"><CalendarDays size={14} /> Monthly Register</Button></Link>
        <Link to="/leads"><Button variant="secondary" data-testid="gm-go-leads"><Users size={14} /> Lead Register</Button></Link>
        <Link to="/bookings"><Button variant="secondary" data-testid="gm-go-bookings"><ClipboardCheck size={14} /> Bookings</Button></Link>
        <Link to="/deliveries"><Button variant="secondary" data-testid="gm-go-deliveries"><Truck size={14} /> Deliveries</Button></Link>
        <Link to="/allocation"><Button variant="secondary" data-testid="gm-go-allocation"><ClipboardList size={14} /> Allocation</Button></Link>
        <Link to="/finance"><Button variant="secondary" data-testid="gm-go-finance"><Landmark size={14} /> Finance Register</Button></Link>
        <Link to="/cancellations"><Button variant="secondary" data-testid="gm-go-cancels"><Ban size={14} /> Cancellations</Button></Link>
        <Link to="/inventory"><Button variant="secondary" data-testid="gm-go-inventory"><Warehouse size={14} /> Inventory</Button></Link>
        <Link to="/executive-incentive"><Button variant="secondary" data-testid="gm-go-exec-incentive"><Trophy size={14} /> Executive Incentive</Button></Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card className="p-5 lg:col-span-2">
          <h3 className="font-heading font-bold text-ink mb-3">Team worklist</h3>
          <Table
            empty="Nothing due — nice work"
            columns={[
              { key: "kind", label: "Action", render: (r) => (
                <Badge tone={r.kind.includes("overdue") ? "bg-red-50 text-red-700 ring-red-600/20"
                  : r.kind.includes("today") ? "bg-amber-50 text-amber-700 ring-amber-600/20"
                    : "bg-sky-50 text-sky-700 ring-sky-600/20"}>{r.kind}</Badge>
              ) },
              { key: "customerName", label: "Customer", render: (r) => (
                <Link to="/leads" className="font-semibold text-cobalt hover:underline">{r.customerName || r.leadId}</Link>
              ) },
              { key: "executive", label: "Executive" },
              { key: "model", label: "Model" },
              { key: "status", label: "Status" },
              { key: "date", label: "Date", mono: true },
            ]}
            rows={d.worklist || []}
          />
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Percent size={16} className="text-ink-faint" />
            <h3 className="font-heading font-bold text-ink">Pipeline funnel</h3>
          </div>
          <div className="space-y-2">
            {(d.funnel || []).map((f) => (
              <div key={f.status} className="flex items-center justify-between text-sm">
                <span className="text-ink-soft">{f.status}</span>
                <span className="font-mono font-semibold tabular">{f.count}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-5 mt-6">
        <h3 className="font-heading font-bold text-ink mb-1">Executive scoreboard</h3>
        <p className="text-xs text-ink-soft mb-3">MTD · Book % = bookings÷leads (includes delivered) · Del % = deliveries÷bookings</p>
        <Table
          rowKey="executive"
          empty="No executives on leads yet"
          columns={[
            { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive}</span> },
            { key: "leadsMtd", label: "Leads", align: "right" },
            { key: "bookingsMtd", label: "Books", align: "right" },
            { key: "deliveriesMtd", label: "Del.", align: "right" },
            { key: "conversion", label: "Book %", align: "right", render: (r) => `${r.conversion || 0}%` },
            { key: "deliveryConversion", label: "Del %", align: "right", render: (r) => `${r.deliveryConversion || 0}%` },
            { key: "followupOverdue", label: "FU overdue", align: "right", render: (r) => (
              r.followupOverdue ? <Badge tone="bg-red-50 text-red-700 ring-red-600/20">{r.followupOverdue}</Badge> : "—"
            ) },
            { key: "pendingDeliveries", label: "Pending del.", align: "right", render: (r) => (
              r.pendingDeliveries ? <Badge tone="bg-amber-50 text-amber-700 ring-amber-600/20">{r.pendingDeliveries}</Badge> : "—"
            ) },
          ]}
          rows={d.executiveScoreboard || []}
        />
      </Card>

      <Card className="p-5 mt-6" data-testid="gm-exec-incentive">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div>
            <h3 className="font-heading font-bold text-ink">Executive incentive (this month)</h3>
            <p className="text-xs text-ink-soft">
              {(d.executiveIncentive && d.executiveIncentive.month) || "—"}
              {" "}· units × each person’s ladder. GM and Owner set targets.
            </p>
          </div>
          <Link to="/executive-incentive">
            <Button variant="secondary" data-testid="gm-set-exec-targets"><Trophy size={14} /> Set targets</Button>
          </Link>
        </div>
        <Table
          rowKey="executive"
          empty="No executives yet"
          columns={[
            { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive}</span> },
            { key: "units", label: "Units", align: "right" },
            { key: "hasOwnPlan", label: "Plan", render: (r) => (
              <Badge tone={r.hasOwnPlan ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-100 text-zinc-600 ring-zinc-500/20"}>
                {r.hasOwnPlan ? "Set" : "Not set"}
              </Badge>
            ) },
            { key: "amountPerUnit", label: "₹ / unit", align: "right", mono: true, render: (r) => inr(r.amountPerUnit) },
            { key: "total", label: "Incentive", align: "right", mono: true, render: (r) => inr(r.total) },
          ]}
          rows={(d.executiveIncentive && d.executiveIncentive.executives) || []}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Lead source mix (MTD)</h3>
          <Table
            rowKey="source"
            empty="No leads yet"
            columns={[
              { key: "source", label: "Source", render: (r) => <span className="font-semibold">{r.source}</span> },
              { key: "count", label: "Count", align: "right" },
            ]}
            rows={d.sourceMix || []}
          />
        </Card>
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Model mix (MTD)</h3>
          <Table
            rowKey="model"
            empty="No models yet"
            columns={[
              { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
              { key: "leads", label: "L", align: "right" },
              { key: "bookings", label: "B", align: "right" },
              { key: "deliveries", label: "D", align: "right" },
            ]}
            rows={d.modelMix || []}
          />
        </Card>
      </div>

      <div className="mt-6">
        <YardStockCard />
      </div>
    </div>
  );
}
