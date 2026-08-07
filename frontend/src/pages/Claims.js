import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { HandCoins } from "lucide-react";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Select, Card } from "../components/ui";

export default function Claims() {
  const [rows, setRows] = useState([]);
  const [active, setActive] = useState(null);
  const [receipt, setReceipt] = useState(false);
  const load = useCallback(() => get("/claims").then(setRows), []);
  useEffect(() => { load(); }, [load]);

  const eligible = rows.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
  const outstandingRows = rows.filter((r) => Number(r.eligibleClaim || 0) - Number(r.receivedAmount || 0) > 0.01);

  return (
    <div>
      <PageHeader title="OEM Claim Register" subtitle={`${rows.length} claimable components · ${inr(eligible)} eligible`}
        actions={<Button data-testid="record-claim-receipt-btn" onClick={() => setReceipt(true)}><HandCoins size={16} /> Record Claim Received</Button>} />
      <Table
        rowKey="claimId"
        onRowClick={setActive}
        columns={[
          { key: "leadId", label: "Lead", mono: true },
          { key: "customer", label: "Customer", render: (r) => <span className="font-semibold">{r.customer}</span> },
          { key: "model", label: "Vehicle" },
          { key: "component", label: "Component", render: (r) => <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.component}</Badge> },
          { key: "claimAmount", label: "Claim Amount", align: "right", mono: true, render: (r) => inr(r.claimAmount) },
          { key: "eligibleClaim", label: "Eligible", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.eligibleClaim)}</span> },
          { key: "receivedAmount", label: "Received", align: "right", mono: true, render: (r) => inr(r.receivedAmount) },
          { key: "outstanding", label: "Outstanding", align: "right", mono: true, render: (r) => { const o = Number(r.eligibleClaim || 0) - Number(r.receivedAmount || 0); return <span className={o > 0.01 ? "text-red-600 font-semibold" : ""}>{inr(Math.max(0, o))}</span>; } },
          { key: "claimStatus", label: "Status", render: (r) => <Badge>{r.claimStatus}</Badge> },
        ]}
        rows={rows}
        empty="No claimable scheme components — apply schemes on booked leads first"
      />
      {active && <SettleModal claim={active} onClose={() => setActive(null)} onDone={() => { setActive(null); load(); }} />}
      {receipt && <ClaimReceiptModal rows={outstandingRows} onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />}
    </div>
  );
}

function ClaimReceiptModal({ rows, onClose, onDone }) {
  const [key, setKey] = useState("");
  const [form, setForm] = useState({ amount: "", date: "", reference: "" });
  const sel = rows.find((r) => `${r.leadId}|${r.componentKey}` === key);
  const outstanding = sel ? Math.max(0, Number(sel.eligibleClaim || 0) - Number(sel.receivedAmount || 0)) : 0;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!sel) return toast.error("Select a claim");
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    try {
      await post("/claims/receipt", { leadId: sel.leadId, componentKey: sel.componentKey, amount: +form.amount, date: form.date, reference: form.reference });
      toast.success("Claim receipt recorded");
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Record Claim Received</h3>
        <p className="text-xs text-ink-soft mb-4">Pick a claim with a pending OEM company-share balance</p>
        <Field label="Claim (lead · component · outstanding)">
          <Select data-testid="claim-receipt-select" value={key} onChange={(e) => setKey(e.target.value)}>
            <option value="">— Select —</option>
            {rows.map((r) => <option key={`${r.leadId}|${r.componentKey}`} value={`${r.leadId}|${r.componentKey}`}>{r.leadId} · {r.customer} · {r.component} · {inr(Math.max(0, Number(r.eligibleClaim || 0) - Number(r.receivedAmount || 0)))}</option>)}
          </Select>
        </Field>
        {sel && (
          <div className="grid grid-cols-3 gap-3 mt-3">
            <Field label="Amount Received (₹)"><Input data-testid="claim-receipt-amount" type="number" value={form.amount} onChange={set("amount")} placeholder={String(outstanding)} /></Field>
            <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
            <Field label="Reference / UTR"><Input value={form.reference} onChange={set("reference")} /></Field>
          </div>
        )}
        {sel && <p className="text-xs text-ink-soft mt-2">Outstanding: <span className="font-mono font-semibold text-red-600">{inr(outstanding)}</span></p>}
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-claim-receipt-btn" onClick={submit}>Record Receipt</Button>
        </div>
      </Card>
    </div>
  );
}

function SettleModal({ claim, onClose, onDone }) {
  const [form, setForm] = useState({ claimStatus: claim.claimStatus || "Submitted", receivedAmount: claim.receivedAmount || claim.eligibleClaim || 0, claimReference: claim.claimReference || "" });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    await post("/claims/settle", { leadId: claim.leadId, componentKey: claim.componentKey, claimStatus: form.claimStatus, receivedAmount: +form.receivedAmount, claimReference: form.claimReference });
    toast.success("Claim updated");
    onDone();
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Settle Claim</h3>
        <p className="text-xs text-ink-soft mb-4">{claim.customer} · {claim.component} · {inr(claim.claimAmount)}</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Claim Status"><Select data-testid="claim-status" value={form.claimStatus} onChange={set("claimStatus")}>{["Pending","Submitted","Approved","Received","Rejected"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Received Amount"><Input type="number" value={form.receivedAmount} onChange={set("receivedAmount")} /></Field>
          <div className="col-span-2"><Field label="Claim Reference / UTR"><Input value={form.claimReference} onChange={set("claimReference")} /></Field></div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-claim-btn" onClick={submit}>Save</Button>
        </div>
      </Card>
    </div>
  );
}
