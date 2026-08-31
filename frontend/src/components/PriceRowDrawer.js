import React, { useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Users } from "lucide-react";
import { get, post, put } from "../lib/api";
import { inr } from "../lib/format";
import { Button, Card, Drawer, Field, Input, Select, Table } from "./ui";

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
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k, t) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const priceMoved = !isNew && (+form.exShowroom || 0) !== (+row.exShowroom || 0);

  // Saving a price pushes it onto every live lead on this vehicle. Let the owner
  // see exactly who moves, and by how much, before committing.
  const checkImpact = async () => {
    setBusy(true);
    try {
      const r = await get(`/price-master/${row.priceId}/reprice-preview`,
        { exShowroom: +form.exShowroom || 0 });
      setPreview(r);
      if (!r.wouldRepriceCount) toast.success("No live leads would change");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not check impact");
    } finally { setBusy(false); }
  };

  const save = async () => {
    if (!form.model || !form.variant) return toast.error("Model & Variant required");
    const body = priceBodyFromForm(form);
    setBusy(true);
    try {
      if (isNew) {
        await post("/price-master", body);
        toast.success("Row added");
      } else {
        const res = await put(`/price-master/${row.priceId}`, body);
        const rp = res?.reprice || {};
        if (rp.repricedCount) {
          toast.success(
            `Row updated — ${rp.repricedCount} lead${rp.repricedCount === 1 ? "" : "s"} repriced` +
            (rp.skippedCount ? ` · ${rp.skippedCount} kept the old price` : ""));
        } else {
          toast.success("Row updated");
        }
      }
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally { setBusy(false); }
  };

  return (
    <Drawer open onClose={onClose} width={preview ? "max-w-3xl" : "max-w-xl"}
      title={isNew ? "Add Price Row" : "Edit Price Row"}
      footer={<div className="flex justify-between items-center gap-2">
        {priceMoved ? (
          <Button variant="ghost" data-testid="check-reprice-impact-btn" onClick={checkImpact} disabled={busy}>
            <Users size={15} /> {busy ? "Checking…" : "Check who this affects"}
          </Button>
        ) : <span />}
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-price-row-btn" onClick={save} disabled={busy}>Save</Button>
        </div>
      </div>}>
      {!isNew && row.priceSource === "oem" && (
        <p className="text-xs text-ink-soft mb-3">
          Ex-showroom is locked to the Euler OEM price. RTO, insurance and other charges stay yours to edit.
        </p>
      )}
      <div className="grid grid-cols-2 gap-3">
        {PRICE_FIELDS.map(([k, label, t]) => {
          const oemLocked = !isNew && row.priceSource === "oem" && k === "exShowroom";
          return (
            <Field key={k} label={oemLocked ? "Ex-Showroom (OEM)" : label}>
              <Input data-testid={`pm-${k}`} type={t} value={form[k]} onChange={set(k, t)} disabled={oemLocked} />
            </Field>
          );
        })}
        <Field label="TCS Applicable"><Select value={form.tcsApplicable} onChange={(e) => setForm({ ...form, tcsApplicable: e.target.value })}><option>No</option><option>Yes</option></Select></Field>
        <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}><option>active</option><option>inactive</option></Select></Field>
      </div>

      {priceMoved && (
        <Card className="p-4 mt-4 bg-amber-50 border-amber-200" data-testid="reprice-warning">
          <div className="flex gap-2 text-sm text-amber-900">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold">Saving reprices live leads</div>
              <p className="text-xs mt-1">
                Every Active, not-yet-delivered lead on {form.model} {form.variant} is moved to the new
                price and its Customer Payable recomputed. Delivered leads and leads that have already
                paid in full are left alone. Each change is written to the Audit Trail.
              </p>
            </div>
          </div>
        </Card>
      )}

      {preview && <RepriceImpact preview={preview} />}
    </Drawer>
  );
}

function RepriceImpact({ preview }) {
  const delta = (preview.proposedExShowroom || 0) - (preview.currentExShowroom || 0);
  return (
    <div className="mt-4" data-testid="reprice-impact">
      <h4 className="font-heading font-bold text-ink text-sm mb-2">
        Impact of {delta >= 0 ? "+" : ""}{inr(delta)} on {preview.model} {preview.variant}
      </h4>
      <div className="grid grid-cols-2 gap-3 mb-4">
        <Card className="p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Would be repriced</div>
          <div className="text-xl font-bold text-cobalt tabular">{preview.wouldRepriceCount}</div>
        </Card>
        <Card className="p-3">
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">Keep the old price</div>
          <div className="text-xl font-bold text-ink-faint tabular">{preview.wouldSkipCount}</div>
        </Card>
      </div>

      {preview.wouldReprice.length > 0 && (
        <Table
          rowKey="leadId"
          columns={[
            { key: "leadId", label: "Lead", mono: true },
            { key: "customerName", label: "Customer" },
            { key: "currentStatus", label: "Status" },
            { key: "customerPayable", label: "Payable now", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
            { key: "estimatedDelta", label: "Change", align: "right", mono: true, render: (r) => (
              <span className={r.estimatedDelta >= 0 ? "text-red-600 font-semibold" : "text-emerald-600 font-semibold"}>
                {r.estimatedDelta >= 0 ? "+" : ""}{inr(r.estimatedDelta)}
              </span>
            ) },
          ]}
          rows={preview.wouldReprice}
        />
      )}

      {preview.wouldSkip.length > 0 && (
        <>
          <h4 className="font-heading font-bold text-ink text-sm mt-4 mb-2">Left at the old price</h4>
          <Table
            rowKey="leadId"
            columns={[
              { key: "leadId", label: "Lead", mono: true },
              { key: "customerName", label: "Customer" },
              { key: "customerPayable", label: "Payable", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
              { key: "reason", label: "Why", render: (r) => <span className="text-xs text-ink-soft">{r.reason}</span> },
            ]}
            rows={preview.wouldSkip}
          />
        </>
      )}
    </div>
  );
}
