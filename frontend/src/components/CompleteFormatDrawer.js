import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { get, put } from "../lib/api";
import { Drawer, Button, Field, Select } from "./ui";
import { LocalKycBlock, kycReady, uploadKycFiles } from "./LeadDocuments";
import DealFormatCard from "./DealFormatCard";
import CallLink from "./CallLink";

export default function CompleteFormatDrawer({ row, onClose, onSaved }) {
  const [budget, setBudget] = useState(Number(row.budget || row.dealAmount || 0) || "");
  const [model, setModel] = useState(row.interestedModel || "");
  const [variant, setVariant] = useState(row.variant || "");
  const [deal, setDeal] = useState(row.dealFormat || null);
  const [dealLoading, setDealLoading] = useState(false);
  const [kyc, setKyc] = useState({});
  const [gstin, setGstin] = useState(row.gstin || "");
  const [busy, setBusy] = useState(false);
  const [masters, setMasters] = useState(null);
  const [variants, setVariants] = useState([]);
  const customerType = row.customerType || "Individual";

  useEffect(() => {
    get("/masters").then(setMasters).catch(() => setMasters({ models: [] }));
  }, []);

  useEffect(() => {
    if (!model) {
      setVariants([]);
      return undefined;
    }
    let alive = true;
    get("/price-master/variants", { model })
      .then((rows) => { if (alive) setVariants(Array.isArray(rows) ? rows : []); })
      .catch(() => { if (alive) setVariants([]); });
    return () => { alive = false; };
  }, [model]);

  useEffect(() => {
    if (!model || !variant) {
      setDeal(row.dealFormat || null);
      return undefined;
    }
    let alive = true;
    setDealLoading(true);
    get("/commercial/deal-preview", {
      model, variant, cxDemand: Number(budget) || 0,
    }).then((d) => { if (alive) setDeal(d); })
      .catch(() => { if (alive) setDeal(row.dealFormat || null); })
      .finally(() => { if (alive) setDealLoading(false); });
    return () => { alive = false; };
  }, [model, variant, row.dealFormat, budget]);

  const save = async () => {
    if (!model || !variant) return toast.error("Select model and variant — Price Master fills RTO, insurance and transport");
    if (!(Number(budget) > 0)) return toast.error("Enter Cx Demand — the final amount given to the customer");
    const kycErr = kycReady(customerType, kyc, gstin);
    if (kycErr) return toast.error(kycErr);
    setBusy(true);
    try {
      await put(`/lead-requests/${row.requestId}`, {
        budget: Number(budget), gstin, interestedModel: model, variant,
      });
      await uploadKycFiles(`/lead-requests/${row.requestId}/documents`, kyc);
      toast.success("Sent for GM / Owner Approve — the lead stays on your register until they tap Approve");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save the approval format");
    } finally { setBusy(false); }
  };

  const models = masters?.models || [];

  return (
    <Drawer open onClose={onClose} width="max-w-2xl"
      title="Complete approval format"
      subtitle={(
        <span className="flex flex-wrap items-center gap-2">
          <span>{row.customerName} · {row.existingLeadId || row.requestId}</span>
          <CallLink mobile={row.mobile} compact />
        </span>
      )}
      footer={<div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button data-testid="save-approval-format-btn" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Send for approval"}
        </Button>
      </div>}
    >
      <div className="space-y-4">
        <p className="text-sm text-ink-soft">
          Pick the vehicle first (same lists as New Lead). Price Master then fills RTO, insurance
          and transport. Enter Cx Demand and KYC, then send for GM / Owner Approve.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Model *">
            <Select data-testid="approval-model" value={model} onChange={(e) => {
              setModel(e.target.value);
              setVariant("");
            }}>
              <option value="">Select model</option>
              {models.map((s) => <option key={s}>{s}</option>)}
              {model && !models.includes(model) ? <option value={model}>{model}</option> : null}
            </Select>
          </Field>
          <Field label="Variant *">
            <Select data-testid="approval-variant" value={variant} onChange={(e) => setVariant(e.target.value)} disabled={!model}>
              <option value="">{model ? "Select variant" : "Select model first"}</option>
              {variants.map((v) => (
                <option key={v.priceId || v.variant} value={v.variant}>
                  {v.variant}{v.inYard ? ` · ${v.inYard} in yard` : ""}
                </option>
              ))}
              {variant && !variants.some((v) => v.variant === variant) ? <option value={variant}>{variant}</option> : null}
            </Select>
          </Field>
        </div>
        <DealFormatCard
          snapshot={deal}
          cxDemand={budget}
          onCxDemand={setBudget}
          loading={dealLoading}
          missingPrice={!model || !variant}
        />
        <LocalKycBlock customerType={customerType} files={kyc} setFiles={setKyc} gstin={gstin} onGstin={setGstin} />
      </div>
    </Drawer>
  );
}
