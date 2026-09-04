import React, { useEffect, useMemo, useState, useCallback } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const COMPONENTS = [
  ["Consumer Discount", "consumerDiscount"], ["Exchange Bonus", "exchangeBonus"],
  ["Loyalty Bonus", "loyaltyBonus"], ["Referral Bonus", "referralBonus"],
  ["DSA Bonus", "dsaDiscount"], ["Additional Discount", "additionalDiscount"],
];

function monthOf(iso) {
  return String(iso || "").slice(0, 7);
}

function lastDayOfMonth(ym) {
  if (!ym || ym.length < 7) return "";
  const [y, m] = ym.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

function rowMatchesMonth(r, asOf) {
  const month = monthOf(asOf);
  const rMonth = monthOf(r.schemeMonth);
  if (rMonth) return rMonth === month;
  const from = String(r.effectiveFrom || "").slice(0, 10);
  const to = String(r.effectiveTo || "").slice(0, 10);
  if (from && asOf < from) return false;
  if (to && asOf > to) return false;
  return Boolean(from || to);
}

export default function SchemeMaster() {
  const { isOwner } = useAuth();
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const [models, setModels] = useState([]);
  const [asOf, setAsOf] = useState(todayISO());
  const [showAll, setShowAll] = useState(false);
  const load = useCallback(() => get("/scheme-master").then(setRows), []);
  useEffect(() => { load(); get("/masters").then((m) => setModels(m.models)); }, [load]);
  const remove = async (r) => { if (!window.confirm("Delete scheme row?")) return; await del(`/scheme-master/${r.schemeId}`); toast.success("Deleted"); load(); };

  const visible = useMemo(
    () => (showAll ? rows : rows.filter((r) => rowMatchesMonth(r, asOf))),
    [rows, asOf, showAll],
  );
  const monthLabel = monthOf(asOf) || asOf;

  return (
    <div>
      <PageHeader title="Scheme Master" subtitle="Enter each month's OEM circular here. Last month does not carry forward. Coulson invoice schemes cannot be pulled — that dropdown is not on their price API."
        actions={isOwner ? <Button data-testid="add-scheme-btn" onClick={() => setEdit({ schemeMonth: monthOf(asOf), effectiveFrom: asOf ? `${monthOf(asOf)}-01` : "", effectiveTo: lastDayOfMonth(monthOf(asOf)) })}><Plus size={16} /> Add Scheme</Button> : null} />
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <Field label="Show schemes for">
          <Input data-testid="scheme-master-date" type="date" value={asOf} onChange={(e) => { setAsOf(e.target.value); setShowAll(false); }} />
        </Field>
        <div className="text-sm text-ink-soft pb-2" data-testid="scheme-master-month-note">
          {showAll ? `All circulars · ${rows.length} rows` : `${monthLabel} · ${visible.length} rows`}
        </div>
        <Button variant="secondary" data-testid="scheme-master-all" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Filter by date" : "Show all months"}
        </Button>
      </div>
      <Table
        rowKey="schemeId"
        columns={[
          { key: "schemeMonth", label: "Month", render: (r) => <span className="font-mono text-xs">{r.schemeMonth || "—"}</span> },
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "component", label: "Component", render: (r) => <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.component}</Badge> },
          { key: "dealerShare", label: "Dealer Share", align: "right", mono: true, render: (r) => inr(r.dealerShare) },
          { key: "companyShare", label: "Company Share", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.companyShare)}</span> },
          { key: "totalBenefit", label: "Total", align: "right", mono: true, render: (r) => inr(r.totalBenefit) },
          { key: "effectiveFrom", label: "Valid From", render: (r) => fmtDate(r.effectiveFrom) },
          { key: "effectiveTo", label: "Valid To", render: (r) => fmtDate(r.effectiveTo) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "act", label: "", align: "right", render: (r) => (
            isOwner ? (
            <div className="flex justify-end gap-2">
              <button data-testid={`edit-scheme-${r.schemeId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
              <button onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
            </div>
            ) : null
          )},
        ]}
        rows={visible}
      />
      {edit && <EditDrawer row={edit} models={models} defaultMonth={monthOf(asOf)} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function EditDrawer({ row, models, defaultMonth, onClose, onSaved }) {
  const isNew = !row.schemeId;
  const startMonth = monthOf(row.schemeMonth) || defaultMonth || monthOf(todayISO());
  const [form, setForm] = useState({
    model: row.model || "", variant: row.variant || "", component: row.component || "Consumer Discount",
    componentKey: row.componentKey || "consumerDiscount", dealerShare: row.dealerShare || 0,
    companyShare: row.companyShare || 0, circularRef: row.circularRef || "",
    schemeMonth: startMonth,
    effectiveFrom: row.effectiveFrom || (startMonth ? `${startMonth}-01` : ""),
    effectiveTo: row.effectiveTo || lastDayOfMonth(startMonth),
    status: row.status || "Active",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setMonth = (e) => {
    const m = e.target.value;
    setForm((f) => ({
      ...f,
      schemeMonth: m,
      effectiveFrom: m ? `${m}-01` : "",
      effectiveTo: lastDayOfMonth(m),
    }));
  };
  const setFrom = (e) => {
    const d = e.target.value;
    setForm((f) => ({ ...f, effectiveFrom: d, schemeMonth: f.schemeMonth || monthOf(d) }));
  };
  const setTo = (e) => {
    const d = e.target.value;
    setForm((f) => ({ ...f, effectiveTo: d, schemeMonth: f.schemeMonth || monthOf(d) }));
  };
  const setComponent = (e) => {
    const label = e.target.value; const key = COMPONENTS.find((c) => c[0] === label)?.[1] || "";
    setForm((f) => ({ ...f, component: label, componentKey: key }));
  };
  const save = async () => {
    if (!form.model) return toast.error("Model required");
    const month = monthOf(form.schemeMonth) || monthOf(form.effectiveFrom) || monthOf(form.effectiveTo);
    const body = {
      ...form,
      schemeMonth: month,
      dealerShare: +form.dealerShare,
      companyShare: +form.companyShare,
      totalBenefit: +form.dealerShare + +form.companyShare,
    };
    try {
      if (isNew) await post("/scheme-master", body); else await put(`/scheme-master/${row.schemeId}`, body);
      toast.success(isNew ? "Scheme added" : "Scheme updated"); onSaved();
    } catch { toast.error("Save failed"); }
  };
  return (
    <Drawer open onClose={onClose} width="max-w-lg" title={isNew ? "Add Scheme" : "Edit Scheme"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-scheme-row-btn" onClick={save}>Save</Button></div>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Scheme Month">
          <Input data-testid="sm-month" type="month" value={form.schemeMonth || ""} onChange={setMonth} />
        </Field>
        <Field label="Circular Ref"><Input value={form.circularRef} onChange={set("circularRef")} /></Field>
        <Field label="Valid From"><Input data-testid="sm-from" type="date" value={form.effectiveFrom || ""} onChange={setFrom} /></Field>
        <Field label="Valid To"><Input data-testid="sm-to" type="date" value={form.effectiveTo || ""} onChange={setTo} /></Field>
        <Field label="Model"><Select data-testid="sm-model" value={form.model} onChange={set("model")}><option value="">—</option>{models.map((m) => <option key={m}>{m}</option>)}</Select></Field>
        <Field label="Variant"><Input value={form.variant} onChange={set("variant")} placeholder="All / specific" /></Field>
        <div className="col-span-2"><Field label="Component"><Select value={form.component} onChange={setComponent}>{COMPONENTS.map((c) => <option key={c[1]}>{c[0]}</option>)}</Select></Field></div>
        <Field label="Dealer Share (₹)"><Input type="number" value={form.dealerShare} onChange={set("dealerShare")} /></Field>
        <Field label="Company Share (₹)"><Input data-testid="sm-company" type="number" value={form.companyShare} onChange={set("companyShare")} /></Field>
        <Field label="Status"><Select value={form.status} onChange={set("status")}><option>Active</option><option>Inactive</option></Select></Field>
      </div>
    </Drawer>
  );
}
