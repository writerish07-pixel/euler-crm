import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, AlertTriangle, FileText, Clock, XCircle, Link2Off } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button, Select } from "../components/ui";
import { useLeadDrawer, LeadLink } from "../components/LeadLink";
import { useAuth } from "../context/AuthContext";

// Euler's own ladder. Approval stages are the ones worth chasing; the terminal
// three have stopped moving and are toned apart so they never read as "pending".
const TERMINAL = ["Settled", "Rejected", "Cancelled"];
const STATUS_TONE = {
  Settled: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Rejected: "bg-rose-50 text-rose-700 ring-rose-600/20",
  Cancelled: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",
  "Credit Note Generated": "bg-blue-50 text-blue-700 ring-blue-600/20",
  "Sales Invoice Generated": "bg-blue-50 text-blue-700 ring-blue-600/20",
};
const tone = (s) => STATUS_TONE[s] || "bg-amber-50 text-amber-800 ring-amber-600/20";

// Days a single desk has been holding the claim. Colour is the whole point:
// a week is a nudge, a fortnight is a phone call.
function stageTone(days) {
  if (days >= 14) return "text-rose-600 font-semibold";
  if (days >= 7) return "text-amber-700 font-semibold";
  return "text-ink-soft";
}

export default function OemClaims() {
  const { isOwner } = useAuth();
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("");
  const [unlinked, setUnlinked] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(() => {
    get("/oem-claims/summary").then(setSummary).catch(() => setSummary(null));
    get("/oem-claims", {
      ...(status ? { status } : {}),
      ...(unlinked ? { unlinked: true } : {}),
    }).then((r) => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]));
  }, [status, unlinked]);

  useEffect(() => { load(); }, [load]);
  const { openLead, drawer } = useLeadDrawer(load);

  const sync = async () => {
    setSyncing(true);
    try {
      const r = await post("/integrations/coulson/sync-claims", {});
      toast.success(`${r.claimsMirrored} claims mirrored from Euler`);
      if (r.claimsIncomplete) {
        toast.error(`Only ${r.claimsMirrored} of ${r.claimsExpected} claims came back`);
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not reach Coulson");
    } finally {
      setSyncing(false);
    }
  };

  if (!summary) return <div className="text-ink-faint text-sm">Loading OEM claims…</div>;

  const { totals, mirror } = summary;
  const openCount = summary.buckets
    .filter((b) => !TERMINAL.includes(b.status))
    .reduce((s, b) => s + b.count, 0);
  const worst = summary.stuck[0];

  return (
    <div>
      <PageHeader
        title="OEM Claim Settlements"
        subtitle={`${summary.total} claims filed with Euler${
          mirror.syncedAt ? ` · synced ${fmtDate(String(mirror.syncedAt).slice(0, 10))}` : ""
        }`}
        actions={isOwner ? (
          <Button data-testid="sync-oem-claims" onClick={sync} disabled={syncing}>
            <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
            {syncing ? "Syncing…" : "Sync from Euler"}
          </Button>
        ) : null}
      />

      {/* A mirror holding a fraction of the register is worse than none at all —
          it looks like an answer. Say so before any number below is believed. */}
      {mirror.incomplete && (
        <Card className="mb-4 border-rose-200 bg-rose-50 p-4 flex items-start gap-3">
          <AlertTriangle size={18} className="text-rose-600 shrink-0 mt-0.5" />
          <div className="text-sm text-rose-800">
            <div className="font-semibold">This list is incomplete.</div>
            Euler reports {mirror.expected} claims; {mirror.mirrored} were mirrored. Every
            total on this page is understated until the next sync succeeds.
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6" data-testid="oem-claim-totals">
        <StatCard label="Open with Euler" value={openCount} sub={inr(totals.openClaimed)}
          icon={Clock} tone="text-amber-600" />
        <StatCard label="Total Claimed" value={inr(totals.claimed)} icon={FileText} />
        <StatCard label="Approved" value={inr(totals.approved)} tone="text-emerald-600" />
        <StatCard label="Longest Wait"
          value={worst ? `${worst.stageDays} days` : "—"}
          sub={worst ? worst.stageLabel : "nothing pending"}
          icon={AlertTriangle}
          tone={worst && worst.stageDays >= 14 ? "text-rose-600" : "text-ink"} />
      </div>

      {/* Money the books may still be carrying as receivable that Euler has refused. */}
      {summary.rejected.length > 0 && (
        <Card className="mb-6 p-4 border-rose-200">
          <div className="flex items-center gap-2 mb-3 text-rose-700 font-semibold text-sm">
            <XCircle size={16} /> {summary.rejected.length} rejected by Euler
          </div>
          <p className="text-xs text-ink-faint mb-3">
            Check the Scheme Claim Register — if these are still listed as eligible there,
            the books are carrying money that is not coming.
          </p>
          <div className="flex flex-wrap gap-2">
            {summary.rejected.map((r) => (
              <Badge key={r.claimNumber} tone="bg-rose-50 text-rose-700 ring-rose-600/20">
                {r.claimNumber} · {inr(r.claimedAmount)}
                {r.leadIds.length ? ` · ${r.leadIds.join(", ")}` : " · not linked"}
              </Badge>
            ))}
          </div>
        </Card>
      )}

      {summary.invoiceConflicts.length > 0 && (
        <Card className="mb-6 p-4 border-amber-200">
          <div className="flex items-center gap-2 mb-2 text-amber-800 font-semibold text-sm">
            <AlertTriangle size={16} /> Invoice disagreements
          </div>
          <ul className="text-xs text-ink-soft space-y-1">
            {summary.invoiceConflicts.map((c, i) => (
              <li key={i}><span className="font-mono">{c.claimNumber}</span> — {c.detail}</li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="mb-6 p-4">
        <div className="text-xs font-semibold text-ink-faint uppercase tracking-wide mb-3">
          Where the claims are sitting
        </div>
        <div className="flex flex-wrap gap-2">
          {summary.buckets.map((b) => (
            <button key={b.status} onClick={() => setStatus(status === b.status ? "" : b.status)}
              className={`text-left rounded-lg border px-3 py-2 transition-colors ${
                status === b.status ? "border-cobalt bg-cobalt/5" : "border-line hover:bg-zinc-50"}`}>
              <div className="text-[11px] text-ink-faint uppercase tracking-wide">{b.status}</div>
              <div className="text-lg font-semibold text-ink">{b.count}</div>
              <div className="text-xs text-ink-faint">{inr(b.claimed)}</div>
            </button>
          ))}
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-xs">
          <option value="">All statuses</option>
          {summary.buckets.map((b) => <option key={b.status}>{b.status}</option>)}
        </Select>
        <Button variant={unlinked ? "primary" : "secondary"} onClick={() => setUnlinked((v) => !v)}>
          <Link2Off size={16} /> Not linked to a lead
        </Button>
      </div>

      <Table
        rowKey="claimNumber"
        columns={[
          { key: "claimNumber", label: "Claim", mono: true, render: (r) => (
            <div>
              <div className="font-semibold text-cobalt">{r.claimNumber}</div>
              <div className="text-xs text-ink-faint">{r.settlementType}</div>
            </div>
          )},
          { key: "status", label: "Status", render: (r) => (
            <div className="flex flex-col gap-1 items-start">
              <Badge tone={tone(r.status)}>{r.status}</Badge>
              {!r.terminal && r.stageLabel && (
                <span className={`text-xs ${stageTone(r.stageDays)}`}>
                  {r.stageDays}d at {r.stageLabel}
                </span>
              )}
            </div>
          )},
          { key: "lead", label: "Lead", render: (r) => (
            r.leadIds && r.leadIds.length ? (
              <div className="flex flex-col items-start gap-0.5">
                {r.leadIds.map((id) => (
                  <LeadLink key={id} leadId={id} onOpen={openLead}
                    subtitle={(r.lineItems || []).find((li) => li.leadId === id)?.leadCustomer} />
                ))}
              </div>
            ) : <Badge tone="bg-zinc-100 text-zinc-600 ring-zinc-500/20">Not linked</Badge>
          )},
          { key: "vehicle", label: "Vehicle / Chassis", render: (r) => (
            <div className="text-xs">
              {(r.lineItems || []).map((li, i) => (
                <div key={i}>
                  <div>{[li.model, li.variant].filter(Boolean).join(" ") || "—"}</div>
                  <div className="font-mono text-ink-faint">{li.chassis || "—"}</div>
                </div>
              ))}
            </div>
          )},
          { key: "claimedAmount", label: "Claimed", align: "right", mono: true,
            render: (r) => inr(r.claimedAmount) },
          { key: "approvedAmount", label: "Approved", align: "right", mono: true,
            render: (r) => <span className={r.approvedAmount > 0 ? "text-emerald-600 font-semibold" : "text-ink-faint"}>{inr(r.approvedAmount)}</span> },
          { key: "createdDate", label: "Raised", render: (r) => (
            <div className="text-xs">
              <div>{fmtDate(r.createdDate)}</div>
              {!r.terminal && <div className="text-ink-faint">{r.claimAgeingDays}d old</div>}
            </div>
          )},
          { key: "doc", label: "", align: "right", render: (r) => (
            r.claimDocumentUrl ? (
              <a href={r.claimDocumentUrl} target="_blank" rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-cobalt text-xs font-medium hover:underline">PDF</a>
            ) : null
          )},
        ]}
        rows={rows}
        empty={mirror.syncedAt ? "No claims match this filter" : "Not synced from Euler yet"}
      />
      {drawer}
    </div>
  );
}
