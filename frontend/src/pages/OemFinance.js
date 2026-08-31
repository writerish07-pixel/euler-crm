import React, { useCallback, useEffect, useState } from "react";
import { Landmark, AlertTriangle, IndianRupee, Clock, RefreshCcw } from "lucide-react";
import { get } from "../lib/api";
import { inr, compactInr, fmtDate } from "../lib/format";
import { PageHeader, Card, StatCard, Table, Badge, Select, Button } from "../components/ui";

const VIEWS = [
  ["all", "All files"],
  ["pending", "Still to receive"],
  ["overdue", "Overdue"],
  ["received", "Fully received"],
];

/**
 * Read-only finance position for the OEM's finance manager.
 *
 * Deliberately carries no contact details — the API builds each row from a
 * whitelist, so there is no mobile or address to hide here in the first place.
 * Identification is by lead number, customer name and vehicle.
 */
export default function OemFinance() {
  const [d, setD] = useState(null);
  const [view, setView] = useState("all");
  const [financer, setFinancer] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    get("/reports/oem-finance", { view, ...(financer ? { financer } : {}) })
      .then((r) => { setD(r); setErr(""); })
      .catch((e) => setErr(e?.response?.data?.detail || "Could not load the report"));
  }, [view, financer]);

  useEffect(() => { load(); }, [load]);

  if (err) return <Card className="p-6 text-sm text-red-700">{err}</Card>;
  if (!d) return <div className="text-sm text-ink-faint">Loading finance position…</div>;

  const t = d.totals;

  return (
    <div data-testid="oem-finance">
      <PageHeader
        title="Retail Finance Position"
        subtitle={`Every finance file, and how long each has been waiting · receipt SLA ${d.slaDays} days`}
        actions={
          <div className="flex gap-2">
            <Select data-testid="oem-view" value={view} onChange={(e) => setView(e.target.value)}
              className="max-w-[12rem]">
              {VIEWS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Select data-testid="oem-financer" value={financer}
              onChange={(e) => setFinancer(e.target.value)} className="max-w-[12rem]">
              <option value="">All financers</option>
              {(d.financers || []).map((f) => <option key={f}>{f}</option>)}
            </Select>
            <Button variant="secondary" onClick={load}><RefreshCcw size={15} /> Refresh</Button>
          </div>
        } />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Files" value={t.files} icon={Landmark} />
        <StatCard label="Still to receive" value={compactInr(t.pending)} icon={IndianRupee}
          tone={t.pending > 0 ? "text-amber-600" : "text-emerald-600"} />
        <StatCard label="Overdue files" value={t.overdueFiles} icon={AlertTriangle}
          tone={t.overdueFiles > 0 ? "text-red-600" : undefined} />
        <StatCard label="Oldest pending" value={`${t.oldestPendingDays} days`} icon={Clock} />
      </div>

      {t.overdueFiles > 0 && (
        <Card className="p-3 mb-6 bg-amber-50 border-amber-200" data-testid="oem-overdue-note">
          <p className="text-sm text-amber-900">
            <b>{t.overdueFiles} file{t.overdueFiles === 1 ? "" : "s"} past the {d.slaDays}-day
            receipt SLA</b> — {inr(t.overdueAmount)} still to come in. Oldest has been waiting{" "}
            {t.oldestPendingDays} days since delivery.
          </p>
        </Card>
      )}

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        <section data-testid="oem-by-financer">
          <h3 className="font-heading font-bold text-ink mb-1">By financer</h3>
          <p className="text-xs text-ink-soft mb-3">Where the money is sitting</p>
          <Table rowKey="financer" rows={d.byFinancer} empty="No finance files"
            columns={[
              { key: "financer", label: "Financer", render: (r) => <span className="font-medium">{r.financer}</span> },
              { key: "files", label: "Files", align: "right" },
              { key: "sanctioned", label: "Sanctioned", align: "right", mono: true, render: (r) => inr(r.sanctioned) },
              { key: "pending", label: "To receive", align: "right", mono: true,
                render: (r) => (r.pending > 0
                  ? <span className="text-amber-700 font-semibold">{inr(r.pending)}</span>
                  : <span className="text-emerald-600">{inr(0)}</span>) },
              { key: "overdue", label: "Overdue", align: "right",
                render: (r) => (r.overdue > 0
                  ? <span className="text-red-600 font-semibold">{r.overdue}</span>
                  : <span className="text-ink-faint">—</span>) },
            ]} />
        </section>

        <section data-testid="oem-ageing">
          <h3 className="font-heading font-bold text-ink mb-1">How long money has been waiting</h3>
          <p className="text-xs text-ink-soft mb-3">Days since the vehicle was delivered</p>
          <Table rowKey="bucket" rows={d.ageing} empty="Nothing pending"
            columns={[
              { key: "bucket", label: "Age", render: (r) => (
                <Badge tone={/15\+|8-15/.test(r.bucket)
                  ? "bg-red-50 text-red-700 ring-red-600/20"
                  : r.bucket === "0-2 days"
                    ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
                    : "bg-amber-50 text-amber-800 ring-amber-600/20"}>{r.bucket}</Badge>
              ) },
              { key: "files", label: "Files", align: "right" },
              { key: "pending", label: "To receive", align: "right", mono: true,
                render: (r) => inr(r.pending) },
            ]} />
        </section>
      </div>

      <section data-testid="oem-files">
        <h3 className="font-heading font-bold text-ink mb-1">Files</h3>
        <p className="text-xs text-ink-soft mb-3">
          Overdue first, then longest waiting. Identified by lead number and vehicle.
        </p>
        <Table rows={d.files} empty="No files match this filter"
          columns={[
            { key: "leadId", label: "Lead", mono: true,
              render: (r) => (
                <div>
                  <div className="font-semibold text-cobalt">{r.leadId}</div>
                  <div className="text-xs text-ink-faint font-sans">{r.customerName}</div>
                </div>
              ) },
            { key: "model", label: "Vehicle",
              render: (r) => (
                <div className="text-sm">
                  <div>{r.model || "—"}</div>
                  <div className="text-xs text-ink-faint">{r.variant}</div>
                </div>
              ) },
            { key: "financer", label: "Financer",
              render: (r) => (
                <div className="text-sm">
                  <div>{r.financer}</div>
                  <div className="text-xs text-ink-faint font-mono">{r.fileNumber}</div>
                </div>
              ) },
            { key: "sanctioned", label: "Sanctioned", align: "right", mono: true, render: (r) => inr(r.sanctioned) },
            { key: "received", label: "Received", align: "right", mono: true,
              render: (r) => <span className="text-emerald-600">{inr(r.received)}</span> },
            { key: "pending", label: "To receive", align: "right", mono: true,
              render: (r) => (r.pending > 0
                ? <span className="text-amber-700 font-semibold">{inr(r.pending)}</span>
                : <span className="text-ink-faint">—</span>) },
            { key: "deliveryDate", label: "Delivered", render: (r) => (
              r.deliveryDate
                ? <div className="text-sm">
                    <div>{fmtDate(r.deliveryDate)}</div>
                    {typeof r.daysSinceDelivery === "number" && (
                      <div className="text-xs text-ink-faint">{r.daysSinceDelivery} days ago</div>
                    )}
                  </div>
                : <span className="text-ink-faint text-xs">not delivered</span>
            ) },
            { key: "status", label: "Status", align: "right", render: (r) => (
              r.overdue
                ? <Badge tone="bg-red-50 text-red-700 ring-red-600/20">Overdue</Badge>
                : r.pending > 0
                  ? <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20">Pending</Badge>
                  : <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">Received</Badge>
            ) },
          ]} />
      </section>

      <p className="text-xs text-ink-faint mt-4">
        Read-only. Customer contact details are not part of this report.
      </p>
    </div>
  );
}
