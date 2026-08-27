import React, { useCallback, useEffect, useState } from "react";
import { Ban, Users, IndianRupee, RotateCcw } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { get } from "../lib/api";
import { inr, compactInr, fmtDate } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Select } from "../components/ui";

const PERIODS = [
  ["month", "This month"],
  ["today", "Today"],
  ["all", "All time"],
];

// Stage is the axis that matters. A lead lost at Enquiry cost a phone call; one
// lost after Booked cost a refund and a chassis that stopped being sellable —
// so they are coloured apart and never summed into one "cancellations" figure.
const STAGE_TONE = {
  Enquiry: "bg-zinc-100 text-zinc-700 ring-zinc-500/20",
  Booked: "bg-amber-50 text-amber-800 ring-amber-600/20",
  Finance: "bg-orange-50 text-orange-800 ring-orange-600/20",
  Delivered: "bg-rose-50 text-rose-700 ring-rose-600/20",
};

export default function Cancellations() {
  const [d, setD] = useState(null);
  const [period, setPeriod] = useState("month");
  const [executive, setExecutive] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    get("/reports/cancellations", {
      period, ...(executive ? { executive } : {}), ...(reason ? { reason } : {}),
    }).then(setD).catch(() => {});
  }, [period, executive, reason]);

  useEffect(() => { load(); }, [load]);

  if (!d) return <div className="text-ink-faint text-sm">Loading cancellations…</div>;

  const chart = d.byExecutive.slice(0, 8).map((r) => ({
    name: r.executive || "Unassigned", Cancelled: r.count,
  }));

  return (
    <div data-testid="cancellations-page">
      <PageHeader
        title="Cancellations"
        subtitle="Who is losing leads, why, and how far down the funnel they got"
        actions={
          <div className="flex gap-2">
            <Select data-testid="cancel-period" value={period}
              onChange={(e) => setPeriod(e.target.value)} className="max-w-[10rem]">
              {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Select data-testid="cancel-exec-filter" value={executive}
              onChange={(e) => setExecutive(e.target.value)} className="max-w-[12rem]">
              <option value="">All executives</option>
              {d.byExecutive.map((r) => (
                <option key={r.executive || "none"} value={r.executive}>{r.executive || "Unassigned"}</option>
              ))}
            </Select>
          </div>
        } />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Cancellations" value={d.total} icon={Ban} tone="text-rose-600" />
        <StatCard label="Back in the funnel" value={d.revived} icon={RotateCcw} tone="text-emerald-600" />
        <StatCard label="Still parked" value={d.parked} icon={Users} />
        <StatCard label="Still to refund" value={compactInr(d.moneyAtRisk)} icon={IndianRupee}
          tone={d.moneyAtRisk > 0 ? "text-amber-600" : undefined} />
      </div>

      {d.withMoney > 0 && (
        <Card className="p-3 mb-6 bg-amber-50 border-amber-200" data-testid="cancel-money-note">
          <p className="text-sm text-amber-900">
            <b>{d.withMoney} cancelled lead{d.withMoney === 1 ? "" : "s"} still hold customer money</b> — {inr(d.moneyAtRisk)} in total.
            Cancelling never reverses a receipt. Open each lead's Payments tab and use
            Refund Customer to return it.
          </p>
        </Card>
      )}

      {d.byExecutive.length > 0 && (
        <Card className="p-5 mb-6">
          <h3 className="font-heading font-bold text-ink mb-4">By Executive</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#52525B" }} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false}
                  tick={{ fontSize: 11, fill: "#A1A1AA" }} width={32} />
                <Tooltip cursor={{ fill: "#F4F4F5" }}
                  contentStyle={{ borderRadius: 10, border: "1px solid #E4E4E7", fontSize: 13 }} />
                <Bar dataKey="Cancelled" fill="#E11D48" radius={[6, 6, 0, 0]} maxBarSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        <section data-testid="cancel-by-reason">
          <h3 className="font-heading font-bold text-ink mb-1">Why</h3>
          <p className="text-xs text-ink-soft mb-3">
            The reason also decides whether the lead comes back — set that in Settings
          </p>
          <Table rowKey="reason" rows={d.byReason} empty="Nothing cancelled in this period"
            onRowClick={(r) => setReason(reason === r.reason ? "" : r.reason)}
            columns={[
              { key: "reason", label: "Reason", render: (r) => <span className="font-medium">{r.reason}</span> },
              { key: "count", label: "Leads", align: "right" },
              { key: "money", label: "To refund", align: "right", mono: true,
                render: (r) => (r.money > 0 ? inr(r.money) : <span className="text-ink-faint">—</span>) },
            ]} />
          {reason && (
            <button className="mt-3 text-xs text-cobalt hover:underline" onClick={() => setReason("")}>
              Clear "{reason}" filter
            </button>
          )}
        </section>

        <section data-testid="cancel-by-stage">
          <h3 className="font-heading font-bold text-ink mb-1">How far they got</h3>
          <p className="text-xs text-ink-soft mb-3">
            An enquiry that fizzled and a booking that collapsed are not the same loss
          </p>
          <Table rowKey="stage" rows={d.byStage} empty="Nothing cancelled in this period"
            columns={[
              { key: "stage", label: "Stage",
                render: (r) => <Badge tone={STAGE_TONE[r.stage]}>{r.stage}</Badge> },
              { key: "count", label: "Leads", align: "right" },
              { key: "money", label: "To refund", align: "right", mono: true,
                render: (r) => (r.money > 0 ? inr(r.money) : <span className="text-ink-faint">—</span>) },
            ]} />
        </section>
      </div>

      <section data-testid="cancel-events">
        <h3 className="font-heading font-bold text-ink mb-1">Every cancellation</h3>
        <p className="text-xs text-ink-soft mb-3">
          A lead cancelled more than once appears once per cancellation
        </p>
        <Table rows={d.events} empty="No cancellations in this period"
          columns={[
            { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
            { key: "customerName", label: "Customer",
              render: (r) => (
                <div>
                  <div className="font-medium">{r.customerName}</div>
                  <div className="text-xs text-ink-faint">{r.leadId}{r.model ? ` · ${r.model}` : ""}</div>
                </div>
              ) },
            { key: "executive", label: "Executive", render: (r) => r.executive || "—" },
            { key: "reason", label: "Reason",
              render: (r) => (
                <div>
                  <div>{r.reason}</div>
                  {r.remarks && <div className="text-xs text-ink-faint">{r.remarks}</div>}
                </div>
              ) },
            { key: "stage", label: "Stage",
              render: (r) => <Badge tone={STAGE_TONE[r.stage]}>{r.stage}</Badge> },
            // Two columns because they answer different questions: what was at
            // stake when the deal died, and what is still owed back today.
            { key: "customerMoney", label: "At stake", align: "right", mono: true,
              render: (r) => (r.customerMoney > 0 ? inr(r.customerMoney) : <span className="text-ink-faint">—</span>) },
            { key: "moneyToRefund", label: "To refund", align: "right", mono: true,
              render: (r) => (r.moneyToRefund > 0
                ? <span className="text-amber-700 font-semibold">{inr(r.moneyToRefund)}</span>
                : <span className="text-ink-faint">—</span>) },
            { key: "currentAccountStatus", label: "Now", align: "right",
              render: (r) => (!r.isLatest
                ? <Badge tone="bg-zinc-100 text-zinc-500 ring-zinc-400/20"
                    title={`Cancellation ${r.sequence} of ${r.cancelCount} on this lead`}>
                    Superseded
                  </Badge>
                : String(r.currentAccountStatus).toLowerCase() === "cancelled"
                  ? <Badge tone="bg-zinc-100 text-zinc-700 ring-zinc-500/20">
                      {r.reviveOn ? `Returns ${fmtDate(r.reviveOn)}` : "Parked"}
                    </Badge>
                  : <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">In funnel</Badge>) },
          ]} />
      </section>
    </div>
  );
}
