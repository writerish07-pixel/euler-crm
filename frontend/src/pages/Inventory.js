import React, { useCallback, useEffect, useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Select, Button, Card } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function Inventory() {
  const { isOwner } = useAuth();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState(null);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get("/inventory", model ? { model } : undefined).then(setRows).catch(() => setRows([]));
    get("/inventory/summary").then(setSummary).catch(() => {});
    get("/integrations/coulson").then(setStatus).catch(() => {});
  }, [model]);
  useEffect(() => { load(); }, [load]);

  const sync = async () => {
    setBusy(true);
    try {
      const r = await post("/integrations/coulson/sync", {});
      if (r.ok) toast.success(`Synced ${r.inventoryCount || 0} vehicles from Euler OEM`);
      else toast.error(r.reason === "not_configured" ? "Save Coulson login in Settings first" : "Sync did not run");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Coulson sync failed");
    } finally { setBusy(false); }
  };

  const models = [...new Set(rows.map((r) => r.model).filter(Boolean))];
  const filtered = model ? rows.filter((r) => r.model === model) : rows;

  return (
    <div data-testid="yard-inventory">
      <PageHeader
        title="Yard Inventory"
        subtitle="Live stock from the Euler OEM portal. Ex-showroom is OEM; RTO and insurance stay on Price Master."
        actions={<div className="flex gap-2">
          {isOwner && (
            <Button data-testid="coulson-sync-btn" onClick={sync} disabled={busy}>
              <RefreshCcw size={15} /> {busy ? "Syncing…" : "Sync from OEM"}
            </Button>
          )}
        </div>} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <Card className="p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">In yard</div>
          <div className="text-xl font-bold tabular">{summary?.total ?? rows.length}</div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Last OEM sync</div>
          <div className="text-sm font-semibold">{status?.lastSyncAt ? fmtDate(status.lastSyncAt) : "Never"}</div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Connection</div>
          <Badge tone={status?.configured
            ? (status.lastSyncOk === false ? "bg-red-50 text-red-700 ring-red-600/20" : "bg-emerald-50 text-emerald-700 ring-emerald-600/20")
            : "bg-amber-50 text-amber-700 ring-amber-600/20"}>
            {status?.configured ? (status.lastSyncOk === false ? "Error" : "Configured") : "Not configured"}
          </Badge>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">OEM catalog</div>
          <div className="text-xl font-bold tabular">{status?.catalogSize || "—"}</div>
        </Card>
      </div>

      {status?.lastError && status.lastSyncOk === false && (
        <Card className="p-3 mb-4 bg-red-50 border-red-200 text-sm text-red-800">{status.lastError}</Card>
      )}

      <div className="flex gap-2 mb-4">
        <Select data-testid="inventory-model-filter" value={model} onChange={(e) => setModel(e.target.value)} className="w-52">
          <option value="">All models</option>
          {models.map((m) => <option key={m}>{m}</option>)}
        </Select>
      </div>

      <Table
        rowKey="chassis"
        empty="No yard stock yet — owner can sync from Settings → Euler OEM."
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "bodyType", label: "Body" },
          { key: "emch", label: "EMCH", mono: true },
          { key: "chassis", label: "Chassis", mono: true, render: (r) => <span className="text-xs">{r.chassis}</span> },
          { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
          { key: "inventoryAgeing", label: "Age (days)", align: "right", mono: true },
          { key: "pdiDone", label: "PDI", render: (r) => <Badge tone={r.pdiDone ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-100 text-zinc-500 ring-zinc-400/20"}>{r.pdiDone ? "Done" : "Pending"}</Badge> },
          { key: "readyForAllocation", label: "Ready", render: (r) => r.readyForAllocation ? "Yes" : "No" },
        ]}
        rows={filtered}
      />
    </div>
  );
}
