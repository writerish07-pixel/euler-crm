import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Select, Button, Drawer, Field, Input } from "../components/ui";

const FIELDS = [
  ["model", "Model", "text"], ["variant", "Variant", "text"], ["bodyType", "Body Type", "text"],
  ["exShowroom", "Ex-Showroom", "number"], ["rto", "RTO", "number"], ["insurance", "Insurance", "number"],
  ["accessories", "Accessories", "number"], ["handlingCharges", "Handling", "number"], ["trc", "TRC", "number"],
  ["fastag", "Fastag", "number"], ["extendedWarranty", "Ext. Warranty", "number"], ["otherCharges", "Other", "number"],
  ["gstPercent", "GST %", "number"], ["priceVersion", "Price Version", "text"],
];

export default function PriceMaster() {
  const [rows, setRows] = useState([]);
  const [model, setModel] = useState("all");
  const [models, setModels] = useState([]);
  const [edit, setEdit] = useState(null);

  const load = useCallback(() => get("/price-master", model !== "all" ? { model } : undefined).then(setRows), [model]);
  useEffect(() => { get("/masters").then((m) => setModels(m.models)); }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async (r) => { if (!window.confirm(`Delete ${r.model} ${r.variant}?`)) return; await del(`/price-master/${r.priceId}`); toast.success("Deleted"); load(); };

  return (
    <div>
      <PageHeader title="Price Master" subtitle={`${rows.length} vehicle price rows`}
        actions={<div className="flex gap-2">
          <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-44"><option value="all">All Models</option>{models.map((m) => <option key={m}>{m}</option>)}</Select>
          <Button data-testid="add-price-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Row</Button>
        </div>} />
      <Table
        rowKey="priceId"
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
          { key: "rto", label: "RTO", align: "right", mono: true, render: (r) => inr(r.rto) },
          { key: "insurance", label: "Insurance", align: "right", mono: true, render: (r) => inr(r.insurance) },
          { key: "tcsApplicable", label: "TCS", render: (r) => <Badge tone={r.tcsApplicable === "Yes" ? "bg-amber-50 text-amber-700 ring-amber-600/20" : "bg-zinc-100 text-zinc-500 ring-zinc-400/20"}>{r.tcsApplicable}</Badge> },
          { key: "status", label: "Status", render: (r) => <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">{r.status}</Badge> },
          { key: "act", label: "", align: "right", render: (r) => (
            <div className="flex justify-end gap-2">
              <button data-testid={`edit-price-${r.priceId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
          )},
        ]}
        rows={rows}
      />
      {edit && <EditDrawer row={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function EditDrawer({ row, onClose, onSaved }) {
  const isNew = !row.priceId;
  const [form, setForm] = useState(() => {
    const f = { tcsApplicable: row.tcsApplicable || "No", status: row.status || "active" };
    FIELDS.forEach(([k, , t]) => (f[k] = row[k] ?? (t === "number" ? 0 : "")));
    return f;
  });
  const set = (k, t) => (e) => setForm((f) => ({ ...f, [k]: t === "number" ? e.target.value : e.target.value }));
  const save = async () => {
    if (!form.model || !form.variant) return toast.error("Model & Variant required");
    const body = { ...form };
    FIELDS.forEach(([k, , t]) => { if (t === "number") body[k] = +form[k]; });
    try {
      if (isNew) await post("/price-master", body); else await put(`/price-master/${row.priceId}`, body);
      toast.success(isNew ? "Row added" : "Row updated"); onSaved();
    } catch { toast.error("Save failed"); }
  };
  return (
    <Drawer open onClose={onClose} width="max-w-xl" title={isNew ? "Add Price Row" : "Edit Price Row"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-price-row-btn" onClick={save}>Save</Button></div>}>
      <div className="grid grid-cols-2 gap-3">
        {FIELDS.map(([k, label, t]) => <Field key={k} label={label}><Input data-testid={`pm-${k}`} type={t} value={form[k]} onChange={set(k, t)} /></Field>)}
        <Field label="TCS Applicable"><Select value={form.tcsApplicable} onChange={(e) => setForm({ ...form, tcsApplicable: e.target.value })}><option>No</option><option>Yes</option></Select></Field>
        <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}><option>active</option><option>inactive</option></Select></Field>
      </div>
    </Drawer>
  );
}
