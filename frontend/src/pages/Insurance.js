import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, Banknote, HandCoins } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select, Card } from "../components/ui";

export default function Insurance() {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const [masters, setMasters] = useState(null);
  const [delivered, setDelivered] = useState([]);
  const [receipt, setReceipt] = useState(false);
  const load = useCallback(() => get("/insurance").then(setRows), []);
  useEffect(() => {
    load();
    get("/masters").then(setMasters);
    get("/leads").then((ls) => setDelivered(ls.filter((l) => (l.deliveryStatus || "").toLowerCase() === "delivered" || (l.currentStatus || "").toLowerCase() === "delivered")));
  }, [load]);

  const expected = rows.reduce((s, r) => s + Number(r.expectedPayout || 0), 0);
  const received = rows.reduce((s, r) => s + Number(r.receivedPayout || 0), 0);
  const remove = async (r) => { if (!window.confirm("Delete entry?")) return; await del(`/insurance/${r.entryId}`); toast.success("Deleted"); load(); };
  const outstandingRows = rows.filter((r) => Number(r.payoutOutstanding || 0) > 0.01);

  return (
    <div>
      <PageHeader title="Insurance Payouts" subtitle={`${rows.length} entries · ${inr(received)} received of ${inr(expected)} expected`}
        actions={<div className="flex items-center gap-2">
          <Button variant="secondary" data-testid="record-payout-btn" onClick={() => setReceipt(true)}><HandCoins size={16} /> Record Payout</Button>
          <Button data-testid="add-insurance-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Entry</Button>
        </div>} />
      <Table
        rowKey="entryId"
        onRowClick={setEdit}
        columns={[
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "insuranceCompany", label: "Insurer" },
          { key: "insuranceAmount", label: "Premium", align: "right", mono: true, render: (r) => inr(r.insuranceAmount) },
          { key: "payoutRate", label: "Rate %", align: "right", render: (r) => `${(Number(r.payoutRate) * 100).toFixed(1)}%` },
          { key: "expectedPayout", label: "Expected", align: "right", mono: true, render: (r) => inr(r.expectedPayout) },
          { key: "receivedPayout", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedPayout)}</span> },
          { key: "payoutOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.payoutOutstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.payoutOutstanding)}</span> },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status || "Pending"}</Badge> },
          { key: "act", label: "", align: "right", render: (r) => (
            <div className="flex justify-end gap-2">
              <button data-testid={`edit-insurance-${r.entryId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button data-testid={`delete-insurance-${r.entryId}`} onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
          )},
        ]}
        rows={rows}
        empty="No insurance entries — click Add Entry"
      />
      {edit && <EntryDrawer row={edit} masters={masters} delivered={delivered} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {receipt && <PayoutReceiptModal rows={outstandingRows} onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />}
    </div>
  );
}

function PayoutReceiptModal({ rows, onClose, onDone }) {
  const [entryId, setEntryId] = useState("");
  const [form, setForm] = useState({ amount: "", date: "", reference: "" });
  const sel = rows.find((r) => r.entryId === entryId);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!sel) return toast.error("Select an entry");
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    try {
      await post(`/insurance/${sel.entryId}/receipt`, { amount: +form.amount, date: form.date, reference: form.reference });
      toast.success("Payout recorded");
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Record Insurer Payout</h3>
        <p className="text-xs text-ink-soft mb-4">Pick an insurance entry with a pending payout</p>
        <Field label="Entry (customer · insurer · outstanding)">
          <Select data-testid="payout-receipt-select" value={entryId} onChange={(e) => setEntryId(e.target.value)}>
            <option value="">— Select —</option>
            {rows.map((r) => <option key={r.entryId} value={r.entryId}>{r.customerName} · {r.insuranceCompany} · {inr(r.payoutOutstanding)}</option>)}
          </Select>
        </Field>
        {sel && (
          <div className="grid grid-cols-3 gap-3 mt-3">
            <Field label="Amount Received (₹)"><Input data-testid="payout-receipt-amount" type="number" value={form.amount} onChange={set("amount")} placeholder={String(sel.payoutOutstanding)} /></Field>
            <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
            <Field label="Reference / UTR"><Input value={form.reference} onChange={set("reference")} /></Field>
          </div>
        )}
        {sel && <p className="text-xs text-ink-soft mt-2">Outstanding: <span className="font-mono font-semibold text-red-600">{inr(sel.payoutOutstanding)}</span></p>}
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-payout-receipt-btn" onClick={submit}>Record Payout</Button>
        </div>
      </Card>
    </div>
  );
}

function EntryDrawer({ row, masters, delivered = [], onClose, onSaved }) {
  const isNew = !row.entryId;
  const [form, setForm] = useState({
    leadId: row.leadId || "", customerName: row.customerName || "", mobile: row.mobile || "",
    model: row.model || "", variant: row.variant || "", insuranceCompany: row.insuranceCompany || "",
    policyNumber: row.policyNumber || "", insuranceAmount: row.insuranceAmount || 0,
    payoutRate: row.payoutRate ? Number(row.payoutRate) * 100 : 0, receivedPayout: row.receivedPayout || 0,
    policyDate: row.policyDate || "", insuranceExecutive: row.insuranceExecutive || "", remarks: row.remarks || "",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const pickLead = (e) => {
    const id = e.target.value;
    const l = delivered.find((x) => x.leadId === id);
    setForm((f) => ({ ...f, leadId: id, customerName: l ? l.customerName : f.customerName, mobile: l ? l.mobile : f.mobile, model: l ? l.interestedModel : f.model, variant: l ? l.variant : f.variant }));
  };
  const premium = Number(form.insuranceAmount) || 0;
  const rate = Number(form.payoutRate) || 0;
  const expected = Math.round(premium * (rate / 100));
  const outstanding = Math.max(0, expected - (Number(form.receivedPayout) || 0));

  const save = async () => {
    if (!form.customerName) return toast.error("Customer name required");
    const body = { ...form, insuranceAmount: +form.insuranceAmount, payoutRate: +form.payoutRate, receivedPayout: +form.receivedPayout };
    try {
      if (isNew) await post("/insurance", body); else await put(`/insurance/${row.entryId}`, body);
      toast.success(isNew ? "Entry added" : "Entry updated"); onSaved();
    } catch { toast.error("Save failed"); }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-xl" title={isNew ? "Add Insurance Entry" : "Insurance Entry"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-insurance-btn" onClick={save}><Banknote size={15} /> Save</Button></div>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Delivered Lead">
          <Select data-testid="ins-lead-select" value={form.leadId} onChange={pickLead}>
            <option value="">— Manual (no lead) —</option>
            {delivered.map((l) => <option key={l.leadId} value={l.leadId}>{l.leadId} · {l.customerName} · {l.interestedModel}</option>)}
          </Select>
        </Field>
        <Field label="Customer Name *"><Input data-testid="ins-customer" value={form.customerName} onChange={set("customerName")} /></Field>
        <Field label="Insurer"><Input value={form.insuranceCompany} onChange={set("insuranceCompany")} /></Field>
        <Field label="Policy Number"><Input value={form.policyNumber} onChange={set("policyNumber")} /></Field>
        <Field label="Premium (₹)"><Input data-testid="ins-premium" type="number" value={form.insuranceAmount} onChange={set("insuranceAmount")} /></Field>
        <Field label="Payout Rate (%)"><Input data-testid="ins-rate" type="number" value={form.payoutRate} onChange={set("payoutRate")} /></Field>
        <Field label="Received Payout (₹)"><Input type="number" value={form.receivedPayout} onChange={set("receivedPayout")} /></Field>
        <Field label="Policy Date"><Input type="date" value={form.policyDate || ""} onChange={set("policyDate")} /></Field>
        <Field label="Insurance Executive"><Select value={form.insuranceExecutive} onChange={set("insuranceExecutive")}><option value="">—</option>{(masters?.executives || []).map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Model"><Input value={form.model} onChange={set("model")} /></Field>
        <div className="col-span-2"><Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field></div>
      </div>
      <Card className="p-4 mt-4 bg-cobalt-tint/40 border-cobalt/20">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div><div className="text-[11px] text-ink-faint uppercase">Expected Payout</div><div className="font-mono font-bold text-ink">{inr(expected)}</div></div>
          <div><div className="text-[11px] text-ink-faint uppercase">Received</div><div className="font-mono font-bold text-emerald-600">{inr(form.receivedPayout)}</div></div>
          <div><div className="text-[11px] text-ink-faint uppercase">Outstanding</div><div className="font-mono font-bold text-cobalt">{inr(outstanding)}</div></div>
        </div>
      </Card>
    </Drawer>
  );
}
