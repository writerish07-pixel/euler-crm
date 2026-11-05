import React, { useCallback, useEffect, useRef, useState } from "react";
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
  const [resolving, setResolving] = useState("");

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

  const resolveReview = async (r, action, leadId, manual = false) => {
    const cand = (r.candidateLeads || []).find((c) => c.leadId === leadId) || {};
    const wrong = cand.wrongChassis || {};
    const what = action === "create"
      ? `Create a NEW lead for ${r.model || "this vehicle"} ${r.chassis}? Use this for a separate purchase.`
      : action === "replace"
        ? `On ${leadId}, replace chassis ${wrong.chassis} (${wrong.model || "other model"}) with ${r.chassis} · invoice ${r.invoiceNumber || "—"}? The old number plate is cleared.`
        : action === "add_unit"
        ? `Add ${r.model || "this vehicle"} ${r.chassis} as ANOTHER UNIT on ${leadId}? Only do this if it is the same order.`
        : `Link chassis ${r.chassis} (invoice ${r.invoiceNumber || "—"}) to ${leadId}?`;
    if (!window.confirm(what)) return;
    setResolving(r.chassis);
    try {
      const body = { chassis: r.chassis, leadId, action };
      if (manual) body.manual = true;
      const res = await post("/oem-billing/resolve", body, { retry: false });
      toast.success(action === "create"
        ? `Created ${res.leadId}`
        : action === "replace"
          ? `Replaced ${res.removedChassis} with ${res.chassis} on ${res.leadId}`
          : action === "add_unit"
          ? `Added as unit ${res.vehicleCount} on ${res.leadId}`
          : `Linked to ${res.leadId}`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not resolve this review"));
    } finally {
      setResolving("");
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
              {canEditCommercials && r.bucket === "needs_review" && (r.candidateLeads || []).length > 0 && (
                <ReviewChoices row={r} busy={busy || resolving === r.chassis}
                  onResolve={resolveReview} onOpen={openLead} />
              )}
              {canEditCommercials && (r.bucket === "needs_review" || r.bucket === "unmatched") && (
                <ManualLeadLink row={r} busy={busy || resolving === r.chassis}
                  onResolve={(row, action, leadId) => resolveReview(row, action, leadId, true)} />
              )}
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


/** Needs review: which CRM file is this chassis? Link / add as unit / new lead. */
export function ReviewChoices({ row, busy, onResolve, onOpen }) {
  const cands = row.candidateLeads || [];
  return (
    <div className="mt-2 space-y-2 min-w-[16rem]" data-testid={`oem-review-${row.chassis}`}>
      {cands.map((c) => (
        <div key={c.leadId}
          className={`rounded-lg ring-1 ring-inset p-2 ${c.recommended ? "ring-emerald-500/40 bg-emerald-50/50" : "ring-line bg-white"}`}
          data-testid={`oem-review-cand-${row.chassis}-${c.leadId}`}>
          <div className="flex items-center gap-1.5 flex-wrap">
            <LeadLink leadId={c.leadId} onOpen={onOpen} subtitle={c.currentStatus} />
            {c.recommended ? <Badge tone="bg-emerald-50 text-emerald-800 ring-emerald-600/20">Suggested</Badge> : null}
          </div>
          <div className="text-[11px] text-ink-soft mt-0.5">
            {[c.model, c.variant].filter(Boolean).join(" · ") || "No vehicle"}
            {c.vehicleCount > 1 ? ` · ${c.vehicleCount} vehicles` : ""}
            {c.chassis ? ` · has ${c.chassis}` : " · no chassis yet"}
            {c.executive ? ` · ${c.executive}` : ""}
          </div>
          {!c.modelMatches ? (
            <div className="text-[11px] text-rose-700 mt-0.5">Different vehicle from the OEM invoice ({row.model || "—"})</div>
          ) : null}
          {c.canReplace && c.wrongChassis ? (
            <div className="text-[11px] text-rose-700 mt-0.5" data-testid={`oem-review-wrong-${row.chassis}-${c.leadId}`}>
              Holds {c.wrongChassis.chassis}, which OEM billed as {c.wrongChassis.model || "another model"}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {c.canReplace ? (
              <Button disabled={busy}
                data-testid={`oem-review-replace-${row.chassis}-${c.leadId}`}
                onClick={() => onResolve(row, "replace", c.leadId)}>
                Replace wrong chassis
              </Button>
            ) : null}
            <Button variant="secondary" disabled={busy || !c.canLink} title={c.linkBlockedReason || ""}
              data-testid={`oem-review-link-${row.chassis}-${c.leadId}`}
              onClick={() => onResolve(row, "link", c.leadId)}>
              Link to {c.leadId}
            </Button>
            <Button variant="secondary" disabled={busy || !c.canAddUnit} title={c.addUnitBlockedReason || ""}
              data-testid={`oem-review-unit-${row.chassis}-${c.leadId}`}
              onClick={() => onResolve(row, "add_unit", c.leadId)}>
              Add as another unit
            </Button>
          </div>
          {(!c.canLink && c.linkBlockedReason) || (!c.canAddUnit && c.addUnitBlockedReason) ? (
            <div className="text-[10.5px] text-ink-faint mt-1">
              {[!c.canLink && c.linkBlockedReason, !c.canAddUnit && c.addUnitBlockedReason].filter(Boolean).join(" · ")}
            </div>
          ) : null}
        </div>
      ))}
      <Button variant="secondary" disabled={busy}
        data-testid={`oem-review-create-${row.chassis}`}
        onClick={() => onResolve(row, "create")}>
        Create new lead (separate purchase)
      </Button>
    </div>
  );
}


function isOpenLead(l) {
  const status = String(l.currentStatus || "").toLowerCase();
  const acct = String(l.accountStatus || "Active").toLowerCase();
  if (l.dealCancelled || ["cancelled", "inactive", "archived", "closed"].includes(acct)) return false;
  if (String(l.deliveryStatus || "").toLowerCase() === "delivered") return false;
  return !(status === "delivered" || status.includes("close won"));
}

function leadChassis(l) {
  const out = [];
  [l.chassisNumber, ...((l.units || []).map((u) => u && u.chassisNumber))].forEach((c) => {
    const v = String(c || "").trim();
    if (v && !out.includes(v)) out.push(v);
  });
  return out;
}

/** Search any open CRM lead and put this OEM chassis on it — its KYC and
 *  documents are already there, so no new lead is needed. */
export function ManualLeadLink({ row, busy, onResolve }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [searching, setSearching] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    if (!open) return undefined;
    const term = q.trim();
    if (term.length < 3) { setHits([]); return undefined; }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      setSearching(true);
      get("/leads", { q: term, limit: 25 })
        .then((rows) => { if (mine === seq.current) setHits((rows || []).filter(isOpenLead).slice(0, 10)); })
        .catch(() => { if (mine === seq.current) setHits([]); })
        .finally(() => { if (mine === seq.current) setSearching(false); });
    }, 300);
    return () => clearTimeout(t);
  }, [q, open]);

  const start = () => {
    setOpen(true);
    setQ(row.mobile || row.customerName || "");
  };

  if (!open) {
    return (
      <Button variant="secondary" className="mt-2" disabled={busy}
        data-testid={`oem-manual-open-${row.chassis}`} onClick={start}>
        Link to an existing lead…
      </Button>
    );
  }
  return (
    <div className="mt-2 rounded-lg ring-1 ring-inset ring-line p-2 bg-white min-w-[16rem]"
      data-testid={`oem-manual-${row.chassis}`}>
      <div className="text-[11px] text-ink-soft mb-1">
        Open leads only. Search name, mobile or lead ID.
      </div>
      <input
        className="w-full rounded-md ring-1 ring-inset ring-line px-2 py-1 text-sm"
        value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name / mobile / LD…"
        data-testid={`oem-manual-q-${row.chassis}`} autoFocus />
      {searching ? <div className="text-[11px] text-ink-faint mt-1">Searching…</div> : null}
      {!searching && q.trim().length >= 3 && hits.length === 0 ? (
        <div className="text-[11px] text-ink-faint mt-1">No open lead found</div>
      ) : null}
      <div className="space-y-1.5 mt-1.5">
        {hits.map((l) => {
          const held = leadChassis(l);
          const mobileDiffers = row.mobile && l.mobile && String(l.mobile).slice(-10) !== String(row.mobile).slice(-10);
          return (
            <div key={l.leadId} className="rounded-md ring-1 ring-inset ring-line p-1.5"
              data-testid={`oem-manual-hit-${row.chassis}-${l.leadId}`}>
              <div className="text-xs font-semibold">{l.leadId} · {l.customerName || "—"}</div>
              <div className="text-[11px] text-ink-soft">
                {[l.interestedModel, l.variant].filter(Boolean).join(" · ") || "No vehicle"}
                {` · ${l.currentStatus || "New"}`}
                {held.length ? ` · has ${held.join(", ")}` : " · no chassis yet"}
              </div>
              {mobileDiffers ? (
                <div className="text-[11px] text-amber-800">Mobile {l.mobile} differs from OEM invoice {row.mobile}</div>
              ) : null}
              <div className="flex flex-wrap gap-1.5 mt-1">
                {held.length === 0 ? (
                  <Button variant="secondary" disabled={busy}
                    data-testid={`oem-manual-link-${row.chassis}-${l.leadId}`}
                    onClick={() => onResolve(row, "link", l.leadId)}>
                    Link here
                  </Button>
                ) : (
                  <Button variant="secondary" disabled={busy}
                    data-testid={`oem-manual-unit-${row.chassis}-${l.leadId}`}
                    onClick={() => onResolve(row, "add_unit", l.leadId)}>
                    Add as another unit
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <button type="button" className="text-[11px] text-ink-faint underline mt-1.5"
        onClick={() => { setOpen(false); setHits([]); }}>
        Cancel
      </button>
    </div>
  );
}
