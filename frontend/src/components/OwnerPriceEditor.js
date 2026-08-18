import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { IndianRupee, Save } from "lucide-react";
import { toast } from "sonner";
import { get, put } from "../lib/api";
import { inr } from "../lib/format";
import { Button, Card, Field, Input, Select } from "./ui";
import { PRICE_MONEY_FIELDS, priceBodyFromForm, priceFormFromRow } from "./PriceRowDrawer";

export default function OwnerPriceEditor() {
  const [rows, setRows] = useState([]);
  const [model, setModel] = useState("");
  const [priceId, setPriceId] = useState("");
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");

  const load = useCallback(() => get("/price-master").then((list) => {
    const next = Array.isArray(list) ? list : [];
    setRows(next);
    return next;
  }).catch(() => {
    toast.error("Could not load Price Master");
    return [];
  }), []);

  useEffect(() => { load(); }, [load]);

  const models = useMemo(
    () => [...new Set(rows.map((r) => r.model).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [rows],
  );

  const variants = useMemo(
    () => rows.filter((r) => r.model === model).sort((a, b) => String(a.variant).localeCompare(String(b.variant))),
    [rows, model],
  );

  const selected = rows.find((r) => r.priceId === priceId) || null;

  const pick = useCallback((row) => {
    if (!row) {
      setPriceId("");
      setForm(null);
      return;
    }
    setModel(row.model);
    setPriceId(row.priceId);
    setForm(priceFormFromRow(row));
  }, []);

  useEffect(() => {
    if (!rows.length) return;
    if (priceId && rows.some((r) => r.priceId === priceId)) return;
    pick(rows[0]);
  }, [rows, priceId, pick]);

  const onModelChange = (name) => {
    setModel(name);
    const next = rows.filter((r) => r.model === name)[0];
    pick(next || null);
  };

  const onVariantChange = (id) => {
    pick(rows.find((r) => r.priceId === id) || null);
  };

  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!selected || !form) return toast.error("Select a model and variant");
    if (!form.model || !form.variant) return toast.error("Model & Variant required");
    setSaving(true);
    try {
      const body = priceBodyFromForm({ ...form, model: selected.model, variant: selected.variant });
      const updated = await put(`/price-master/${selected.priceId}`, body);
      toast.success(`Price updated for ${selected.model} ${selected.variant}`);
      const list = await load();
      const fresh = list.find((r) => r.priceId === selected.priceId) || updated;
      if (fresh) pick(fresh);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save price");
    } finally {
      setSaving(false);
    }
  };

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((r) => `${r.model} ${r.variant} ${r.bodyType || ""}`.toLowerCase().includes(needle));
  }, [rows, q]);

  return (
    <Card id="owner-price-editor" className="p-5 mt-6" data-testid="owner-price-editor">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <IndianRupee size={16} className="text-cobalt" />
            <h3 className="font-heading font-bold text-ink">Change model price</h3>
          </div>
          <p className="text-sm text-ink-soft mt-1">
            Owner can update Ex-Showroom, RTO, insurance and other charges for any model / variant.
            New quotes and lead Ex-Showroom use these Price Master values.
          </p>
        </div>
        <Link to="/price-master">
          <Button variant="secondary" data-testid="owner-open-price-master">Full Price Master</Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <Field label="Model">
          <Select data-testid="owner-price-model" value={model} onChange={(e) => onModelChange(e.target.value)}>
            {models.length === 0 && <option value="">No models</option>}
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </Select>
        </Field>
        <Field label="Variant">
          <Select data-testid="owner-price-variant" value={priceId} onChange={(e) => onVariantChange(e.target.value)} disabled={!model}>
            {variants.length === 0 && <option value="">No variants</option>}
            {variants.map((r) => <option key={r.priceId} value={r.priceId}>{r.variant || r.priceId}</option>)}
          </Select>
        </Field>
        <Field label="Search any model">
          <Input data-testid="owner-price-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type model or variant" />
        </Field>
      </div>

      {form && selected && (
        <div className="rounded-lg border border-line bg-zinc-50/60 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
            <div className="font-heading font-bold text-ink">
              {selected.model} <span className="font-sans font-medium text-ink-soft">{selected.variant}</span>
            </div>
            <div className="text-xs text-ink-faint">Current Ex-Showroom {inr(selected.exShowroom)}</div>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {PRICE_MONEY_FIELDS.map(([k, label, t]) => (
              <Field key={k} label={label}>
                <Input data-testid={`owner-price-${k}`} type={t} value={form[k]} onChange={setField(k)} />
              </Field>
            ))}
          </div>
          <div className="flex justify-end mt-4">
            <Button data-testid="owner-save-price-btn" onClick={save} disabled={saving}>
              <Save size={16} /> {saving ? "Saving…" : "Save price"}
            </Button>
          </div>
        </div>
      )}

      <div className="mt-4 max-h-56 overflow-auto rounded-lg border border-line">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="bg-zinc-50 border-b border-line text-[11px] uppercase tracking-wider text-ink-faint">
              <th className="px-3 py-2 font-semibold">Model</th>
              <th className="px-3 py-2 font-semibold">Variant</th>
              <th className="px-3 py-2 font-semibold text-right">Ex-Showroom</th>
              <th className="px-3 py-2 font-semibold text-right">RTO</th>
              <th className="px-3 py-2 font-semibold text-right">Insurance</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-8 text-center text-ink-faint">No matching models</td></tr>
            )}
            {filtered.map((r) => (
              <tr
                key={r.priceId}
                data-testid={`owner-price-row-${r.priceId}`}
                onClick={() => { setQ(""); pick(r); }}
                className={`border-b border-zinc-100 last:border-0 cursor-pointer hover:bg-cobalt-tint/50 ${r.priceId === priceId ? "bg-cobalt-tint/40" : ""}`}
              >
                <td className="px-3 py-2 font-semibold">{r.model}</td>
                <td className="px-3 py-2">{r.variant}</td>
                <td className="px-3 py-2 text-right font-mono tabular">{inr(r.exShowroom)}</td>
                <td className="px-3 py-2 text-right font-mono tabular">{inr(r.rto)}</td>
                <td className="px-3 py-2 text-right font-mono tabular">{inr(r.insurance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
