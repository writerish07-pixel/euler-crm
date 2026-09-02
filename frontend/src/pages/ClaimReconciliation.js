import React, { useEffect, useState } from "react";
import { Scale, AlertTriangle, XCircle } from "lucide-react";
import { get } from "../lib/api";
import { inr } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge } from "../components/ui";

// Three numbers that have never been comparable before:
//   entitled — what Scheme Master says Euler owes on this lead
//   filed    — what was actually claimed in Coulson, matched on chassis
//   approved — what Euler has actually agreed to
// The gaps between them are the whole point of the page.
export default function ClaimReconciliation() {
  const [d, setD] = useState(null);

  useEffect(() => {
    get("/reports/claim-reconciliation").then(setD).catch(() => setD(null));
  }, []);

  if (!d) return <div className="text-ink-faint text-sm">Loading reconciliation…</div>;

  const { totals, rows } = d;
  const neverFiled = rows.filter((r) => r.neverFiled > 0.01);
  const rejected = rows.filter((r) => r.rejected > 0.01);

  return (
    <div>
      <PageHeader
        title="Claim Reconciliation"
        subtitle="Scheme Master entitlement against what was actually filed with Euler"
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6" data-testid="reconciliation-totals">
        <StatCard label="Entitled (Scheme Master)" value={inr(totals.entitled)} icon={Scale} />
        <StatCard label="Filed with Euler" value={inr(totals.filed)} tone="text-cobalt" />
        <StatCard label="Approved by Euler" value={inr(totals.approved)} tone="text-emerald-600" />
        <StatCard label="Never Filed" value={inr(totals.neverFiled)}
          sub={`${neverFiled.length} leads`} icon={AlertTriangle} tone="text-rose-600" />
      </div>

      {totals.neverFiled > 0.01 && (
        <Card className="mb-6 p-4 border-amber-200 bg-amber-50/50">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="text-amber-700 shrink-0 mt-0.5" />
            <div className="text-sm text-ink-soft">
              <span className="font-semibold text-amber-900">
                {inr(totals.neverFiled)} of entitlement has no matching claim in Coulson.
              </span>{" "}
              That is either money nobody has asked Euler for, or a claim whose chassis does
              not match the lead. Both are worth opening before month end.
            </div>
          </div>
        </Card>
      )}

      {rejected.length > 0 && (
        <Card className="mb-6 p-4 border-rose-200">
          <div className="flex items-center gap-2 mb-2 text-rose-700 font-semibold text-sm">
            <XCircle size={16} /> {inr(totals.rejected)} rejected by Euler on {rejected.length} lead(s)
          </div>
          <p className="text-xs text-ink-faint">
            If the Scheme Claim Register still shows these as eligible, the books are
            carrying a receivable that will not arrive.
          </p>
        </Card>
      )}

      <Table
        rowKey="leadId"
        columns={[
          { key: "leadId", label: "Lead", mono: true,
            render: (r) => <span className="font-semibold text-cobalt">{r.leadId}</span> },
          { key: "customer", label: "Customer", render: (r) => (
            <div>
              <div className="font-semibold text-ink">{r.customer || "—"}</div>
              <div className="text-xs text-ink-faint">{r.model}</div>
            </div>
          )},
          { key: "chassisNumber", label: "Chassis", mono: true, render: (r) => (
            <span className="text-xs">{r.chassisNumber || "—"}</span>
          )},
          { key: "entitled", label: "Entitled", align: "right", mono: true,
            render: (r) => inr(r.entitled) },
          { key: "filed", label: "Filed", align: "right", mono: true,
            render: (r) => <span className={r.filed > 0 ? "text-cobalt" : "text-ink-faint"}>{inr(r.filed)}</span> },
          { key: "approved", label: "Approved", align: "right", mono: true,
            render: (r) => <span className={r.approved > 0 ? "text-emerald-600 font-semibold" : "text-ink-faint"}>{inr(r.approved)}</span> },
          { key: "neverFiled", label: "Gap", align: "right", mono: true, render: (r) => (
            <span className={r.neverFiled > 0.01 ? "text-rose-600 font-semibold" : "text-ink-faint"}>
              {inr(r.neverFiled)}
            </span>
          )},
          { key: "oemStatuses", label: "With Euler", render: (r) => (
            r.claimNumbers.length ? (
              <div className="flex flex-col gap-1 items-start">
                {r.claimNumbers.map((n) => (
                  <span key={n} className="font-mono text-[11px] text-ink-faint">{n}</span>
                ))}
                {r.oemStatuses.map((s) => <Badge key={s}>{s}</Badge>)}
              </div>
            ) : <Badge tone="bg-rose-50 text-rose-700 ring-rose-600/20">No claim filed</Badge>
          )},
        ]}
        rows={rows}
        empty="No leads carry scheme entitlement yet"
      />

      <p className="text-xs text-ink-faint mt-4">{d.note}</p>
    </div>
  );
}
