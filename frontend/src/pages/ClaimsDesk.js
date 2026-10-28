import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { HandCoins, Plus, RefreshCw } from "lucide-react";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import {
  OEM_MATCH, REGISTER_MATCH, claimHasVehicle, eulerClaimJob, lineChassisList,
  lineLeadIds, lineLeadLabel, lineNeedsCreate, oemLineText, rowLeadIds, rowLineItems,
  schemeClaimJob,
} from "../lib/claimMatch";
import { PageHeader, Table, Badge, Button, Card, Input } from "../components/ui";
import { useLeadDrawer, LeadLink } from "../components/LeadLink";
import { useAuth } from "../context/AuthContext";
import PeriodBar from "../components/PeriodBar";
import { usePeriodState } from "../lib/period";
import ClaimsDeskSwitch from "../components/ClaimsDeskSwitch";
import { ClaimReceiptModal, ManualClaimModal, MatchOemModal, SettleModal } from "./Claims";
import { CreateOemButton, MatchRegisterModal } from "./OemClaims";

const JOBS = [
  { id: "not_claimed", view: "ours", label: "We have not filed these", tone: "text-red-600" },
  { id: "rejected", view: "ours", label: "Euler rejected these", tone: "text-rose-700" },
  { id: "no_lead", view: "euler", label: "Euler has the claim. We have no lead.", tone: "text-violet-800" },
  { id: "missing_chassis", view: "euler", label: "Chassis is missing", tone: "text-amber-800" },
];

function outstandingOf(row) {
  return Math.max(0, Number(row.eligibleClaim || 0) - Number(row.receivedAmount || 0));
}

function ourStatus(row) {
  const state = row?.oemMatch?.state || "";
  if (state === "not_filed") return "Not claimed";
  if (state === "rejected") return "Rejected";
  if (state === "accepted") return "Approved";
  if (state === "resubmitted") return "Refiled";
  if (state === "filed") return "Filed";
  if (row.claimStatus === "Received") return "Received";
  return row.claimStatus || "—";
}

function schemeVehicle(row) {
  return [row.chassisNumber, row.invoiceNumber].filter(Boolean).join(" · ") || "—";
}

function eulerCustomer(row) {
  const id = rowLeadIds(row)[0];
  if (!id) return "";
  const line = rowLineItems(row).find((li) => lineLeadIds(li).includes(id)) || {};
  return lineLeadLabel(line, id) || "";
}

function eulerVehicle(row) {
  if (!claimHasVehicle(row)) return "";
  const line = rowLineItems(row).find((li) => lineChassisList(li).length || li.sourceInvoiceNumber) || rowLineItems(row)[0] || {};
  return [lineChassisList(line)[0], line.sourceInvoiceNumber].filter(Boolean).join(" · ");
}

function closedScheme(row) {
  return ["Received", "Dropped", "Cancelled"].includes(row.claimStatus || "");
}

