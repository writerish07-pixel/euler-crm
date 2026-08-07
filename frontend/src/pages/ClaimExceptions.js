import React, { useEffect, useState } from "react";
import { ShieldAlert, CheckCircle2 } from "lucide-react";
import { get } from "../lib/api";
import { Card, PageHeader, Table, Badge } from "../components/ui";

const SEV_TONE = {
  High: "bg-red-50 text-red-700 ring-red-600/20",
  Medium: "bg-amber-50 text-amber-700 ring-amber-600/20",
  Info: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
};

export default function ClaimExceptions() {
  const [d, setD] = useState(null);
  useEffect(() => { get("/reports/claim-exceptions").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="text-ink-faint text-sm">Reconciling claims…</div>;
  return (
    <div data-testid="claim-exceptions-report">
      <PageHeader title="Claim Exception Report" subtitle="Owner · reconciliation of claims, payments & data integrity" />
      {d.count === 0 ? (
        <Card className="p-8 flex flex-col items-center gap-3 text-center" data-testid="no-exceptions">
          <CheckCircle2 size={40} className="text-emerald-500" />
          <div className="font-heading font-bold text-ink">No exceptions found</div>
          <div className="text-sm text-ink-soft">Every booking reconciles cleanly against the claim register.</div>
        </Card>
      ) : (
        <>
          <div className="flex items-center gap-2 mb-4 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 w-fit">
            <ShieldAlert size={16} /> {d.count} exception{d.count > 1 ? "s" : ""} need attention
          </div>
          <Table rowKey="_k"
            columns={[
              { key: "leadId", label: "Lead", render: (r) => <span className="font-mono font-semibold">{r.leadId}</span> },
              { key: "type", label: "Exception", render: (r) => <span className="font-semibold">{r.type}</span> },
              { key: "severity", label: "Severity", render: (r) => <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ring-1 ring-inset ${SEV_TONE[r.severity] || SEV_TONE.Info}`}>{r.severity}</span> },
              { key: "detail", label: "Detail", render: (r) => <span className="text-ink-soft">{r.detail || "—"}</span> },
            ]}
            rows={d.exceptions.map((e, i) => ({ ...e, _k: `${e.leadId}-${e.type}-${i}` }))} empty="No exceptions" />
        </>
      )}
    </div>
  );
}
