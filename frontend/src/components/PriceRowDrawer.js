import React, { useState } from "react";
import { toast } from "sonner";
import { post, put } from "../lib/api";
import { Button, Drawer, Field, Input, Select } from "./ui";

export const PRICE_FIELDS = [
  ["model", "Model", "text"], ["variant", "Variant", "text"], ["bodyType", "Body Type", "text"],
  ["exShowroom", "Ex-Showroom", "number"], ["rto", "RTO", "number"], ["insurance", "Insurance", "number"],
  ["accessories", "Accessories", "number"], ["handlingCharges", "Handling", "number"], ["trc", "TRC", "number"],
  ["fastag", "Fastag", "number"], ["extendedWarranty", "Ext. Warranty", "number"], ["otherCharges", "Other", "number"],
  ["gstPercent", "GST %", "number"], ["priceVersion", "Price Version", "text"],
];

export const PRICE_MONEY_FIELDS = PRICE_FIELDS.filter(([, , t]) => t === "number");

export function priceFormFromRow(row = {}) {
  const f = { tcsApplicable: row.tcsApplicable || "No", status: row.status || "active", remarks: row.remarks || "" };
  PRICE_FIELDS.forEach(([k, , t]) => (f[k] = row[k] ?? (t === "number" ? 0 : "")));
  return f;
}

export function priceBodyFromForm(form) {
  const body = { ...form };
  PRICE_FIELDS.forEach(([k, , t]) => { if (t === "number") body[k] = +form[k] || 0; });
  return body;
}

export function PriceRowDrawer({ row, onClose, onSaved }) {
  const isNew = !row.priceId;
  const [form, setForm] = useState(() => priceFormFromRow(row));
  const set = (k, t) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const save = async () => {
    if (!form.model || !form.variant) return toast.error("Model & Variant required");
    const body = priceBodyFromForm(form);
    try {
      if (isNew) await post("/price-master", body); else await put(`/price-master/${row.priceId}`, body);
      toast.success(isNew ? "Row added" : "Row updated");
      onSaved();
    } catch {
      toast.error("Save failed");
    }
  };
  return (
    <Drawer open onClose={onClose} width="max-w-xl" title={isNew ? "Add Price Row" : "Edit Price Row"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-price-row-btn" onClick={save}>Save</Button></div>}>
      <div className="grid grid-cols-2 gap-3">
        {PRICE_FIELDS.map(([k, label, t]) => <Field key={k} label={label}><Input data-testid={`pm-${k}`} type={t} value={form[k]} onChange={set(k, t)} /></Field>)}
        <Field label="TCS Applicable"><Select value={form.tcsApplicable} onChange={(e) => setForm({ ...form, tcsApplicable: e.target.value })}><option>No</option><option>Yes</option></Select></Field>
        <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}><option>active</option><option>inactive</option></Select></Field>
      </div>
    </Drawer>
  );
}