export default function ClaimsDesk() {
  const { canSyncOemClaims, isMoneyDesk } = useAuth();
  const [params, setParams] = useSearchParams();
  const period = usePeriodState();
  const [scheme, setScheme] = useState([]);
  const [euler, setEuler] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState(params.get("q") || "");
  const [showClosed, setShowClosed] = useState(false);
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
  };

  const needle = q.trim().toLowerCase();
  const schemeInScope = scheme.filter((row) => {
    if (leadFilter && row.leadId !== leadFilter) return false;
    if (chassisFilter && !schemeVehicle(row).includes(chassisFilter)) return false;
    if (invoiceFilter && !schemeVehicle(row).includes(invoiceFilter)) return false;
    return true;
  });
  const eulerInScope = euler.filter((row) => {
    if (leadFilter && !rowLeadIds(row).includes(leadFilter)) return false;
    const vehicle = `${eulerVehicle(row)} ${JSON.stringify(rowLineItems(row))}`;
    if (chassisFilter && !vehicle.includes(chassisFilter)) return false;
    if (invoiceFilter && !vehicle.includes(invoiceFilter)) return false;
    return true;
  });
  const schemeRows = schemeInScope.filter((row) => {
    if (job === "not_claimed" || job === "rejected") return schemeClaimJob(row) === job;
    if (view !== "ours") return false;
    if (!showClosed && closedScheme(row)) return false;
    return true;
  }).filter((row) => {
    if (!needle) return true;
    const claims = (row.oemMatch?.claimNumbers || []).join(" ");
    return `${row.customer || ""} ${row.leadId || ""} ${schemeVehicle(row)} ${row.component || ""} ${claims}`.toLowerCase().includes(needle);
  });

  const eulerRows = eulerInScope.filter((row) => {
    if (job === "no_lead" || job === "missing_chassis") return eulerClaimJob(row) === job;
    if (view !== "euler") return false;
    if (!showClosed && row.terminal) return false;
    return true;
  }).filter((row) => {
    if (!needle) return true;
    const lines = rowLineItems(row).map((li) => `${oemLineText(li)} ${lineChassisList(li).join(" ")} ${li.sourceInvoiceNumber || ""}`).join(" ");
    return `${row.claimNumber || ""} ${eulerCustomer(row)} ${lines}`.toLowerCase().includes(needle);
  });

  const notClaimed = schemeInScope.filter((row) => schemeClaimJob(row) === "not_claimed");
  const rejected = schemeInScope.filter((row) => schemeClaimJob(row) === "rejected");
  const noLead = eulerInScope.filter((row) => eulerClaimJob(row) === "no_lead");
  const missing = eulerInScope.filter((row) => eulerClaimJob(row) === "missing_chassis");
  const jobRows = {
    not_claimed: notClaimed,
    rejected: rejected,
    no_lead: noLead,
    missing_chassis: missing,
  };
  const jobMoney = (id) => {
    const rows = jobRows[id] || [];
    if (id === "not_claimed" || id === "rejected") return rows.reduce((s, r) => s + outstandingOf(r), 0);
    return rows.reduce((s, r) => s + Number(r.claimedAmount || 0), 0);
  };

  const openManual = () => {
    setManual(true);
    if (!leads.length) get("/leads", { scope: "all" }).then(setLeads).catch(() => setLeads([]));
  };

  const sync = async () => {
    setSyncing(true);
    try {
      const r = await post("/integrations/coulson/sync-claims", {});
      toast.success(`${r.claimsMirrored} claims mirrored from Euler`);
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

  return (
    <div data-testid="claims-desk">
      <PageHeader
        title={title}
        subtitle={loading ? "Loading…" : "One page for our claims, Euler claims, and missing chassis"}
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <ClaimsDeskSwitch />
            {(view === "euler" || job === "no_lead" || job === "missing_chassis") && canSyncOemClaims ? (
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

      {view !== "euler" && !job?.startsWith("no_") && job !== "missing_chassis" ? (
        <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
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

      {(leadFilter || chassisFilter || invoiceFilter) ? (
        <p className="mb-3 text-xs text-ink-soft">
          Filtered to {leadFilter || chassisFilter || invoiceFilter}.{" "}
          <button
            type="button"
            className="text-cobalt hover:underline"
            onClick={() => {
              const next = new URLSearchParams(params);
              next.delete("leadId");
              next.delete("chassis");
              next.delete("invoice");
              next.delete("q");
              setParams(next, { replace: true });
            }}
          >
            Show every claim
          </button>
        </p>
      ) : null}

      {view === "work" && !job ? (
        <p className="mt-3 text-xs text-ink-faint">
          Not filed and rejected follow the month bar. Euler jobs are every claim in the mirror.
          Old claim screens puts the three registers back.
        </p>
      ) : null}

      {view !== "work" || job ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input
            data-testid="claims-desk-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Name, lead, chassis, invoice, claim no."
            className="max-w-xs"
          />
          {!job ? (
            <Button variant="secondary" onClick={() => setShowClosed((v) => !v)}>
              {showClosed ? "Hide closed" : "Show closed"}
            </Button>
          ) : null}
        </div>
      ) : null}

      {(view === "ours" || job === "not_claimed" || job === "rejected") ? (
        <Table
          rowKey="claimId"
          onRowClick={setSelected}
          columns={[
            { key: "customer", label: "Customer", render: (r) => (
              <div>
                <div className="font-semibold">{r.customer || "—"}</div>
                <LeadLink leadId={r.leadId} onOpen={openLead} />
              </div>
            ) },
            { key: "vehicle", label: "Chassis and invoice", mono: true, render: (r) => schemeVehicle(r) },
            { key: "component", label: "Component", render: (r) => (
              <span>{r.component}{r.unitSno ? ` · Unit ${r.unitSno}` : ""}</span>
            ) },
            { key: "eligible", label: "Eligible", align: "right", mono: true, render: (r) => inr(r.eligibleClaim) },
            { key: "due", label: "Still due", align: "right", mono: true, render: (r) => {
              const due = outstandingOf(r);
              return <span className={due > 0.01 ? "text-red-600 font-semibold" : ""}>{inr(due)}</span>;
            } },
            { key: "status", label: "Status", render: (r) => {
              const m = OEM_MATCH[r.oemMatch?.state] || {};
              return <Badge tone={m.tone}>{ourStatus(r)}</Badge>;
            } },
          ]}
          rows={schemeRows}
          empty={loading ? "Loading…" : "Nothing in this list"}
        />
      ) : null}

      {(view === "euler" || job === "no_lead" || job === "missing_chassis") ? (
        <Table
          rowKey="claimNumber"
          onRowClick={setSelected}
          columns={[
            { key: "claim", label: "Claim", mono: true, render: (r) => <span className="font-semibold">{r.claimNumber}</span> },
            { key: "customer", label: "Customer", render: (r) => (
              rowLeadIds(r).length
                ? <LeadLink leadId={rowLeadIds(r)[0]} onOpen={openLead} subtitle={eulerCustomer(r)} />
                : <Badge>Not linked</Badge>
            ) },
            { key: "vehicle", label: "Chassis and invoice", mono: true, render: (r) => (
              claimHasVehicle(r) ? eulerVehicle(r) : <span className="text-amber-800">Chassis missing</span>
            ) },
            { key: "claimed", label: "Claimed", align: "right", mono: true, render: (r) => inr(r.claimedAmount) },
            { key: "approved", label: "Approved", align: "right", mono: true, render: (r) => inr(r.approvedAmount) },
            { key: "where", label: "Where it is", render: (r) => {
              const id = eulerClaimJob(r);
              if (id === "missing_chassis") return <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20">Missing chassis</Badge>;
              if (id === "no_lead") return <Badge tone={REGISTER_MATCH.unknown_lead.tone}>No lead</Badge>;
              const m = REGISTER_MATCH[r.registerMatch?.state] || REGISTER_MATCH.in_register;
              return <Badge tone={m.tone}>{r.status || m.label}</Badge>;
            } },
          ]}
          rows={eulerRows}
          empty={loading ? "Loading…" : "Nothing in this list"}
        />
      ) : null}

      {selected && selected.claimId ? (
        <Card className="mt-4 p-4" data-testid="claims-desk-detail">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-heading font-bold text-ink">{selected.customer || "Claim"}</div>
              <div className="text-xs text-ink-faint mt-1">
                {selected.leadId} · {selected.component}{selected.unitSno ? ` · Unit ${selected.unitSno}` : ""} · {schemeVehicle(selected)}
              </div>
              <div className="text-sm text-ink-soft mt-2">
                Eligible {inr(selected.eligibleClaim)}. Still due {inr(outstandingOf(selected))}.
                {" "}Submitted {selected.submittedDate ? fmtDate(selected.submittedDate) : "not yet"}.
                {" "}{(selected.oemMatch?.claimNumbers || []).length
                  ? `Euler ${(selected.oemMatch.claimNumbers || []).join(", ")}.`
                  : "No Euler claim yet."}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {schemeClaimJob(selected) || selected.oemMatch?.state === "unmapped" ? (
                <Button data-testid="claims-desk-match" onClick={() => setMatchClaim(selected)}>
                  {schemeClaimJob(selected) === "rejected" ? "Refile" : "Match Euler claim"}
                </Button>
              ) : null}
              {outstandingOf(selected) > 0.01 ? (
                <Button variant="secondary" onClick={() => setReceipt(true)}>Record money received</Button>
              ) : null}
              <Button variant="secondary" onClick={() => setSelected({ ...selected, settle: true })}>Edit dates</Button>
              {isMoneyDesk && selected.componentKey === "oemExtraSupport" && selected.claimStatus !== "Dropped"
                && Number(selected.receivedAmount || 0) <= 0.01 ? (
                <button
                  type="button"
                  className="text-xs font-semibold text-rose-700 hover:underline"
                  onClick={() => {
                    if (!window.confirm("Drop this OEM Extra Support? It leaves the claim register.")) return;
                    post("/claims/drop-extra-support", { claimId: selected.claimId, leadId: selected.leadId })
                      .then(() => { toast.success("Extra Support dropped"); setSelected(null); load(); })
                      .catch((err) => toast.error(apiErrorMessage(err, "Could not drop")));
                  }}
                >
                  Drop
                </button>
              ) : null}
              <Button variant="ghost" onClick={() => setSelected(null)}>Close</Button>
            </div>
          </div>
        </Card>
      ) : null}

      {selected && selected.claimNumber && !selected.claimId ? (
        <Card className="mt-4 p-4" data-testid="claims-desk-detail">
          <div className="font-heading font-bold text-ink">{selected.claimNumber}</div>
          <div className="text-sm text-ink-soft mt-1">
            {selected.status || "Open"}. Claimed {inr(selected.claimedAmount)}. Approved {inr(selected.approvedAmount)}.
          </div>
          <div className="mt-3 space-y-3">
            {(rowLineItems(selected).length ? rowLineItems(selected) : [{}]).map((line, i) => (
              <div key={line.lineId || i} className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
                <div className="text-sm">
                  <div>{oemLineText(line)}</div>
                  <div className="text-xs text-ink-faint">
                    {claimHasVehicle({ lineItems: [line] })
                      ? [lineChassisList(line)[0], line.sourceInvoiceNumber].filter(Boolean).join(" · ")
                      : "Chassis missing"}
                    {lineLeadIds(line).length ? "" : " · Not linked"}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    data-testid={`claims-desk-link-${line.lineId || i}`}
                    onClick={() => setMatchRow({ ...selected, matchLine: line })}
                  >
                    {lineLeadIds(line).length ? "Change link" : "Link to a lead"}
                  </Button>
                  {lineNeedsCreate(selected, line) ? (
                    <CreateOemButton row={selected} line={line} onDone={() => { setSelected(null); load(); }} />
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3">
            <Button variant="ghost" onClick={() => setSelected(null)}>Close</Button>
          </div>
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
