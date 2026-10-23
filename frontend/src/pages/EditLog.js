import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ScrollText } from "lucide-react";
import { get } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Field, Select, Input } from "../components/ui";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { usePeriodState } from "../lib/period";

const ROLES = [
  ["", "All roles"],
  ["sales_gm", "Sales GM"],
  ["tl", "Showroom Admin"],
  ["team_lead", "Team Leader"],
  ["executive", "Executive"],
];
const MODULES = [
  ["", "All changes"],
  ["lead", "Lead details"],
  ["lead-field", "Lead field"],
  ["price-structure", "Price"],
  ["scheme", "Scheme"],
  ["extra-income", "Extra income"],
  ["activity", "Activity / follow-up"],
  ["gstin", "GSTIN"],
  ["lead-unit", "Unit"],
];
const ACTION_TONE = {
  update: "bg-amber-50 text-amber-800 ring-amber-600/20",
  amend: "bg-sky-50 text-sky-800 ring-sky-600/20",
  allocate: "bg-violet-50 text-violet-800 ring-violet-600/20",
};

export default function EditLog() {
  const [rows, setRows] = useState([]);
  const [role, setRole] = useState("");
  const [module, setModule] = useState("");
  const [q, setQ] = useState("");
  const period = usePeriodState();

  const load = useCallback(() => {
    return get("/edit-log", {
      ...(role ? { role } : {}),
      ...(module ? { module } : {}),
      ...(q.trim() ? { q: q.trim() } : {}),
      ...period.params,
    }).then(setRows).catch(() => setRows([]));
  }, [role, module, q, period.params]);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="edit-log-page">
      <PageHeader
        title="Edit Log Register"
        subtitle={`${rows.length} desk edits · Sales GM, Showroom Admin, Team Leader, Executive`}
        actions={<ReportActions onRefresh={load} />}
      />
      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
      <div className="flex flex-col gap-2 mb-4 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="w-full sm:w-44">
          <Field label="Edited by">
            <Select data-testid="edit-log-role" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLES.map(([v, l]) => <option key={v || "all"} value={v}>{l}</option>)}
            </Select>
          </Field>
        </div>
        <div className="w-full sm:w-48">
          <Field label="What changed">
            <Select data-testid="edit-log-module" value={module} onChange={(e) => setModule(e.target.value)}>
              {MODULES.map(([v, l]) => <option key={v || "all"} value={v}>{l}</option>)}
            </Select>
          </Field>
        </div>
        <div className="w-full sm:flex-1 sm:min-w-[200px]">
          <Field label="Search">
            <Input data-testid="edit-log-search" placeholder="Name / lead / change…" value={q} onChange={(e) => setQ(e.target.value)} />
          </Field>
        </div>
        <div className="flex items-center gap-2 text-sm text-ink-soft pb-1">
          <ScrollText size={16} className="text-ink-faint" /> {rows.length}
        </div>
      </div>
      <Table
        rowKey="editId"
        columns={[
          { key: "timestamp", label: "When", render: (r) => (
            <span className="text-xs">{fmtDate(r.timestamp)} {String(r.timestamp || "").slice(11, 19)}</span>
          ) },
          { key: "name", label: "Who", render: (r) => (
            <div className="text-sm">
              <span className="font-semibold">{r.name || r.user || "—"}</span>
              <div className="text-xs text-ink-faint">{r.roleLabel || r.role}</div>
            </div>
          ) },
          { key: "action", label: "Action", render: (r) => (
            <Badge tone={ACTION_TONE[r.action] || ""}>{r.action}</Badge>
          ) },
          { key: "leadId", label: "Lead", render: (r) => r.leadId ? (
            <div>
              <Link to={`/leads?open=${encodeURIComponent(r.leadId)}`} className="font-mono text-xs font-semibold text-cobalt hover:underline">{r.leadId}</Link>
              {r.customerName ? <div className="text-xs text-ink">{r.customerName}</div> : null}
              {r.executive ? <div className="text-[11px] text-ink-faint">{r.executive}</div> : null}
            </div>
          ) : <span className="text-ink-faint">—</span> },
          { key: "summary", label: "What changed", render: (r) => (
            <span className="text-xs text-ink">{r.summary || "—"}</span>
          ) },
        ]}
        rows={rows}
        empty="No desk edits in this filter"
      />
    </div>
  );
}
