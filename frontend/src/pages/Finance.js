import React, { useEffect, useMemo, useState, useCallback } from "react";
import { toast } from "sonner";
import { Landmark } from "lucide-react";
import { get, post } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Select, Card, Modal } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import PeriodBar from "../components/PeriodBar";
import { usePeriodState } from "../lib/period";

function financerRollup(rows) {
  const map = new Map();
  for (const r of rows || []) {
    const key = (r.financer || "—").trim() || "—";
    const cur = map.get(key) || {
      financer: key,
      files: 0,
      pendingFiles: 0,
      sanctionedAmount: 0,
      receivedAgainstFile: 0,
      fileOutstanding: 0,
    };
    cur.files += 1;
    cur.sanctionedAmount += Number(r.sanctionedAmount) || 0;
    cur.receivedAgainstFile += Number(r.receivedAgainstFile) || 0;
    cur.fileOutstanding += Number(r.fileOutstanding) || 0;
    if ((Number(r.fileOutstanding) || 0) > 0 && r.status !== "Received") cur.pendingFiles += 1;
    map.set(key, cur);
  }
  return [...map.values()].sort((a, b) => b.fileOutstanding - a.fileOutstanding || a.financer.localeCompare(b.financer));
}

export default function Finance() {
  const { isMoneyDesk, isField, isExecutive } = useAuth();
  const [rows, setRows] = useState([]);
  const [view, setView] = useState("all");
  const [receipt, setReceipt] = useState(false);
  const period = usePeriodState();
  const load = useCallback(() => get("/finance", { view, ...period.params }).then(setRows), [view, period.params]);
  useEffect(() => { load(); }, [load]);
  const views = [["all", "All Files"], ["pending", "Pending"], ["overdue", "Overdue"]];
  const [allFiles, setAllFiles] = useState([]);
  useEffect(() => {
    if (!isMoneyDesk) return undefined;
    get("/finance", { view: "pending" }).then(setAllFiles);
    return undefined;
  }, [receipt, isMoneyDesk]);

  const byFinancer = useMemo(() => financerRollup(rows), [rows]);

  return (
    <div data-testid="finance-register">
      <PageHeader
        title="Finance Register"
        subtitle={isExecutive
          ? "Your finance files only — disbursed vs still outstanding"
          : isField && !isMoneyDesk
          ? "Read-only · which financer has paid vs still outstanding"
          : "Financer files — committed vs disbursed"}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
              {views.map(([k, l]) => (
                <button key={k} onClick={() => setView(k)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${view === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>{l}</button>
              ))}
            </div>
            {isMoneyDesk && (
              <Button data-testid="record-financer-receipt-btn" onClick={() => setReceipt(true)}>
                <Landmark size={16} /> Record Financer Receipt
              </Button>
            )}
          </div>
        }
      />

      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />

      {byFinancer.length > 0 && (
        <Card className="p-5 mb-6" data-testid="finance-by-financer">
          <h3 className="font-heading font-bold text-ink mb-1">By financer</h3>
          <p className="text-xs text-ink-soft mb-3">Disbursed vs remaining for the current view</p>
          <Table
            rowKey="financer"
            columns={[
              { key: "financer", label: "Financer", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.financer}</Badge> },
              { key: "files", label: "Files", align: "right" },
              { key: "pendingFiles", label: "Pending", align: "right", render: (r) => (
                r.pendingFiles ? <span className="text-amber-700 font-semibold">{r.pendingFiles}</span> : "—"
              ) },
              { key: "sanctionedAmount", label: "Committed", align: "right", mono: true, render: (r) => inr(r.sanctionedAmount) },
              { key: "receivedAgainstFile", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedAgainstFile)}</span> },
              { key: "fileOutstanding", label: "Remaining", align: "right", mono: true, render: (r) => (
                <span className={r.fileOutstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.fileOutstanding)}</span>
              ) },
            ]}
            rows={byFinancer}
          />
        </Card>
      )}

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
      {receipt && isMoneyDesk && (
        <FinanceReceiptModal files={allFiles} onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />
      )}
    </div>
  );
}

function FinanceReceiptModal({ files, onClose, onDone }) {
  const [fileNumber, setFileNumber] = useState("");
  const [form, setForm] = useState({ amount: "", date: todayISO(), reference: "" });
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
    <Modal onClose={onClose} width="max-w-lg">
      <div className="overflow-y-auto overscroll-contain p-6">
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
      </div>
    </Modal>
  );
}
