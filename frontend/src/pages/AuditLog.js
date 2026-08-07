import React, { useEffect, useState, useCallback } from "react";
import { ScrollText, RefreshCw } from "lucide-react";
import { get } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Select } from "../components/ui";

const MODULES = ["", "payment", "finance", "claim", "insurance", "scheme", "price-structure", "extra-income", "lead"];
const ACTION_TONE = {
  receipt: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  create: "bg-blue-50 text-blue-700 ring-blue-600/20",
  update: "bg-amber-50 text-amber-700 ring-amber-600/20",
  delete: "bg-red-50 text-red-700 ring-red-600/20",
  settle: "bg-violet-50 text-violet-700 ring-violet-600/20",
  close: "bg-slate-100 text-slate-700 ring-slate-500/20",
};

const short = (v) => {
  if (v === null || v === undefined) return "—";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
};

export default function AuditLog() {
  const [rows, setRows] = useState([]);
  const [module, setModule] = useState("");
  const load = useCallback(() => {
    get("/audit-log", module ? { module } : {}).then(setRows).catch(() => setRows([]));
  }, [module]);
  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="audit-log-page">
      <PageHeader title="Audit Trail" subtitle="Owner · append-only log of every finance-sensitive change (who · what · when)"
        actions={<Button data-testid="refresh-audit-log-btn" onClick={load}><RefreshCw size={15} /> Refresh</Button>} />

      <div className="flex items-center gap-3 mb-4">
        <div className="w-56">
          <Field label="Filter by module">
            <Select data-testid="audit-module-filter" value={module} onChange={(e) => setModule(e.target.value)}>
              {MODULES.map((m) => <option key={m} value={m}>{m || "All modules"}</option>)}
            </Select>
          </Field>
        </div>
        <div className="ml-auto flex items-center gap-2 text-sm text-ink-soft">
          <ScrollText size={16} className="text-ink-faint" /> {rows.length} entries
        </div>
      </div>

      <Table
        rowKey="auditId"
        columns={[
          { key: "timestamp", label: "When", render: (r) => <span className="text-xs">{fmtDate(r.timestamp)} {String(r.timestamp || "").slice(11, 19)}</span> },
          { key: "user", label: "User", render: (r) => <div className="text-sm"><span className="font-semibold">{r.user}</span><div className="text-xs text-ink-faint">{r.role}{r.ip ? ` · ${r.ip}` : ""}</div></div> },
          { key: "action", label: "Action", render: (r) => <Badge tone={ACTION_TONE[r.action] || ""}>{r.action}</Badge> },
          { key: "module", label: "Module", render: (r) => <Badge>{r.module}</Badge> },
          { key: "ref", label: "Reference", render: (r) => <span className="text-xs font-mono">{[r.leadId, r.paymentId, r.claimId, r.financeFileNumber].filter(Boolean).join(" · ") || "—"}</span> },
          { key: "oldValue", label: "Old", render: (r) => <span className="text-xs text-ink-faint font-mono">{short(r.oldValue)}</span> },
          { key: "newValue", label: "New", render: (r) => <span className="text-xs text-ink font-mono">{short(r.newValue)}</span> },
        ]}
        rows={rows}
        empty="No audit entries yet — finance-sensitive changes will appear here"
      />
    </div>
  );
}
