import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { get, put } from "../lib/api";
import { Drawer, Button } from "./ui";
import { LocalKycBlock, kycReady, uploadKycFiles } from "./LeadDocuments";
import DealFormatCard from "./DealFormatCard";
import CallLink from "./CallLink";

export default function CompleteFormatDrawer({ row, onClose, onSaved }) {
  const [budget, setBudget] = useState(Number(row.budget || row.dealAmount || 0) || "");
  const [deal, setDeal] = useState(row.dealFormat || null);
  const [dealLoading, setDealLoading] = useState(false);
  const [kyc, setKyc] = useState({});
  const [gstin, setGstin] = useState(row.gstin || "");
  const [busy, setBusy] = useState(false);
  const customerType = row.customerType || "Individual";

  useEffect(() => {
    if (!row.interestedModel || !row.variant) {
      setDeal(row.dealFormat || null);
      return undefined;
    }
    let alive = true;
    setDealLoading(true);
    get("/commercial/deal-preview", {
      model: row.interestedModel, variant: row.variant, cxDemand: Number(budget) || 0,
    }).then((d) => { if (alive) setDeal(d); })
      .catch(() => { if (alive) setDeal(row.dealFormat || null); })
      .finally(() => { if (alive) setDealLoading(false); });
    return () => { alive = false; };
  }, [row.interestedModel, row.variant, row.dealFormat, budget]);

  const save = async () => {
    if (!(Number(budget) > 0)) return toast.error("Enter Cx Demand — the final amount given to the customer");
    const kycErr = kycReady(customerType, kyc, gstin);
    if (kycErr) return toast.error(kycErr);
    setBusy(true);
    try {
      await put(`/lead-requests/${row.requestId}`, { budget: Number(budget), gstin });
      await uploadKycFiles(`/lead-requests/${row.requestId}/documents`, kyc);
      toast.success("Sent for GM / Owner Approve — the lead stays on your register until they tap Approve");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save the approval format");
    } finally { setBusy(false); }
  };

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
          This customer is on your Lead Register. Fill Deal format and KYC, then send for
          GM / Owner Approve. After they approve you can work the lead.
        </p>
        <DealFormatCard
          snapshot={deal}
          cxDemand={budget}
          onCxDemand={setBudget}
          loading={dealLoading}
          missingPrice={!row.interestedModel || !row.variant}
        />
        <LocalKycBlock customerType={customerType} files={kyc} setFiles={setKyc} gstin={gstin} onGstin={setGstin} />
      </div>
    </Drawer>
  );
}
