import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Landmark } from "lucide-react";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Select, Card } from "../components/ui";

export default function Finance() {
  const [rows, setRows] = useState([]);
  const [view, setView] = useState("all");
  const [receipt, setReceipt] = useState(false);
  const load = useCallback(() => get("/finance", { view }).then(setRows), [view]);
  useEffect(() => { load(); }, [load]);
  const views = [["all", "All Files"], ["pending", "Pending"], ["overdue", "Overdue"]];
  const [allFiles, setAllFiles] = useState([]);
  useEffect(() => { get("/finance", { view: "pending" }).then(setAllFiles); }, [receipt]);
  return (
    <div>
      <PageHeader title="Finance Register" subtitle="Financer files — committed vs disbursed"
        actions={
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
              {views.map(([k, l]) => (
                <button key={k} onClick={() => setView(k)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${view === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>{l}</button>
              ))}
            </div>
            <Button data-testid="record-financer-receipt-btn" onClick={() => setReceipt(true)}><Landmark size={16} /> Record Financer Receipt</Button>
          </div>
        } />
      <Table
        rowKey="fileNumber"
        columns={[
          { key: "fileNumber", label: "File #", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.fileNumber}</span> },
          { key: "customerName", label: "Customer" },
          { key: "financer", label: "Financer", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.financer}</Badge> },
          { key: "sanctionedAmount", label: "Committed", align: "right", mono: true, render: (r) => inr(r.sanctionedAmount) },
          { key: "receivedAgainstFile", label: "Disbursed", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedAgainstFile)}</span> },
          { key: "fileOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.fileOutstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.fileOutstanding)}</span> },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "lastPaymentDate", label: "Last Receipt", render: (r) => fmtDate(r.lastPaymentDate) },
        ]}
        rows={rows}
        empty="No finance files — created automatically when a Finance-mode payment is recorded on a lead"
      />
      {receipt && <FinanceReceiptModal files={allFiles} onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />}
    </div>
  );
}

function FinanceReceiptModal({ files, onClose, onDone }) {
  const [fileNumber, setFileNumber] = useState("");
  const [form, setForm] = useState({ amount: "", date: "", reference: "" });
  const sel = files.find((f) => f.fileNumber === fileNumber);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!sel) return toast.error("Select a finance file");
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    try {
      await post(`/finance/${encodeURIComponent(sel.fileNumber)}/receipt`, { amount: +form.amount, date: form.date, reference: form.reference });
      toast.success("Financer receipt recorded");
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Record Financer Receipt</h3>
        <p className="text-xs text-ink-soft mb-4">Money actually disbursed by the financer. This does not change the customer's outstanding.</p>
        <Field label="Finance file (financer · customer · outstanding)">
          <Select data-testid="finance-receipt-select" value={fileNumber} onChange={(e) => setFileNumber(e.target.value)}>
            <option value="">— Select —</option>
            {files.map((f) => <option key={f.fileNumber} value={f.fileNumber}>{f.fileNumber} · {f.financer} · {f.customerName} · {inr(f.fileOutstanding)}</option>)}
          </Select>
        </Field>
        {sel && (
          <div className="grid grid-cols-3 gap-3 mt-3">
            <Field label="Amount Received (₹)"><Input data-testid="finance-receipt-amount" type="number" value={form.amount} onChange={set("amount")} placeholder={String(sel.fileOutstanding)} /></Field>
            <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
            <Field label="Reference / UTR"><Input value={form.reference} onChange={set("reference")} /></Field>
          </div>
        )}
        {sel && <p className="text-xs text-ink-soft mt-2">Outstanding: <span className="font-mono font-semibold text-red-600">{inr(sel.fileOutstanding)}</span></p>}
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-finance-receipt-btn" onClick={submit}>Record Receipt</Button>
        </div>
      </Card>
    </div>
  );
}
