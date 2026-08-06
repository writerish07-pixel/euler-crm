import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

export default function Finance() {
  const [rows, setRows] = useState([]);
  const [view, setView] = useState("all");
  useEffect(() => { get("/finance", { view }).then(setRows); }, [view]);
  const views = [["all", "All Files"], ["pending", "Pending"], ["overdue", "Overdue"]];
  return (
    <div>
      <PageHeader title="Finance Register" subtitle="Financer files — sanctioned vs received"
        actions={
          <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
            {views.map(([k, l]) => (
              <button key={k} onClick={() => setView(k)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${view === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>{l}</button>
            ))}
          </div>
        } />
      <Table
        rowKey="fileNumber"
        columns={[
          { key: "fileNumber", label: "File #", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.fileNumber}</span> },
          { key: "customerName", label: "Customer" },
          { key: "financer", label: "Financer", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.financer}</Badge> },
          { key: "sanctionedAmount", label: "Sanctioned", align: "right", mono: true, render: (r) => inr(r.sanctionedAmount) },
          { key: "receivedAgainstFile", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedAgainstFile)}</span> },
          { key: "fileOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.fileOutstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.fileOutstanding)}</span> },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "lastPaymentDate", label: "Last Payment", render: (r) => fmtDate(r.lastPaymentDate) },
        ]}
        rows={rows}
        empty="No finance files — created automatically when a Finance-mode payment is recorded"
      />
    </div>
  );
}
