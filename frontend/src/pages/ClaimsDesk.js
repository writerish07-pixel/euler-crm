import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, FileText, HandCoins, Link2Off, Plus, RefreshCw, RotateCcw, XCircle } from "lucide-react";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import {
  OEM_MATCH, REGISTER_MATCH, DocFlag, claimHasVehicle, componentLabel, eulerClaimJob,
  lineChassisList, lineLeadIds, lineLeadLabel, lineNeedsCreate, looksCombinedSupport, oemLineText, oemMatchOf,
  registerMatchOf, rowLeadIds, rowLineItems, schemeClaimJob,
} from "../lib/claimMatch";
import { eulerRowVisible, isIncentiveClaim, schemeRowVisible } from "../lib/claimsDeskFilters";
import { PageHeader, Table, Badge, Button, Card, Input, StatCard } from "../components/ui";
import { useLeadDrawer, LeadLink } from "../components/LeadLink";
import { useAuth } from "../context/AuthContext";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { usePeriodState } from "../lib/period";
import ClaimsDeskSwitch from "../components/ClaimsDeskSwitch";
import { ClaimReceiptModal, ManualClaimModal, MatchOemModal, OemOnlyCreate, SettleModal } from "./Claims";
import { CreateOemButton, MatchRegisterModal, RelinkButton } from "./OemClaims";

const JOBS = [
  { id: "not_claimed", view: "ours", label: "We have not filed these", tone: "text-red-600" },
  { id: "rejected", view: "ours", label: "Euler rejected these", tone: "text-rose-700" },
  { id: "no_lead", view: "euler", label: "Euler has the claim. We have no lead.", tone: "text-violet-800" },
  { id: "missing_chassis", view: "euler", label: "Chassis is missing", tone: "text-amber-800" },
];

const SCHEME_MATCHES = ["accepted", "filed", "resubmitted", "unmapped", "rejected", "not_filed"];
const REGISTER_MATCHES = ["in_register", "missing_register", "unmapped", "unknown_lead"];

function outstandingOf(row) {
  return Math.max(0, Number(row.eligibleClaim || 0) - Number(row.receivedAmount || 0));
}

function schemeVehicle(row) {
  return [row.chassisNumber, row.invoiceNumber].filter(Boolean).join(" · ") || "—";
}

function claimStatusTone(status) {
  if (status === "Cancelled" || status === "Dropped") return "bg-zinc-100 text-zinc-600 ring-zinc-400/30";
  if (status === "Received" || status === "Approved") return "bg-emerald-50 text-emerald-700 ring-emerald-600/20";
  if (status === "Submitted") return "bg-blue-50 text-blue-700 ring-blue-600/20";
  if (status === "Rejected") return "bg-rose-50 text-rose-700 ring-rose-600/20";
  if (status === "Partial") return "bg-amber-50 text-amber-700 ring-amber-600/20";
  return undefined;
}

function stageTone(days) {
  if (days >= 14) return "text-rose-600 font-semibold";
  if (days >= 7) return "text-amber-700 font-semibold";
  return "text-ink-soft";
}

function Chip({ active, onClick, testId, children }) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={`rounded-lg border px-3 py-2 text-left transition-colors ${
        active ? "border-cobalt bg-cobalt/5" : "border-line hover:bg-zinc-50"
      }`}
    >
      {children}
    </button>
  );
}

