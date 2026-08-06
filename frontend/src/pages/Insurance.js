import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2, Banknote } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select, Card } from "../components/ui";

export default function Insurance() {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const [masters, setMasters] = useState(null);
  const load = useCallback(() => get("/insurance").then(setRows), []);
  useEffect(() => { load(); get("/masters").then(setMasters); }, [load]);

  const expected = rows.reduce((s, r) => s + Number(r.expectedPayout || 0), 0);
  const received = rows.reduce((s, r) => s + Number(r.receivedPayout || 0), 0);
  const remove = async (r) => { if (!window.confirm("Delete entry?")) return; await del(`/insurance/${r.entryId}`); toast.success("Deleted"); load(); };

  return (
    <div>
      <PageHeader title="Insurance Payouts" subtitle={`${rows.length} entries · ${inr(received)} received of ${inr(expected)} expected`}
        actions={<Button data-testid="add-insurance-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Entry</Button>} />
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
              <button onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
          )},
        ]}
        rows={rows}
        empty="No insurance entries — click Add Entry"
      />
      {edit && <EntryDrawer row={edit} masters={masters} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function EntryDrawer({ row, masters, onClose, onSaved }) {
  const isNew = !row.entryId;
  const [form, setForm] = useState({
    leadId: row.leadId || "", customerName: row.customerName || "", mobile: row.mobile || "",
    model: row.model || "", variant: row.variant || "", insuranceCompany: row.insuranceCompany || "",
    policyNumber: row.policyNumber || "", insuranceAmount: row.insuranceAmount || 0,
    payoutRate: row.payoutRate ? Number(row.payoutRate) * 100 : 0, receivedPayout: row.receivedPayout || 0,
    policyDate: row.policyDate || "", insuranceExecutive: row.insuranceExecutive || "", remarks: row.remarks || "",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
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
        <Field label="Customer Name *"><Input data-testid="ins-customer" value={form.customerName} onChange={set("customerName")} /></Field>
        <Field label="Lead ID (optional)"><Input value={form.leadId} onChange={set("leadId")} /></Field>
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
