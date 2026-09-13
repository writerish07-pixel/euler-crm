import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { get, put, apiErrorMessage } from "../lib/api";
import { Drawer, Button, Field, Input, Select } from "./ui";
import { digitsLast10 } from "../lib/format";
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
  const [oemExtra, setOemExtra] = useState(
    Number(row.oemExtraSupportReceived) > 0 ? Number(row.oemExtraSupportReceived) : "");
  const [mobile, setMobile] = useState(row.mobile || "");
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
    if (!model || !variant) return toast.error("Select model and variant");
    if (!(Number(budget) > 0)) return toast.error("Enter Cx Demand");
    if (!digitsLast10(mobile)) return toast.error("A 10-digit mobile is required before sending for approval");
    const alreadyKyc = row.kycComplete === true;
    const kycErr = alreadyKyc ? "" : kycReady(customerType, kyc, gstin);
    if (kycErr) return toast.error(kycErr);
    setBusy(true);
    try {
      await put(`/lead-requests/${row.requestId}`, {
        budget: Number(budget), gstin, interestedModel: model, variant,
        oemExtraSupportReceived: Number(oemExtra) || 0,
        mobile: digitsLast10(mobile),
      });
      await uploadKycFiles(`/lead-requests/${row.requestId}/documents`, kyc);
      toast.success("Sent for approval");
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save the approval format"));
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
          Select the vehicle, enter a 10-digit mobile and Cx Demand, attach KYC, then send for approval.
        </p>
        <Field label="Mobile *">
          <Input data-testid="approval-mobile" value={mobile} inputMode="numeric"
            placeholder="10-digit mobile" onChange={(e) => setMobile(e.target.value)} />
        </Field>
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
        <Field label="OEM Extra Support">
          <Input data-testid="approval-oem-extra" type="number" min="0" step="1"
            value={oemExtra} onChange={(e) => setOemExtra(e.target.value)} />
          <p className="text-[11px] text-ink-faint mt-1">
            Filled if extra support already exists against this lead. On Approve it becomes Scheme · OEM Extra Support Received.
          </p>
        </Field>
        <LocalKycBlock customerType={customerType} files={kyc} setFiles={setKyc} gstin={gstin} onGstin={setGstin} />
      </div>
    </Drawer>
  );
}
