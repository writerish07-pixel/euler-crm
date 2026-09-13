import React, { useCallback, useEffect, useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Select, Button, Card } from "../components/ui";
import ReportActions from "../components/ReportActions";
import { useAuth } from "../context/AuthContext";

const TABS = [
  ["yard", "In yard"],
  ["transit", "In transit"],
  ["order", "Need to order"],
];

export default function Inventory() {
  const { isOwner } = useAuth();
  const [tab, setTab] = useState("yard");
  const [rows, setRows] = useState([]);
  const [transit, setTransit] = useState([]);
  const [need, setNeed] = useState([]);
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState(null);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const q = model ? { model } : undefined;
    get("/inventory", q).then(setRows).catch(() => setRows([]));
    get("/inventory/transit", q).then(setTransit).catch(() => setTransit([]));
    get("/inventory/need-to-order").then(setNeed).catch(() => setNeed([]));
    get("/inventory/summary").then(setSummary).catch(() => {});
    get("/integrations/coulson").then(setStatus).catch(() => {});
  }, [model]);
  useEffect(() => { load(); }, [load]);

  const sync = async () => {
    setBusy(true);
    try {
      const r = await post("/integrations/coulson/sync", {});
      if (r.ok) toast.success(
        `Synced ${r.inventoryCount || 0} in yard · ${r.transitCount || 0} in transit · ${(r.leadsVehicleIds && r.leadsVehicleIds.updated) || 0} leads chassis/invoice`,
      );
      else toast.error(r.reason === "not_configured" ? "Save Coulson login in Settings first" : "Sync did not run");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Coulson sync failed"));
    } finally { setBusy(false); }
  };

  const models = [...new Set([
    ...rows.map((r) => r.model),
    ...transit.map((r) => r.model),
    ...need.map((r) => r.model),
  ].filter(Boolean))];
  const yardRows = model ? rows.filter((r) => r.model === model) : rows;
  const transitRows = model ? transit.filter((r) => r.model === model) : transit;
  const needRows = model ? need.filter((r) => r.model === model) : need;

  return (
    <div data-testid="yard-inventory">
      <PageHeader
        title="Yard Inventory"
        subtitle="Live stock from the Euler OEM portal. Ex-showroom is OEM; RTO and insurance stay on Price Master."
        actions={<div className="flex gap-2">
          <ReportActions onRefresh={load} />
          {isOwner && (
            <Button data-testid="coulson-sync-btn" onClick={sync} disabled={busy}>
              <RefreshCcw size={15} /> {busy ? "Syncing…" : "Sync from OEM"}
            </Button>
          )}
        </div>} />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        <Card className="p-3" data-testid="inv-card-yard">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">In yard</div>
          <div className="text-xl font-bold tabular">{summary?.total ?? rows.length}</div>
        </Card>
        <Card className="p-3" data-testid="inv-card-transit">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">In transit</div>
          <div className="text-xl font-bold tabular">{summary?.transit ?? transit.length}</div>
        </Card>
        <Card className="p-3" data-testid="inv-card-need">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Need to order</div>
          <div className="text-xl font-bold tabular">{summary?.needToOrder ?? need.length}</div>
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
      </div>

      {status?.lastError && status.lastSyncOk === false && (
        <Card className="p-3 mb-4 bg-red-50 border-red-200 text-sm text-red-800">{status.lastError}</Card>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
          {TABS.map(([k, l]) => (
            <button key={k} type="button" data-testid={`inv-tab-${k}`} onClick={() => setTab(k)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${tab === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>
              {l}
            </button>
          ))}
        </div>
        <Select data-testid="inventory-model-filter" value={model} onChange={(e) => setModel(e.target.value)} className="w-52">
          <option value="">All models</option>
          {models.map((m) => <option key={m}>{m}</option>)}
        </Select>
      </div>

      {tab === "yard" && (
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
          rows={yardRows}
        />
      )}

      {tab === "transit" && (
        <Table
          rowKey="chassis"
          empty="No vehicles in transit from the last OEM sync."
          columns={[
            { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
            { key: "variant", label: "Variant" },
            { key: "bodyType", label: "Body" },
            { key: "emch", label: "EMCH", mono: true },
            { key: "chassis", label: "Chassis", mono: true, render: (r) => <span className="text-xs">{r.chassis}</span> },
            { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
            { key: "inventoryAgeing", label: "Age (days)", align: "right", mono: true },
          ]}
          rows={transitRows}
        />
      )}

      {tab === "order" && (
        <Table
          rowKey="leadId"
          empty="Every open booking has yard stock for its model and variant."
          columns={[
            { key: "leadId", label: "Lead", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.leadId}</span> },
            { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
            { key: "model", label: "Vehicle", render: (r) => <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div> },
            { key: "executive", label: "Executive" },
            { key: "bookingDate", label: "Booked", render: (r) => fmtDate(r.bookingDate) },
            { key: "currentStatus", label: "Status", render: (r) => <Badge>{r.currentStatus}</Badge> },
            { key: "customerPayable", label: "Deal amount", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
          ]}
          rows={needRows}
        />
      )}
    </div>
  );
}
