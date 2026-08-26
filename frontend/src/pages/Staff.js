import React, { useCallback, useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Save, Send, BarChart3 } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select, Card } from "../components/ui";

const ROLES = [
  ["executive", "Executive"], ["ASM", "ASM"], ["RM", "RM"],
  ["owner", "Owner"], ["accounts", "Accounts"],
];

const REPORTS = [
  ["exec_morning", "Morning — my day ahead"],
  ["exec_eod", "EOD — my scorecard"],
  ["manager_eod", "EOD — team volume (no money)"],
  ["owner_eod", "EOD — full business + finance"],
];

const DEFAULTS = {
  executive: ["exec_morning", "exec_eod"],
  ASM: ["manager_eod"], RM: ["manager_eod"],
  owner: ["owner_eod"], accounts: [],
};

const roleLabel = (r) => (ROLES.find(([k]) => k === r) || [r, r])[1];

export default function Staff() {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const [busy, setBusy] = useState("");
  const load = useCallback(() => get("/staff").then(setRows).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const remove = async (r) => {
    if (!window.confirm(`Remove ${r.name}?`)) return;
    try {
      await del(`/staff/${r.staffId}`);
      toast.success("Removed");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not remove"); }
  };

  const sendNow = async (slot) => {
    setBusy(slot);
    try {
      const r = await post(`/integrations/botspace/send-daily-report?slot=${slot}`, {});
      if (r.alreadySent) toast.success(`${slot} report already went out today`);
      else if (r.ok) toast.success(`Sent to ${r.sent} recipient${r.sent === 1 ? "" : "s"}${r.failed ? ` · ${r.failed} failed` : ""}`);
      else toast.error(r.reason || "Could not send");
    } catch (e) { toast.error(e?.response?.data?.detail || "Send failed"); }
    finally { setBusy(""); }
  };

  const noMobile = rows.filter((r) => !r.mobile && (r.reports || []).length).length;

  return (
    <div data-testid="staff-master">
      <PageHeader
        title="Staff & Reports"
        subtitle="One list for everyone — name, WhatsApp, role, target and which daily reports they get"
        actions={<div className="flex items-center gap-2">
          <Button variant="secondary" data-testid="send-morning-btn" onClick={() => sendNow("morning")} disabled={!!busy}>
            <Send size={15} /> {busy === "morning" ? "Sending…" : "Send morning now"}
          </Button>
          <Button variant="secondary" data-testid="send-eod-btn" onClick={() => sendNow("eod")} disabled={!!busy}>
            <Send size={15} /> {busy === "eod" ? "Sending…" : "Send EOD now"}
          </Button>
          <Button data-testid="add-staff-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Person</Button>
        </div>} />

      {noMobile > 0 && (
        <Card className="p-3 mb-4 bg-amber-50 border-amber-200 text-sm text-amber-900">
          {noMobile} {noMobile === 1 ? "person is" : "people are"} subscribed to a report but have
          no WhatsApp number — they will be skipped silently until one is added.
        </Card>
      )}

      <Table
        rowKey="staffId"
        onRowClick={setEdit}
        columns={[
          { key: "name", label: "Name", render: (r) => <span className="font-semibold">{r.name}</span> },
          { key: "role", label: "Role", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{roleLabel(r.role)}</Badge> },
          { key: "mobile", label: "WhatsApp", mono: true, render: (r) => (
            r.mobile ? r.mobile : <span className="text-amber-700">not set</span>
          ) },
          { key: "monthlyTarget", label: "Target", align: "right", render: (r) => (
            r.monthlyTarget ? `${r.monthlyTarget} units` : "—"
          ) },
          { key: "reports", label: "Daily reports", render: (r) => (
            <span className="text-xs text-ink-soft">
              {(r.reports || []).length
                ? (r.reports || []).map((k) => (REPORTS.find(([x]) => x === k) || [k, k])[1].split(" — ")[0]).join(" · ")
                : "none"}
            </span>
          ) },
          { key: "whatsappOptIn", label: "WhatsApp", render: (r) => (
            r.whatsappOptIn === false
              ? <Badge tone="bg-zinc-100 text-zinc-600 ring-zinc-500/20">Opted out</Badge>
              : <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">On</Badge>
          ) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "act", label: "", align: "right", render: (r) => (
            <div className="flex justify-end gap-2">
              <button data-testid={`edit-staff-${r.staffId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button data-testid={`delete-staff-${r.staffId}`} onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
          ) },
        ]}
        rows={rows}
        empty="No staff yet — click Add Person"
      />

      <p className="text-xs text-ink-faint mt-3">
        Executive names here feed every Executive dropdown in the app. Renaming someone who already
        has leads is blocked — set them Inactive and add the new name instead.
      </p>

      {edit && <StaffDrawer row={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function StaffDrawer({ row, onClose, onSaved }) {
  const isNew = !row.staffId;
  const [form, setForm] = useState({
    name: row.name || "", mobile: row.mobile || "", email: row.email || "",
    role: row.role || "executive", monthlyTarget: row.monthlyTarget || 0,
    reports: row.reports || DEFAULTS[row.role || "executive"],
    whatsappOptIn: row.whatsappOptIn !== false,
    status: row.status || "Active", remarks: row.remarks || "",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // Changing role resets the report subscriptions to that role's defaults.
  const setRole = (e) => {
    const role = e.target.value;
    setForm((f) => ({ ...f, role, reports: DEFAULTS[role] || [] }));
  };
  const toggleReport = (k) => setForm((f) => ({
    ...f,
    reports: f.reports.includes(k) ? f.reports.filter((x) => x !== k) : [...f.reports, k],
  }));

  const save = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    if (form.reports.length && !form.mobile.trim()) {
      return toast.error("A WhatsApp number is needed to receive reports");
    }
    const body = { ...form, monthlyTarget: +form.monthlyTarget || 0 };
    try {
      if (isNew) await post("/staff", body); else await put(`/staff/${row.staffId}`, body);
      toast.success(isNew ? "Person added" : "Saved");
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-xl" title={isNew ? "Add Person" : form.name || "Staff"}
      footer={<div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button data-testid="save-staff-btn" onClick={save}><Save size={15} /> Save</Button>
      </div>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name *"><Input data-testid="staff-name" value={form.name} onChange={set("name")} /></Field>
        <Field label="Role">
          <Select data-testid="staff-role" value={form.role} onChange={setRole}>
            {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Select>
        </Field>
        <Field label="WhatsApp number"><Input data-testid="staff-mobile" value={form.mobile} onChange={set("mobile")} placeholder="10-digit mobile" /></Field>
        <Field label="Email"><Input value={form.email} onChange={set("email")} /></Field>
        {form.role === "executive" && (
          <Field label="Monthly target (units)">
            <Input data-testid="staff-target" type="number" value={form.monthlyTarget} onChange={set("monthlyTarget")} />
          </Field>
        )}
        <Field label="Status">
          <Select value={form.status} onChange={set("status")}><option>Active</option><option>Inactive</option></Select>
        </Field>
      </div>

      <Card className="p-4 mt-4">
        <div className="font-heading font-bold text-ink text-sm flex items-center gap-2 mb-1">
          <BarChart3 size={15} /> Daily WhatsApp reports
        </div>
        <p className="text-xs text-ink-soft mb-3">
          Morning goes out at 8:30 AM, EOD at 8:00 PM. Team reports carry volume only — no revenue,
          outstanding or finance amounts.
        </p>
        <div className="space-y-2">
          {REPORTS.map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-sm text-ink-soft">
              <input type="checkbox" data-testid={`staff-report-${k}`}
                checked={form.reports.includes(k)} onChange={() => toggleReport(k)} />
              {label}
            </label>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-soft mt-3 pt-3 border-t border-line">
          <input type="checkbox" data-testid="staff-optin" checked={form.whatsappOptIn}
            onChange={(e) => setForm((f) => ({ ...f, whatsappOptIn: e.target.checked }))} />
          Send WhatsApp to this person
        </label>
      </Card>

      <div className="mt-4">
        <Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field>
      </div>
    </Drawer>
  );
}
