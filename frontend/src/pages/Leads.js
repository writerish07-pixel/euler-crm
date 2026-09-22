import React, { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, ChevronRight, Upload } from "lucide-react";
import ReportActions from "../components/ReportActions";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Button, Table, Badge, Input } from "../components/ui";
import LeadDrawer from "./LeadDrawer";
import LeadImport from "./LeadImport";
import NewLeadDrawer from "./NewLeadDrawer";
import { useAuth } from "../context/AuthContext";
import PeriodBar from "../components/PeriodBar";
import { usePeriodState } from "../lib/period";
import CallLink from "../components/CallLink";
import CompleteFormatDrawer from "../components/CompleteFormatDrawer";

const STATUS_FILTERS = ["all", "New", "Contacted", "Follow-up", "In Progress", "Booked", "Finance Process", "Delivered", "Close Won", "Lost"];

export default function Leads() {
  const { isField, isExecutive, isOwner } = useAuth();
  const [leads, setLeads] = useState([]);
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(null);
  const [proceed, setProceed] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [showNew, setShowNew] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [masters, setMasters] = useState(null);
  const [repairBusy, setRepairBusy] = useState(false);
  const period = usePeriodState();

  const load = useCallback(() => {
    get("/leads", { status, q: q || undefined, ...period.params }).then(setLeads);
  }, [status, q, period.params]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { get("/masters").then(setMasters); }, []);
  useEffect(() => {
    const open = searchParams.get("open");
    if (!open) return undefined;
    setActive(open);
    const next = new URLSearchParams(searchParams);
    next.delete("open");
    setSearchParams(next, { replace: true });
    return undefined;
  }, [searchParams, setSearchParams]);

  const openLead = (r) => { setActive(r.leadId); };

  const startApproval = async (r) => {
    try {
      const row = await get(`/leads/${r.leadId}/approval-request`);
      setProceed(row);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not start approval"));
    }
  };

  const columns = [
    { key: "leadId", label: "Lead ID", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.leadId}</span> },
    { key: "customerName", label: "Customer", render: (r) => (
      <div>
        <div className="font-semibold text-ink">{r.customerName}</div>
        <CallLink mobile={r.mobile} compact />
      </div>
    )},
    { key: "vehicle", label: "Vehicle", render: (r) => {
      const n = Number(r.vehicleCount || (r.units || []).length || 1);
      if (n > 1) {
        return (
          <div className="text-sm" data-testid={`lead-units-${r.leadId}`}>
            <div className="font-medium">{n} units</div>
            <div className="text-xs text-ink-faint">
              {(r.units || []).map((u) => [u.model, u.variant].filter(Boolean).join(" ")).filter(Boolean).join(" · ")
                || `${r.interestedModel || "—"} ${r.variant || ""}`}
            </div>
          </div>
        );
      }
      return <div className="text-sm"><div>{r.interestedModel || "—"}</div><div className="text-xs text-ink-faint">{r.variant}</div></div>;
    } },
    { key: "executive", label: "Executive", render: (r) => (
      r.executive ? (
        <div>
          <div className="font-medium">{r.executive}</div>
          {isExecutive && r.assignmentPending && (
            <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20">Awaiting approval</Badge>
          )}
        </div>
      ) : <span className="text-ink-faint">—</span>
    ) },
    { key: "currentStatus", label: "Status", render: (r) => (
      <div className="flex flex-wrap items-center gap-1">
        <Badge>{r.currentStatus}</Badge>
        {/* A lead that has walked away before is worth seeing before the next call —
            including one that has since come back and reads as "New" again. */}
        {Number(r.cancelCount || 0) > 0 && (
          <Badge tone="bg-rose-50 text-rose-700 ring-rose-600/20"
            title={`${r.lastCancelReason || "Cancelled"}${r.lastCancelDate ? ` · ${r.lastCancelDate}` : ""}`}>
            {Number(r.cancelCount) === 1 ? "Cancelled once" : `Cancelled ${r.cancelCount}×`}
          </Badge>
        )}
      </div>
    ) },
    ...(!isField ? [
      { key: "customerPayable", label: "Payable", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
      { key: "customerOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.customerOutstanding > 0 ? "text-red-600 font-semibold" : "text-emerald-600"}>{inr(r.customerOutstanding)}</span> },
      // Money held above Customer Payable, and what has already gone back.
      { key: "excessReceived", label: "Excess / Refund", align: "right", mono: true, render: (r) => (
        <div className="text-xs">
          <div className={r.excessReceived > 0 ? "text-amber-700 font-semibold" : "text-ink-faint"}>{inr(r.excessReceived || 0)}</div>
          {r.refundedAmount > 0 && <div className="text-ink-faint">refunded {inr(r.refundedAmount)}</div>}
        </div>
      )},
    ] : []),
    { key: "go", label: "", align: "right", render: (r) => (
      isExecutive && r.assignmentPending
        ? (
          <Button data-testid={`proceed-${r.leadId}`} className="!py-1 !px-2.5 text-xs"
            onClick={(e) => { e.stopPropagation(); startApproval(r); }}>
            Proceed
          </Button>
        )
        : <ChevronRight size={16} className="text-ink-faint inline" />
    ) },
  ];

  const pendingN = isExecutive ? leads.filter((l) => l.assignmentPending).length : 0;

  return (
    <div>
      <PageHeader
        title="Lead Register"
        subtitle={`${leads.length} leads · ${leads.reduce((n, r) => n + (Number(r.vehicleCount || (r.units || []).length) || 1), 0)} vehicles${isField ? " · field view" : ""}${pendingN ? ` · ${pendingN} to Proceed` : ""}`}
        actions={<div className="flex gap-2">
          <ReportActions onRefresh={load} />
          {isOwner && (
            <Button variant="secondary" data-testid="repair-dup-leads-btn" disabled={repairBusy}
              onClick={async () => {
                if (!window.confirm("Collapse New files created by the triple-id bug? Same customer, same day, no booking or payment. Identical SKU extras are deleted. Different models join one pack.")) return;
                setRepairBusy(true);
                try {
                  const r = await post("/leads/repair-retry-duplicates", {});
                  toast.success(r.repaired ? `Fixed ${r.repaired} customer group${r.repaired === 1 ? "" : "s"}` : "No duplicate New files to fix");
                  load();
                } catch (e) {
                  toast.error(apiErrorMessage(e, "Could not repair duplicates"));
                } finally { setRepairBusy(false); }
              }}>
              {repairBusy ? "Fixing…" : "Fix duplicate New files"}
            </Button>
          )}
          {!isField && !isExecutive && (
            <Button variant="secondary" data-testid="import-leads-btn" onClick={() => setShowImport(true)}><Upload size={16} /> Import</Button>
          )}
          {!isField && (
            <Button data-testid="new-lead-btn" onClick={() => setShowNew(true)}><Plus size={16} /> {isExecutive ? "Request lead" : "New Lead"}</Button>
          )}
        </div>}
      />

      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />

      <div className="flex flex-col gap-2 mb-4 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex gap-1 overflow-x-auto bg-white rounded-lg p-1 border border-line shadow-card scrollbar-thin -mx-1 px-1 sm:mx-0 sm:flex-wrap">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              data-testid={`filter-${s}`}
              onClick={() => setStatus(s)}
              className={`shrink-0 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${status === s ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}
        </div>
        <div className="w-full sm:flex-1 sm:min-w-[200px]">
          <Input data-testid="lead-search" placeholder="Search name / mobile / ID…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <Table
        rowKey="leadId"
        onRowClick={(r) => openLead(r)}
        columns={columns}
        rows={leads}
        empty="No leads match this filter"
      />

      {active && (
        <LeadDrawer leadId={active} masters={masters} onClose={() => setActive(null)} onChanged={load} />
      )}
      {proceed && (
        <CompleteFormatDrawer
          row={proceed}
          onClose={() => setProceed(null)}
          onSaved={() => { setProceed(null); load(); }}
        />
      )}
      {showNew && (
        <NewLeadDrawer
          masters={masters}
          onClose={() => setShowNew(false)}
          onCreated={(id) => { setShowNew(false); load(); if (id) setActive(id); }}
        />
      )}
      {showImport && (
        <LeadImport onClose={() => setShowImport(false)} onDone={() => { setShowImport(false); load(); }} />
      )}
    </div>
  );
}
