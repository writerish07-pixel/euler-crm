import React, { useCallback, useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Save, Users } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select, Card } from "../components/ui";

// Same family vocabulary the Scheme Master uses. "*" is the catch-all every
// model without its own row falls back to.
const FAMILIES = [
  ["storm", "Storm"],
  ["turbo", "Turbo / Turbo Max"],
  ["hiload", "HiLoad / Hi-Load"],
  ["hicity", "HiCity"],
  ["hirange", "HiRange / Neo HiRange"],
  ["*", "All other models (catch-all)"],
];

const familyLabel = (k) => (FAMILIES.find(([f]) => f === k) || [k, k])[1];

const slabSummary = (slabs) => (slabs || [])
  .map((s) => `${familyLabel(s.modelFamily)} ${s.payoutRatePct}%`)
  .join(" · ") || "No slabs set";

export default function InsuranceAgents() {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => get("/insurance-agents").then(setRows).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.agentName}?`)) return;
    try {
      await del(`/insurance-agents/${r.agentId}`);
      toast.success("Agent deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <div data-testid="insurance-agents">
      <PageHeader
        title="Insurance Agents"
        subtitle="Brokers who pay the insurance payout · each carries its own slab"
        actions={<Button data-testid="add-agent-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Agent</Button>}
      />
      <Table
        rowKey="agentId"
        onRowClick={setEdit}
        columns={[
          { key: "agentName", label: "Agent", render: (r) => (
            <span className="font-semibold">
              {r.agentName}
              {r.isDefault && <Badge tone="bg-cobalt-tint text-cobalt ring-cobalt/20" className="ml-2">Default</Badge>}
            </span>
          ) },
          { key: "agentCode", label: "Code", mono: true, render: (r) => r.agentCode || "—" },
          { key: "contactPerson", label: "Contact", render: (r) => r.contactPerson || "—" },
          { key: "mobile", label: "Mobile", mono: true, render: (r) => r.mobile || "—" },
          { key: "slabs", label: "Payout slabs", render: (r) => (
            <span className="text-xs text-ink-soft">{slabSummary(r.slabs)}</span>
          ) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "act", label: "", align: "right", render: (r) => (
            <div className="flex justify-end gap-2">
              <button data-testid={`edit-agent-${r.agentId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }}
                className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button data-testid={`delete-agent-${r.agentId}`} onClick={(e) => { e.stopPropagation(); remove(r); }}
                className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
          ) },
        ]}
        rows={rows}
        empty="No insurance agents yet — click Add Agent"
      />
      <p className="text-xs text-ink-faint mt-3">
        A slab change applies to <strong>new</strong> entries only. Payouts already booked keep the
        rate they were created with, so past earnings never move.
      </p>
      {edit && <AgentDrawer row={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function AgentDrawer({ row, onClose, onSaved }) {
  const isNew = !row.agentId;
  const [form, setForm] = useState({
    agentName: row.agentName || "", agentCode: row.agentCode || "",
    contactPerson: row.contactPerson || "", mobile: row.mobile || "", email: row.email || "",
    status: row.status || "Active", isDefault: !!row.isDefault, remarks: row.remarks || "",
  });
  const [slabs, setSlabs] = useState(() =>
    (row.slabs && row.slabs.length
      ? row.slabs
      : [{ modelFamily: "storm", payoutRatePct: "" },
         { modelFamily: "turbo", payoutRatePct: "" },
         { modelFamily: "*", payoutRatePct: "" }]
    ).map((s) => ({
      modelFamily: s.modelFamily || "*",
      payoutRatePct: s.payoutRatePct ?? "",
      effectiveFrom: s.effectiveFrom || "",
      effectiveTo: s.effectiveTo || "",
    })));

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setSlab = (i, k) => (e) => setSlabs((rows) =>
    rows.map((s, n) => (n === i ? { ...s, [k]: e.target.value } : s)));
  const addSlab = () => setSlabs((r) => [...r, { modelFamily: "*", payoutRatePct: "", effectiveFrom: "", effectiveTo: "" }]);
  const dropSlab = (i) => setSlabs((r) => r.filter((_s, n) => n !== i));

  const save = async () => {
    if (!form.agentName.trim()) return toast.error("Agent name is required");
    const clean = slabs
      .filter((s) => Number(s.payoutRatePct) > 0)
      .map((s) => ({ ...s, payoutRatePct: Number(s.payoutRatePct) }));
    if (!clean.length) return toast.error("Add at least one payout slab");
    const body = { ...form, isDefault: !!form.isDefault, slabs: clean };
    try {
      if (isNew) await post("/insurance-agents", body);
      else await put(`/insurance-agents/${row.agentId}`, body);
      toast.success(isNew ? "Agent added" : "Agent updated");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-2xl"
      title={isNew ? "Add Insurance Agent" : form.agentName || "Insurance Agent"}
      footer={<div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button data-testid="save-agent-btn" onClick={save}><Save size={15} /> Save</Button>
      </div>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Agent Name *"><Input data-testid="agent-name" value={form.agentName} onChange={set("agentName")} /></Field>
        <Field label="Agent Code"><Input value={form.agentCode} onChange={set("agentCode")} /></Field>
        <Field label="Contact Person"><Input value={form.contactPerson} onChange={set("contactPerson")} /></Field>
        <Field label="Mobile"><Input value={form.mobile} onChange={set("mobile")} /></Field>
        <Field label="Email"><Input value={form.email} onChange={set("email")} /></Field>
        <Field label="Status">
          <Select value={form.status} onChange={set("status")}>
            <option>Active</option><option>Inactive</option>
          </Select>
        </Field>
        <div className="col-span-2">
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            <input type="checkbox" data-testid="agent-default" checked={form.isDefault}
              onChange={(e) => setForm((f) => ({ ...f, isDefault: e.target.checked }))} />
            Default agent — pre-selected at delivery
          </label>
        </div>
      </div>

      <Card className="p-4 mt-4">
        <div className="flex items-center justify-between mb-1">
          <div className="font-heading font-bold text-ink text-sm flex items-center gap-2">
            <Users size={15} /> Payout slabs
          </div>
          <Button variant="secondary" onClick={addSlab}><Plus size={14} /> Add slab</Button>
        </div>
        <p className="text-xs text-ink-soft mb-3">
          Rate as a percentage of the premium. A model without its own row uses the catch-all.
          Leave the dates blank unless the slab starts or ends on a specific day.
        </p>
        <div className="space-y-2">
          {slabs.map((s, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-end">
              <div className="col-span-4">
                <Field label={i === 0 ? "Model family" : ""}>
                  <Select data-testid={`slab-family-${i}`} value={s.modelFamily} onChange={setSlab(i, "modelFamily")}>
                    {FAMILIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </Select>
                </Field>
              </div>
              <div className="col-span-2">
                <Field label={i === 0 ? "Rate %" : ""}>
                  <Input data-testid={`slab-rate-${i}`} type="number" step="0.1"
                    value={s.payoutRatePct} onChange={setSlab(i, "payoutRatePct")} />
                </Field>
              </div>
              <div className="col-span-2">
                <Field label={i === 0 ? "From" : ""}>
                  <Input type="date" value={s.effectiveFrom || ""} onChange={setSlab(i, "effectiveFrom")} />
                </Field>
              </div>
              <div className="col-span-3">
                <Field label={i === 0 ? "To" : ""}>
                  <Input type="date" value={s.effectiveTo || ""} onChange={setSlab(i, "effectiveTo")} />
                </Field>
              </div>
              <div className="col-span-1 pb-2">
                <button onClick={() => dropSlab(i)} className="text-ink-faint hover:text-red-600">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="mt-4">
        <Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field>
      </div>
    </Drawer>
  );
}
