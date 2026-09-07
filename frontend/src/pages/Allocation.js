import React, { useCallback, useEffect, useMemo, useState } from "react";
import { UserCheck, Users, AlertTriangle, RefreshCcw, Search, Percent } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, apiErrorMessage } from "../lib/api";
import { fmtDate } from "../lib/format";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Card, StatCard, Table, Badge, Button, Select, Input } from "../components/ui";
import CallLink from "../components/CallLink";

/**
 * Allocate leads to executives.
 *
 * This page matters more since executives were scoped to their own leads: a lead
 * with nobody on it is now invisible to every executive, so it would sit unworked
 * and unnoticed. "Unassigned" is therefore the default filter.
 */
export default function Allocation() {
  const { canEditLeadSplit } = useAuth();
  const [summary, setSummary] = useState(null);
  const [leads, setLeads] = useState([]);
  const [execs, setExecs] = useState([]);
  const [filter, setFilter] = useState("unassigned");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState({});
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState([]);
  const [splitBusy, setSplitBusy] = useState(false);
  const [matchPick, setMatchPick] = useState({});
  const [matchBusy, setMatchBusy] = useState("");

  const load = useCallback(() => {
    get("/leads/allocation/summary").then((s) => {
      setSummary(s);
      setDraft((s.split?.shares || []).map((row) => ({ executive: row.executive, pct: row.pct })));
      const picks = {};
      (s.executiveMatches || []).forEach((row) => { picks[row.key] = row.suggested || ""; });
      setMatchPick(picks);
    }).catch(() => {});
    get("/leads").then(setLeads).catch(() => toast.error("Could not load leads"));
    get("/masters").then((m) => setExecs(m.executives || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const splitTotal = Math.round(draft.reduce((s, r) => s + (Number(r.pct) || 0), 0) * 100) / 100;
  const splitOk = draft.length > 0 && Math.abs(splitTotal - 100) <= 0.05;

  const rows = useMemo(() => {
    let out = leads.filter((l) => (l.accountStatus || "Active") === "Active");
    if (filter === "unassigned") out = out.filter((l) => !String(l.executive || "").trim());
    else if (filter !== "all") out = out.filter((l) => l.executive === filter);
    const needle = q.trim().toLowerCase();
    if (needle) {
      out = out.filter((l) => [l.customerName, l.leadId, l.mobile, l.interestedModel]
        .some((v) => String(v || "").toLowerCase().includes(needle)));
    }
    return out;
  }, [leads, filter, q]);

  const chosen = Object.keys(picked).filter((k) => picked[k]);
  const allShown = rows.length > 0 && rows.every((r) => picked[r.leadId]);

  const toggleAll = () => {
    if (allShown) return setPicked({});
    const next = {};
    rows.forEach((r) => { next[r.leadId] = true; });
    setPicked(next);
  };

  const allocate = async () => {
    if (!target) return toast.error("Pick an executive to allocate to");
    if (!chosen.length) return toast.error("Select at least one lead");
    setBusy(true);
    try {
      const r = await post("/leads/allocate", { leadIds: chosen, executive: target });
      const skipped = (r.skipped || []).length;
      toast.success(`${r.movedCount} lead${r.movedCount === 1 ? "" : "s"} allocated to ${target}`
        + (skipped ? ` · ${skipped} skipped` : ""));
      setPicked({});
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Allocation failed"));
    } finally { setBusy(false); }
  };

  const setShare = (name, pct) => {
    setDraft((rows) => rows.map((r) => (r.executive === name ? { ...r, pct } : r)));
  };

  const evenSplit = () => {
    const n = draft.length;
    if (!n) return;
    const base = Math.floor(10000 / n) / 100;
    const first = +(100 - base * (n - 1)).toFixed(2);
    setDraft((rows) => rows.map((r, i) => ({ ...r, pct: i === 0 ? first : base })));
  };

  const saveSplit = async () => {
    if (!splitOk) return toast.error(`Shares must add up to 100% (now ${splitTotal}%)`);
    setSplitBusy(true);
    try {
      await put("/leads/split", { shares: draft.map((r) => ({ executive: r.executive, pct: Number(r.pct) || 0 })) });
      toast.success("Split saved — new uploads and Apply to unassigned use these percentages");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save the lead split"));
    } finally { setSplitBusy(false); }
  };

  const applyToUnassigned = async () => {
    if (!splitOk) return toast.error(`Shares must add up to 100% (now ${splitTotal}%)`);
    if (!(summary?.unassigned)) return toast.error("There are no unassigned leads to apply the split to");
    setSplitBusy(true);
    try {
      const r = await post("/leads/split/apply-unassigned", {});
      const n = Number(r.assigned || 0);
      if (!n) {
        toast.success("No unassigned leads to apply");
      } else {
        toast.success(
          `${n} lead${n === 1 ? "" : "s"} named on the Lead Register — executive taps Proceed, then GM / Owner Approve`,
        );
      }
      setFilter("all");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not apply the split to unassigned leads"));
    } finally { setSplitBusy(false); }
  };

  const transferMatch = async (row) => {
    const to = matchPick[row.key] || row.suggested;
    if (!to) return toast.error("Pick an executive in the app");
    setMatchBusy(row.key);
    try {
      const r = await post("/leads/match-executive", { key: row.key, executive: to });
      toast.success(`${r.movedCount} lead${r.movedCount === 1 ? "" : "s"} moved to ${to}`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not match that executive"));
    } finally { setMatchBusy(""); }
  };

  return (
    <div data-testid="allocation-page">
      <PageHeader
        title="Lead Allocation"
        subtitle="Who is working which customer — and which leads nobody has yet"
        actions={<Button variant="secondary" onClick={load}><RefreshCcw size={15} /> Refresh</Button>} />

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          <StatCard label="Active leads" value={summary.activeLeads} icon={Users} />
          <StatCard label="Unassigned" value={summary.unassigned} icon={AlertTriangle}
            tone={summary.unassigned > 0 ? "text-amber-600" : "text-emerald-600"} />
          <StatCard label="Executives carrying leads" value={summary.executives.length} icon={UserCheck} />
        </div>
      )}

      {summary && summary.unassigned > 0 && (
        <Card className="p-3 mb-6 bg-amber-50 border-amber-200" data-testid="unassigned-note">
          <p className="text-sm text-amber-900">
            <b>{summary.unassigned} active lead{summary.unassigned === 1 ? " has" : "s have"} no
            executive.</b> Executives only see leads assigned to them, so nobody is working these.
            Save a 100% split, then <b>Apply to unassigned</b> — names go on the Lead Register.
            The executive taps <b>Proceed</b> there to start Deal format + KYC, then GM / Owner Approve.
          </p>
        </Card>
      )}

      {summary && (summary.executiveMatches || []).length > 0 && (
        <Card className="p-4 mb-6" data-testid="exec-match-card">
          <h3 className="font-heading font-bold text-ink mb-1">Match executives</h3>
          <p className="text-xs text-ink-soft mb-3">
            These leads already have an executive name, but it does not match the app list
            (capital letters, extra words). Confirm the person and we transfer those leads to them.
          </p>
          <div className="space-y-2" data-testid="exec-match-scroll">
            {summary.executiveMatches.map((row) => (
              <div key={row.key} className="flex flex-wrap items-center gap-3 rounded-lg ring-1 ring-inset ring-line px-3 py-2">
                <div className="min-w-[8rem] flex-1">
                  <div className="text-sm font-medium text-ink">{row.raw}</div>
                  <div className="text-[11px] text-ink-faint">{row.count} lead{row.count === 1 ? "" : "s"}</div>
                </div>
                <Select
                  data-testid={`alloc-match-${row.key}`}
                  value={matchPick[row.key] ?? row.suggested ?? ""}
                  onChange={(e) => setMatchPick((m) => ({ ...m, [row.key]: e.target.value }))}
                  className="w-56"
                >
                  <option value="">Pick executive…</option>
                  {(row.candidates || []).map((n) => <option key={n} value={n}>{n}</option>)}
                  {execs.filter((n) => !(row.candidates || []).includes(n)).map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </Select>
                <Button
                  data-testid={`alloc-transfer-${row.key}`}
                  onClick={() => transferMatch(row)}
                  disabled={matchBusy === row.key || !(matchPick[row.key] || row.suggested)}
                >
                  <UserCheck size={15} />
                  {matchBusy === row.key ? "Moving…" : "Transfer"}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="p-4 mb-6" data-testid="lead-split-card">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div>
            <h3 className="font-heading font-bold text-ink flex items-center gap-2">
              <Percent size={16} className="text-cobalt" /> Bulk import split
            </h3>
            <p className="text-xs text-ink-soft mt-1">
              Owner and Sales GM set what % of a TL / Owner bulk upload each executive receives,
              and the same % for unassigned leads already on the register. Named Executive cells
              in the sheet stay on that person. Split-assigned rows wait for Deal format + KYC
              and GM / Owner Approve before the executive can work them.
            </p>
          </div>
          {canEditLeadSplit && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" data-testid="split-even-btn" onClick={evenSplit} disabled={!draft.length}>
                Split evenly
              </Button>
              <Button data-testid="split-save-btn" onClick={saveSplit} disabled={splitBusy || !draft.length}>
                {splitBusy ? "Saving…" : "Save split"}
              </Button>
              <Button
                data-testid="split-apply-btn"
                variant="secondary"
                onClick={applyToUnassigned}
                disabled={splitBusy || !splitOk || !(summary?.unassigned)}
              >
                {splitBusy ? "Assigning…" : `Apply to ${summary?.unassigned || 0} unassigned`}
              </Button>
            </div>
          )}
        </div>
        {!draft.length ? (
          <p className="text-sm text-ink-faint">No executives on the staff / Settings list yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="split-grid-scroll">
              {draft.map((row) => (
                <label key={row.executive} className="flex items-center justify-between gap-3 rounded-lg ring-1 ring-inset ring-line px-3 py-2">
                  <span className="text-sm font-medium text-ink truncate">{row.executive}</span>
                  {canEditLeadSplit ? (
                    <span className="flex items-center gap-1 shrink-0">
                      <Input
                        data-testid={`split-pct-${row.executive}`}
                        type="number" min="0" max="100" step="0.01"
                        value={row.pct}
                        onChange={(e) => setShare(row.executive, e.target.value)}
                        className="w-20 text-right tabular" />
                      <span className="text-xs text-ink-faint">%</span>
                    </span>
                  ) : (
                    <span className="font-mono font-semibold tabular" data-testid={`split-pct-${row.executive}`}>{row.pct}%</span>
                  )}
                </label>
              ))}
            </div>
            <p className={`text-xs mt-3 tabular ${splitOk ? "text-emerald-700" : "text-red-600"}`} data-testid="split-total">
              Total {splitTotal}%{splitOk ? "" : " — must be 100% to save"}
              {!canEditLeadSplit ? " · Owner / Sales GM can change this" : ""}
            </p>
          </>
        )}
      </Card>

      {summary && summary.executives.length > 0 && (
        <section className="mb-6" data-testid="allocation-load">
          <h3 className="font-heading font-bold text-ink mb-1">Current load</h3>
          <p className="text-xs text-ink-soft mb-3">Active leads each executive is carrying</p>
          <Table rowKey="executive" rows={summary.executives} empty="Nobody has leads yet"
            maxHeight="16rem"
            onRowClick={(r) => setFilter(r.executive)}
            columns={[
              { key: "executive", label: "Executive", render: (r) => <span className="font-medium">{r.executive}</span> },
              { key: "total", label: "Total", align: "right" },
              { key: "open", label: "Still open", align: "right" },
              { key: "booked", label: "Booked", align: "right" },
            ]} />
        </section>
      )}

      <Card className="p-4 mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[10rem]">
            <label className="block text-xs text-ink-faint mb-1">Show</label>
            <Select data-testid="alloc-filter" value={filter} onChange={(e) => { setFilter(e.target.value); setPicked({}); }}>
              <option value="unassigned">Unassigned only</option>
              <option value="all">All active leads</option>
              {execs.map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
          </div>
          <div className="relative flex-1 min-w-[12rem] max-w-sm">
            <label className="block text-xs text-ink-faint mb-1">Search</label>
            <Search size={14} className="absolute left-2.5 bottom-2.5 text-ink-faint" />
            <Input data-testid="alloc-search" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Name, mobile, lead ID" className="pl-8" />
          </div>
          <div className="min-w-[12rem]">
            <label className="block text-xs text-ink-faint mb-1">Allocate to</label>
            <Select data-testid="alloc-target" value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Select executive…</option>
              {execs.map((n) => <option key={n}>{n}</option>)}
            </Select>
          </div>
          <Button data-testid="alloc-btn" onClick={allocate} disabled={busy || !chosen.length || !target}>
            <UserCheck size={15} />
            {busy ? "Allocating…" : `Allocate ${chosen.length || ""}`.trim()}
          </Button>
        </div>
      </Card>

      <Table rows={rows} empty="No leads match this filter"
        columns={[
          { key: "pick", label: (
            <button onClick={toggleAll} className="text-cobalt hover:underline text-[11px]">
              {allShown ? "None" : "All"}
            </button>
          ), render: (r) => (
            <input type="checkbox" data-testid={`pick-${r.leadId}`} checked={!!picked[r.leadId]}
              onChange={(e) => { e.stopPropagation(); setPicked((p) => ({ ...p, [r.leadId]: !p[r.leadId] })); }}
              onClick={(e) => e.stopPropagation()} />
          ) },
          { key: "leadId", label: "Lead", mono: true,
            render: (r) => <span className="font-semibold text-cobalt">{r.leadId}</span> },
          { key: "customerName", label: "Customer",
            render: (r) => (
              <div>
                <div className="font-medium">{r.customerName}</div>
                <CallLink mobile={r.mobile} compact />
              </div>
            ) },
          { key: "interestedModel", label: "Vehicle", render: (r) => r.interestedModel || "—" },
          { key: "currentStatus", label: "Status", render: (r) => <Badge>{r.currentStatus}</Badge> },
          { key: "executive", label: "Executive", render: (r) => (
            r.executive
              ? (
                <div>
                  <div>{r.executive}</div>
                  {r.assignmentPending && (
                    <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20">Awaiting approval</Badge>
                  )}
                </div>
              )
              : <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20">Unassigned</Badge>
          ) },
          { key: "createdDate", label: "Created", align: "right",
            render: (r) => <span className="text-xs">{fmtDate(r.createdDate)}</span> },
        ]} />

      <p className="text-xs text-ink-faint mt-3">
        Reallocating moves who works the lead from now on. It does not move history —
        a booking or cancellation stays credited to whoever held the lead at the time.
      </p>
    </div>
  );
}
