import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { del, get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Table, Badge } from "../components/ui";

export default function Payments() {
  const { isOwner } = useAuth();
  const [rows, setRows] = useState([]);
  const load = useCallback(() => { get("/payments").then(setRows); }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async (r) => {
    const label = r.entryType === "Refund" ? "refund" : "receipt";
    if (!window.confirm(`Permanently delete ${label} ${r.receiptNumber} (${inr(r.amount)}) for ${r.leadId}? This cannot be undone.`)) return;
    try {
      await del(`/payments/${r.receiptNumber}`);
      toast.success(`${r.receiptNumber} deleted`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  const total = rows.reduce((s, r) => s + Number(r.amount || 0), 0);
  const columns = [
    { key: "receiptNumber", label: "Receipt", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.receiptNumber}</span> },
    { key: "leadId", label: "Lead", mono: true },
    { key: "customerName", label: "Customer" },
    { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
    { key: "amount", label: "Amount", align: "right", mono: true, render: (r) => <span className="font-semibold">{inr(r.amount)}</span> },
    { key: "paymentMode", label: "Mode", render: (r) => <Badge>{r.entryType === "Refund" ? "Refund" : r.paymentMode}</Badge> },
    { key: "outstandingBalance", label: "Balance", align: "right", mono: true, render: (r) => inr(r.outstandingBalance) },
    { key: "narration", label: "Narration" },
    ...(isOwner ? [{
      key: "act", label: "", align: "right",
      render: (r) => (
        <button
          type="button"
          data-testid={`delete-payment-${r.receiptNumber}`}
          onClick={(e) => { e.stopPropagation(); remove(r); }}
          className="text-ink-faint hover:text-red-600 inline-flex items-center"
          title="Delete receipt"
        >
          <Trash2 size={15} />
        </button>
      ),
    }] : []),
  ];
  return (
    <div>
      <PageHeader title="Payment Ledger" subtitle={`${rows.length} receipts · ${inr(total)} collected`} />
      <Table rowKey="receiptNumber" columns={columns} rows={rows} />
    </div>
  );
}
