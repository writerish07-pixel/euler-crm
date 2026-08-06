import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Select } from "../components/ui";

export default function PriceMaster() {
  const [rows, setRows] = useState([]);
  const [model, setModel] = useState("all");
  const [models, setModels] = useState([]);

  useEffect(() => { get("/masters").then((m) => setModels(m.models)); }, []);
  useEffect(() => { get("/price-master", model !== "all" ? { model } : undefined).then(setRows); }, [model]);

  return (
    <div>
      <PageHeader title="Price Master" subtitle={`${rows.length} vehicle price rows`}
        actions={
          <Select value={model} onChange={(e) => setModel(e.target.value)} className="w-48">
            <option value="all">All Models</option>
            {models.map((m) => <option key={m}>{m}</option>)}
          </Select>
        } />
      <Table
        rowKey="priceId"
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "bodyType", label: "Body" },
          { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
          { key: "rto", label: "RTO", align: "right", mono: true, render: (r) => inr(r.rto) },
          { key: "insurance", label: "Insurance", align: "right", mono: true, render: (r) => inr(r.insurance) },
          { key: "tcsApplicable", label: "TCS", render: (r) => <Badge tone={r.tcsApplicable === "Yes" ? "bg-amber-50 text-amber-700 ring-amber-600/20" : "bg-zinc-100 text-zinc-500 ring-zinc-400/20"}>{r.tcsApplicable}</Badge> },
          { key: "priceVersion", label: "Version", mono: true },
          { key: "status", label: "Status", render: (r) => <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">{r.status}</Badge> },
        ]}
        rows={rows}
      />
    </div>
  );
}
