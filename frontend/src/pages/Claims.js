import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { HandCoins, Plus } from "lucide-react";
import { get, post } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Select, Card, StatCard, Modal } from "../components/ui";

export default function Claims() {
  const [rows, setRows] = useState([]);
  const [active, setActive] = useState(null);
  const [receipt, setReceipt] = useState(false);
  const [manual, setManual] = useState(false);
  const [leads, setLeads] = useState([]);
  const load = useCallback(() => get("/claims").then(setRows), []);
  useEffect(() => { load(); get("/leads").then(setLeads); }, [load]);

  const isIncentive = (r) => String(r.componentKey || "").startsWith("executiveIncentive")
    || /executive incentive/i.test(String(r.component || r.claimType || ""));
  const schemeRows = rows.filter((r) => !r.manual || !isIncentive(r));
  const incentiveRows = rows.filter((r) => isIncentive(r));
  const schemeEligible = schemeRows.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
  const incentiveEligible = incentiveRows.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
  const eligible = schemeEligible + incentiveEligible;
  const outstandingOf = (list) => list.reduce((s, r) => s + Math.max(0, Number(r.eligibleClaim || 0) - Number(r.receivedAmount || 0)), 0);
  const schemeOutstanding = outstandingOf(schemeRows);
  const incentiveOutstanding = outstandingOf(incentiveRows);
  const totalOutstanding = schemeOutstanding + incentiveOutstanding;
  const outstandingRows = rows.filter((r) => Number(r.eligibleClaim || 0) - Number(r.receivedAmount || 0) > 0.01);

  return (
    <div>
      <PageHeader title="OEM Claim Register" subtitle={`${rows.length} claims · ${inr(eligible)} eligible`}
        actions={<div className="flex items-center gap-2">
          <Button variant="secondary" data-testid="add-manual-claim-btn" onClick={() => setManual(true)}><Plus size={16} /> Add Manual Claim</Button>
          <Button data-testid="record-claim-receipt-btn" onClick={() => setReceipt(true)}><HandCoins size={16} /> Record Claim Received</Button>
        </div>} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6" data-testid="claim-totals">
        <StatCard label="Scheme Eligible" value={inr(schemeEligible)} tone="text-cobalt" />
        <StatCard label="Executive Incentive" value={inr(incentiveEligible)} tone="text-violet-600" />
        <StatCard label="Total Eligible" value={inr(eligible)} tone="text-emerald-600" />
        <StatCard label="Total Outstanding" value={inr(totalOutstanding)} tone="text-red-600" />
      </div>
      <Table
        rowKey="claimId"
        onRowClick={setActive}
        columns={[
          { key: "leadId", label: "Lead", mono: true, render: (r) => r.leadId || "—" },
          { key: "customer", label: "Customer", render: (r) => <span className="font-semibold">{r.customer || "—"}</span> },
          { key: "model", label: "Vehicle", render: (r) => r.model || "—" },
          { key: "component", label: "Component", render: (r) => (
            <div className="flex items-center gap-1.5">
              <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.component}</Badge>
              {r.manual && <Badge tone="bg-blue-50 text-blue-700 ring-blue-600/20">Manual</Badge>}
            </div>
          )},
          { key: "claimAmount", label: "Claim Amount", align: "right", mono: true, render: (r) => inr(r.claimAmount) },
          { key: "eligibleClaim", label: "Eligible", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.eligibleClaim)}</span> },
          { key: "receivedAmount", label: "Received", align: "right", mono: true, render: (r) => inr(r.receivedAmount) },
          { key: "outstanding", label: "Outstanding", align: "right", mono: true, render: (r) => { const o = Number(r.eligibleClaim || 0) - Number(r.receivedAmount || 0); return <span className={o > 0.01 ? "text-red-600 font-semibold" : ""}>{inr(Math.max(0, o))}</span>; } },
          { key: "claimStatus", label: "Status", render: (r) => <Badge>{r.claimStatus}</Badge> },
          { key: "submittedDate", label: "Submitted", render: (r) => r.submittedDate ? fmtDate(r.submittedDate) : "—" },
          { key: "approvedDate", label: "Approved", render: (r) => r.approvedDate ? fmtDate(r.approvedDate) : "—" },
          { key: "ageingDays", label: "Ageing", align: "right", render: (r) => r.ageingDays ? <Badge tone={r.ageingDays > 30 ? "bg-red-50 text-red-700 ring-red-600/20" : "bg-amber-50 text-amber-700 ring-amber-600/20"}>{r.ageingDays}d</Badge> : "—" },
        ]}
        rows={rows}
        empty="No claims yet — apply schemes on booked leads, mark incentives paid, or click Add Manual Claim"
      />
      {active && <SettleModal claim={active} onClose={() => setActive(null)} onDone={() => { setActive(null); load(); }} />}
      {receipt && <ClaimReceiptModal rows={outstandingRows} onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />}
      {manual && <ManualClaimModal leads={leads} onClose={() => setManual(false)} onDone={() => { setManual(false); load(); }} />}
    </div>
  );
}

