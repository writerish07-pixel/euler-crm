import React, { useCallback, useEffect, useMemo, useState } from "react";
import { UserCheck, Users, AlertTriangle, RefreshCcw, Search } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Card, StatCard, Table, Badge, Button, Select, Input } from "../components/ui";

/**
 * Allocate leads to executives.
 *
 * This page matters more since executives were scoped to their own leads: a lead
 * with nobody on it is now invisible to every executive, so it would sit unworked
 * and unnoticed. "Unassigned" is therefore the default filter.
 */
export default function Allocation() {
  const [summary, setSummary] = useState(null);
  const [leads, setLeads] = useState([]);
  const [execs, setExecs] = useState([]);
  const [filter, setFilter] = useState("unassigned");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState({});
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get("/leads/allocation/summary").then(setSummary).catch(() => {});
    get("/leads").then(setLeads).catch(() => toast.error("Could not load leads"));
    get("/masters").then((m) => setExecs(m.executives || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

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
      toast.error(e?.response?.data?.detail || "Allocation failed");
    } finally { setBusy(false); }
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
          </p>
        </Card>
      )}

      {summary && summary.executives.length > 0 && (
        <section className="mb-6" data-testid="allocation-load">
          <h3 className="font-heading font-bold text-ink mb-1">Current load</h3>
          <p className="text-xs text-ink-soft mb-3">Active leads each executive is carrying</p>
          <Table rowKey="executive" rows={summary.executives} empty="Nobody has leads yet"
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
                <div className="text-xs text-ink-faint">{r.mobile}</div>
              </div>
            ) },
          { key: "interestedModel", label: "Vehicle", render: (r) => r.interestedModel || "—" },
          { key: "currentStatus", label: "Status", render: (r) => <Badge>{r.currentStatus}</Badge> },
          { key: "executive", label: "Executive", render: (r) => (
            r.executive
              ? r.executive
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
