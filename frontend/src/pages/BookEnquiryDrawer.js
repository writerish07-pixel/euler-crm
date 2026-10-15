import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { get, post, apiErrorMessage, downloadPost } from "../lib/api";
import { digitsLast10, todayISO } from "../lib/format";
import { Drawer, Button, Field, Input, Select } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import {
  LocalKycBlock, kycReady, uploadKycFiles,
  extraSupportReady, LocalOemExtraBlock,
  dealSheetReady, LocalDealSheetBlock,
} from "../components/LeadDocuments";
import DealFormatCard from "../components/DealFormatCard";
import CallLink from "../components/CallLink";

function paymentRefLabel(mode) {
  const m = String(mode || "").toLowerCase();
  if (m === "cheque") return "Cheque number";
  if (m === "upi" || m === "neft") return "UTR / transaction number";
  if (m === "card") return "Transaction number";
  return "Transaction number";
}

function paymentRefRequired(mode, amount) {
  const m = String(mode || "").toLowerCase();
  if (m === "cash" || m === "finance" || !m) return false;
  return Number(amount) > 0;
}

function kindsPresent(docs, kinds) {
  const have = new Set((docs || []).map((d) => d.kind));
  const files = {};
  kinds.forEach((k) => { if (have.has(k)) files[k] = true; });
  return files;
}