const CLAIM_TYPES = ["OEM Incentive", "Warranty Claim", "Scheme Support", "Target Incentive", "Other"];
function ManualClaimModal({ leads, onClose, onDone }) {
  const [form, setForm] = useState({ claimType: "OEM Incentive", oemCompany: "", leadId: "", customer: "", model: "", claimAmount: "", submittedDate: todayISO(), claimReference: "", note: "" });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const pickLead = (e) => {
    const id = e.target.value;
    const l = leads.find((x) => x.leadId === id);
    setForm((f) => ({ ...f, leadId: id, customer: l ? l.customerName : f.customer, model: l ? l.interestedModel : f.model }));
  };
  const submit = async () => {
    if (!form.claimAmount || +form.claimAmount <= 0) return toast.error("Enter a valid claim amount");
    try {
      await post("/claims/manual", { ...form, claimAmount: +form.claimAmount });
      toast.success("Manual claim added to register");
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  return (
    <Modal onClose={onClose} width="max-w-xl">
      <div className="overflow-y-auto overscroll-contain p-6">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Add Manual Claim</h3>
        <p className="text-xs text-ink-soft mb-4">Record a claim manually (e.g. an OEM incentive). It joins the register; record money later via "Record Claim Received".</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Claim Type"><Select data-testid="manual-claim-type" value={form.claimType} onChange={set("claimType")}>{CLAIM_TYPES.map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="OEM / Company"><Input data-testid="manual-claim-oem" value={form.oemCompany} onChange={set("oemCompany")} placeholder="e.g. Euler Motors" /></Field>
          <Field label="Linked Lead (optional)">
            <Select data-testid="manual-claim-lead" value={form.leadId} onChange={pickLead}>
              <option value="">— None —</option>
              {leads.map((l) => <option key={l.leadId} value={l.leadId}>{l.leadId} · {l.customerName}</option>)}
            </Select>
          </Field>
          <Field label="Customer"><Input data-testid="manual-claim-customer" value={form.customer} onChange={set("customer")} /></Field>
          <Field label="Claim Amount (₹) *"><Input data-testid="manual-claim-amount" type="number" value={form.claimAmount} onChange={set("claimAmount")} /></Field>
          <Field label="Submitted Date"><Input data-testid="manual-claim-date" type="date" value={form.submittedDate} onChange={set("submittedDate")} /></Field>
          <div className="col-span-2"><Field label="Reference / Note"><Input data-testid="manual-claim-ref" value={form.claimReference} onChange={set("claimReference")} placeholder="Reference / UTR / note" /></Field></div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-manual-claim-btn" onClick={submit}>Add to Register</Button>
        </div>
      </div>
    </Modal>
  );
}

function ClaimReceiptModal({ rows, onClose, onDone }) {
  const [key, setKey] = useState("");
  const [form, setForm] = useState({ amount: "", date: todayISO(), reference: "" });
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
    <Modal onClose={onClose} width="max-w-lg">
      <div className="overflow-y-auto overscroll-contain p-6">
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
      </div>
    </Modal>
  );
}

function SettleModal({ claim, onClose, onDone }) {
  const [form, setForm] = useState({ claimStatus: claim.claimStatus || "Submitted", receivedAmount: claim.receivedAmount || claim.eligibleClaim || 0, claimReference: claim.claimReference || "", submittedDate: claim.submittedDate || todayISO(), approvedDate: claim.approvedDate || todayISO() });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    await post("/claims/settle", { leadId: claim.leadId, componentKey: claim.componentKey, claimStatus: form.claimStatus, receivedAmount: +form.receivedAmount, claimReference: form.claimReference, submittedDate: form.submittedDate, approvedDate: form.approvedDate });
    toast.success("Claim updated");
    onDone();
  };
  return (
    <Modal onClose={onClose} width="max-w-lg">
      <div className="overflow-y-auto overscroll-contain p-6">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Settle Claim</h3>
        <p className="text-xs text-ink-soft mb-4">{claim.customer} · {claim.component} · {inr(claim.claimAmount)}</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Claim Status"><Select data-testid="claim-status" value={form.claimStatus} onChange={set("claimStatus")}>{["Pending","Submitted","Approved","Received","Rejected"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Received Amount"><Input type="number" value={form.receivedAmount} onChange={set("receivedAmount")} /></Field>
          <Field label="Submitted Date"><Input data-testid="claim-submitted-date" type="date" value={form.submittedDate} onChange={set("submittedDate")} /></Field>
          <Field label="Approved Date"><Input data-testid="claim-approved-date" type="date" value={form.approvedDate} onChange={set("approvedDate")} /></Field>
          <div className="col-span-2"><Field label="Claim Reference / UTR"><Input value={form.claimReference} onChange={set("claimReference")} /></Field></div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-claim-btn" onClick={submit}>Save</Button>
        </div>
      </div>
    </Modal>
  );
}
