import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select } from "../components/ui";

const COMPONENTS = [
  ["Consumer Discount", "consumerDiscount"], ["Exchange Bonus", "exchangeBonus"],
  ["Loyalty Bonus", "loyaltyBonus"], ["Referral Bonus", "referralBonus"],
  ["DSA Bonus", "dsaDiscount"], ["Additional Discount", "additionalDiscount"],
];

export default function SchemeMaster() {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const [models, setModels] = useState([]);
  const load = useCallback(() => get("/scheme-master").then(setRows), []);
  useEffect(() => { load(); get("/masters").then((m) => setModels(m.models)); }, [load]);
  const remove = async (r) => { if (!window.confirm("Delete scheme row?")) return; await del(`/scheme-master/${r.schemeId}`); toast.success("Deleted"); load(); };

  return (
    <div>
      <PageHeader title="Scheme Master" subtitle="Monthly OEM consumer scheme matrix — dealer vs company share"
        actions={<Button data-testid="add-scheme-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Scheme</Button>} />
      <Table
        rowKey="schemeId"
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "component", label: "Component", render: (r) => <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.component}</Badge> },
          { key: "dealerShare", label: "Dealer Share", align: "right", mono: true, render: (r) => inr(r.dealerShare) },
          { key: "companyShare", label: "Company Share", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.companyShare)}</span> },
          { key: "totalBenefit", label: "Total", align: "right", mono: true, render: (r) => inr(r.totalBenefit) },
          { key: "effectiveTo", label: "Valid To", render: (r) => fmtDate(r.effectiveTo) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "act", label: "", align: "right", render: (r) => (
            <div className="flex justify-end gap-2">
              <button data-testid={`edit-scheme-${r.schemeId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
          )},
        ]}
        rows={rows}
      />
      {edit && <EditDrawer row={edit} models={models} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function EditDrawer({ row, models, onClose, onSaved }) {
  const isNew = !row.schemeId;
  const [form, setForm] = useState({
    model: row.model || "", variant: row.variant || "", component: row.component || "Consumer Discount",
    componentKey: row.componentKey || "consumerDiscount", dealerShare: row.dealerShare || 0,
    companyShare: row.companyShare || 0, circularRef: row.circularRef || "", effectiveTo: row.effectiveTo || "",
    status: row.status || "Active",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setComponent = (e) => {
    const label = e.target.value; const key = COMPONENTS.find((c) => c[0] === label)?.[1] || "";
    setForm((f) => ({ ...f, component: label, componentKey: key }));
  };
  const save = async () => {
    if (!form.model) return toast.error("Model required");
    const body = { ...form, dealerShare: +form.dealerShare, companyShare: +form.companyShare, totalBenefit: +form.dealerShare + +form.companyShare };
    try {
      if (isNew) await post("/scheme-master", body); else await put(`/scheme-master/${row.schemeId}`, body);
      toast.success(isNew ? "Scheme added" : "Scheme updated"); onSaved();
    } catch { toast.error("Save failed"); }
  };
  return (
    <Drawer open onClose={onClose} width="max-w-lg" title={isNew ? "Add Scheme" : "Edit Scheme"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-scheme-row-btn" onClick={save}>Save</Button></div>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Model"><Select data-testid="sm-model" value={form.model} onChange={set("model")}><option value="">—</option>{models.map((m) => <option key={m}>{m}</option>)}</Select></Field>
        <Field label="Variant"><Input value={form.variant} onChange={set("variant")} placeholder="All / specific" /></Field>
        <div className="col-span-2"><Field label="Component"><Select value={form.component} onChange={setComponent}>{COMPONENTS.map((c) => <option key={c[1]}>{c[0]}</option>)}</Select></Field></div>
        <Field label="Dealer Share (₹)"><Input type="number" value={form.dealerShare} onChange={set("dealerShare")} /></Field>
        <Field label="Company Share (₹)"><Input data-testid="sm-company" type="number" value={form.companyShare} onChange={set("companyShare")} /></Field>
        <Field label="Circular Ref"><Input value={form.circularRef} onChange={set("circularRef")} /></Field>
        <Field label="Valid To"><Input type="date" value={form.effectiveTo || ""} onChange={set("effectiveTo")} /></Field>
        <Field label="Status"><Select value={form.status} onChange={set("status")}><option>Active</option><option>Inactive</option></Select></Field>
      </div>
    </Drawer>
  );
}
