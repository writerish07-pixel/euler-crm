import React, { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Trash2, Wallet, X } from "lucide-react";
import { del, get, post } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Table, Badge, Card, Field, Input, Select, Button } from "../components/ui";
import PeriodBar from "../components/PeriodBar";
import { usePeriodState } from "../lib/period";

export default function Payments() {
  const { isOwner } = useAuth();
  const [params, setParams] = useSearchParams();
  const leadId = params.get("leadId") || params.get("lead_id") || "";
  const [rows, setRows] = useState([]);
  const [lead, setLead] = useState(null);
  const [masters, setMasters] = useState(null);
  const period = usePeriodState();
  const load = useCallback(() => {
    get("/payments", { ...period.params, ...(leadId ? { lead_id: leadId } : {}) }).then(setRows);
  }, [period.params, leadId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { get("/masters").then(setMasters).catch(() => setMasters(null)); }, []);
  useEffect(() => {
    if (!leadId) { setLead(null); return undefined; }
    get(`/leads/${leadId}`).then(setLead).catch(() => setLead(null));
    return undefined;
  }, [leadId]);

  const clearLead = () => {
    const next = new URLSearchParams(params);
    next.delete("leadId");
    next.delete("lead_id");
    setParams(next, { replace: true });
  };

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
  const subtitle = leadId
    ? `${lead?.customerName || leadId} · ${rows.length} receipts · ${inr(total)}`
    : `${rows.length} receipts · ${inr(total)} collected`;
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
      <PageHeader title="Payment Ledger" subtitle={subtitle} />
      {leadId && (
        <div className="flex flex-wrap items-center gap-2 mb-3 text-sm" data-testid="payments-lead-filter">
          <span className="text-ink-soft">Showing receipts for</span>
          <Badge>{lead?.customerName || leadId} · {leadId}</Badge>
          <button type="button" className="inline-flex items-center gap-1 text-xs text-cobalt" onClick={clearLead} data-testid="payments-show-all">
            <X size={12} /> Show all leads
          </button>
          <Link to="/accounts" className="text-xs text-ink-faint ml-auto">Back to Accounts</Link>
        </div>
      )}
      {leadId && <AddReceiptForm leadId={leadId} masters={masters} onSaved={load} />}
      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
      <Table rowKey="receiptNumber" columns={columns} rows={rows} />
    </div>
  );
}

function AddReceiptForm({ leadId, masters, onSaved }) {
  const [form, setForm] = useState({ amount: "", paymentMode: "Cash", narration: "", financerName: "", financeFileNumber: "", date: todayISO() });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const add = async (allowExcess = false) => {
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    if (!form.date) return toast.error("Payment date is required");
    if (form.paymentMode === "Finance" && !form.financerName) return toast.error("Select a Financer for a Finance receipt");
    try {
      await post(`/leads/${leadId}/payments`, { ...form, amount: +form.amount, allowExcess });
      toast.success(`Receipt added · ${inr(+form.amount)}`);
      setForm({ amount: "", paymentMode: "Cash", narration: "", financerName: "", financeFileNumber: "", date: todayISO() });
      onSaved();
    } catch (e) {
      const detail = e?.response?.data?.detail || "Could not add receipt";
      if (!allowExcess && /excess payment/i.test(detail)) {
        if (window.confirm(`${detail}\n\nRecord ₹${+form.amount} anyway and hold the surplus as excess?`)) {
          return add(true);
        }
        return undefined;
      }
      toast.error(detail);
    }
    return undefined;
  };
  return (
    <Card className="p-4 mb-4" data-testid="payments-add-receipt">
      <div className="text-sm font-semibold text-ink mb-3">Add receipt for this lead</div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 items-end">
        <Field label="Amount (₹)"><Input data-testid="ledger-payment-amount" type="number" value={form.amount} onChange={set("amount")} /></Field>
        <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
        <Field label="Mode">
          <Select value={form.paymentMode} onChange={set("paymentMode")}>
            {(masters?.paymentModes || ["Cash", "UPI", "Cheque", "NEFT", "Finance"]).map((m) => <option key={m}>{m}</option>)}
          </Select>
        </Field>
        <Field label="Narration"><Input value={form.narration} onChange={set("narration")} /></Field>
        <Button data-testid="ledger-add-payment-btn" onClick={() => add(false)}><Wallet size={15} /> Add Receipt</Button>
      </div>
      {form.paymentMode === "Finance" && (
        <div className="grid grid-cols-2 gap-3 mt-3">
          <Field label="Financer">
            <Select value={form.financerName} onChange={set("financerName")}><option value="">—</option>{(masters?.financers || []).map((f) => <option key={f}>{f}</option>)}</Select>
          </Field>
          <Field label="Finance File Number"><Input value={form.financeFileNumber} onChange={set("financeFileNumber")} placeholder="Auto-generated on save" /></Field>
        </div>
      )}
    </Card>
  );
}