/** Convert to Booking: fill model / deal / KYC, then book or send for approval. */
export default function BookEnquiryDrawer({ lead, onClose, onDone }) {
  const { canSeeOwnerCommercials, isExecutive, isTeamLead } = useAuth();
  const hideScheme = isExecutive || isTeamLead;
  const [masters, setMasters] = useState(null);
  const [variants, setVariants] = useState([]);
  const [model, setModel] = useState(lead.interestedModel || "");
  const [variant, setVariant] = useState(lead.variant || "");
  const [budget, setBudget] = useState(Number(lead.budget || lead.cxDemand || 0) || "");
  const [customerType, setCustomerType] = useState(lead.customerType || "Individual");
  const [gstin, setGstin] = useState(lead.gstin || "");
  const [oemExtra, setOemExtra] = useState(
    Number(lead.oemExtraSupportReceived) > 0 ? Number(lead.oemExtraSupportReceived) : "");
  const [deal, setDeal] = useState(lead.dealFormat || null);
  const [dealLoading, setDealLoading] = useState(false);
  const [passOn, setPassOn] = useState(() => lead.schemePassOn || {});
  const [kyc, setKyc] = useState({});
  const [extraProof, setExtraProof] = useState({});
  const [dealSheet, setDealSheet] = useState({});
  const [docs, setDocs] = useState([]);
  const [form, setForm] = useState({
    bookingAmount: 0,
    paymentMode: "UPI",
    paymentReference: "",
    financeRequired: lead.financeRequired || "No",
    exchangeRequired: lead.exchangeRequired || "No",
    bookingDate: lead.bookingDate || todayISO(),
  });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const setPay = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    get("/masters").then(setMasters).catch(() => setMasters({ models: [] }));
    get(`/leads/${lead.leadId}/documents`).then((d) => setDocs(Array.isArray(d) ? d : [])).catch(() => setDocs([]));
  }, [lead.leadId]);

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
      setDeal(null);
      return undefined;
    }
    let alive = true;
    setDealLoading(true);
    const passOnKeys = hideScheme ? "" : Object.keys(passOn).filter((k) => passOn[k]).join(",");
    get("/commercial/deal-preview", {
      model, variant, cxDemand: Number(budget) || 0,
      passOnKeys: passOnKeys || undefined,
    }).then((d) => { if (alive) setDeal(d); })
      .catch(() => { if (alive) setDeal(null); })
      .finally(() => { if (alive) setDealLoading(false); });
    return () => { alive = false; };
  }, [model, variant, budget, passOn, hideScheme]);

  const models = masters?.models || [];
  const priceFound = Boolean(deal && (deal.priceFound !== false) && Number(deal.exShowroom || deal.priceTotal) > 0);
  const needsApproval = Boolean(Number(budget) > 0 && deal && deal.needsApproval);
  const kycFiles = { ...kindsPresent(docs, customerType === "B2B"
    ? ["kyc_pan", "kyc_gst"] : ["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"]), ...kyc };
  const kycErr = kycReady(customerType, kycFiles, gstin);
  const extraErr = extraSupportReady(oemExtra, extraProof, docs);
  const sheetErr = needsApproval ? dealSheetReady(dealSheet, docs) : "";

  const submit = async () => {
    if (!model || !variant) return toast.error("Select model and variant");
    if (!form.bookingDate) return toast.error("Booking date is required");
    if (kycErr) return toast.error(kycErr);
    if (extraErr) return toast.error(extraErr);
    if (sheetErr) return toast.error(sheetErr);
    if (paymentRefRequired(form.paymentMode, form.bookingAmount) && !String(form.paymentReference || "").trim()) {
      return toast.error(`Enter the ${paymentRefLabel(form.paymentMode).toLowerCase()}`);
    }
    setBusy(true);
    try {
      await uploadKycFiles(`/leads/${lead.leadId}/documents`, { ...kyc, ...extraProof, ...dealSheet });
      const res = await post(`/leads/${lead.leadId}/convert-booking`, {
        bookingAmount: +form.bookingAmount,
        paymentMode: form.paymentMode,
        executive: lead.executive,
        financeRequired: form.financeRequired,
        exchangeRequired: form.exchangeRequired,
        bookingDate: form.bookingDate,
        paymentReference: String(form.paymentReference || "").trim(),
        gstin: String(gstin || "").trim(),
        interestedModel: model,
        variant,
        budget: Number(budget) || 0,
        oemExtraSupportReceived: Number(oemExtra) || 0,
        customerType,
        ...(hideScheme ? {} : { schemePassOn: passOn }),
      });
      setResult({ booking: res, lead: res.lead || {} });
      toast.success("Booking confirmed");
    } catch (e) {
      const msg = apiErrorMessage(e, "Booking failed");
      if (e?.response?.status === 409 && /approv/i.test(String(msg))) {
        toast.success(msg);
        onDone();
        return;
      }
      toast.error(msg);
    } finally { setBusy(false); }
  };

  const printDealSheet = async () => {
    if (!lead.customerName) return toast.error("Customer name is missing");
    if (!model || !variant) return toast.error("Select a vehicle");
    if (!(Number(budget) > 0)) return toast.error("Enter Cx Demand");
    setBusy(true);
    try {
      await downloadPost("/commercial/deal-sheet.pdf", `deal-sheet-${lead.customerName}.pdf`, {
        customerName: lead.customerName,
        mobile: digitsLast10(lead.mobile),
        city: lead.city || "",
        customerType,
        gstin,
        interestedModel: model,
        variant,
        budget: Number(budget) || 0,
        executive: lead.executive || "",
        createdDate: String(lead.createdDate || "").slice(0, 10),
        passOnKeys: hideScheme ? "" : Object.keys(passOn).filter((k) => passOn[k]).join(","),
      });
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not print the deal sheet"));
    } finally { setBusy(false); }
  };

  if (result) {
    const l = result.lead || {};
    return (
      <Drawer open onClose={onDone} width="max-w-2xl" title="Booking Confirmed"
        footer={<div className="flex justify-end"><Button data-testid="booking-done-btn" onClick={onDone}>Done</Button></div>}>
        <div className="space-y-1.5 text-sm" data-testid="booking-summary">
          <div className="flex justify-between"><span className="text-ink-soft">Lead</span><span>{lead.leadId}</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Booking ID</span><span>{result.booking?.bookingId || "—"}</span></div>
          <div className="flex justify-between font-semibold"><span>Customer Payable</span><span>{l.customerPayable ?? "—"}</span></div>
        </div>
      </Drawer>
    );
  }

  return (
    <Drawer open onClose={onClose} width="max-w-2xl"
      title="Convert to Booking"
      subtitle={(
        <span className="flex flex-wrap items-center gap-2">
          <span>{lead.customerName} · {lead.leadId}</span>
          <CallLink mobile={lead.mobile} compact />
        </span>
      )}
      footer={<div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button data-testid="confirm-booking-btn" onClick={submit} disabled={busy}>
          {busy ? "Saving…" : (needsApproval ? "Send for approval" : "Confirm Booking")}
        </Button>
      </div>}
    >
      <div className="space-y-4" data-testid="book-enquiry-drawer">
        <p className="text-sm text-ink-soft">
          Walk-in files start with name and mobile. Fill the vehicle, deal, KYC and papers here, then book.
          A dealer discount waits on GM / Owner Approvals.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Model *">
            <Select data-testid="book-model" value={model} onChange={(e) => { setModel(e.target.value); setVariant(""); }}>
              <option value="">Select model</option>
              {models.map((s) => <option key={s}>{s}</option>)}
              {model && !models.includes(model) ? <option value={model}>{model}</option> : null}
            </Select>
          </Field>
          <Field label="Variant *">
            <Select data-testid="book-variant" value={variant} onChange={(e) => setVariant(e.target.value)} disabled={!model}>
              <option value="">{model ? "Select variant" : "Select model first"}</option>
              {variants.map((v) => (
                <option key={v.priceId || v.variant} value={v.variant}>
                  {v.variant}{v.inYard ? ` · ${v.inYard} in yard` : ""}
                </option>
              ))}
              {variant && !variants.some((v) => v.variant === variant) ? <option value={variant}>{variant}</option> : null}
            </Select>
          </Field>
          <Field label="Customer type">
            <Select data-testid="book-customer-type" value={customerType} onChange={(e) => setCustomerType(e.target.value)}>
              <option>Individual</option>
              <option value="B2B">B2B</option>
            </Select>
          </Field>
        </div>
        {!priceFound && model && variant && !dealLoading && (
          <div className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="price-error">
            Price Master entry not found for {model} / {variant}. Select a valid vehicle or update Price Master.
          </div>
        )}
        <DealFormatCard
          snapshot={deal}
          cxDemand={budget}
          onCxDemand={setBudget}
          loading={dealLoading}
          missingPrice={!model || !variant}
          showOwnerPnl={!!canSeeOwnerCommercials}
          hideScheme={hideScheme}
          passOn={hideScheme ? {} : passOn}
          onPrint={printDealSheet}
          printBusy={busy}
          onPassOn={hideScheme ? undefined : (key, yes, available) => {
            setPassOn((p) => ({ ...p, [key]: yes }));
            setBudget((cur) => {
              const n = Number(cur) || Number(deal?.netToCx) || 0;
              const delta = yes ? -(Number(available) || 0) : (Number(available) || 0);
              return Math.max(0, n + delta);
            });
          }}
        />
        <Field label="OEM Extra Support">
          <Input data-testid="book-oem-extra" type="number" min="0" step="1"
            value={oemExtra} onChange={(e) => setOemExtra(e.target.value)} />
        </Field>
        <LocalOemExtraBlock files={extraProof} setFiles={setExtraProof} amount={oemExtra} existingDocs={docs} />
        {needsApproval && (
          <LocalDealSheetBlock files={dealSheet} setFiles={setDealSheet} existingDocs={docs}
            onPrint={printDealSheet} printBusy={busy} />
        )}
        <LocalKycBlock customerType={customerType} files={kyc} setFiles={setKyc} gstin={gstin} onGstin={setGstin} />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Booking Date"><Input data-testid="booking-date" type="date" value={form.bookingDate} onChange={setPay("bookingDate")} /></Field>
          <Field label="Booking advance (₹)">
            <Input data-testid="booking-amount" type="number" min="0" value={form.bookingAmount} onChange={setPay("bookingAmount")} />
          </Field>
          <p className="sm:col-span-2 text-xs text-ink-soft -mt-1">
            Use 0 when the customer pays the full amount with no separate booking advance.
          </p>
          <Field label="Payment Mode">
            <Select data-testid="booking-payment-mode" value={form.paymentMode} onChange={setPay("paymentMode")}>
              {["Cash", "UPI", "Cheque", "NEFT", "Card"].map((m) => <option key={m}>{m}</option>)}
            </Select>
          </Field>
          <Field label={paymentRefLabel(form.paymentMode)}>
            <Input data-testid="booking-payment-ref" value={form.paymentReference} onChange={setPay("paymentReference")}
              placeholder={form.paymentMode === "Cheque" ? "Cheque number" : "UTR / transaction number"} />
          </Field>
          <Field label="Finance Required"><Select value={form.financeRequired} onChange={setPay("financeRequired")}><option>No</option><option>Yes</option></Select></Field>
          <Field label="Exchange Required"><Select value={form.exchangeRequired} onChange={setPay("exchangeRequired")}><option>No</option><option>Yes</option></Select></Field>
        </div>
      </div>
    </Drawer>
  );
}
