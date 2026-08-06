import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

export default function Payments() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/payments").then(setRows); }, []);
  const total = rows.reduce((s, r) => s + Number(r.amount || 0), 0);
  return (
    <div>
      <PageHeader title="Payment Ledger" subtitle={`${rows.length} receipts · ${inr(total)} collected`} />
      <Table
        rowKey="receiptNumber"
        columns={[
          { key: "receiptNumber", label: "Receipt", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.receiptNumber}</span> },
          { key: "leadId", label: "Lead", mono: true },
          { key: "customerName", label: "Customer" },
          { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
          { key: "amount", label: "Amount", align: "right", mono: true, render: (r) => <span className="font-semibold">{inr(r.amount)}</span> },
          { key: "paymentMode", label: "Mode", render: (r) => <Badge>{r.paymentMode}</Badge> },
          { key: "outstandingBalance", label: "Balance", align: "right", mono: true, render: (r) => inr(r.outstandingBalance) },
          { key: "narration", label: "Narration" },
        ]}
        rows={rows}
      />
    </div>
  );
}
