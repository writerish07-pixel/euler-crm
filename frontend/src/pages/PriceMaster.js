import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, del } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Select, Button } from "../components/ui";
import { PriceRowDrawer } from "../components/PriceRowDrawer";

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
      {edit && <PriceRowDrawer row={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}
