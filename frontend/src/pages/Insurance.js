import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

export default function Insurance() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/insurance").then(setRows); }, []);
  return (
    <div>
      <PageHeader title="Insurance Payouts" subtitle="Premium entries & insurer payout tracking" />
      <Table
        rowKey="entryId"
        columns={[
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "model", label: "Vehicle", render: (r) => <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div> },
          { key: "insuranceCompany", label: "Insurer" },
          { key: "insuranceAmount", label: "Premium", align: "right", mono: true, render: (r) => inr(r.insuranceAmount) },
          { key: "payoutRate", label: "Rate %", align: "right", render: (r) => `${(r.payoutRate * 100).toFixed(1)}%` },
          { key: "expectedPayout", label: "Expected", align: "right", mono: true, render: (r) => inr(r.expectedPayout) },
          { key: "receivedPayout", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedPayout)}</span> },
          { key: "payoutOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => inr(r.payoutOutstanding) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status || "Pending"}</Badge> },
        ]}
        rows={rows}
        empty="No insurance payout entries yet"
      />
    </div>
  );
}
