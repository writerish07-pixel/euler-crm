import React, { useCallback, useEffect, useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { fmtDate } from "../lib/format";
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
  const [tab, setTab] = useState("pending_delivery");
  const [payload, setPayload] = useState({ rows: [], counts: {}, soldCount: 0 });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get("/oem-billing", period.params)
      .then((r) => setPayload(r && typeof r === "object" ? r : { rows: [], counts: {}, soldCount: 0 }))
      .catch(() => setPayload({ rows: [], counts: {}, soldCount: 0 }));
  }, [period.params]);
  useEffect(() => { load(); }, [load]);
  const { openLead, drawer } = useLeadDrawer(load);

  const sync = async () => {
    setBusy(true);
    try {
      const qs = new URLSearchParams(period.params).toString();
      const r = await post(qs ? `/oem-billing/sync?${qs}` : "/oem-billing/sync", {});
      setPayload(r && typeof r === "object" ? r : payload);
      const created = r.created || 0;
      toast.success(
        created
          ? `Synced OEM Sold · created ${created} lead${created === 1 ? "" : "s"}`
          : `Synced OEM Sold · ${(r.soldCount || 0)} billed`,
      );
    } catch (e) {
      toast.error(apiErrorMessage(e, "OEM billing sync failed"));
    } finally {
      setBusy(false);
    }
  };

  const counts = payload.counts || {};
  const rows = (payload.rows || []).filter((r) => !tab || r.bucket === tab);

  return (
    <div data-testid="oem-billing">
      <PageHeader
        title="OEM Billing"
        subtitle="Coulson Sold this month versus Euler leads. Pending files still need Mark Delivered. Missing customers are created as New leads."
        actions={<div className="flex gap-2">
          <ReportActions onRefresh={load} />
          {canEditCommercials && (
            <Button data-testid="oem-billing-sync" onClick={sync} disabled={busy}>
              <RefreshCcw size={15} /> {busy ? "Syncing…" : "Sync from OEM"}
            </Button>
          )}
        </div>}
      />
      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
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
            <div className="text-sm">{r.model || "—"}<div className="text-xs text-ink-faint">{r.variant}</div></div>
          ) },
          { key: "chassis", label: "Chassis", mono: true },
          { key: "invoiceNumber", label: "Invoice", mono: true },
          { key: "soldDate", label: "OEM date", render: (r) => (
            r.undated ? <span className="text-ink-faint">Un-dated</span> : fmtDate(r.soldDate)
          ) },
          { key: "leadId", label: "CRM lead", render: (r) => (
            r.leadId
              ? <LeadLink leadId={r.leadId} onOpen={openLead} subtitle={r.crmStatus} />
              : <span className="text-xs text-ink-faint">—</span>
          ) },
          { key: "bucket", label: "Status", render: (r) => (
            <div>
              <Badge tone={TONE[r.bucket] || TONE.unmatched}>{LABEL[r.bucket] || r.bucket}</Badge>
              {r.reviewReason ? <div className="text-[11px] text-ink-faint mt-1">{r.reviewReason}</div> : null}
            </div>
          ) },
        ]}
        rows={rows}
        empty={tab === "pending_delivery"
          ? "No OEM-billed files waiting to be marked delivered"
          : "No OEM billed rows in this period"}
      />
      {drawer}
    </div>
  );
}
