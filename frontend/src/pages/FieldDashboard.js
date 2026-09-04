import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Users, ClipboardCheck, Truck, TrendingUp, AlertCircle, Landmark,
  ReceiptText, Percent, Map, Warehouse, CalendarDays,
} from "lucide-react";
import { toast } from "sonner";
import { get } from "../lib/api";
import { compactInr, num, ytdCount } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button } from "../components/ui";
import YardStockCard from "../components/YardStockCard";

/** Shared home for company ASM and RM — retail + pipeline hygiene. */
export default function FieldDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => {
    get("/field/dashboard").then(setD).catch(() => toast.error("Could not load field dashboard"));
  }, []);

  if (!d) return <div className="text-ink-faint text-sm">Loading field dashboard…</div>;
  const k = d.kpis || {};

  return (
    <div data-testid="field-dashboard">
      <PageHeader
        title="Field Dashboard"
        subtitle={`ASM / RM · company retail · MTD + YTD · updated ${d.lastUpdated ? new Date(d.lastUpdated).toLocaleTimeString("en-IN") : "—"}`}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="field-period-kpis">
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
        <StatCard label="Scheme use rate" value={`${k.schemeUseRate || 0}%`} icon={Percent} tone="text-amber-600" />
        <StatCard label="OEM claims open" value={compactInr(k.oemClaimsOpen)}
          sub={`${k.oemClaimsOpenCount || 0} lines · ${k.lostCount || 0} lost`} icon={ReceiptText} tone="text-amber-700" />
      </div>

      <div className="flex flex-wrap gap-2 mt-5">
        <Link to="/monthly"><Button variant="secondary" data-testid="field-go-monthly"><CalendarDays size={14} /> Monthly Register</Button></Link>
        <Link to="/leads"><Button variant="secondary" data-testid="field-go-leads"><Users size={14} /> Lead Register</Button></Link>
        <Link to="/bookings"><Button variant="secondary" data-testid="field-go-bookings"><ClipboardCheck size={14} /> Bookings</Button></Link>
        <Link to="/deliveries"><Button variant="secondary" data-testid="field-go-deliveries"><Truck size={14} /> Deliveries</Button></Link>
        <Link to="/finance"><Button variant="secondary" data-testid="field-go-finance"><Landmark size={14} /> Finance Register</Button></Link>
        <Link to="/inventory"><Button variant="secondary" data-testid="field-go-inventory"><Warehouse size={14} /> Inventory</Button></Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Map size={16} className="text-ink-faint" />
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

      <div className="mt-6">
        <YardStockCard />
      </div>
    </div>
  );
}
