import React, { useCallback, useEffect, useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, fmtDate, oemStampSummary } from "../lib/format";
import { PageHeader, Table, Badge, Select, Button, Card } from "../components/ui";
import ReportActions from "../components/ReportActions";
import { useAuth } from "../context/AuthContext";

const TABS = [
  ["yard", "In yard"],
  ["transit", "In transit"],
  ["held", "Booked / Pilot / Demo"],
  ["sold", "Sold"],
  ["received", "Received from OEM"],
  ["order", "Need to order"],
];

export default function Inventory() {
  const { isOwner, isShowroomAdmin, isExecutive, isTeamLead, isTl } = useAuth();
  const canSeeChassisLedger = !isExecutive && !isTeamLead && !isTl;
  const [tab, setTab] = useState("yard");
  const [rows, setRows] = useState([]);
  const [transit, setTransit] = useState([]);
  const [held, setHeld] = useState([]);
  const [need, setNeed] = useState([]);
  const [sold, setSold] = useState([]);
  const [received, setReceived] = useState({ rows: [], byMonth: [], total: 0 });
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState(null);
  const [check, setCheck] = useState(null);
  const [ticks, setTicks] = useState({});
  const [model, setModel] = useState("");
  const [receivedMonth, setReceivedMonth] = useState("");
  const [busy, setBusy] = useState(false);
  const canConfirm = isOwner || isShowroomAdmin;

  const load = useCallback(() => {
    const q = model ? { model } : undefined;
    const receivedQ = receivedMonth ? { month: receivedMonth } : undefined;
    return Promise.all([
      get("/inventory", q).then((list) => {
        const next = Array.isArray(list) ? list : [];
        setRows(next);
        setTicks((cur) => {
          const out = { ...cur };
          next.forEach((r) => {
            if (r.chassis && r.physicalStatus && !out[r.chassis]) out[r.chassis] = r.physicalStatus;
          });
          return out;
        });
      }).catch(() => setRows([])),
      get("/inventory/transit", q).then(setTransit).catch(() => setTransit([])),
      get("/inventory/held", q).then((list) => setHeld(Array.isArray(list) ? list : [])).catch(() => setHeld([])),
      ...(canSeeChassisLedger ? [
        get("/inventory/sold").then((list) => setSold(Array.isArray(list) ? list : [])).catch(() => setSold([])),
        get("/inventory/received", receivedQ).then((payload) => {
          if (payload && typeof payload === "object" && Array.isArray(payload.rows)) {
            setReceived({
              rows: payload.rows,
              byMonth: Array.isArray(payload.byMonth) ? payload.byMonth : [],
              total: payload.total ?? payload.rows.length,
            });
          } else {
            setReceived({ rows: [], byMonth: [], total: 0 });
          }
        }).catch(() => setReceived({ rows: [], byMonth: [], total: 0 })),
      ] : []),
      get("/inventory/need-to-order").then(setNeed).catch(() => setNeed([])),
      get("/inventory/summary").then(setSummary).catch(() => {}),
      get("/inventory/check").then(setCheck).catch(() => {}),
      get("/integrations/coulson").then(setStatus).catch(() => {}),
    ]);
  }, [model, receivedMonth, canSeeChassisLedger]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!canSeeChassisLedger && (tab === "sold" || tab === "received")) setTab("yard");
  }, [canSeeChassisLedger, tab]);

  const sync = async () => {
    setBusy(true);
    try {
      const r = await post("/integrations/coulson/sync", {});
      if (r.ok) toast.success(
        `Synced ${r.inventoryCount || 0} in yard · ${r.soldCount || 0} billed · ${r.receivedCount || 0} received · ${r.transitCount || 0} in transit · ${r.heldCount || 0} booked/pilot/demo · ${oemStampSummary(r.leadsVehicleIds)}`,
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
    ...held.map((r) => r.model),
    ...need.map((r) => r.model),
  ].filter(Boolean))];
  const yardRows = model ? rows.filter((r) => r.model === model) : rows;
  const transitRows = model ? transit.filter((r) => r.model === model) : transit;
  const heldRows = model ? held.filter((r) => r.model === model) : held;
  const needRows = model ? need.filter((r) => r.model === model) : need;

  return (
    <div data-testid="yard-inventory">
      <PageHeader
        title="Yard Inventory"
        subtitle="OEM Invoice List is the billed source. In yard drops those chassis. Sold tracks every billed chassis. Received keeps every chassis that arrived from OEM."
        actions={<div className="flex gap-2">
          <ReportActions onRefresh={load} />
          {isOwner && (
            <Button data-testid="coulson-sync-btn" onClick={sync} disabled={busy}>
              <RefreshCcw size={15} /> {busy ? "Syncing…" : "Sync from OEM"}
            </Button>
          )}
        </div>} />

      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-5">
        <Card className="p-3" data-testid="inv-card-yard">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">In yard</div>
          <div className="text-xl font-bold tabular">{summary?.total ?? rows.length}</div>
        </Card>
        <Card className="p-3" data-testid="inv-card-transit">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">In transit</div>
          <div className="text-xl font-bold tabular">{summary?.transit ?? transit.length}</div>
        </Card>
        <Card className="p-3" data-testid="inv-card-held">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Booked / Pilot / Demo</div>
          <div className="text-xl font-bold tabular">{summary?.held ?? held.length}</div>
        </Card>
        {canSeeChassisLedger && (
          <Card className="p-3" data-testid="inv-card-sold">
            <div className="text-[11px] uppercase tracking-wide text-ink-faint">Sold</div>
            <div className="text-xl font-bold tabular">{summary?.sold ?? sold.length}</div>
          </Card>
        )}
        {canSeeChassisLedger && (
          <Card className="p-3" data-testid="inv-card-received">
            <div className="text-[11px] uppercase tracking-wide text-ink-faint">Received from OEM</div>
            <div className="text-xl font-bold tabular">{summary?.received ?? received.total}</div>
          </Card>
        )}
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

      <Card className="p-3 mb-4" data-testid="inventory-check-banner">
        {check?.confirmed && check.date === (check.today || "")
          ? <p className="text-sm text-emerald-800">Yard confirmed today by {check.submittedBy || "Showroom Admin"} · {check.presentCount || 0} present · {check.missingCount || 0} missing · {check.damagedCount || 0} damaged.</p>
          : <p className="text-sm text-amber-800">Yard not confirmed today{check?.lastConfirmedDate ? ` — last check: ${fmtDate(check.lastConfirmedDate)}` : ""}.</p>}
      </Card>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
          {TABS.filter(([k]) => canSeeChassisLedger || (k !== "sold" && k !== "received")).map(([k, l]) => (
            <button key={k} type="button" data-testid={`inv-tab-${k}`} onClick={() => setTab(k)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${tab === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>
              {l}
            </button>
          ))}
        </div>
        {tab !== "sold" && tab !== "received" && (
          <Select data-testid="inventory-model-filter" value={model} onChange={(e) => setModel(e.target.value)} className="w-52">
            <option value="">All models</option>
            {models.map((m) => <option key={m}>{m}</option>)}
          </Select>
        )}
        {canSeeChassisLedger && tab === "received" && (
          <Select data-testid="inventory-received-month" value={receivedMonth} onChange={(e) => setReceivedMonth(e.target.value)} className="w-52">
            <option value="">All months</option>
            {(received.byMonth || []).filter((m) => m.month && m.month !== "undated").map((m) => (
              <option key={m.month} value={m.month}>
                {m.month} ({m.count})
              </option>
            ))}
          </Select>
        )}
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
            { key: "motorNumber", label: "Motor", mono: true, render: (r) => <span className="text-xs">{r.motorNumber || "—"}</span> },
            { key: "batteryNumber", label: "Battery", mono: true, render: (r) => <span className="text-xs">{r.batteryNumber || "—"}</span> },
            { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
            { key: "inventoryAgeing", label: "Age (days)", align: "right", mono: true },
            { key: "pdiDone", label: "PDI", render: (r) => <Badge tone={r.pdiDone ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-100 text-zinc-500 ring-zinc-400/20"}>{r.pdiDone ? "Done" : "Pending"}</Badge> },
            { key: "readyForAllocation", label: "Ready", render: (r) => r.readyForAllocation ? "Yes" : "No" },
            { key: "physicalStatus", label: "Physical", render: (r) => (
              canConfirm ? (
                <Select
                  data-testid={`inv-tick-${r.chassis}`}
                  value={ticks[r.chassis] || r.physicalStatus || ""}
                  onChange={(e) => setTicks((cur) => ({ ...cur, [r.chassis]: e.target.value }))}
                  className="w-32"
                >
                  <option value="">—</option>
                  <option value="present">Present</option>
                  <option value="missing">Missing</option>
                  <option value="damaged">Damaged</option>
                </Select>
              ) : <Badge>{r.physicalStatus || "—"}</Badge>
            ) },
          ]}
          rows={yardRows}
        />
      )}
      {tab === "yard" && canConfirm && (
        <div className="mt-3">
          <Button data-testid="submit-inventory-check" disabled={busy} onClick={async () => {
            const items = yardRows.map((r) => ({
              chassis: r.chassis, model: r.model, variant: r.variant,
              status: ticks[r.chassis] || r.physicalStatus || "",
            }));
            if (items.some((i) => !i.status)) return toast.error("Tick every vehicle Present, Missing or Damaged.");
            setBusy(true);
            try {
              await post("/inventory/check", { items });
              toast.success("Yard confirmed");
              load();
            } catch (e) {
              toast.error(apiErrorMessage(e, "Could not save the yard check"));
            } finally { setBusy(false); }
          }}>
            Confirm today's yard
          </Button>
        </div>
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
            { key: "motorNumber", label: "Motor", mono: true, render: (r) => <span className="text-xs">{r.motorNumber || "—"}</span> },
            { key: "batteryNumber", label: "Battery", mono: true, render: (r) => <span className="text-xs">{r.batteryNumber || "—"}</span> },
            { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
            { key: "inventoryAgeing", label: "Age (days)", align: "right", mono: true },
          ]}
          rows={transitRows}
        />
      )}

      {tab === "held" && (
        <Table
          rowKey="chassis"
          empty="No booked, pilot, or demo vehicles from the last OEM sync."
          columns={[
            { key: "coulsonStatus", label: "OEM status", render: (r) => <Badge>{r.coulsonStatus || r.stockStatus || "Held"}</Badge> },
            { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
            { key: "variant", label: "Variant" },
            { key: "bodyType", label: "Body" },
            { key: "emch", label: "EMCH", mono: true },
            { key: "chassis", label: "Chassis", mono: true, render: (r) => <span className="text-xs">{r.chassis}</span> },
            { key: "motorNumber", label: "Motor", mono: true, render: (r) => <span className="text-xs">{r.motorNumber || "—"}</span> },
            { key: "batteryNumber", label: "Battery", mono: true, render: (r) => <span className="text-xs">{r.batteryNumber || "—"}</span> },
            { key: "exShowroom", label: "Ex-Showroom", align: "right", mono: true, render: (r) => inr(r.exShowroom) },
            { key: "inventoryAgeing", label: "Age (days)", align: "right", mono: true },
          ]}
          rows={heldRows}
        />
      )}

      {canSeeChassisLedger && tab === "sold" && (
        <Table
          rowKey="chassis"
          empty="No billed chassis yet — owner can sync Invoice List from OEM."
          columns={[
            { key: "chassis", label: "Chassis", mono: true, render: (r) => <span className="text-xs">{r.chassis}</span> },
            { key: "soldDate", label: "Sold date", render: (r) => fmtDate(r.soldDate) },
            { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName || "—"}</span> },
          ]}
          rows={sold}
        />
      )}

      {canSeeChassisLedger && tab === "received" && (
        <Table
          rowKey="chassis"
          empty="No chassis received from OEM yet — owner can sync from OEM."
          columns={[
            { key: "chassis", label: "Chassis", mono: true, render: (r) => <span className="text-xs">{r.chassis}</span> },
            { key: "receivedDate", label: "Received date", render: (r) => fmtDate(r.receivedDate) },
            { key: "receivedMonth", label: "Month" },
          ]}
          rows={received.rows || []}
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
