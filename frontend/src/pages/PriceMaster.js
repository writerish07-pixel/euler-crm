import React, { useEffect, useState, useCallback } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, del } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Select, Button } from "../components/ui";
import { PriceRowDrawer } from "../components/PriceRowDrawer";
import OemPriceSyncButton from "../components/OemPriceSyncButton";

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
      <PageHeader title="Price Master" subtitle={`${rows.length} vehicle price rows · Sync from OEM overwrites ex-showroom`}
        actions={<div className="flex gap-2">
          <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-44"><option value="all">All Models</option>{models.map((m) => <option key={m}>{m}</option>)}</Select>
          <OemPriceSyncButton onDone={load} testId="price-master-oem-sync" />
          <Button data-testid="add-price-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Row</Button>
        </div>} />
      <Table
        rowKey="priceId"
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => (
            <span>
              {inr(r.exShowroom, { decimals: 2 })}
              {r.priceSource === "oem" ? <span className="ml-1 text-[10px] text-cobalt font-semibold">OEM</span> : null}
              {Number(r.turboUplift) > 0 ? (
                <span className="block text-[10px] text-amber-700 font-semibold">From 1 Sep {inr(r.sellingExShowroom)}</span>
              ) : null}
            </span>
          ) },
          { key: "inYard", label: "In yard", align: "right", mono: true, render: (r) => r.inYard || 0 },
          { key: "rto", label: "RTO", align: "right", mono: true, render: (r) => inr(r.rto) },
          { key: "insurance", label: "Insurance", align: "right", mono: true, render: (r) => inr(r.insurance) },
          { key: "tcsApplicable", label: "TCS", render: (r) => (
            <Badge tone={r.tcsAuto ? "bg-amber-50 text-amber-700 ring-amber-600/20" : "bg-zinc-100 text-zinc-500 ring-zinc-400/20"}>
              {r.tcsAuto ? `Auto ${inr(r.sellingTcs)}` : "—"}
            </Badge>
          ) },
          { key: "status", label: "Status", render: (r) => <Badge tone={String(r.status).toLowerCase() === "inactive" ? "bg-zinc-100 text-zinc-500 ring-zinc-400/20" : "bg-emerald-50 text-emerald-700 ring-emerald-600/20"}>{r.status}</Badge> },
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