export default function ClaimsDesk() {
  const { canSyncOemClaims, isMoneyDesk } = useAuth();
  const [params, setParams] = useSearchParams();
  const period = usePeriodState();
  const [scheme, setScheme] = useState([]);
  const [euler, setEuler] = useState([]);
  const [summary, setSummary] = useState(null);
  const [oemOnly, setOemOnly] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState(params.get("q") || "");
  const [status, setStatus] = useState("");
  const [unlinked, setUnlinked] = useState(false);
  const [missingDoc, setMissingDoc] = useState(false);
  const [schemeMatch, setSchemeMatch] = useState("");
  const [registerMatch, setRegisterMatch] = useState("");
  const [selected, setSelected] = useState(null);
  const [matchClaim, setMatchClaim] = useState(null);
  const [matchRow, setMatchRow] = useState(null);
  const [receipt, setReceipt] = useState(false);
  const [manual, setManual] = useState(false);
  const [leads, setLeads] = useState([]);
  const [syncing, setSyncing] = useState(false);

  const job = params.get("job") || "";
  const leadFilter = params.get("leadId") || "";
  const chassisFilter = params.get("chassis") || "";
  const invoiceFilter = params.get("invoice") || "";
  const explicitView = params.get("view") || "";
  const view = explicitView || (chassisFilter || invoiceFilter ? "euler" : leadFilter ? "ours" : "work");

  const load = useCallback(() => {
    setLoading(true);
    return Promise.all([
      get("/claims", period.params, { timeout: 60000 })
        .then((r) => setScheme(Array.isArray(r) ? r : []))
        .catch((err) => {
          toast.error(apiErrorMessage(err, "Could not load our claims"));
          setScheme([]);
        }),
      get("/oem-claims")
        .then((r) => setEuler(Array.isArray(r) ? r : []))
        .catch((err) => {
          toast.error(apiErrorMessage(err, "Could not load Euler claims"));
          setEuler([]);
        }),
      get("/oem-claims/summary").then((r) => setSummary(r && !Array.isArray(r) ? r : null)).catch(() => setSummary(null)),
      get("/claims/oem-only").then((r) => setOemOnly(r && !Array.isArray(r) ? r : null)).catch(() => setOemOnly(null)),
    ]).finally(() => setLoading(false));
  }, [period.params]);

  useEffect(() => { load(); }, [load]);
  const { openLead, drawer } = useLeadDrawer(load);

  const go = (nextView, nextJob = "") => {
    const next = new URLSearchParams(params);
    if (nextView && nextView !== "work") next.set("view", nextView);
    else next.delete("view");
    if (nextJob) next.set("job", nextJob);
    else next.delete("job");
    setParams(next, { replace: true });
    setSelected(null);
    setSchemeMatch("");
    setRegisterMatch("");
    setStatus("");
  };

  const clearJoin = () => {
    const next = new URLSearchParams(params);
    next.delete("leadId");
    next.delete("chassis");
    next.delete("invoice");
    next.delete("q");
    setQ("");
    setParams(next, { replace: true });
  };

  const scope = {
    view, job, leadId: leadFilter, chassis: chassisFilter, invoice: invoiceFilter, q,
    status, unlinked, missingDoc, registerMatch, match: schemeMatch,
  };
  const schemeRows = scheme.filter((row) => schemeRowVisible(row, scope));
  const eulerRows = euler.filter((row) => eulerRowVisible(row, scope));

  const schemeScoped = scheme.filter((row) => !leadFilter || row.leadId === leadFilter);
  const notClaimed = schemeScoped.filter((row) => schemeClaimJob(row) === "not_claimed");
  const rejected = schemeScoped.filter((row) => schemeClaimJob(row) === "rejected");
  const noLead = euler.filter((row) => eulerRowVisible(row, { ...scope, view: "euler", job: "no_lead", status: "", unlinked: false, missingDoc: false, registerMatch: "" }));
  const missing = euler.filter((row) => eulerRowVisible(row, { ...scope, view: "euler", job: "missing_chassis", status: "", unlinked: false, missingDoc: false, registerMatch: "" }));
  const jobRows = { not_claimed: notClaimed, rejected, no_lead: noLead, missing_chassis: missing };
  const jobMoney = (id) => {
    const rows = jobRows[id] || [];
    if (id === "not_claimed" || id === "rejected") return rows.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
    return rows.reduce((s, r) => s + Number(r.claimedAmount || 0), 0);
  };

  const schemeMoney = schemeScoped.filter((row) => !isIncentiveClaim(row));
  const incentiveMoney = schemeScoped.filter((row) => isIncentiveClaim(row));
  const sumEligible = (list) => list.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
  const sumOutstanding = (list) => list.reduce((s, r) => s + outstandingOf(r), 0);
  const unclaimedValue = notClaimed.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
  const rejectedValue = rejected.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);
  const schemeCounts = schemeScoped.reduce((acc, row) => {
    const state = row?.oemMatch?.state || "";
    if (state && state !== "not_applicable") acc[state] = (acc[state] || 0) + 1;
    return acc;
  }, {});
  const registerCounts = euler.reduce((acc, row) => {
    const state = row?.registerMatch?.state;
    if (state) acc[state] = (acc[state] || 0) + 1;
    return acc;
  }, {});

  const mirror = summary?.mirror || {};
  const totals = summary?.totals || {};
  const buckets = Array.isArray(summary?.buckets) ? summary.buckets : [];
  const eulerRejected = Array.isArray(summary?.rejected) ? summary.rejected : [];
  const invoiceConflicts = Array.isArray(summary?.invoiceConflicts) ? summary.invoiceConflicts : [];
  const openCount = buckets.filter((b) => !["Settled", "Rejected", "Cancelled"].includes(b.status)).reduce((s, b) => s + (b.count || 0), 0);

  const openManual = () => {
    setManual(true);
    if (!leads.length) get("/leads", { scope: "all" }).then(setLeads).catch(() => setLeads([]));
  };

  const sync = async () => {
    setSyncing(true);
    try {
      const r = await post("/integrations/coulson/sync-claims", {});
      toast.success(`${r.claimsMirrored} claims mirrored from Euler`);
      if (r.claimsIncomplete) toast.error(`Only ${r.claimsMirrored} of ${r.claimsExpected} claims came back`);
      if ((r.claimsWithVehicle || 0) < (r.claimsMirrored || 0)) {
        toast.error(`Chassis/invoice on ${r.claimsWithVehicle || 0} of ${r.claimsMirrored} claims — sync again after deploy if this stays 0`);
      }
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not reach Euler"));
    } finally {
      setSyncing(false);
    }
  };

  const jobMeta = JOBS.find((j) => j.id === job);
  const title = jobMeta ? jobMeta.label : view === "ours" ? "Our claims" : view === "euler" ? "Euler claims" : "Claims";
  const outstandingRows = scheme.filter((r) => outstandingOf(r) > 0.01);
  const showScheme = view === "ours" || job === "not_claimed" || job === "rejected";
  const showEuler = view === "euler" || job === "no_lead" || job === "missing_chassis";
  const showBooks = view === "work" || view === "ours" || job === "not_claimed" || job === "rejected";

  return (
    <div data-testid="claims-desk">
      <PageHeader
        title={title}
        subtitle={loading ? "Loading…" : "One page for our claims, Euler claims, and missing chassis"}
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <ClaimsDeskSwitch />
            <ReportActions onRefresh={load} showRebuild />
            {canSyncOemClaims ? (
              <Button data-testid="sync-oem-claims" onClick={sync} disabled={syncing}>
                <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
                {syncing ? "Syncing…" : "Sync from Euler"}
              </Button>
            ) : null}
            <Button variant="secondary" data-testid="add-manual-claim-btn" onClick={openManual}>
              <Plus size={16} /> Add manual claim
            </Button>
            <Button data-testid="record-claim-receipt-btn" onClick={() => setReceipt(true)}>
              <HandCoins size={16} /> Record money received
            </Button>
          </div>
        )}
      />

      <div className="flex flex-wrap gap-2 mb-4">
        {[
          ["work", "Jobs to do"],
          ["ours", "Our claims"],
          ["euler", "Euler claims"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            data-testid={`claims-desk-tab-${id}`}
            onClick={() => go(id)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              (id === "work" ? view === "work" && !job : view === id && !job)
                ? "bg-cobalt text-white"
                : "bg-zinc-100 text-ink-soft hover:bg-zinc-200"
            }`}
          >
            {label}
          </button>
        ))}
        {job ? (
          <button type="button" className="text-sm text-cobalt hover:underline" onClick={() => go("work")}>
            Back to jobs
          </button>
        ) : null}
      </div>

      {showBooks ? <PeriodBar month={period.month} year={period.year} onChange={period.onChange} /> : null}

      {mirror.incomplete ? (
        <Card className="mb-4 border-rose-200 bg-rose-50 p-4 flex items-start gap-3">
          <AlertTriangle size={18} className="text-rose-600 shrink-0 mt-0.5" />
          <div className="text-sm text-rose-800">
            <div className="font-semibold">This Euler list is incomplete.</div>
            Euler reports {mirror.expected} claims; {mirror.mirrored} were mirrored. Every
            Euler total is understated until the next sync succeeds.
          </div>
        </Card>
      ) : null}

      {showBooks ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4" data-testid="claim-totals">
          <StatCard label="Scheme Eligible" value={inr(sumEligible(schemeMoney))} tone="text-cobalt" />
          <StatCard label="Executive Incentive" value={inr(sumEligible(incentiveMoney))} tone="text-violet-600" />
          <StatCard label="Total Eligible" value={inr(sumEligible(schemeScoped))} tone="text-emerald-600" />
          <StatCard label="Total Outstanding" value={inr(sumOutstanding(schemeScoped))} tone="text-red-600" />
        </div>
      ) : null}

      {(unclaimedValue > 0.01 || rejectedValue > 0.01) && showBooks ? (
        <div className="mb-4 space-y-1 text-sm">
          {unclaimedValue > 0.01 ? (
            <div className="flex items-start gap-2 text-red-700">
              <AlertTriangle size={15} className="shrink-0 mt-0.5" />
              <span><b>{inr(unclaimedValue)}</b> is eligible here with no claim filed in Euler. Raise these before the scheme month closes.</span>
            </div>
          ) : null}
          {rejectedValue > 0.01 ? (
            <div className="flex items-start gap-2 text-rose-800">
              <RotateCcw size={15} className="shrink-0 mt-0.5" />
              <span><b>{inr(rejectedValue)}</b> was rejected by Euler and has not been refiled. A rejection is not reopened — it needs a fresh claim.</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {showEuler ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4" data-testid="oem-claim-totals">
          <StatCard label="Open with Euler" value={openCount} sub={inr(totals.openClaimed)} tone="text-amber-600" />
          <StatCard label="Total Claimed" value={inr(totals.claimed)} icon={FileText} />
          <StatCard label="Approved" value={inr(totals.approved)} tone="text-emerald-600" />
          <StatCard label="No document" value={mirror.missingDocument ?? "—"} sub="Each claim item needs its own file"
            tone={(mirror.missingDocument || 0) > 0 ? "text-rose-600" : "text-ink"} />
        </div>
      ) : null}

      {showEuler && job !== "missing_chassis" && summary?.total > 0 && (mirror.withVehicle || 0) < summary.total ? (
        <Card className="mb-4 border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" data-testid="oem-missing-chassis">
          <div className="font-semibold">Chassis and invoice are missing on some claims.</div>
          {mirror.withVehicle || 0} of {summary.total} have a vehicle id. Sync from Euler uses the debit-note journey, not the list row.{" "}
          <button type="button" className="font-semibold underline" onClick={() => go("euler", "missing_chassis")}>
            Open the {mirror.missingVehicle || 0} claims without chassis or invoice
          </button>
        </Card>
      ) : null}

      {(leadFilter || chassisFilter || invoiceFilter || params.get("q")) ? (
        <p className="mb-3 text-xs text-ink-soft" data-testid="claims-join-filter">
          Filtered to {[leadFilter, chassisFilter, invoiceFilter, params.get("q")].filter(Boolean).join(" · ")}.{" "}
          {leadFilter ? <LeadLink leadId={leadFilter} onOpen={openLead} /> : null}{" "}
          <button type="button" className="text-cobalt hover:underline" onClick={clearJoin}>Show every claim</button>
        </p>
      ) : null}

      {view === "work" && !job ? (
        <Table
          rowKey="id"
          columns={[
            { key: "label", label: "Job", render: (r) => <span className={`font-semibold ${r.tone}`}>{r.label}</span> },
            { key: "files", label: "Files", align: "right", render: (r) => String((jobRows[r.id] || []).length) },
            { key: "money", label: "Money still open", align: "right", mono: true, render: (r) => inr(jobMoney(r.id)) },
            { key: "open", label: "", align: "right", render: (r) => (
              <Button variant={r.id === "not_claimed" ? "primary" : "secondary"} data-testid={`claims-job-${r.id}`}
                onClick={(e) => { e.stopPropagation(); go(r.view, r.id); }}>
                Open
              </Button>
            ) },
          ]}
          rows={JOBS}
          onRowClick={(r) => go(r.view, r.id)}
          empty={loading ? "Loading…" : "No jobs"}
        />
      ) : null}

      {view === "work" && !job ? (
        <p className="mt-3 text-xs text-ink-faint">
          Not filed and rejected follow the month above. Euler jobs are every claim in the mirror.
          Old claim screens puts the three registers back.
        </p>
      ) : null}

      {showScheme && !job ? (
        <Card className="mb-4 p-4" data-testid="oem-crosscheck">
          <div className="text-xs font-semibold text-ink-faint uppercase tracking-wide mb-3">Cross-check with Euler</div>
          <div className="flex flex-wrap gap-2">
            {SCHEME_MATCHES.map((state) => (
              schemeCounts[state] ? (
                <Chip key={state} testId={`match-filter-${state}`} active={schemeMatch === state}
                  onClick={() => setSchemeMatch(schemeMatch === state ? "" : state)}>
                  <Badge tone={OEM_MATCH[state].tone}>{OEM_MATCH[state].label}</Badge>
                  <div className="text-lg font-semibold text-ink mt-1">{schemeCounts[state]}</div>
                </Chip>
              ) : null
            ))}
          </div>
        </Card>
      ) : null}

      {showEuler && !job ? (
        <>
          <Card className="mb-4 p-4" data-testid="register-crosscheck">
            <div className="text-xs font-semibold text-ink-faint uppercase tracking-wide mb-3">Cross-check with our register</div>
            <div className="flex flex-wrap gap-2">
              {REGISTER_MATCHES.map((state) => (
                registerCounts[state] ? (
                  <Chip key={state} testId={`register-filter-${state}`} active={registerMatch === state}
                    onClick={() => setRegisterMatch(registerMatch === state ? "" : state)}>
                    <Badge tone={REGISTER_MATCH[state].tone}>{REGISTER_MATCH[state].label}</Badge>
                    <div className="text-lg font-semibold text-ink mt-1">{registerCounts[state]}</div>
                  </Chip>
                ) : null
              ))}
            </div>
            {(registerCounts.missing_register || registerCounts.unknown_lead) ? (
              <p className="mt-3 text-sm text-violet-800">
                Violet rows still need a lead. Grey rows never matched a chassis or invoice.
                Once a claim is matched to a lead it leaves the unmatched list.
              </p>
            ) : null}
          </Card>
          {buckets.length ? (
            <Card className="mb-4 p-4">
              <div className="text-xs font-semibold text-ink-faint uppercase tracking-wide mb-3">Where the claims are sitting</div>
              <div className="flex flex-wrap gap-2">
                {buckets.map((b) => (
                  <Chip key={b.status} active={status === b.status} onClick={() => setStatus(status === b.status ? "" : b.status)}>
                    <div className="text-[11px] text-ink-faint uppercase tracking-wide">{b.status}</div>
                    <div className="text-lg font-semibold text-ink">{b.count}</div>
                    <div className="text-xs text-ink-faint">{inr(b.claimed)}</div>
                  </Chip>
                ))}
              </div>
            </Card>
          ) : null}
        </>
      ) : null}

      {showEuler && eulerRejected.length > 0 ? (
        <Card className="mb-4 p-4 border-rose-200">
          <div className="flex items-center gap-2 mb-2 text-rose-700 font-semibold text-sm">
            <XCircle size={16} /> {eulerRejected.length} rejected by Euler
          </div>
          <p className="text-xs text-ink-faint mb-3">
            Euler does not reopen a rejected debit note — a resubmission is a new claim
            on the same chassis. Check our claims if these are still listed as eligible.
          </p>
          <div className="flex flex-wrap gap-2">
            {eulerRejected.map((r) => (
              <div key={r.claimNumber} className="rounded-lg border border-rose-200 bg-rose-50/60 px-3 py-2 text-xs">
                <span className="font-mono font-semibold text-rose-800">{r.claimNumber}</span>
                <span className="text-ink-soft ml-2">{inr(r.claimedAmount)}</span>
                {r.resubmittedBy
                  ? <Badge tone="bg-sky-50 text-sky-700 ring-sky-600/20">Refiled as {r.resubmittedBy}</Badge>
                  : r.needsResubmission
                    ? <Badge tone="bg-rose-100 text-rose-800 ring-rose-600/30">Needs refile</Badge>
                    : null}
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      {invoiceConflicts.length > 0 && (showEuler || view === "work") ? (
        <Card className="mb-4 p-4 border-amber-200">
          <div className="flex items-center gap-2 mb-2 text-amber-800 font-semibold text-sm">
            <AlertTriangle size={16} /> Invoice disagreements
          </div>
          <p className="text-xs text-ink-faint mb-2">
            Chassis still matches the lead. The OEM claim was filed on the cancelled invoice; the new tax invoice is on the lead.
          </p>
          <ul className="text-xs text-ink-soft space-y-1">
            {invoiceConflicts.map((c, i) => (
              <li key={`${c.claimNumber || i}`}>
                <span className="font-mono">{c.claimNumber}</span>
                {c.invoiceCancelled || (c.cancelledInvoice && c.newInvoice)
                  ? <> — {c.chassis || "chassis"}: invoice <span className="font-mono">{c.cancelledInvoice}</span> cancelled; new invoice <span className="font-mono">{c.newInvoice}</span></>
                  : <> — {c.detail}</>}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {showScheme || showEuler ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input
            data-testid={showEuler ? "oem-claim-search" : "claims-desk-search"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Name, lead, chassis, invoice, claim no."
            className="max-w-xs"
          />
          {showEuler && !job ? (
            <>
              <Button type="button" variant={unlinked ? "primary" : "secondary"} onClick={() => setUnlinked((v) => !v)}>
                <Link2Off size={16} /> Not linked to a lead
              </Button>
              <Button type="button" variant={missingDoc ? "primary" : "secondary"} data-testid="oem-missing-doc-filter"
                onClick={() => setMissingDoc((v) => !v)}>
                <FileText size={16} /> No document
              </Button>
            </>
          ) : null}
        </div>
      ) : null}

      {showScheme ? (
        <Table
          rowKey="claimId"
          onRowClick={setSelected}
          rowClassName={(r) => oemMatchOf(r).row}
          columns={[
            { key: "customer", label: "Customer", render: (r) => (
              <div>
                <div className="font-semibold">{r.customer || "—"}</div>
                <LeadLink leadId={r.leadId} onOpen={openLead} />
                {r.manual ? <Badge tone="bg-blue-50 text-blue-700 ring-blue-600/20">Manual</Badge> : null}
              </div>
            ) },
            { key: "vehicle", label: "Chassis and invoice", mono: true, render: (r) => schemeVehicle(r) },
            { key: "component", label: "Component", render: (r) => (
              <span>{r.component}{r.unitSno ? ` · Unit ${r.unitSno}` : ""}{r.model ? ` · ${r.model}` : ""}</span>
            ) },
            { key: "eligible", label: "Eligible", align: "right", mono: true, render: (r) => inr(r.eligibleClaim) },
            { key: "due", label: "Still due", align: "right", mono: true, render: (r) => {
              const due = outstandingOf(r);
              return <span className={due > 0.01 ? "text-red-600 font-semibold" : ""}>{inr(due)}</span>;
            } },
            { key: "status", label: "Status", render: (r) => {
              const eulerState = oemMatchOf(r);
              return (
                <div className="flex flex-col items-start gap-1">
                  <Badge tone={claimStatusTone(r.claimStatus)}>{r.claimStatus || "—"}</Badge>
                  {eulerState.label ? <Badge tone={eulerState.tone}>{eulerState.label}</Badge> : null}
                </div>
              );
            } },
          ]}
          rows={schemeRows}
          empty={loading ? "Loading…" : "Nothing in this list"}
        />
      ) : null}

      {showEuler ? (
        <Table
          rowKey="claimNumber"
          onRowClick={setSelected}
          rowClassName={(r) => registerMatchOf(r).row}
          columns={[
            { key: "claim", label: "Claim", mono: true, render: (r) => (
              <div>
                <div className="font-semibold">{r.claimNumber}</div>
                <div className="text-[10px] text-ink-faint">{r.settlementType}</div>
              </div>
            ) },
            { key: "customer", label: "Customer", render: (r) => (
              rowLeadIds(r).length
                ? (
                  <div className="flex flex-col items-start gap-0.5">
                    {rowLeadIds(r).map((id) => (
                      <LeadLink key={id} leadId={id} onOpen={openLead}
                        subtitle={lineLeadLabel(rowLineItems(r).find((li) => lineLeadIds(li).includes(id)) || {}, id)} />
                    ))}
                  </div>
                )
                : <Badge>Not linked</Badge>
            ) },
            { key: "vehicle", label: "Chassis and invoice", mono: true, render: (r) => (
              claimHasVehicle(r)
                ? rowLineItems(r).flatMap((li) => [...lineChassisList(li), li.sourceInvoiceNumber]).filter(Boolean).join(" · ") || "—"
                : <span className="text-amber-800">Chassis missing</span>
            ) },
            { key: "claimed", label: "Claimed", align: "right", mono: true, render: (r) => inr(r.claimedAmount) },
            { key: "approved", label: "Approved", align: "right", mono: true, render: (r) => inr(r.approvedAmount) },
            { key: "where", label: "Where it is", render: (r) => {
              const match = registerMatchOf(r);
              return (
                <div className="flex flex-col items-start gap-1">
                  <Badge tone={match.tone}>{r.status || match.label}</Badge>
                  <Badge tone={match.tone}>{match.label}</Badge>
                  {!r.terminal && r.stageLabel ? (
                    <span className={`text-xs ${stageTone(r.stageDays)}`}>{r.stageDays}d at {r.stageLabel}</span>
                  ) : null}
                </div>
              );
            } },
          ]}
          rows={eulerRows}
          empty={loading ? "Loading…" : mirror.syncedAt ? "No claims match this filter" : "Not synced from Euler yet"}
        />
      ) : null}

      {selected && selected.claimId ? (
        <SchemeDetail
          row={selected}
          isMoneyDesk={isMoneyDesk}
          onMatch={() => setMatchClaim(selected)}
          onReceipt={() => setReceipt(true)}
          onSettle={() => setSelected({ ...selected, settle: true })}
          onClose={() => setSelected(null)}
          onDrop={() => {
            post("/claims/drop-extra-support", { claimId: selected.claimId, leadId: selected.leadId })
              .then(() => { toast.success("Extra Support dropped"); setSelected(null); load(); })
              .catch((err) => toast.error(apiErrorMessage(err, "Could not drop")));
          }}
        />
      ) : null}

      {selected && selected.claimNumber && !selected.claimId ? (
        <EulerDetail
          row={selected}
          onMatch={(line, relink) => setMatchRow({ ...selected, matchLine: line, relink: Boolean(relink) })}
          onDone={() => { setSelected(null); load(); }}
          onClose={() => setSelected(null)}
        />
      ) : null}

      {oemOnly && oemOnly.count > 0 && (view === "work" || showScheme) ? (
        <Card className="mt-6 p-4 border-violet-200" data-testid="oem-only-claims">
          <div className="flex items-center gap-2 mb-1 text-violet-800 font-semibold text-sm">
            <AlertTriangle size={16} />
            In Euler but not in this register — {oemOnly.count} line(s), {inr(oemOnly.total)}
          </div>
          <p className="text-xs text-ink-faint mb-3">
            Claims Euler is working on that still have no CRM lead. Matched debit notes leave this list even when the scheme component was not used.
          </p>
          <Table
            rowKey="rowId"
            columns={[
              { key: "claimNumber", label: "Claim", mono: true, render: (r) => r.claimNumber },
              { key: "description", label: "What Euler is claiming", render: (r) => r.description || r.claimType || "—" },
              { key: "vehicle", label: "Chassis and invoice", mono: true, render: (r) => [r.chassis, r.sourceInvoiceNumber].filter(Boolean).join(" · ") || "—" },
              { key: "amount", label: "Amount", align: "right", mono: true, render: (r) => inr(r.amount) },
              { key: "oemStatus", label: "Status", render: (r) => <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.oemStatus}</Badge> },
              { key: "act", label: "", render: (r) => <OemOnlyCreate row={r} onDone={load} /> },
            ]}
            rows={(oemOnly.rows || []).map((r, i) => ({ ...r, rowId: `${r.claimNumber}-${r.lineId || i}` }))}
            empty="Nothing"
          />
        </Card>
      ) : null}

      {drawer}
      {selected && selected.settle ? (
        <SettleModal claim={selected} onClose={() => setSelected({ ...selected, settle: false })}
          onDone={() => { setSelected(null); load(); }} />
      ) : null}
      {receipt ? (
        <ClaimReceiptModal rows={outstandingRows} onClose={() => setReceipt(false)}
          onDone={() => { setReceipt(false); load(); }} />
      ) : null}
      {manual ? (
        <ManualClaimModal leads={leads} onClose={() => setManual(false)}
          onDone={() => { setManual(false); load(); }} />
      ) : null}
      {matchClaim ? (
        <MatchOemModal claim={matchClaim} onClose={() => setMatchClaim(null)}
          onDone={() => { setMatchClaim(null); setSelected(null); load(); }} />
      ) : null}
      {matchRow ? (
        <MatchRegisterModal row={matchRow} onClose={() => setMatchRow(null)}
          onDone={() => { setMatchRow(null); setSelected(null); load(); }} />
      ) : null}
    </div>
  );
}

function SchemeDetail({ row, isMoneyDesk, onMatch, onReceipt, onSettle, onDrop, onClose }) {
  const due = outstandingOf(row);
  const eulerState = oemMatchOf(row);
  const relink = row.claimStatus === "Cancelled" || row.oemMatch?.oemStatus === "Cancelled";
  return (
    <Card className="mt-4 p-4" data-testid="claims-desk-detail">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-heading font-bold text-ink">{row.customer || "Claim"}</div>
          <div className="text-xs text-ink-faint mt-1">
            {row.leadId} · {row.component}{row.unitSno ? ` · Unit ${row.unitSno}` : ""}{row.model ? ` · ${row.model}` : ""} · {schemeVehicle(row)}
          </div>
          <div className="text-sm text-ink-soft mt-2">
            Claim amount {inr(row.claimAmount)}. Eligible {inr(row.eligibleClaim)}. Received {inr(row.receivedAmount)}. Still due {inr(due)}.
          </div>
          <div className="text-xs text-ink-faint mt-1">
            Submitted {row.submittedDate ? fmtDate(row.submittedDate) : "not yet"}.
            {" "}Approved {row.approvedDate ? fmtDate(row.approvedDate) : "not yet"}.
            {row.ageingDays ? ` Ageing ${row.ageingDays}d.` : ""}
            {" "}{(row.oemMatch?.claimNumbers || []).length ? `Euler ${(row.oemMatch.claimNumbers || []).join(", ")}.` : "No Euler claim yet."}
            {row.oemMatch?.oemStatus ? ` ${row.oemMatch.oemStatus}${row.oemMatch.stageLabel ? ` · ${row.oemMatch.stageDays || 0}d ${row.oemMatch.stageLabel}` : ""}.` : ""}
            {row.oemMatch?.manual ? " Manual match." : ""}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone={claimStatusTone(row.claimStatus)}>{row.claimStatus || "—"}</Badge>
            {eulerState.label ? <Badge tone={eulerState.tone}>{eulerState.label}</Badge> : null}
            {!row.manual ? (
              <DocFlag yes={row.oemMatch?.hasDocument} url={row.oemMatch?.claimDocumentUrl} count={row.oemMatch?.documentCount} />
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {!row.manual ? (
            <Button data-testid="claims-desk-match" onClick={onMatch}>
              {relink ? "Relink" : schemeClaimJob(row) === "rejected" ? "Refile" : "Match OEM claim"}
            </Button>
          ) : null}
          {due > 0.01 ? <Button variant="secondary" onClick={onReceipt}>Record money received</Button> : null}
          <Button variant="secondary" onClick={onSettle}>Update status</Button>
          {isMoneyDesk && row.componentKey === "oemExtraSupport" && row.claimStatus !== "Dropped" && Number(row.receivedAmount || 0) <= 0.01 ? (
            <button
              type="button"
              className="text-xs font-semibold text-rose-700 hover:underline"
              onClick={() => {
                if (!window.confirm("Drop this OEM Extra Support? It leaves the claim register, is recorded on Dropped Extra Support, and is taken out of dealer earnings.")) return;
                onDrop();
              }}
            >
              Drop
            </button>
          ) : null}
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </div>
      </div>
    </Card>
  );
}

function EulerDetail({ row, onMatch, onDone, onClose }) {
  const match = registerMatchOf(row);
  const lines = rowLineItems(row);
  return (
    <Card className="mt-4 p-4" data-testid="claims-desk-detail">
      <div className="font-heading font-bold text-ink">{row.claimNumber}</div>
      <div className="text-sm text-ink-soft mt-1">
        {row.settlementType ? `${row.settlementType}. ` : ""}
        {row.status || "Open"}. Claimed {inr(row.claimedAmount)}. Approved {inr(row.approvedAmount)}.
        {!row.terminal && row.claimAgeingDays ? ` ${row.claimAgeingDays}d old.` : ""}
        {row.createdDate ? ` Raised ${fmtDate(row.createdDate)}.` : ""}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Badge tone={match.tone}>{match.label}</Badge>
        {(row.registerMatch?.mappedComponents || []).length ? (
          <span className="text-xs text-ink-faint">{row.registerMatch.mappedComponents.map(componentLabel).join(", ")}</span>
        ) : null}
        {row.registerMatch?.resubmittedBy
          ? <span className="text-xs text-sky-700">Refiled as {row.registerMatch.resubmittedBy}</span>
          : row.registerMatch?.needsResubmission
            ? <span className="text-xs text-rose-700">Needs refile</span>
            : null}
        <DocFlag yes={row.hasDocument} url={row.claimDocumentUrl} count={row.documentCount}
          lines={row.lineItemCount} documented={row.documentedLineCount} />
      </div>
      <div className="mt-3 space-y-3">
        {(lines.length ? lines : [{}]).map((line, i) => (
          <div key={line.lineId || i} className="border-t border-line pt-3" data-testid={`oem-line-${row.claimNumber}-${line.lineId || i}`}>
            <div className="text-sm font-medium">{oemLineText(line) || "Not pulled — sync again"}</div>
            {line.claimType && oemLineText(line) !== line.claimType ? (
              <div className="text-[10px] text-ink-faint">{line.claimType}</div>
            ) : null}
            <div className="text-xs text-ink-faint">
              {[line.model, line.variant].filter(Boolean).join(" ")}
              {lineChassisList(line).map((ch) => ` · ${ch}${line.unitSno ? ` unit ${line.unitSno}` : ""}`).join("")}
              {line.sourceInvoiceNumber ? ` · ${line.sourceInvoiceNumber}` : ""}
              {line.totalAmount ? ` · ${inr(line.totalAmount)}` : ""}
            </div>
            {line.invoiceCancelled || line.invoiceMismatch ? (
              <div className="text-[10px] text-amber-800">
                Invoice cancelled{line.cancelledInvoiceNumber ? ` ${line.cancelledInvoiceNumber}` : ""}
                {line.newInvoiceNumber ? ` · new ${line.newInvoiceNumber}` : ""}
              </div>
            ) : null}
            {lineLeadIds(line).length > 1 ? (
              <div className="text-[10px] text-violet-800">Matched to {lineLeadIds(line).length} leads</div>
            ) : looksCombinedSupport(line) ? (
              <div className="text-[10px] text-amber-800">Combined amount — match each lead</div>
            ) : null}
            <div className={(line.documentCount || 0) > 0 ? "text-emerald-700 text-xs" : "text-rose-600 text-xs"}>
              {(line.documentCount || 0) > 0 ? `${line.documentCount} doc${line.documentCount === 1 ? "" : "s"}` : "No docs"}
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              <Button data-testid={`claims-desk-link-${line.lineId || i}`} onClick={() => onMatch(line, false)}>
                {lineLeadIds(line).length ? "Add lead" : "Match"}
              </Button>
              <RelinkButton row={row} line={line} onClick={() => onMatch(line, true)} />
              {lineNeedsCreate(row, line) ? <CreateOemButton row={row} line={line} onDone={onDone} /> : null}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3">
        <Button variant="ghost" onClick={onClose}>Close</Button>
      </div>
    </Card>
  );
}
