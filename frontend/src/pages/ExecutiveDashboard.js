import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Users, ClipboardCheck, Truck, TrendingUp, AlertCircle, Landmark,
  IndianRupee, Activity, ClipboardList,
} from "lucide-react";
import { toast } from "sonner";
import { get } from "../lib/api";
import { inr, compactInr, num } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button } from "../components/ui";

export default function ExecutiveDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => {
    get("/executive/dashboard").then(setD).catch(() => toast.error("Could not load executive dashboard"));
  }, []);

  if (!d) return <div className="text-ink-faint text-sm">Loading executive dashboard…</div>;
  const k = d.kpis || {};
  const scope = d.scope || {};

  return (
    <div data-testid="executive-dashboard">
      <PageHeader
        title="Executive Dashboard"
        subtitle={`${scope.note || "My pipeline"} · ${scope.matchedLeads || 0} leads · updated ${d.lastUpdated ? new Date(d.lastUpdated).toLocaleTimeString("en-IN") : "—"}`}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="My leads (MTD)" value={num(k.myLeadsMtd)} sub={`${k.todayLeads || 0} today`} icon={Users} />
        <StatCard label="My bookings (MTD)" value={num(k.myBookingsMtd)} sub={`${k.activeBookings || 0} active`} icon={ClipboardCheck} tone="text-emerald-600" />
        <StatCard label="My deliveries (MTD)" value={num(k.myDeliveriesMtd)} sub={`${k.pendingDeliveries || 0} pending`} icon={Truck} tone="text-cobalt" />
        <StatCard label="Conversion" value={`${k.conversion || 0}%`} sub="bookings ÷ MTD leads" icon={TrendingUp} tone="text-violet-600" />
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
        <StatCard label="Follow-ups due" value={num(k.followupDue)} icon={ClipboardCheck} tone="text-amber-600" />
        <StatCard label="Follow-ups overdue" value={num(k.followupOverdue)} icon={AlertCircle} tone="text-red-600" />
        <StatCard label="Finance stuck" value={num(k.financeStuck)} icon={Landmark} tone="text-violet-600" />
        <StatCard label="Customer OS (mine)" value={compactInr(k.customerOutstanding)} icon={IndianRupee} tone="text-red-600" />
      </div>

      <div className="flex flex-wrap gap-2 mt-5">
        <Link to="/leads"><Button variant="secondary" data-testid="exec-go-leads"><Users size={14} /> Leads</Button></Link>
        <Link to="/bookings"><Button variant="secondary" data-testid="exec-go-bookings"><ClipboardList size={14} /> Bookings</Button></Link>
        <Link to="/activities"><Button variant="secondary" data-testid="exec-go-activities"><Activity size={14} /> Activities</Button></Link>
        <Link to="/deliveries"><Button variant="secondary" data-testid="exec-go-deliveries"><Truck size={14} /> Deliveries</Button></Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card className="p-5 lg:col-span-2">
          <h3 className="font-heading font-bold text-ink mb-3">Today’s worklist</h3>
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
              { key: "model", label: "Model" },
              { key: "status", label: "Status" },
              { key: "date", label: "Date", mono: true },
            ]}
            rows={d.worklist || []}
          />
        </Card>

        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">My funnel</h3>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Lead source mix</h3>
          <Table
            rowKey="source"
            empty="No leads in scope"
            columns={[
              { key: "source", label: "Source", render: (r) => <span className="font-semibold">{r.source}</span> },
              { key: "count", label: "Leads", align: "right" },
            ]}
            rows={d.sourceMix || []}
          />
        </Card>
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Model mix</h3>
          <Table
            rowKey="model"
            empty="No models yet"
            columns={[
              { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
              { key: "leads", label: "Leads", align: "right" },
              { key: "bookings", label: "Books", align: "right" },
              { key: "deliveries", label: "Del.", align: "right" },
              { key: "pending", label: "Pending", align: "right", render: (r) => r.pending || "—" },
            ]}
            rows={d.modelMix || []}
          />
        </Card>
      </div>
    </div>
  );
}
