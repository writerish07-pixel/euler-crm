import React, { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { RefreshCw, AlertTriangle, FileText, Clock, XCircle, Link2Off, ExternalLink, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { REGISTER_MATCH, registerMatchOf, claimsHref } from "../lib/claimMatch";
import { Card, PageHeader, StatCard, Table, Badge, Button, Select, Input } from "../components/ui";
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
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("");
  const [unlinked, setUnlinked] = useState(false);
  const [matchFilter, setMatchFilter] = useState("");
  const [q, setQ] = useState(params.get("q") || "");
  const [syncing, setSyncing] = useState(false);

  const chassis = params.get("chassis") || "";
  const invoice = params.get("invoice") || "";
  const leadId = params.get("leadId") || "";
  const qParam = params.get("q") || "";

  const load = useCallback(() => {
    get("/oem-claims/summary").then(setSummary).catch(() => setSummary(null));
    get("/oem-claims", {
      ...(status ? { status } : {}),
      ...(unlinked ? { unlinked: true } : {}),
      ...(qParam ? { q: qParam } : {}),
      ...(chassis ? { chassis } : {}),
      ...(invoice ? { invoice } : {}),
      ...(leadId ? { leadId } : {}),
    }).then((r) => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]));
  }, [status, unlinked, qParam, chassis, invoice, leadId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setQ(qParam); }, [qParam]);
  const { openLead, drawer } = useLeadDrawer(load);

  const applySearch = (e) => {
    e?.preventDefault?.();
    const next = new URLSearchParams(params);
    if (q.trim()) next.set("q", q.trim());
    else next.delete("q");
    setParams(next, { replace: true });
  };

  const clearJoin = () => {
    const next = new URLSearchParams(params);
    next.delete("chassis");
    next.delete("invoice");
    next.delete("leadId");
    next.delete("q");
    setQ("");
    setParams(next, { replace: true });
  };

  const sync = async () => {
    setSyncing(true);
    try {
      const r = await post("/integrations/coulson/sync-claims", {});
      toast.success(`${r.claimsMirrored} claims mirrored from Euler`);
      if (r.claimsIncomplete) {
        toast.error(`Only ${r.claimsMirrored} of ${r.claimsExpected} claims came back`);
      }
      if ((r.claimsWithVehicle || 0) < (r.claimsMirrored || 0)) {
        toast.error(
          `Chassis/invoice on ${r.claimsWithVehicle || 0} of ${r.claimsMirrored} claims — sync again after deploy if this stays 0`
        );
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
  const joinActive = Boolean(chassis || invoice || leadId || qParam);

  const visibleRows = matchFilter
    ? rows.filter((r) => (r.registerMatch?.state || "") === matchFilter)
    : rows;
  const matchCounts = rows.reduce((acc, r) => {
    const s = r.registerMatch?.state;
    if (s) acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <PageHeader
        title="OEM Claim Settlements"
        subtitle={`${summary.total} claims filed with Euler${
          mirror.syncedAt ? ` · synced ${fmtDate(String(mirror.syncedAt).slice(0, 10))}` : ""
        }`}
        actions={<div className="flex items-center gap-2">
          <Link to="/claims" data-testid="open-scheme-register"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-cobalt hover:underline">
            Scheme Claim Register <ExternalLink size={14} />
          </Link>
          {isOwner ? (
            <Button data-testid="sync-oem-claims" onClick={sync} disabled={syncing}>
              <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Syncing…" : "Sync from Euler"}
            </Button>
          ) : null}
        </div>}
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

      {summary.total > 0 && (mirror.withVehicle || 0) < summary.total && (
        <Card className="mb-4 border-amber-200 bg-amber-50 p-4 flex items-start gap-3" data-testid="oem-missing-chassis">
          <AlertTriangle size={18} className="text-amber-700 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-900">
            <div className="font-semibold">Chassis and invoice are missing on some claims.</div>
            {mirror.withVehicle || 0} of {summary.total} have a vehicle id. Use{" "}
            <b>Sync from Euler</b> — the detail call is{" "}
            <code className="text-xs">debit-note/journey</code>, not the list row.
          </div>
        </Card>
      )}

      {joinActive && (
        <Card className="mb-4 p-3 flex flex-wrap items-center gap-2 text-sm" data-testid="oem-join-filter">
          <span className="text-ink-soft">Showing claims matching</span>
          {qParam && <Badge tone="bg-cobalt/10 text-cobalt ring-cobalt/20">claim {qParam}</Badge>}
          {chassis && <Badge tone="bg-cobalt/10 text-cobalt ring-cobalt/20">chassis {chassis}</Badge>}
          {invoice && <Badge tone="bg-cobalt/10 text-cobalt ring-cobalt/20">invoice {invoice}</Badge>}
          {leadId && <Badge tone="bg-cobalt/10 text-cobalt ring-cobalt/20">lead {leadId}</Badge>}
          <button className="text-xs text-cobalt hover:underline" onClick={clearJoin}>Clear</button>
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

      {/* Reverse of the Scheme Claim Register colours: Euler has it, this app may not. */}
      <Card className="mb-6 p-4" data-testid="register-crosscheck">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div className="text-xs font-semibold text-ink-faint uppercase tracking-wide">
            Cross-check with Scheme Claim Register
          </div>
          {matchFilter && (
            <button className="text-xs text-cobalt hover:underline" onClick={() => setMatchFilter("")}>
              Clear filter
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {["in_register", "missing_register", "unmapped", "unknown_lead"].map((s) => (
            matchCounts[s] ? (
              <button key={s} onClick={() => setMatchFilter(matchFilter === s ? "" : s)}
                data-testid={`register-filter-${s}`}
                className={`rounded-lg border px-3 py-2 text-left transition-colors ${
                  matchFilter === s ? "border-cobalt bg-cobalt/5" : "border-line hover:bg-zinc-50"}`}>
                <Badge tone={REGISTER_MATCH[s].tone}>{REGISTER_MATCH[s].label}</Badge>
                <div className="text-lg font-semibold text-ink mt-1">{matchCounts[s]}</div>
              </button>
            ) : null
          ))}
        </div>
        {(matchCounts.missing_register || matchCounts.unknown_lead) ? (
          <p className="mt-3 text-sm text-violet-800">
            Violet rows are filed in Euler but missing from the Scheme Claim Register.
            Grey rows never matched a lead chassis or invoice.
          </p>
        ) : null}
      </Card>

      {/* Money the books may still be carrying as receivable that Euler has refused. */}
      {summary.rejected.length > 0 && (
        <Card className="mb-6 p-4 border-rose-200">
          <div className="flex items-center gap-2 mb-3 text-rose-700 font-semibold text-sm">
            <XCircle size={16} /> {summary.rejected.length} rejected by Euler
          </div>
          <p className="text-xs text-ink-faint mb-3">
            Euler does not reopen a rejected debit note — a resubmission is a new claim
            on the same chassis. Check the Scheme Claim Register if these are still listed
            as eligible.
          </p>
          <div className="flex flex-wrap gap-2">
            {summary.rejected.map((r) => (
              <div key={r.claimNumber} className="rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-semibold text-rose-800">{r.claimNumber}</span>
                  <span className="text-ink-soft">{inr(r.claimedAmount)}</span>
                  {r.resubmittedBy
                    ? <Badge tone="bg-sky-50 text-sky-700 ring-sky-600/20">Refiled as {r.resubmittedBy}</Badge>
                    : r.needsResubmission
                      ? <Badge tone="bg-rose-100 text-rose-800 ring-rose-600/30">
                          <RotateCcw size={11} className="inline mr-0.5" /> Needs refile
                        </Badge>
                      : null}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {(r.leadIds || []).length
                    ? r.leadIds.map((id) => (
                      <LeadLink key={id} leadId={id} onOpen={openLead} />
                    ))
                    : <span className="text-ink-faint">not linked</span>}
                </div>
              </div>
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

      <form onSubmit={applySearch} className="flex flex-wrap items-center gap-2 mb-4">
        <Input
          data-testid="oem-claim-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Claim no. / chassis / invoice / lead"
          className="max-w-xs"
        />
        <Button type="submit" variant="secondary">Search</Button>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-xs">
          <option value="">All statuses</option>
          {summary.buckets.map((b) => <option key={b.status}>{b.status}</option>)}
        </Select>
        <Button type="button" variant={unlinked ? "primary" : "secondary"} onClick={() => setUnlinked((v) => !v)}>
          <Link2Off size={16} /> Not linked to a lead
        </Button>
      </form>

      <Table
        rowKey="claimNumber"
        rowClassName={(r) => registerMatchOf(r).row}
        columns={[
          { key: "claimNumber", label: "Claim", mono: true, render: (r) => (
            <div>
              <div className="font-semibold text-cobalt">{r.claimNumber}</div>
              <div className="text-xs text-ink-faint">{r.settlementType}</div>
            </div>
          )},
          { key: "registerMatch", label: "In this app", render: (r) => {
            const m = registerMatchOf(r);
            return (
              <div className="flex flex-col items-start gap-1" title={r.registerMatch?.detail || ""}>
                <Badge tone={m.tone}>{m.label}</Badge>
                {r.registerMatch?.resubmittedBy
                  ? <span className="text-[10px] text-sky-700">Refiled as {r.registerMatch.resubmittedBy}</span>
                  : r.registerMatch?.needsResubmission
                    ? <span className="text-[10px] text-rose-700">Needs refile</span>
                    : null}
              </div>
            );
          }},
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
                <Link to={claimsHref({ leadId: r.leadIds[0] })}
                  onClick={(e) => e.stopPropagation()}
                  className="text-[10px] text-cobalt hover:underline">Scheme register</Link>
              </div>
            ) : <Badge tone="bg-zinc-100 text-zinc-600 ring-zinc-500/20">Not linked</Badge>
          )},
          { key: "vehicle", label: "Chassis / Invoice", render: (r) => (
            (r.lineItems || []).length ? (
            <div className="text-xs">
              {(r.lineItems || []).map((li, i) => (
                <div key={i} className="mb-1">
                  <div>{[li.model, li.variant].filter(Boolean).join(" ") || "—"}</div>
                  <div className="font-mono text-ink-faint">{li.chassis || "—"}</div>
                  {li.sourceInvoiceNumber
                    ? <div className="font-mono text-ink-faint">{li.sourceInvoiceNumber}</div>
                    : null}
                </div>
              ))}
            </div>
            ) : <span className="text-xs text-ink-faint">Not pulled — sync again</span>
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
        rows={visibleRows}
        empty={mirror.syncedAt ? "No claims match this filter" : "Not synced from Euler yet"}
      />
      {drawer}
    </div>
  );
}
