import React, { useCallback, useEffect, useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { fmtDate, oemSyncToast } from "../lib/format";
import { PageHeader, Table, Badge, Button, Card } from "../components/ui";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { useLeadDrawer, LeadLink } from "../components/LeadLink";
import { usePeriodState, thisMonth, thisYear } from "../lib/period";
import { useAuth } from "../context/AuthContext";

const TABS = [
  ["pending_delivery", "Pending delivery"],
  ["created_from_oem", "Created from OEM"],
  ["matched_delivered", "Delivered"],
  ["needs_review", "Needs review"],
  ["unmatched", "Not in CRM"],
  ["", "All billed"],
];

const TONE = {
  pending_delivery: "bg-amber-50 text-amber-800 ring-amber-600/20",
  created_from_oem: "bg-sky-50 text-sky-800 ring-sky-600/20",
  matched_delivered: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  needs_review: "bg-rose-50 text-rose-800 ring-rose-600/20",
  unmatched: "bg-zinc-100 text-zinc-700 ring-zinc-500/20",
};

const LABEL = {
  pending_delivery: "Pending delivery",
  created_from_oem: "Created from OEM",
  matched_delivered: "Delivered",
  needs_review: "Needs review",
  unmatched: "Not in CRM",
};

export default function OemBilling() {
  const { canEditCommercials } = useAuth();
  const period = usePeriodState(thisMonth(), thisYear());
  const [tab, setTab] = useState("");
  const [day, setDay] = useState("");
  const [payload, setPayload] = useState({ rows: [], counts: {}, byDate: [], soldCount: 0, repair: {} });
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState("");

  const load = useCallback(() => {
    setLoadError("");
    return get("/oem-billing", period.params)
      .then((r) => {
        setPayload(r && typeof r === "object" ? r : { rows: [], counts: {}, byDate: [], soldCount: 0, repair: {} });
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, "Could not load OEM billing");
        setLoadError(msg);
        toast.error(msg);
      });
  }, [period.params]);
  useEffect(() => { load(); }, [load]);
  const { openLead, drawer } = useLeadDrawer(load);

  const applyPayload = (r) => {
    if (r && typeof r === "object") {
      setPayload(r);
      setLoadError("");
    }
  };

  const sync = async () => {
    setBusy(true);
    try {
      const qs = new URLSearchParams(period.params).toString();
      const r = await post(qs ? `/oem-billing/sync?${qs}` : "/oem-billing/sync", {});
      applyPayload(r);
      toast.success(oemSyncToast(r));
    } catch (e) {
      toast.error(apiErrorMessage(e, "OEM billing sync failed"));
    } finally {
      setBusy(false);
    }
  };

  const relinkSafe = async () => {
    setBusy(true);
    try {
      const r = await post("/oem-billing/repair-merge", { safeOnly: true });
      applyPayload({ ...payload, repair: r });
      const n = r.mergedCount || 0;
      toast.success(
        n
          ? `Connected ${n} original${n === 1 ? "" : "s"} and deleted the empty duplicate${n === 1 ? "" : "s"}`
          : "No safe matches to relink",
      );
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not relink OEM stubs"));
    } finally {
      setBusy(false);
    }
  };

  const connectPair = async (stubLeadId, originalLeadId) => {
    if (!stubLeadId || !originalLeadId) return;
    setBusy(true);
    try {
      const r = await post("/oem-billing/repair-merge", {
        pairs: [{ stubLeadId, originalLeadId }],
      });
      const n = r.mergedCount || 0;
      if (n) {
        toast.success(`Connected ${originalLeadId} and deleted duplicate ${stubLeadId}`);
      } else {
        const why = (r.skipped && r.skipped[0] && r.skipped[0].reason) || "Could not connect";
        toast.error(why);
      }
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not connect leads"));
    } finally {
      setBusy(false);
    }
  };

  const createUnmatched = async (chassis) => {
    if (!chassis) return;
    setCreating(chassis);
    try {
      const r = await post("/oem-billing/create", { chassis });
      toast.success(r.appended ? `Added chassis to ${r.leadId}` : `Created ${r.leadId}`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not create lead"));
    } finally {
      setCreating("");
    }
  };

  const counts = payload.counts || {};
  const byDate = payload.byDate || [];
  const repair = payload.repair || {};
  const pairsByStub = Object.fromEntries(
    (repair.pairs || []).filter((p) => p?.stub?.leadId).map((p) => [p.stub.leadId, p]),
  );
  const rows = (payload.rows || []).filter((r) => {
    if (tab && r.bucket !== tab) return false;
    if (!day) return true;
    const sold = r.undated ? "undated" : String(r.soldDate || "").slice(0, 10);
    return sold === day;
  });
  const emptyBecauseError = Boolean(loadError) && !(payload.soldCount || (payload.rows || []).length);

  return (
    <div data-testid="oem-billing">
      <PageHeader
        title="OEM Billing"
        subtitle="Every Coulson tax invoice, on the India date the OEM app printed. Sync refreshes Sold + Invoice List — it does not invent invoices."
        actions={<div className="flex gap-2">
          <ReportActions onRefresh={load} />
          {canEditCommercials && (repair.safeCount || 0) > 0 && (
            <Button data-testid="oem-billing-relink" onClick={relinkSafe} disabled={busy} variant="secondary">
              Relink {repair.safeCount} original{repair.safeCount === 1 ? "" : "s"}
            </Button>
          )}
          {canEditCommercials && (
            <Button data-testid="oem-billing-sync" onClick={sync} disabled={busy}>
              <RefreshCcw size={15} /> {busy ? "Syncing…" : "Sync from OEM"}
            </Button>
          )}
        </div>}
      />
      <PeriodBar month={period.month} year={period.year} onChange={(next) => { setDay(""); period.onChange(next); }} />
      {byDate.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4" data-testid="oem-bill-by-date">
          <button
            type="button"
            data-testid="oem-bill-day-all"
            onClick={() => setDay("")}
            className={`px-2.5 py-1 rounded-full text-[11px] font-semibold ring-1 ring-inset ${
              !day ? "bg-cobalt text-white ring-cobalt" : "bg-zinc-50 text-ink-soft ring-line"
            }`}
          >
            All days {payload.soldCount || 0}
          </button>
          {byDate.map((d) => (
            <button
              key={d.date}
              type="button"
              data-testid={`oem-bill-day-${d.date}`}
              onClick={() => setDay(d.date === day ? "" : d.date)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-semibold ring-1 ring-inset ${
                day === d.date ? "bg-cobalt text-white ring-cobalt" : "bg-zinc-50 text-ink-soft ring-line"
              }`}
            >
              {d.date === "undated" ? "Un-dated" : fmtDate(d.date)} · {d.count}
            </button>
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        <Card className="p-3" data-testid="oem-bill-card-total">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">OEM billed</div>
          <div className="text-xl font-bold tabular">{payload.soldCount || 0}</div>
        </Card>
        <Card className="p-3" data-testid="oem-bill-card-pending">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Pending delivery</div>
          <div className="text-xl font-bold tabular">{counts.pending_delivery || 0}</div>
        </Card>
        <Card className="p-3" data-testid="oem-bill-card-created">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Created from OEM</div>
          <div className="text-xl font-bold tabular">{counts.created_from_oem || 0}</div>
        </Card>
        <Card className="p-3" data-testid="oem-bill-card-delivered">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Delivered</div>
          <div className="text-xl font-bold tabular">{counts.matched_delivered || 0}</div>
        </Card>
        <Card className="p-3" data-testid="oem-bill-card-review">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Needs review</div>
          <div className="text-xl font-bold tabular">{counts.needs_review || 0}</div>
        </Card>
      </div>
      <div className="flex flex-wrap gap-2 mb-4">
        {TABS.map(([id, label]) => (
          <button
            key={id || "all"}
            type="button"
            data-testid={`oem-bill-tab-${id || "all"}`}
            onClick={() => setTab(id)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold ring-1 ring-inset ${
              tab === id
                ? "bg-cobalt text-white ring-cobalt"
                : "bg-zinc-50 text-ink-soft ring-line"
            }`}
          >
            {label}
            {id ? ` ${counts[id] || 0}` : ""}
          </button>
        ))}
      </div>
      <Table
        rowKey="chassis"
        columns={[
          { key: "customerName", label: "Customer", render: (r) => (
            <div>
              <div className="font-semibold">{r.customerName || "—"}</div>
              <div className="text-xs text-ink-faint font-mono">{r.mobile || "—"}</div>
            </div>
          ) },
          { key: "model", label: "Vehicle", render: (r) => (
            <div className="text-sm">
              {r.model || "—"}
              <div className="text-xs text-ink-faint">{r.variant}</div>
              {r.availableBodyType && r.billedBodyType && r.availableBodyType !== r.billedBodyType ? (
                <div className="text-[11px] text-ink-faint" data-testid={`oem-bill-body-${r.chassis}`}>
                  billed {r.billedBodyType} · available {r.availableBodyType}
                </div>
              ) : (r.billedBodyType ? (
                <div className="text-[11px] text-ink-faint">{r.billedBodyType}</div>
              ) : null)}
            </div>
          ) },
          { key: "chassis", label: "Chassis", mono: true },
          { key: "motorNumber", label: "Motor", mono: true, render: (r) => r.motorNumber || "—" },
          { key: "batteryNumber", label: "Battery", mono: true, render: (r) => r.batteryNumber || "—" },
          { key: "invoiceNumber", label: "Invoice", mono: true },
          { key: "soldDate", label: "OEM date", render: (r) => (
            r.undated ? <span className="text-ink-faint">Un-dated</span> : fmtDate(r.soldDate)
          ) },
          { key: "leadId", label: "CRM lead", render: (r) => {
            const pair = pairsByStub[r.leadId];
            const original = pair?.original;
            return (
              <div>
                {r.leadId
                  ? <LeadLink leadId={r.leadId} onOpen={openLead} subtitle={r.crmStatus} />
                  : <span className="text-xs text-ink-faint">—</span>}
                {original?.leadId && (
                  <div className="mt-1">
                    <div className="text-[11px] text-ink-faint">Original booked file</div>
                    <LeadLink leadId={original.leadId} onOpen={openLead} subtitle={original.currentStatus} />
                  </div>
                )}
                {pair?.reason && r.bucket === "created_from_oem" && (
                  <div className="text-[11px] text-ink-faint mt-1">{pair.reason}</div>
                )}
              </div>
            );
          } },
          { key: "bucket", label: "Status", render: (r) => (
            <div>
              <Badge tone={TONE[r.bucket] || TONE.unmatched}>{LABEL[r.bucket] || r.bucket}</Badge>
              {r.reviewReason ? <div className="text-[11px] text-ink-faint mt-1">{r.reviewReason}</div> : null}
              {canEditCommercials && r.bucket === "unmatched" && (
                <Button
                  variant="secondary"
                  className="mt-2"
                  data-testid={`oem-billing-create-${r.chassis}`}
                  disabled={busy || creating === r.chassis}
                  onClick={() => createUnmatched(r.chassis)}
                >
                  {creating === r.chassis ? "Creating…" : "Create lead"}
                </Button>
              )}
              {canEditCommercials && r.bucket === "needs_review" && (r.holderLeads || []).length > 1 && (
                <div className="mt-2 space-y-1" data-testid={`oem-billing-holders-${r.chassis}`}>
                  {(r.holderLeads || []).map((h) => (
                    <div key={h.leadId} className="text-[11px] text-ink-soft">
                      {h.leadId} · {h.currentStatus || "—"} · {h.executive || "no exec"}
                    </div>
                  ))}
                  {(r.duplicateLeadIds || []).map((dupId) => (
                    <Button
                      key={dupId}
                      variant="secondary"
                      className="mt-1"
                      data-testid={`oem-billing-connect-${r.chassis}-${dupId}`}
                      disabled={busy || !r.keeperLeadId}
                      onClick={() => connectPair(dupId, r.keeperLeadId)}
                    >
                      Keep {r.keeperLeadId}, delete {dupId}
                    </Button>
                  ))}
                  {!r.keeperLeadId && (r.holderLeads || []).filter((h) => h.leadId && h.leadId !== r.leadId).map((h) => (
                    <Button
                      key={`alt-${h.leadId}`}
                      variant="secondary"
                      className="mt-1"
                      data-testid={`oem-billing-connect-${r.chassis}-${h.leadId}`}
                      disabled={busy}
                      onClick={() => connectPair(h.leadId, r.leadId)}
                    >
                      Keep {r.leadId}, delete {h.leadId}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          ) },
        ]}
        rows={emptyBecauseError ? [] : rows}
        empty={emptyBecauseError
          ? loadError
          : tab === "pending_delivery"
            ? "No OEM-billed files waiting to be marked delivered"
            : "No OEM billed rows in this period"}
      />
      {loadError ? (
        <p className="text-[12px] text-rose-700 mt-3" data-testid="oem-billing-load-error">
          {loadError}
        </p>
      ) : null}
      {tab === "created_from_oem" && (repair.stubCount || 0) > 0 && (
        <p className="text-[12px] text-ink-faint mt-3" data-testid="oem-billing-repair-hint">
          These IDs are empty copies. Payments and scheme stay on the original file
          (including Close Won). Relink moves chassis/invoice onto that original and
          deletes the empty copy.
        </p>
      )}
      {drawer}
    </div>
  );
}
