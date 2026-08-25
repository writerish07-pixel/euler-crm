import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { ArrowRightLeft, Wallet, XCircle, Pencil, Trash2, Printer, FileText } from "lucide-react";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { Drawer, Modal, Tabs, Badge, Button, Field, Input, Select, Card } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import LeadWhatsApp from "./LeadWhatsApp";

const CHARGE_FIELDS = [
  ["exShowroom", "Ex-Showroom"], ["rto", "RTO"], ["insuranceAmount", "Insurance"],
  ["accessoriesAmount", "Accessories"], ["handlingCharges", "Handling"], ["trc", "TRC"],
  ["fastag", "Fastag"], ["extendedWarranty", "Ext. Warranty"], ["rsaAmc", "RSA / AMC"], ["otherCharges", "Other"],
];
const SCHEME_FIELDS = [
  ["consumerDiscount", "Consumer Discount"], ["exchangeBonus", "Exchange Bonus"],
  ["loyaltyBonus", "Loyalty Bonus"], ["referralBonus", "Referral Bonus"],
  ["dsaDiscount", "DSA Bonus"], ["additionalDiscount", "Additional (Dealer)"],
];

export default function LeadDrawer({ leadId, masters, onClose, onChanged }) {
  const { isOwner, isField } = useAuth();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [tab, setTab] = useState("overview");
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    setLoadError(null);
    get(`/leads/${leadId}/360`)
      .then(setData)
      .catch((e) => {
        const msg = e?.response?.data?.detail || e?.message || "Failed to load lead";
        setLoadError(typeof msg === "string" ? msg : "Failed to load lead");
        toast.error("Could not open this lead");
      });
  }, [leadId]);
  useEffect(() => { load(); }, [load]);

  const refresh = useCallback(() => { load(); onChanged && onChanged(); }, [load, onChanged]);
  const advance = useCallback((nextTab) => {
    refresh();
    if (nextTab) setTab(nextTab);
  }, [refresh]);

  if (loadError && !data) {
    return (
      <Drawer open onClose={onClose} title="Lead">
        <div className="space-y-3 text-sm">
          <p className="text-ink-soft">{loadError}</p>
          <div className="flex gap-2">
            <Button onClick={load}>Retry</Button>
            <Button variant="ghost" onClick={onClose}>Close</Button>
          </div>
        </div>
      </Drawer>
    );
  }
  if (!data) return <Drawer open onClose={onClose} title="Loading…"><div className="text-ink-faint text-sm">Fetching lead…</div></Drawer>;

  const lead = data.lead;
  const c = data.commercials;
  const actions = data.actions || {};
  const fieldView = isField || !!data.fieldView || !!actions.fieldView;
  const leadLocked = !!actions.isLocked || !actions.isActive;

  const tabs = fieldView
    ? [
        { key: "overview", label: "Overview" },
        { key: "delivery", label: "Delivery" },
        { key: "activity", label: `Activity (${(data.activities || []).length})` },
      ]
    : [
        { key: "overview", label: "Overview" },
        { key: "whatsapp", label: `WhatsApp${data.whatsapp?.count ? ` (${data.whatsapp.count})` : ""}` },
        { key: "price", label: "Price Structure" },
        { key: "scheme", label: "Scheme" },
        { key: "payments", label: `Payments (${data.payments.length})` },
        { key: "delivery", label: "Delivery" },
        ...(isOwner ? [{ key: "insurance", label: "Insurance" }] : []),
        { key: "activity", label: `Activity (${data.activities.length})` },
      ];

  return (
    <Drawer open onClose={onClose} width="max-w-3xl"
      title={lead.customerName}
      subtitle={`${lead.leadId} · ${lead.interestedModel} ${lead.variant} · ${lead.mobile}`}
      footer={fieldView
        ? <div className="flex items-center gap-2 text-sm text-ink-soft">
            {(!actions.isActive || String(lead.accountStatus || "").toLowerCase() === "closed")
              ? <Badge data-testid="close-won-badge" tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">Close Won</Badge>
              : (
                <>
                  {actions.isBooked && <Badge data-testid="already-booked-badge">Booked ✓</Badge>}
                  {actions.isDelivered && <Badge data-testid="already-delivered-badge">Delivered ✓</Badge>}
                </>
              )}
            <span className="ml-auto text-xs">Field view · pipeline only</span>
          </div>
        : <DrawerActions lead={lead} actions={actions} refresh={refresh} onClose={onClose} onBooked={() => advance("price")} />}
    >
      <div className="flex items-center gap-2 mb-4">
        <Badge>{lead.currentStatus}</Badge>
        <Badge>{lead.accountStatus}</Badge>
        {leadLocked && <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20" data-testid="lead-locked-badge">Locked</Badge>}
        {!fieldView && !leadLocked && (
          <Button variant="secondary" data-testid="edit-lead-btn" onClick={() => setEditing(true)} className="!py-1 !px-2.5 text-xs"><Pencil size={13} /> Edit</Button>
        )}
        {!fieldView && isOwner && (
          <Button variant="secondary" data-testid="delete-lead-btn"
            onClick={async () => {
              if (!window.confirm(`Permanently DELETE lead ${lead.leadId} (${lead.customerName}) and all its bookings, payments, claims, insurance & delivery records? This cannot be undone.`)) return;
              try {
                await del(`/leads/${lead.leadId}`);
                toast.success(`Lead ${lead.leadId} deleted`);
                onClose();
                onChanged && onChanged();
              } catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
            }}
            className="!py-1 !px-2.5 text-xs !text-red-600 hover:!bg-red-50"><Trash2 size={13} /> Delete</Button>
        )}
        {!fieldView && (
          <div className="ml-auto text-right">
            <div className="text-xs text-ink-faint">Outstanding</div>
            <div className={`font-mono font-bold ${lead.customerOutstanding > 0 ? "text-red-600" : "text-emerald-600"}`}>{inr(lead.customerOutstanding)}</div>
          </div>
        )}
      </div>

      {editing && !leadLocked && !fieldView && (
        <EditLeadModal
          lead={lead}
          masters={masters}
          isOwner={isOwner}
          actions={actions}
          onClose={() => setEditing(false)}
          onSaved={(opts) => {
            setEditing(false);
            if (opts?.vehicleChanged) advance("price");
            else refresh();
          }}
        />
      )}

      {fieldView && (
        <StepLock text="ASM / RM field view — pipeline status only. Commercial amounts, payments and claims are hidden." />
      )}

      {!fieldView && leadLocked && (
        <StepLock text="This lead is Closed — commercial steps are locked. Active leads (including Delivered) can still be edited by the owner." />
      )}

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === "overview" && (fieldView
        ? <FieldOverview lead={lead} booking={data.booking} delivery={data.delivery} />
        : <Overview lead={lead} c={c} actions={actions} onSaved={refresh} />)}
      {!fieldView && tab === "price" && <PriceStructure lead={lead} actions={actions} isOwner={isOwner} onSaved={() => advance("scheme")} />}
      {!fieldView && tab === "scheme" && <SchemeTab lead={lead} c={c} actions={actions} isOwner={isOwner} masters={masters} onSaved={() => advance("payments")} onRefresh={refresh} />}
      {!fieldView && tab === "payments" && <PaymentsTab lead={lead} actions={actions} payments={data.payments} masters={masters} isOwner={isOwner} onSaved={refresh} />}
      {tab === "delivery" && (
        fieldView
          ? <FieldDeliveryReadOnly delivery={data.delivery} lead={lead} />
          : (
            <DeliveryTab
              lead={lead}
              actions={actions}
              isOwner={isOwner}
              delivery={data.delivery}
              billingSummary={data.billingSummary}
              onSaved={refresh}
            />
          )
      )}
      {!fieldView && tab === "insurance" && isOwner && <InsuranceTab lead={lead} masters={masters} />}
      {!fieldView && tab === "whatsapp" && <LeadWhatsApp leadId={lead.leadId} />}
      {tab === "activity" && <ActivityTab lead={lead} activities={data.activities} masters={masters} onSaved={refresh} readOnly={fieldView} />}
    </Drawer>
  );
}

function FieldOverview({ lead, booking, delivery }) {
  return (
    <div className="grid grid-cols-1 gap-5" data-testid="field-lead-overview">
      <Card className="p-4">
        <h4 className="font-heading font-bold text-ink text-sm mb-2">Pipeline</h4>
        <div className="grid grid-cols-2 gap-x-6">
          <KV label="Executive" value={lead.executive || "—"} />
          <KV label="Priority" value={lead.priority || "—"} />
          <KV label="Lead Source" value={lead.leadSource || "—"} />
          <KV label="Status" value={lead.currentStatus || "—"} />
          <KV label="Created" value={fmtDate(lead.createdDate)} />
          <KV label="Next Follow-up" value={fmtDate(lead.nextFollowupDate || lead.nextFollowup)} />
          <KV label="Booking Date" value={fmtDate(lead.bookingDate || booking?.bookingDate)} />
          <KV label="Delivery Date" value={fmtDate(lead.deliveryDate || delivery?.deliveryDate)} />
          <KV label="Finance Required" value={lead.financeRequired || "—"} />
          <KV label="Exchange" value={lead.exchangeRequired || "—"} />
        </div>
        {lead.remarks && <div className="mt-2 text-sm text-ink-soft bg-zinc-50 rounded-lg p-3">{lead.remarks}</div>}
      </Card>
    </div>
  );
}

function FieldDeliveryReadOnly({ delivery, lead }) {
  return (
    <Card className="p-4" data-testid="field-delivery-readonly">
      <h4 className="font-heading font-bold text-ink text-sm mb-2">Delivery status</h4>
      <div className="grid grid-cols-2 gap-x-6">
        <KV label="Status" value={lead.deliveryStatus || lead.currentStatus || "—"} />
        <KV label="Delivery Date" value={fmtDate(lead.deliveryDate || delivery?.deliveryDate)} />
        <KV label="Invoice" value={delivery?.invoiceNumber || lead.invoiceNumber || "—"} />
        <KV label="Chassis" value={delivery?.chassisNumber || "—"} />
        <KV label="Engine" value={delivery?.engineNumber || "—"} />
        <KV label="RC Status" value={delivery?.rcStatus || "—"} />
      </div>
    </Card>
  );
}

function StepLock({ text }) {
  return <div data-testid="step-lock-notice" className="mb-3 flex items-center gap-2 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">{text}</div>;
}

function DrawerActions({ lead, actions, refresh, onClose, onBooked }) {
  const [modal, setModal] = useState(null);
  const closed = !actions.isActive || String(lead.accountStatus || "").toLowerCase() === "closed";
  return (
    <div className="flex flex-wrap items-center gap-2">
      {closed && <Badge data-testid="close-won-badge" tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">Close Won</Badge>}
      {!closed && actions.canBook && <Button data-testid="convert-booking-btn" onClick={() => setModal("book")}><ArrowRightLeft size={15} /> Convert to Booking</Button>}
      {!closed && actions.isBooked && !actions.canBook && <Badge data-testid="already-booked-badge">Booked ✓</Badge>}
      {!closed && actions.isDelivered && <Badge data-testid="already-delivered-badge">Delivered ✓</Badge>}
      {actions.canClose && (
        <Button variant="secondary" data-testid="close-lead-btn" onClick={() => setModal("close")}><XCircle size={15} /> Close Lead</Button>
      )}
      <div className="w-full sm:w-auto sm:ml-auto text-sm text-ink-soft">Payable <span className="font-mono font-semibold text-ink">{inr(lead.customerPayable)}</span></div>
      {modal === "book" && <BookingModal lead={lead} onClose={() => setModal(null)} onDone={() => { setModal(null); (onBooked || refresh)(); }} />}
      {modal === "close" && <CloseModal lead={lead} onClose={() => setModal(null)} onDone={() => { setModal(null); refresh(); onClose(); }} />}
    </div>
  );
}

/** Company-kept retained preview (matches commercial.compute_scheme_allocation). */
function companyKeptRetained(oemShare, customerBenefit) {
  const oem = Math.max(0, Number(oemShare) || 0);
  const cb = Math.max(0, Number(customerBenefit) || 0);
  return Math.max(0, oem - Math.min(oem, cb));
}

/* -------------------------------------------------- Overview */
function KV({ label, value, tone }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-zinc-100 last:border-0">
      <span className="text-sm text-ink-soft">{label}</span>
      <span className={`font-mono tabular text-sm font-medium ${tone || "text-ink"}`}>{value}</span>
    </div>
  );
}

function Overview({ lead, c, actions = {}, onSaved }) {
  const booked = !!actions.isBooked;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
      <Card className="p-4">
        <h4 className="font-heading font-bold text-ink text-sm mb-2">Commercial Breakup</h4>
        <KV label="Gross Vehicle Cost" value={inr(c.grossVehicleCost)} />
        <KV label="TCS" value={inr(c.tcs)} />
        <KV label="Total Discount" value={inr(c.totalDiscount)} tone="text-emerald-600" />
        <KV label="Passed to Customer" value={inr(c.totalPassedToCustomer)} />
        <KV label="Final Exchange Value" value={inr(lead.finalExchangeValue || 0)} />
        <div className="mt-2 pt-2 border-t border-line flex items-center justify-between">
          <span className="text-sm font-semibold text-ink">Customer Payable</span>
          <span className="font-mono font-bold text-cobalt">{inr(c.customerPayable)}</span>
        </div>
      </Card>
      <Card className="p-4">
        <h4 className="font-heading font-bold text-ink text-sm mb-2">Collections & Claims</h4>
        <KV label="Total Received" value={inr(lead.totalReceived)} tone="text-emerald-600" />
        <KV label="Customer Outstanding" value={inr(lead.customerOutstanding)} tone={lead.customerOutstanding > 0 ? "text-red-600" : "text-emerald-600"} />
        <KV label="OEM Claimable (Company Share)" value={inr(c.oemClaimCompanyShare ?? c.claim.claimEligible)} tone="text-amber-600" />
        <KV label="OEM Extra Support Received" value={inr(lead.oemExtraSupportReceived || c.oemExtraSupport?.oemExtraSupportReceived || 0)} tone="text-amber-600" />
        <KV label="OEM Extra Support Passed" value={inr(lead.oemExtraSupportPassed || c.oemExtraSupport?.oemExtraSupportPassed || 0)} />
        <KV label="OEM Extra Support Retained" value={inr(lead.oemExtraSupportRetained || c.oemExtraSupport?.oemExtraSupportRetained || 0)} tone="text-emerald-600" />
        <KV label="Dealer Scheme Retained" value={inr(c.dealerSchemeRetained ?? c.dealerRetained)} />
        <KV label="Dealer-Funded Benefit" value={inr(c.dealerFundedBenefit ?? lead.dealerFundedBenefit ?? 0)} tone="text-rose-600" />
        <KV label="Dealer Margin (Net)" value={inr(c.margin.marginNetExGst)} />
        <KV label="Lead Source" value={lead.leadSource || "—"} tone="text-ink" />
      </Card>
      <Card className="p-4 sm:col-span-2">
        <h4 className="font-heading font-bold text-ink text-sm mb-2">Details</h4>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6">
          <KV label="Executive" value={lead.executive || "—"} />
          <KV label="Priority" value={lead.priority} />
          <KV label="Created" value={fmtDate(lead.createdDate)} />
          <KV label="Booking Date" value={fmtDate(lead.bookingDate)} />
          <KV label="Finance" value={lead.financeRequired} />
          <KV label="Exchange" value={lead.exchangeRequired} />
        </div>
        {lead.remarks && <div className="mt-2 text-sm text-ink-soft bg-zinc-50 rounded-lg p-3">{lead.remarks}</div>}
      </Card>
      {booked && (
        <div className="sm:col-span-2">
          <BookingConfirmSend leadId={lead.leadId} already={!!lead.whatsappBookingSentAt} onSent={onSaved} />
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------- Price Structure */
function PriceStructure({ lead, actions = {}, isOwner = false, onSaved }) {
  const inactive = !actions.canPrice;
  const staffLocked = !isOwner && !!actions.priceCompleted;
  const locked = inactive || staffLocked;
  const [priceDate, setPriceDate] = useState(lead.bookingDate || lead.createdDate || todayISO());
  const [masterMsg, setMasterMsg] = useState("");
  const [form, setForm] = useState(() => {
    const f = {
      tcsApplicable: lead.tcsApplicable || "No",
      finalExchangeValue: lead.finalExchangeValue || 0,
      insuranceArrangedBy: lead.insuranceArrangedBy === "self" ? "self" : "dealer",
    };
    CHARGE_FIELDS.forEach(([k]) => (f[k] = lead[k] || 0));
    return f;
  });
  const [preview, setPreview] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  // Ex-Showroom is locked to Price Master for the lead's model/variant.
  useEffect(() => {
    let alive = true;
    get(`/leads/${lead.leadId}/price-preview`)
      .then((d) => {
        if (!alive) return;
        if (d?.found && d.priceStructure) {
          setForm((f) => ({ ...f, exShowroom: d.priceStructure.exShowroom || 0 }));
          setMasterMsg("Ex-Showroom is fixed from Price Master and cannot be edited.");
        } else {
          setMasterMsg(d?.message || "Price Master entry not found — select a valid model/variant.");
        }
      })
      .catch(() => { if (alive) setMasterMsg("Could not load Price Master for this vehicle."); });
    return () => { alive = false; };
  }, [lead.leadId, lead.interestedModel, lead.variant]);

  const computePreview = useCallback(() => {
    post("/commercial/compute", {
      exShowroom: +form.exShowroom, accessories: +form.accessoriesAmount, insurance: +form.insuranceAmount,
      insuranceArrangedBy: form.insuranceArrangedBy,
      registrationRto: +form.rto, fastag: +form.fastag, handlingCharges: +form.handlingCharges, trc: +form.trc,
      extendedWarranty: +form.extendedWarranty, otherCharges: +form.otherCharges,
      rsaAmc: +form.rsaAmc,
      tcsApplicable: form.tcsApplicable, finalExchangeValue: +form.finalExchangeValue,
      consumerDiscount: lead.consumerDiscount, exchangeBonus: lead.exchangeBonus, loyaltyBonus: lead.loyaltyBonus,
      referralBonus: lead.referralBonus, dsaDiscount: lead.dsaDiscount, additionalDiscount: lead.additionalDiscount,
      benefitMode: lead.benefitMode || "Full Benefit",
    }).then(setPreview);
  }, [form, lead]);
  useEffect(() => { computePreview(); }, [computePreview]);

  const save = async () => {
    if (!priceDate) return toast.error("Price date is required");
    if (!(+form.exShowroom > 0)) return toast.error("Ex-Showroom from Price Master is required");
    try {
      await put(`/leads/${lead.leadId}/price-structure`, {
        exShowroom: +form.exShowroom, rto: +form.rto, insuranceAmount: +form.insuranceAmount,
        insuranceArrangedBy: form.insuranceArrangedBy === "self" ? "self" : "dealer",
        accessoriesAmount: +form.accessoriesAmount, handlingCharges: +form.handlingCharges, trc: +form.trc,
        fastag: +form.fastag, extendedWarranty: +form.extendedWarranty, otherCharges: +form.otherCharges,
        rsaAmc: +form.rsaAmc,
        tcsApplicable: form.tcsApplicable, finalExchangeValue: +form.finalExchangeValue,
      });
      toast.success("Price structure saved — continue with Scheme");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Price save failed");
    }
  };

  return (
    <div>
      {inactive && <StepLock text="This lead is not Active — price structure is read-only." />}
      {!inactive && staffLocked && <StepLock text="Price structure is saved. Only the owner can edit a completed step." />}
      {masterMsg && <p className="text-xs text-ink-soft mb-3" data-testid="exshowroom-lock-note">{masterMsg}</p>}
      <div className="grid grid-cols-3 gap-3">
        <Field label="Price Date"><Input data-testid="price-date" type="date" value={priceDate} onChange={(e) => setPriceDate(e.target.value)} disabled={locked} /></Field>
        {CHARGE_FIELDS.map(([k, label]) => (
          <Field key={k} label={label}>
            <Input
              data-testid={`price-${k}`}
              type="number"
              value={form[k]}
              onChange={set(k)}
              disabled={locked || k === "exShowroom"}
              readOnly={k === "exShowroom"}
            />
          </Field>
        ))}
        <Field label="Insurance arranged by">
          <Select
            data-testid="price-insuranceArrangedBy"
            value={form.insuranceArrangedBy}
            onChange={set("insuranceArrangedBy")}
            disabled={locked}
          >
            <option value="dealer">Dealer</option>
            <option value="self">Self (customer)</option>
          </Select>
        </Field>
        <Field label="Final Exchange Value"><Input type="number" value={form.finalExchangeValue} onChange={set("finalExchangeValue")} disabled={locked} /></Field>
        <Field label="TCS Applicable"><Select value={form.tcsApplicable} onChange={set("tcsApplicable")} disabled={locked}><option>No</option><option>Yes</option></Select></Field>
      </div>
      {form.insuranceArrangedBy === "self" && (
        <p className="text-xs text-ink-soft mt-2" data-testid="insurance-self-note">
          Self insurance: premium is not added to customer outstanding, and there is no dealer insurance payout earning.
        </p>
      )}
      {preview && (
        <Card className="p-4 mt-4 bg-cobalt-tint/40 border-cobalt/20">
          <div className="grid grid-cols-4 gap-3 text-center">
            <Prev label="Gross Vehicle Cost" v={preview.grossVehicleCost} />
            <Prev label="TCS" v={preview.tcs} />
            <Prev label="Total Discount" v={preview.totalDiscount} />
            <Prev label="Customer Payable" v={preview.customerPayable} highlight />
          </div>
        </Card>
      )}
      <div className="flex justify-end mt-4">
        <Button data-testid="save-price-btn" onClick={save} disabled={locked}>Save Price Structure</Button>
      </div>
    </div>
  );
}

function Prev({ label, v, highlight }) {
  return (
    <div>
      <div className="text-[11px] text-ink-faint uppercase tracking-wide">{label}</div>
      <div className={`font-mono font-bold ${highlight ? "text-cobalt text-lg" : "text-ink"}`}>{inr(v)}</div>
    </div>
  );
}

/* -------------------------------------------------- Scheme */
function SchemeTab({ lead, c, actions = {}, isOwner = false, masters, onSaved, onRefresh }) {
  const inactive = !actions.canScheme;
  const staffLocked = !isOwner && !!actions.schemeCompleted;
  const locked = inactive || staffLocked;
  const [rules, setRules] = useState(null);
  const [schemeDate, setSchemeDate] = useState(lead.bookingDate || todayISO());
  const [form, setForm] = useState(() => ({
    oemExtraSupportReceived: lead.oemExtraSupportReceived || 0,
    oemExtraSupportPassed: lead.oemExtraSupportPassed || 0,
    additionalDiscount: lead.additionalDiscount || 0,
  }));
  const [breakup, setBreakup] = useState(() => {
    try { return lead.benefitPassedBreakup ? JSON.parse(lead.benefitPassedBreakup) : {}; }
    catch { return {}; }
  });
  const [usedMap, setUsedMap] = useState(() => {
    try {
      if (lead.schemeComponentsUsed) return JSON.parse(lead.schemeComponentsUsed);
    } catch { /* ignore */ }
    // Historical: infer "used" from persisted customer benefit > 0. Never default to Yes.
    const inferred = {};
    try {
      const b = lead.benefitPassedBreakup ? JSON.parse(lead.benefitPassedBreakup) : {};
      Object.keys(b).forEach((k) => { inferred[k] = Number(b[k]) > 0; });
    } catch { /* ignore */ }
    return inferred;
  });

  useEffect(() => { get(`/leads/${lead.leadId}/scheme-rules`).then(setRules).catch(() => setRules({ rules: {} })); }, [lead.leadId]);
  useEffect(() => { setSchemeDate(lead.bookingDate || todayISO()); }, [lead.bookingDate]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const r = rules?.rules || {};
  const entitlements = rules?.entitlements || [];

  // Eligible components from Scheme Master only — same card for every component.
  // Eligibility ≠ assignment: default Use Scheme = No, Customer Benefit = 0.
  const components = [];
  SCHEME_FIELDS.forEach(([k, label]) => {
    if (k === "additionalDiscount") return;
    const rule = r[k];
    if (!rule || !rule.allowed) return;
    const avail = rule.schemeAvailable || rule.maxAmount || 0;
    if (!(avail > 0)) return;
    components.push({
      key: k, label,
      available: avail,
      oemShare: rule.oemShare ?? rule.companyShare ?? 0,
      dealerShare: rule.dealerFundedShare ?? rule.dealerShare ?? 0,
    });
  });
  entitlements.forEach((e) => {
    components.push({
      key: e.key, label: e.label,
      available: e.schemeAvailable ?? e.totalBenefit ?? 0,
      oemShare: e.oemShare ?? e.companyShare ?? 0,
      dealerShare: e.dealerFundedShare ?? e.dealerShare ?? 0,
    });
  });

  const hiddenFields = SCHEME_FIELDS.filter(([k]) => k !== "additionalDiscount" && r[k] && !r[k].allowed);

  const setUsed = (key, yes) => {
    setUsedMap((u) => ({ ...u, [key]: yes }));
    if (!yes) {
      setBreakup((b) => ({ ...b, [key]: 0 }));
    } else {
      // Do NOT auto-fill full available — dealer must enter Customer Benefit.
      setBreakup((b) => ({ ...b, [key]: b[key] !== undefined && b[key] !== "" ? b[key] : 0 }));
    }
  };

  const setCb = (key, avail) => (e) => {
    const raw = e.target.value;
    setUsedMap((u) => ({ ...u, [key]: true }));
    if (raw === "") {
      setBreakup((b) => ({ ...b, [key]: "" }));
      return;
    }
    const n = Math.max(0, Math.min(+raw || 0, avail));
    setBreakup((b) => ({ ...b, [key]: n }));
  };

  const save = async () => {
    const clean = {};
    const usedClean = {};
    components.forEach((comp) => {
      const isUsed = !!usedMap[comp.key];
      usedClean[comp.key] = isUsed;
      if (!isUsed) clean[comp.key] = 0;
      else clean[comp.key] = Math.max(0, Math.min(+(breakup[comp.key] ?? 0) || 0, comp.available));
    });
    const payload = {
      // Benefit Mode removed from UI — backend stores Partial for compatibility.
      benefitMode: "Partial Benefit",
      oemExtraSupportReceived: +form.oemExtraSupportReceived || 0,
      oemExtraSupportPassed: +form.oemExtraSupportPassed || 0,
      additionalDiscount: +form.additionalDiscount || 0,
      // Offer pools are filled by the backend from Scheme Master on explicit save.
      consumerDiscount: 0, exchangeBonus: 0, loyaltyBonus: 0, referralBonus: 0, dsaDiscount: 0,
      benefitPassedBreakup: JSON.stringify(clean),
      schemeComponentsUsed: JSON.stringify(usedClean),
      customerBenefitPassed: Object.values(clean).reduce((s, v) => s + (+v || 0), 0),
    };
    if (!schemeDate) return toast.error("Scheme date is required");
    try {
      // Only rewrite bookingDate after a real booking — never invent a booking via date alone.
      const alreadyBooked = Boolean(lead.bookingId || lead.bookingDate
        || ["booked", "finance process", "delivered"].includes(String(lead.currentStatus || "").toLowerCase()));
      if (alreadyBooked && schemeDate !== (lead.bookingDate || "")) {
        await put(`/leads/${lead.leadId}`, { bookingDate: schemeDate });
      }
      await put(`/leads/${lead.leadId}/scheme`, payload);
      toast.success("Scheme updated — continue with Payments");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Scheme validation failed");
    }
  };

  // Live preview totals from local decisions (backend remains SSOT on save).
  // Use=No ⇒ full opt-out (no CB / retained / OEM claim). Use=Yes ⇒ company-kept retained.
  const previewCb = components.reduce((s, comp) => {
    if (!usedMap[comp.key]) return s;
    return s + Math.max(0, Math.min(+(breakup[comp.key] ?? 0) || 0, comp.available));
  }, 0);
  const previewAvail = components.reduce((s, comp) => s + comp.available, 0);
  const previewRetained = components.reduce((s, comp) => {
    if (!usedMap[comp.key]) return s;
    const cb = Math.max(0, Math.min(+(breakup[comp.key] ?? 0) || 0, comp.available));
    return s + companyKeptRetained(comp.oemShare, cb);
  }, 0);
  const previewOem = components.reduce((s, comp) => (usedMap[comp.key] ? s + comp.oemShare : s), 0);
  const previewFunded = components.reduce((s, comp) => {
    if (!usedMap[comp.key]) return s;
    const cb = Math.max(0, Math.min(+(breakup[comp.key] ?? 0) || 0, comp.available));
    return s + Math.max(0, Math.min(comp.dealerShare, Math.max(0, cb - comp.oemShare)));
  }, 0);

  // OEM Extra Support (NOT Additional Dealer): Received = full OEM claim;
  // Passed ≤ Received reduces payable; Retained = Received − Passed → earnings.
  const oemRecv = Math.max(0, +form.oemExtraSupportReceived || 0);
  const oemPass = Math.max(0, Math.min(+form.oemExtraSupportPassed || 0, oemRecv));
  const oemRetained = Math.max(0, oemRecv - oemPass);
  const previewOemTotal = previewOem + oemRecv;

  return (
    <div>
      {inactive && <StepLock text="This lead is not Active — scheme is read-only." />}
      {!inactive && staffLocked && <StepLock text="Scheme is saved. Only the owner can edit a completed step." />}
      {rules && (
        <div className="text-xs text-ink-soft mb-3" data-testid="scheme-month-note">
          Scheme Master · <span className="font-semibold text-ink">{rules.model} {rules.variant}</span> · {rules.schemeMonth}
          <span className="text-ink-faint"> — eligible components only; dealer assigns each scheme</span>
          {components.length === 0 && <span className="text-amber-700"> — no scheme components for this model/variant this month</span>}
        </div>
      )}

      <div className="grid grid-cols-4 gap-3 mb-2">
        <Field label="Scheme Date">
          <Input data-testid="scheme-date" type="date" value={schemeDate} onChange={(e) => setSchemeDate(e.target.value)} disabled={locked} />
        </Field>
        <Field label="OEM Extra Support Received">
          <Input data-testid="oem-extra-received" type="number" value={form.oemExtraSupportReceived}
            onChange={set("oemExtraSupportReceived")} disabled={locked} />
        </Field>
        <Field label="OEM Extra Support Passed">
          <Input data-testid="oem-extra-passed" type="number" value={form.oemExtraSupportPassed}
            onChange={set("oemExtraSupportPassed")} disabled={locked} />
        </Field>
        <Field label="Additional (Dealer)">
          <Input data-testid="scheme-additionalDiscount" type="number" value={form.additionalDiscount} onChange={set("additionalDiscount")} disabled={locked} />
        </Field>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-4 text-sm" data-testid="oem-extra-support-preview">
        <div>
          <div className="text-[11px] text-ink-faint uppercase">OEM Extra Claim (full Received)</div>
          <div className="font-mono text-amber-700" data-testid="oem-extra-claim">{inr(oemRecv)}</div>
        </div>
        <div>
          <div className="text-[11px] text-ink-faint uppercase">OEM Extra Retained (earnings)</div>
          <div className="font-mono text-emerald-700" data-testid="oem-extra-retained">{inr(oemRetained)}</div>
        </div>
        <div className="text-[11px] text-ink-faint self-end">
          Passed comes from Received only. Additional (Dealer) is your margin discount — separate.
        </div>
      </div>
      {hiddenFields.length > 0 && (
        <div className="text-[11px] text-ink-faint mb-3" data-testid="scheme-unavailable-note">
          Not available for this model/variant: {hiddenFields.map(([, l]) => l).join(", ")}
        </div>
      )}

      <div className="text-xs font-semibold text-ink mb-2">
        Scheme allocation — Scheme Master sets eligibility; dealer decides Use Scheme and Customer Benefit
      </div>
      <div className="space-y-3" data-testid="scheme-components">
        {components.map((comp) => {
          const isUsed = !!usedMap[comp.key];
          const cb = !isUsed ? 0 : Math.max(0, Math.min(+(breakup[comp.key] ?? 0) || 0, comp.available));
          // Live local math while editing so Use=No never shows a stale OEM claim.
          const retained = isUsed ? companyKeptRetained(comp.oemShare, cb) : 0;
          const oemClaim = isUsed ? comp.oemShare : 0;
          return (
            <Card key={comp.key} className="p-4 bg-zinc-50/80 border-line" data-testid={`scheme-component-${comp.key}`}>
              <div className="text-sm font-semibold text-ink mb-3">{comp.label}</div>
              <div className="grid grid-cols-3 gap-3 text-sm mb-3">
                <div>
                  <div className="text-[11px] text-ink-faint uppercase">Available</div>
                  <div className="font-mono" data-testid={`avail-${comp.key}`}>{inr(comp.available)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-ink-faint uppercase">OEM Share</div>
                  <div className="font-mono">{inr(comp.oemShare)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-ink-faint uppercase">Dealer Share</div>
                  <div className="font-mono">{inr(comp.dealerShare)}</div>
                </div>
              </div>
              <div className="flex items-center gap-3 mb-3" data-testid={`use-scheme-${comp.key}`}>
                <div className="text-[11px] text-ink-faint uppercase min-w-[6.5rem]">Use this scheme?</div>
                <label className="flex items-center gap-1.5 text-sm">
                  <input type="radio" name={`use-${comp.key}`} data-testid={`use-no-${comp.key}`}
                    checked={!isUsed} disabled={locked}
                    onChange={() => setUsed(comp.key, false)} />
                  No
                </label>
                <label className="flex items-center gap-1.5 text-sm">
                  <input type="radio" name={`use-${comp.key}`} data-testid={`use-yes-${comp.key}`}
                    checked={isUsed} disabled={locked}
                    onChange={() => setUsed(comp.key, true)} />
                  Yes
                </label>
              </div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                {isUsed ? (
                  <Field label="Customer Benefit">
                    <Input data-testid={`breakup-${comp.key}`} type="number" min={0} max={comp.available}
                      value={breakup[comp.key] ?? 0}
                      onChange={setCb(comp.key, comp.available)}
                      disabled={locked} />
                  </Field>
                ) : (
                  <div>
                    <div className="text-[11px] text-ink-faint uppercase">Customer Benefit</div>
                    <div className="font-mono" data-testid={`breakup-${comp.key}`}>{inr(0)}</div>
                  </div>
                )}
                <div>
                  <div className="text-[11px] text-ink-faint uppercase">Dealer Retained</div>
                  <div className="font-mono font-semibold text-emerald-700" data-testid={`retained-${comp.key}`}>{inr(retained)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-ink-faint uppercase">OEM Claim</div>
                  <div className="font-mono text-amber-700" data-testid={`oem-claim-${comp.key}`}>{inr(oemClaim)}</div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <Card className="p-4 mt-4 bg-amber-50/50 border-amber-200" data-testid="scheme-allocation-summary">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
          <Prev label="Customer Benefit" v={previewCb} />
          <Prev label="Dealer Scheme Retained" v={previewRetained} />
          <Prev label="OEM Claimable" v={previewOemTotal} />
          <Prev label="Dealer-Funded Benefit" v={previewFunded} />
          <Prev label="Scheme Available" v={previewAvail} />
        </div>
        <div className="text-[11px] text-ink-faint text-center mt-2">
          Summary follows Use Scheme = Yes only. Save to persist on the lead.
        </div>
      </Card>
      <ExtraIncomeCard lead={lead} locked={locked} onSaved={onRefresh || onSaved} />
      <div className="flex justify-end mt-4"><Button data-testid="save-scheme-btn" onClick={save} disabled={locked}>Update Scheme</Button></div>
    </div>
  );
}

const EXTRA_INCOME_FIELDS = [
  ["documentationIncome", "Documentation"], ["warrantyIncome", "Warranty"],
  ["rsaIncome", "RSA"], ["referralIncome", "Referral"],
  ["otherIncome", "Other Income"],
  ["customerInsuranceBenefitPassed", "Cust. Ins. Benefit Passed (from scheme alloc; not earnings)"],
  ["financeIncentive", "Finance Incentive"], ["accessoriesMargin", "Accessories Margin"],
  ["exchangeMargin", "Exchange Margin"], ["campaignIncentive", "Campaign Incentive"],
];
function ExtraIncomeCard({ lead, locked, onSaved }) {
  const [form, setForm] = useState(() => {
    const f = {};
    EXTRA_INCOME_FIELDS.forEach(([k]) => (f[k] = lead[k] || 0));
    return f;
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  // customerInsuranceBenefitPassed is customer discount memo — exclude from earnings total.
  const total = EXTRA_INCOME_FIELDS.reduce(
    (s, [k]) => s + (k === "customerInsuranceBenefitPassed" ? 0 : (Number(form[k]) || 0)), 0);
  const save = async () => {
    try {
      const payload = {};
      EXTRA_INCOME_FIELDS.forEach(([k]) => (payload[k] = +form[k] || 0));
      await put(`/leads/${lead.leadId}/extra-income`, payload);
      toast.success("Dealer extra income saved");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };
  return (
    <Card className="p-4 mt-4 bg-emerald-50/40 border-emerald-200" data-testid="extra-income-card">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-semibold text-ink">Dealer Extra Income (folds into Dealer Earnings)</div>
        <div className="text-xs text-ink-soft">Total <span className="font-mono font-semibold text-emerald-700">{inr(total)}</span></div>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {EXTRA_INCOME_FIELDS.map(([k, label]) => (
          <Field key={k} label={label}>
            <Input data-testid={`extra-${k}`} type="number" value={form[k]} onChange={set(k)} disabled={locked} />
          </Field>
        ))}
      </div>
      <div className="flex justify-end mt-3">
        <Button variant="secondary" data-testid="save-extra-income-btn" onClick={save} disabled={locked} className="!py-1 !px-3 text-xs">Save Extra Income</Button>
      </div>
    </Card>
  );
}

/* -------------------------------------------------- Payments */
function PaymentsTab({ lead, actions = {}, payments, masters, isOwner = false, onSaved }) {
  const [form, setForm] = useState({ amount: "", paymentMode: "Cash", narration: "", financerName: "", financeFileNumber: "", date: todayISO() });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const isFinance = form.paymentMode === "Finance";
  const locked = isFinance ? !actions.canFinanceReceipt : !actions.canPayment;
  const excess = +(lead.excessReceived || 0);
  const refunded = +(lead.refundedAmount || 0);
  const add = async (allowExcess = false) => {
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    if (!form.date) return toast.error("Payment date is required");
    // The backend requires a financer on Finance receipts (it is what resolves/creates the
    // finance file). Ask for it here so staff get a clear prompt instead of a raw 422.
    if (isFinance && !form.financerName) return toast.error("Select a Financer for a Finance receipt");
    try {
      const saved = await post(`/leads/${lead.leadId}/payments`, { ...form, amount: +form.amount, allowExcess });
      const file = saved?.financeFileNumber ? ` · Finance File ${saved.financeFileNumber}` : "";
      toast.success(`Receipt added · ${inr(+form.amount)}${file}`);
      setForm({ amount: "", paymentMode: "Cash", narration: "", financerName: "", financeFileNumber: "", date: todayISO() });
      onSaved();
    } catch (e) {
      const detail = e?.response?.data?.detail || "Could not add receipt";
      // Over-payment is allowed, but only once staff confirm it is deliberate.
      if (!allowExcess && /excess payment/i.test(detail)) {
        if (window.confirm(`${detail}\n\nRecord ₹${+form.amount} anyway and hold the surplus as excess?`)) {
          return add(true);
        }
        return undefined;
      }
      toast.error(detail);
    }
    return undefined;
  };
  const remove = async (p) => {
    const label = p.entryType === "Refund" ? "refund" : "receipt";
    if (!window.confirm(`Permanently delete ${label} ${p.receiptNumber} (${inr(p.amount)})? This cannot be undone. Lead totals will be recalculated.`)) return;
    try {
      await del(`/payments/${p.receiptNumber}`);
      toast.success(`${p.receiptNumber} deleted`);
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };
  return (
    <div>
      {locked && <StepLock text={isFinance ? "This lead is archived — no receipts allowed." : "This lead is not Active — only Finance receipts are allowed."} />}
      {(excess > 0 || refunded > 0) && (
        <Card className="p-4 mb-4 border-amber-200 bg-amber-50/60" data-testid="excess-panel">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-ink">
                Excess held: <span className="font-mono text-amber-700">{inr(excess)}</span>
              </div>
              <div className="text-xs text-ink-soft mt-0.5">
                {refunded > 0 ? `${inr(refunded)} already refunded · ` : ""}
                Money collected above Customer Payable. Refundable even after delivery or closure.
              </div>
            </div>
          </div>
          {excess > 0 && <RefundForm lead={lead} excess={excess} onSaved={onSaved} />}
        </Card>
      )}
      <Card className="p-4 mb-4">
        <div className="grid grid-cols-5 gap-3 items-end">
          <Field label="Amount (₹)"><Input data-testid="payment-amount" type="number" value={form.amount} onChange={set("amount")} /></Field>
          <Field label="Date"><Input data-testid="payment-date" type="date" value={form.date} onChange={set("date")} /></Field>
          <Field label="Mode"><Select data-testid="payment-mode" value={form.paymentMode} onChange={set("paymentMode")}>{(masters?.paymentModes || []).map((m) => <option key={m}>{m}</option>)}</Select></Field>
          <Field label="Narration"><Input value={form.narration} onChange={set("narration")} /></Field>
          <Button data-testid="add-payment-btn" onClick={() => add(false)} disabled={locked}><Wallet size={15} /> Add Receipt</Button>
        </div>
        {form.paymentMode === "Finance" && (
          <div className="grid grid-cols-2 gap-3 mt-3">
            <Field label="Financer"><Select value={form.financerName} onChange={set("financerName")}><option value="">—</option>{(masters?.financers || []).map((f) => <option key={f}>{f}</option>)}</Select></Field>
            <Field label="Finance File Number"><Input value={form.financeFileNumber} onChange={set("financeFileNumber")} placeholder="Auto-generated on save" /></Field>
          </div>
        )}
      </Card>
      <div className="space-y-2">
        {payments.length === 0 && <div className="text-sm text-ink-faint text-center py-6">No payments recorded yet</div>}
        {payments.map((p) => {
          const isRefund = p.entryType === "Refund";
          return (
            <div key={p.receiptNumber} className={`flex items-center justify-between border rounded-lg px-4 py-2.5 ${isRefund ? "border-amber-200 bg-amber-50/50" : "border-line bg-white"}`}>
              <div>
                <div className={`text-sm font-semibold ${isRefund ? "text-amber-700" : "text-ink"}`}>
                  {inr(p.amount)}
                  <Badge className="ml-1">{isRefund ? "Refund" : p.paymentMode}</Badge>
                  {isRefund && p.paymentMode ? <span className="text-xs text-ink-faint ml-1">via {p.paymentMode}</span> : null}
                </div>
                <div className="text-xs text-ink-faint">{p.receiptNumber} · {fmtDate(p.date)} · {p.narration || "—"}{p.financeFileNumber ? ` · ${p.financeFileNumber}` : ""}</div>
              </div>
              <div className="text-right text-xs text-ink-soft">
                <div>Running: <span className="font-mono">{inr(p.runningTotal)}</span></div>
                <div>Balance: <span className="font-mono">{inr(p.outstandingBalance)}</span></div>
                {isOwner && (
                  <button
                    type="button"
                    data-testid={`delete-payment-${p.receiptNumber}`}
                    onClick={() => remove(p)}
                    className="mt-1 text-ink-faint hover:text-red-600 inline-flex items-center gap-1"
                  >
                    <Trash2 size={13} /> Delete
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Refund of surplus money. Not gated on delivery/closure — the excess is the
 *  customer's money, so it must be returnable at any point. */
function RefundForm({ lead, excess, onSaved }) {
  const [form, setForm] = useState({ amount: "", paymentMode: "Cash", date: todayISO(), reference: "", narration: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid refund amount");
    if (+form.amount > excess + 0.01) return toast.error(`Only ${inr(excess)} is available to refund`);
    if (!form.date) return toast.error("Refund date is required");
    setBusy(true);
    try {
      await post(`/leads/${lead.leadId}/refund`, { ...form, amount: +form.amount });
      toast.success(`Refund recorded · ${inr(+form.amount)}`);
      setForm({ amount: "", paymentMode: "Cash", date: todayISO(), reference: "", narration: "" });
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Refund failed");
    } finally { setBusy(false); }
  };
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 items-end mt-4 pt-4 border-t border-amber-200">
      <Field label="Refund (₹)">
        <Input data-testid="refund-amount" type="number" value={form.amount} onChange={set("amount")} placeholder={String(excess)} />
      </Field>
      <Field label="Date"><Input data-testid="refund-date" type="date" value={form.date} onChange={set("date")} /></Field>
      <Field label="Mode">
        <Select data-testid="refund-mode" value={form.paymentMode} onChange={set("paymentMode")}>
          {["Cash", "UPI", "Cheque", "NEFT"].map((m) => <option key={m}>{m}</option>)}
        </Select>
      </Field>
      <Field label="Reference / UTR"><Input value={form.reference} onChange={set("reference")} /></Field>
      <Button data-testid="refund-btn" onClick={submit} disabled={busy}>
        <ArrowRightLeft size={15} /> {busy ? "Refunding…" : "Refund Excess"}
      </Button>
    </div>
  );
}

/* -------------------------------------------------- Delivery */
function BookingConfirmSend({ leadId, already, onSent }) {
  const [busy, setBusy] = useState(false);
  const send = async (force) => {
    setBusy(true);
    try {
      const r = await post(`/leads/${leadId}/whatsapp/booking-confirm`, { force: !!force });
      if (r.skipped) toast.success("Booking WhatsApp was already sent");
      else toast.success("Booking confirmation WhatsApp sent");
      if (onSent) onSent();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send booking WhatsApp");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="p-4" data-testid="booking-whatsapp-card">
      <div className="font-heading font-bold text-ink text-sm">Booking WhatsApp</div>
      <p className="text-xs text-ink-soft mt-1 mb-3">
        Send the booking confirmation template to this customer’s WhatsApp.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="send-booking-whatsapp-btn" onClick={() => send(false)} disabled={busy}>
          {busy ? "Sending…" : already ? "Already sent" : "Send booking WhatsApp"}
        </Button>
        {already && <Button variant="secondary" onClick={() => send(true)} disabled={busy}>Send again</Button>}
      </div>
    </Card>
  );
}

function GoogleReviewSend({ leadId, already, onSent }) {
  const [busy, setBusy] = useState(false);
  const send = async (force) => {
    setBusy(true);
    try {
      const r = await post(`/leads/${leadId}/whatsapp/google-review`, { force: !!force });
      if (r.skipped) toast.success("Google review WhatsApp was already sent");
      else toast.success("Google review WhatsApp sent");
      if (onSent) onSent();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send Google review WhatsApp");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card className="p-4 mt-4 mb-2" data-testid="delivery-google-review">
      <div className="font-heading font-bold text-ink text-sm">Google review WhatsApp</div>
      <p className="text-xs text-ink-soft mt-1 mb-3">
        Send the delivered + Google review template to this customer’s WhatsApp.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="delivery-send-review-btn" onClick={() => send(false)} disabled={busy}>
          {busy ? "Sending…" : already ? "Already sent" : "Send Google review"}
        </Button>
        {already && <Button variant="secondary" onClick={() => send(true)} disabled={busy}>Send again</Button>}
      </div>
    </Card>
  );
}

const DELIV_STEPS = [["insurance", "Insurance"], ["registration", "Registration"], ["invoice", "Invoice"], ["rc", "RC"], ["pdi", "PDI"]];
function DeliveryTab({ lead, actions = {}, isOwner = false, delivery, billingSummary, onSaved }) {
  const alreadyDelivered = actions.isDelivered;
  const closedOrInactive = !actions.isActive;
  // Staff freeze after Mark Delivered; owner may edit delivery paperwork until closed.
  const locked = closedOrInactive || (alreadyDelivered && !isOwner);
  const canMarkDelivered = actions.canDeliver;   // active + booked + not delivered
  const [form, setForm] = useState(() => {
    const f = { delivered: delivery.delivered || "", invoiceNumber: delivery.invoiceNumber || lead.invoiceNumber || "", chassisNumber: delivery.chassisNumber || "", numberPlate: delivery.numberPlate || "", insurerName: delivery.insurerName || "", insuranceAgentId: lead.insuranceAgentId || "", deliveryDate: delivery.deliveryDate || todayISO() };
    DELIV_STEPS.forEach(([k]) => (f[k] = delivery[k] || ""));
    return f;
  });
  const [summary, setSummary] = useState(billingSummary || null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  // Insurance agent is chosen here; it decides the payout slab on the entry
  // that Mark Delivered opens.
  const [agents, setAgents] = useState([]);
  // Customer-arranged insurance earns no payout, so no agent is required there.
  const selfArranged = String(lead.insuranceArrangedBy || "dealer").toLowerCase() === "self";

  useEffect(() => { setSummary(billingSummary || null); }, [billingSummary]);

  useEffect(() => { get("/insurance-agents").then(setAgents).catch(() => setAgents([])); }, []);

  useEffect(() => {
    if (!alreadyDelivered) return;
    if (billingSummary && billingSummary.leadId) return;
    let cancelled = false;
    setSummaryLoading(true);
    get(`/leads/${lead.leadId}/billing-summary`)
      .then((s) => { if (!cancelled) setSummary(s); })
      .catch(() => { if (!cancelled) setSummary(null); })
      .finally(() => { if (!cancelled) setSummaryLoading(false); });
    return () => { cancelled = true; };
  }, [alreadyDelivered, lead.leadId, billingSummary]);

  const toggle = (k) => { if (!locked) setForm((f) => ({ ...f, [k]: f[k] === "Done" ? "" : "Done" })); };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const save = async () => {
    if (form.delivered === "Yes" && !form.deliveryDate) return toast.error("Delivery date is required");
    // The agent decides the payout slab; the server rejects a blank one too.
    if (form.delivered === "Yes" && !form.insuranceAgentId && !selfArranged) {
      return toast.error("Select the insurance agent before marking delivered");
    }
    try {
      await put(`/leads/${lead.leadId}/delivery`, form);
      toast.success(form.delivered === "Yes"
        ? "Delivered — billing summary ready for Tally cross-check"
        : "Delivery status updated");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delivery update failed");
    }
  };
  return (
    <div>
      {alreadyDelivered && !isOwner && <StepLock text="Vehicle delivered — this lead is locked. No further delivery or commercial edits." />}
      {alreadyDelivered && isOwner && !closedOrInactive && <StepLock text="Delivered — owner may still edit until the lead is closed." />}
      {!alreadyDelivered && closedOrInactive && <StepLock text="This lead is Closed — delivery cannot be changed." />}
      {!alreadyDelivered && !closedOrInactive && !canMarkDelivered && <StepLock text="Convert this lead to a Booking before it can be delivered." />}
      <div className="flex flex-wrap gap-2 mb-4">
        {DELIV_STEPS.map(([k, label]) => (
          <button key={k} data-testid={`deliv-${k}`} onClick={() => toggle(k)} disabled={locked}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold ring-1 ring-inset transition-colors ${form[k] === "Done" ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-50 text-ink-soft ring-line"} ${locked ? "opacity-60 cursor-not-allowed" : ""}`}>
            {label} {form[k] === "Done" ? "✓" : ""}
          </button>
        ))}
      </div>
      <p className="text-xs text-ink-soft mb-3">Invoice number, chassis number, and number plate must be unique across all leads.</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Invoice Number"><Input data-testid="delivery-invoice" value={form.invoiceNumber} onChange={set("invoiceNumber")} disabled={locked} /></Field>
        <Field label="Chassis Number"><Input data-testid="delivery-chassis" value={form.chassisNumber} onChange={set("chassisNumber")} disabled={locked} /></Field>
        <Field label="Number Plate"><Input data-testid="delivery-plate" value={form.numberPlate} onChange={set("numberPlate")} disabled={locked} /></Field>
        <Field label="Insurer Name"><Input value={form.insurerName} onChange={set("insurerName")} disabled={locked} /></Field>
        <Field label="Insurance Agent *">
          <Select data-testid="delivery-insurance-agent" value={form.insuranceAgentId}
            onChange={set("insuranceAgentId")} disabled={locked}>
            <option value="">— Select agent —</option>
            {agents.filter((a) => (a.status || "Active").toLowerCase() === "active" || a.agentId === form.insuranceAgentId)
              .map((a) => <option key={a.agentId} value={a.agentId}>{a.agentName}</option>)}
          </Select>
        </Field>
        <Field label="Delivery Date"><Input type="date" value={form.deliveryDate || ""} onChange={set("deliveryDate")} disabled={locked} /></Field>
        <Field label="Mark Delivered?">
          <Select data-testid="delivered-select" value={form.delivered} onChange={set("delivered")} disabled={locked || alreadyDelivered || !canMarkDelivered}>
            <option value="">Not yet</option><option value="Yes">Yes — Delivered</option>
          </Select>
        </Field>
      </div>
      <div className="flex justify-end mt-4"><Button data-testid="save-delivery-btn" onClick={save} disabled={locked || (!alreadyDelivered && !canMarkDelivered)}>Save Delivery</Button></div>

      {alreadyDelivered && (
        <GoogleReviewSend leadId={lead.leadId} already={!!lead.whatsappDeliverySentAt} onSent={onSaved} />
      )}

      {alreadyDelivered && (
        <div className="mt-6" data-testid="billing-summary-section">
          {summaryLoading && <div className="text-sm text-ink-faint">Loading billing summary…</div>}
          {!summaryLoading && summary && <BillingSummaryPanel summary={summary} />}
          {!summaryLoading && !summary && (
            <div className="text-sm text-ink-soft border border-line rounded-lg px-3 py-3">
              Billing summary not found. Open again after refresh, or call billing-summary API.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BillingSummaryPanel({ summary }) {
  const printSummary = () => {
    const el = document.getElementById("billing-summary-print");
    if (!el) return;
    const w = window.open("", "_blank", "noopener,noreferrer,width=900,height=1000");
    if (!w) {
      toast.error("Pop-up blocked — allow pop-ups to print");
      return;
    }
    w.document.write(`<!DOCTYPE html><html><head><title>${summary.title || "Billing Summary"} — ${summary.leadId}</title>
      <style>
        body{font-family:ui-sans-serif,system-ui,sans-serif;color:#111;padding:24px;max-width:800px;margin:0 auto}
        h1{font-size:18px;margin:0 0 4px} .disc{font-size:12px;color:#444;margin-bottom:16px;padding:8px 10px;border:1px solid #ccc;background:#faf8f5}
        table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}
        th,td{padding:6px 4px;border-bottom:1px solid #e5e5e5;text-align:left}
        td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
        .muted{color:#666;font-size:11px} .grand td{font-weight:700;border-top:2px solid #111;padding-top:10px}
        h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;margin:18px 0 6px;color:#333}
        @media print{body{padding:0}}
      </style></head><body>${el.innerHTML}
      <script>window.onload=function(){window.print();}</script></body></html>`);
    w.document.close();
  };

  const t = summary.totals || {};
  const cust = summary.customer || {};
  const veh = summary.vehicle || {};
  const gst = summary.gstReference || {};

  return (
    <Card className="p-4 border-line" data-testid="billing-summary-panel">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-ink-soft" />
            <h3 className="font-heading text-base font-bold text-ink">Delivery Billing Summary</h3>
          </div>
          <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-1.5 mt-2 max-w-xl">
            {summary.disclaimer || "For Tally cross-check only — not a GST tax invoice."}
          </p>
        </div>
        <Button variant="secondary" data-testid="print-billing-summary-btn" onClick={printSummary} className="!py-1.5 !px-2.5 text-xs shrink-0">
          <Printer size={14} /> Print for accounts
        </Button>
      </div>

      <div id="billing-summary-print">
        <h1 style={{ fontSize: "18px", fontWeight: 700, marginBottom: 4 }}>Delivery Billing Summary</h1>
        <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-1.5 mb-3">
          {summary.disclaimer || "For Tally cross-check only — not a GST tax invoice."}
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm mb-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-ink-faint">Customer</div>
            <div className="font-semibold text-ink">{cust.name}</div>
            <div className="text-xs text-ink-soft">{cust.mobile || "—"} · {cust.city || cust.village || "—"}</div>
            <div className="text-xs text-ink-faint">Exec: {cust.executive || "—"} · Source: {cust.leadSource || "—"}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wide text-ink-faint">Invoice / Delivery</div>
            <div className="font-mono font-semibold">{summary.invoiceNumber || "—"}</div>
            <div className="text-xs text-ink-soft">{fmtDate(summary.deliveryDate) || "—"}</div>
            <div className="text-xs text-ink-faint">{summary.leadId} · {veh.model} {veh.variant}</div>
            <div className="text-xs text-ink-faint">Chassis: {veh.chassisNumber || "—"}</div>
          </div>
        </div>

        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mt-4 mb-1">A. Customer charges (full amount on Tally)</h2>
        <table className="w-full text-sm">
          <tbody>
            {(summary.chargeLines || []).map((ln) => (
              <tr key={ln.code}>
                <td>{ln.label}</td>
                <td className="text-right font-mono">{inr(ln.amount)}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td>Gross (before passed benefits)</td>
              <td className="text-right font-mono">{inr(t.grossVehicleCost)}</td>
            </tr>
          </tbody>
        </table>

        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mt-4 mb-1">B. Benefit passed to customer (only these on Tally)</h2>
        <table className="w-full text-sm">
          <tbody>
            {(summary.discountLines || []).length === 0 && (
              <tr><td colSpan={2} className="text-ink-faint text-xs">No benefit passed — do not show any scheme/discount line on the Tally invoice</td></tr>
            )}
            {(summary.discountLines || []).map((ln) => (
              <tr key={ln.code + ln.label}>
                <td>{ln.label}{ln.fundHint ? <span className="text-ink-faint text-xs ml-1">({ln.fundHint})</span> : null}</td>
                <td className="text-right font-mono">{inr(ln.amount)}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td>Total benefit passed</td>
              <td className="text-right font-mono">− {inr(t.customerBenefitPassed)}</td>
            </tr>
          </tbody>
        </table>

        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mt-4 mb-1">C. Tally bill total (= amount from customer)</h2>
        <table className="w-full text-sm">
          <tbody>
            <tr><td>Tally / customer bill</td><td className="text-right font-mono font-bold">{inr(t.tallyBillTotal ?? t.netAfterBenefits ?? t.customerPayable)}</td></tr>
            <tr><td>Customer payable (CRM)</td><td className="text-right font-mono">{inr(t.customerPayable)}</td></tr>
            <tr><td>Amount received</td><td className="text-right font-mono">{inr(t.totalReceived)}</td></tr>
            <tr><td>Customer outstanding</td><td className="text-right font-mono">{inr(t.customerOutstanding)}</td></tr>
            {(Number(t.excessReceived) > 0) && (
              <tr><td>Excess received</td><td className="text-right font-mono text-amber-700">{inr(t.excessReceived)}</td></tr>
            )}
            <tr><td>Booking advance</td><td className="text-right font-mono">{inr(t.bookingAmount)}</td></tr>
          </tbody>
        </table>

        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mt-4 mb-1">D. GST reference (optional — Tally is final)</h2>
        <table className="w-full text-sm">
          <tbody>
            <tr><td>Assumed rate</td><td className="text-right font-mono">{gst.ratePct}%</td></tr>
            <tr><td>Taxable value (ref.)</td><td className="text-right font-mono">{inr(gst.taxableValue)}</td></tr>
            <tr><td>CGST / SGST (ref.)</td><td className="text-right font-mono">{inr(gst.cgst)} / {inr(gst.sgst)}</td></tr>
          </tbody>
        </table>
        <p className="text-[11px] text-ink-faint mt-1">{gst.note}</p>

        {(summary.doNotPostInTally || []).length > 0 && (
          <>
            <h2 className="text-[11px] font-semibold uppercase tracking-wide text-red-700/80 mt-4 mb-1">E. Do not post on customer bill in Tally</h2>
            <table className="w-full text-sm">
              <tbody>
                {(summary.doNotPostInTally || []).map((ln, i) => (
                  <tr key={i}>
                    <td className="text-ink-soft">{ln.label}</td>
                    <td className="text-right font-mono text-ink-soft">{inr(ln.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </Card>
  );
}

/* -------------------------------------------------- Edit lead details */
function EditLeadModal({ lead, masters, isOwner = false, actions = {}, onClose, onSaved }) {
  const vehicleLocked = !isOwner && (!!actions.priceCompleted || !!actions.schemeCompleted);
  const [form, setForm] = useState({
    customerName: lead.customerName || "", mobile: lead.mobile || "", altMobile: lead.altMobile || "",
    village: lead.village || "", city: lead.city || "", leadSource: lead.leadSource || "Walk-in",
    interestedModel: lead.interestedModel || "", variant: lead.variant || "", executive: lead.executive || "",
    currentStatus: lead.currentStatus || "New", priority: lead.priority || "Normal", budget: lead.budget || 0,
    remarks: lead.remarks || "", financeRequired: lead.financeRequired || "No",
    exchangeRequired: lead.exchangeRequired || "No", nextFollowupDate: lead.nextFollowupDate || "",
    bookingAmount: lead.bookingAmount ?? 0,
  });
  const [variants, setVariants] = useState([]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  useEffect(() => { if (form.interestedModel) get("/price-master/variants", { model: form.interestedModel }).then(setVariants); }, [form.interestedModel]);
  const isBookedLead = Boolean(lead.bookingDate)
    || ["booked", "finance process", "delivered", "close won"].includes(String(lead.currentStatus || "").toLowerCase());

  const save = async () => {
    if (!form.customerName) return toast.error("Customer name is required");
    const vehicleChanged = form.interestedModel !== (lead.interestedModel || "")
      || form.variant !== (lead.variant || "");
    try {
      const body = { ...form, budget: Number(form.budget) };
      if (isBookedLead) body.bookingAmount = Number(form.bookingAmount) || 0;
      else delete body.bookingAmount;
      await put(`/leads/${lead.leadId}`, body);
      toast.success(vehicleChanged
        ? "Lead updated — Ex-Showroom & scheme recalculated from masters"
        : "Lead updated");
      onSaved({ vehicleChanged });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    }
  };
  const m = masters || {};
  return (
    <Modal onClose={onClose} width="max-w-2xl" testid="edit-lead-modal">
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-6">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Edit Lead — {lead.leadId}</h3>
        <p className="text-xs text-ink-soft mb-4">
          Correct any details captured against this lead.
          {vehicleLocked
            ? " Model/variant is locked after pricing — ask the owner to change the vehicle."
            : " Changing model/variant refreshes Ex-Showroom from Price Master and realigns scheme."}
        </p>
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2"><Field label="Customer Name *"><Input data-testid="edit-name" value={form.customerName} onChange={set("customerName")} /></Field></div>
          <Field label="Status"><Select data-testid="edit-status" value={form.currentStatus} onChange={set("currentStatus")}>{(m.statuses || ["New","Contacted","Follow-up","In Progress","Booked","Finance Process","Delivered","Close Won","Lost"]).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Mobile"><Input data-testid="edit-mobile" value={form.mobile} onChange={set("mobile")} /></Field>
          <Field label="Alt Mobile"><Input value={form.altMobile} onChange={set("altMobile")} /></Field>
          <Field label="City"><Input value={form.city} onChange={set("city")} /></Field>
          <Field label="Village"><Input value={form.village} onChange={set("village")} /></Field>
          <Field label="Lead Source"><Select value={form.leadSource} onChange={set("leadSource")}>{(m.leadSources || []).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Executive"><Select value={form.executive} onChange={set("executive")}><option value="">—</option>{(m.executives || []).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Model"><Select value={form.interestedModel} onChange={set("interestedModel")} disabled={vehicleLocked}><option value="">—</option>{(m.models || []).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Variant"><Select value={form.variant} onChange={set("variant")} disabled={vehicleLocked}><option value="">—</option>{variants.map((v) => <option key={v.priceId} value={v.variant}>{v.variant}</option>)}</Select></Field>
          <Field label="Priority"><Select value={form.priority} onChange={set("priority")}>{(m.priorities || ["Low","Normal","High","Urgent"]).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Budget (₹)"><Input type="number" value={form.budget} onChange={set("budget")} /></Field>
          <Field label="Finance Required"><Select value={form.financeRequired} onChange={set("financeRequired")}><option>No</option><option>Yes</option></Select></Field>
          <Field label="Exchange Required"><Select value={form.exchangeRequired} onChange={set("exchangeRequired")}><option>No</option><option>Yes</option></Select></Field>
          {isBookedLead && (
            <Field label="Booking advance (₹)">
              <Input data-testid="edit-booking-amount" type="number" min="0" value={form.bookingAmount} onChange={set("bookingAmount")} />
            </Field>
          )}
          <Field label="Next Follow-up"><Input type="date" value={form.nextFollowupDate || ""} onChange={set("nextFollowupDate")} /></Field>
          {isBookedLead && (
            <p className="col-span-3 text-xs text-ink-soft -mt-1">Set booking advance to 0 if there was no token payment (corrects the old ₹5,000 default). Updates the booking advance receipt when present.</p>
          )}
          <div className="col-span-3"><Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field></div>
        </div>
      </div>
      <div className="flex justify-end gap-2 px-6 py-4 border-t border-line bg-zinc-50/60 shrink-0">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button data-testid="save-edit-lead-btn" onClick={save}>Save Changes</Button>
      </div>
    </Modal>
  );
}

/* -------------------------------------------------- Insurance (from lead) */
const suggestInsRate = (model) => {
  const s = String(model || "").toLowerCase();
  return (s.includes("storm") || s.includes("turbo")) ? 49 : 36.5;
};
function InsuranceTab({ lead, masters }) {
  const [entries, setEntries] = useState([]);
  const [rateTouched, setRateTouched] = useState(false);
  const [form, setForm] = useState({
    insuranceCompany: lead.insurerName || "", policyNumber: "",
    insuranceAmount: lead.insuranceAmount || 0, payoutRate: suggestInsRate(lead.interestedModel),
    receivedPayout: 0, insuranceExecutive: lead.executive || "", policyDate: todayISO(),
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setRate = (e) => { setRateTouched(true); setForm((f) => ({ ...f, payoutRate: e.target.value })); };
  const load = useCallback(() => get("/insurance", { lead_id: lead.leadId }).then(setEntries), [lead.leadId]);
  useEffect(() => { load(); }, [load]);

  const premium = Number(form.insuranceAmount) || 0;
  const rate = Number(form.payoutRate) || 0;
  const expected = Math.round(premium * (rate / 100));

  const save = async () => {
    if (!form.policyDate) return toast.error("Policy date is required");
    await post("/insurance", {
      leadId: lead.leadId, customerName: lead.customerName, mobile: lead.mobile,
      model: lead.interestedModel, variant: lead.variant,
      insuranceCompany: form.insuranceCompany, policyNumber: form.policyNumber,
      insuranceAmount: +form.insuranceAmount, payoutRate: +form.payoutRate,
      receivedPayout: +form.receivedPayout, insuranceExecutive: form.insuranceExecutive,
      policyDate: form.policyDate,
    });
    toast.success("Insurance entry added");
    setForm((f) => ({ ...f, policyNumber: "", policyDate: todayISO() }));
    load();
  };

  return (
    <div>
      <Card className="p-4 mb-4">
        <p className="text-xs text-ink-soft mb-3">Premium is pre-filled from this lead's price structure. Enter the insurer & payout rate.</p>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Insurer"><Input data-testid="lead-ins-company" value={form.insuranceCompany} onChange={set("insuranceCompany")} /></Field>
          <Field label="Policy Number"><Input value={form.policyNumber} onChange={set("policyNumber")} /></Field>
          <Field label="Policy Date"><Input data-testid="lead-ins-policy-date" type="date" value={form.policyDate} onChange={set("policyDate")} /></Field>
          <Field label="Executive"><Select value={form.insuranceExecutive} onChange={set("insuranceExecutive")}><option value="">—</option>{(masters?.executives || []).map((x) => <option key={x}>{x}</option>)}</Select></Field>
          <Field label="Premium (₹)"><Input data-testid="lead-ins-premium" type="number" value={form.insuranceAmount} onChange={set("insuranceAmount")} /></Field>
          <Field label="Payout Rate (%)"><Input data-testid="lead-ins-rate" type="number" value={form.payoutRate} onChange={setRate} /></Field>
          <Field label="Received (₹)"><Input type="number" value={form.receivedPayout} onChange={set("receivedPayout")} /></Field>
        </div>
        <div className="text-[11px] text-ink-faint mt-1" data-testid="lead-ins-rate-hint">
          Auto-filled {suggestInsRate(lead.interestedModel)}% for {lead.interestedModel || "this model"} ({/storm|turbo/i.test(lead.interestedModel || "") ? "Storm/Turbo" : "other models"}) — editable.
        </div>
        <div className="flex items-center justify-between mt-3">
          <div className="text-sm text-ink-soft">Expected payout <span className="font-mono font-semibold text-cobalt">{inr(expected)}</span></div>
          <Button data-testid="lead-add-insurance-btn" onClick={save}>Add Insurance</Button>
        </div>
      </Card>
      <div className="space-y-2">
        {entries.length === 0 && <div className="text-sm text-ink-faint text-center py-4">No insurance entries for this lead yet</div>}
        {entries.map((e) => (
          <div key={e.entryId} className="flex items-center justify-between bg-white border border-line rounded-lg px-4 py-2.5">
            <div>
              <div className="text-sm font-semibold text-ink">{e.insuranceCompany || "—"} <Badge className="ml-1">{e.status}</Badge></div>
              <div className="text-xs text-ink-faint">Premium {inr(e.insuranceAmount)} · Rate {(Number(e.payoutRate) * 100).toFixed(1)}%</div>
            </div>
            <div className="text-right text-xs text-ink-soft">
              <div>Expected: <span className="font-mono">{inr(e.expectedPayout)}</span></div>
              <div>Outstanding: <span className="font-mono">{inr(e.payoutOutstanding)}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------- Activity */
function ActivityTab({ lead, activities, masters, onSaved, readOnly = false }) {
  const [form, setForm] = useState({ activityType: "Call", discussion: "", nextFollowup: "", date: todayISO() });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const add = async () => {
    if (!form.discussion) return toast.error("Add a discussion note");
    if (!form.date) return toast.error("Activity date is required");
    await post(`/leads/${lead.leadId}/activities`, { ...form, executive: lead.executive });
    toast.success("Activity logged");
    setForm({ activityType: "Call", discussion: "", nextFollowup: "", date: todayISO() });
    onSaved();
  };
  return (
    <div>
      {!readOnly && (
        <Card className="p-4 mb-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <Field label="Type"><Select value={form.activityType} onChange={set("activityType")}>{(masters?.activityTypes || []).map((t) => <option key={t}>{t}</option>)}</Select></Field>
            <Field label="Date"><Input data-testid="activity-date" type="date" value={form.date} onChange={set("date")} /></Field>
            <Field label="Next Follow-up"><Input data-testid="activity-followup" type="date" value={form.nextFollowup} onChange={set("nextFollowup")} /></Field>
            <div className="sm:col-span-2"><Field label="Discussion"><Input data-testid="activity-note" value={form.discussion} onChange={set("discussion")} /></Field></div>
          </div>
          <div className="flex justify-end mt-3">
            <Button data-testid="add-activity-btn" onClick={add}>Log</Button>
          </div>
        </Card>
      )}
      <div className="space-y-2">
        {activities.map((a) => (
          <div key={a.activityId} className="flex gap-3 bg-white border border-line rounded-lg px-4 py-2.5">
            <Badge>{a.activityType}</Badge>
            <div className="flex-1">
              <div className="text-sm text-ink">{a.discussion}</div>
              <div className="text-xs text-ink-faint">{fmtDate(a.date)} {a.time} · {a.executive || "—"}</div>
            </div>
          </div>
        ))}
        {!activities.length && <div className="text-sm text-ink-faint py-6 text-center">No activities yet</div>}
      </div>
    </div>
  );
}

/* -------------------------------------------------- Modals */
function BookingModal({ lead, onClose, onDone }) {
  const [form, setForm] = useState({ bookingAmount: 0, paymentMode: "UPI", financeRequired: lead.financeRequired || "No", exchangeRequired: lead.exchangeRequired || "No", bookingDate: lead.bookingDate || todayISO() });
  // Commercial gate: a booking may only be confirmed once the backend has resolved
  // the vehicle against Price Master. All figures below come from the API — nothing
  // is calculated or defaulted in React, so there is no path to a silent zero.
  const [preview, setPreview] = useState(undefined); // undefined = loading
  const [previewError, setPreviewError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    let alive = true;
    get(`/leads/${lead.leadId}/price-preview`)
      .then((d) => { if (alive) setPreview(d); })
      .catch((e) => { if (alive) { setPreview(null); setPreviewError(e?.response?.data?.detail || "Could not reach the pricing service."); } });
    return () => { alive = false; };
  }, [lead.leadId]);

  // STRICT PRODUCTION BOOKING MODE: a saved price structure is never sufficient on
  // its own. Every booking requires a fresh Price Master hit for the lead's CURRENT
  // model/variant, matching the backend's own revalidation.
  const canBook = Boolean(preview && preview.found === true && Number(preview.priceStructure?.exShowroom) > 0);
  const loading = preview === undefined;
  const ps = (preview && preview.priceStructure) || {};
  const charges = ["rto", "insuranceAmount", "accessoriesAmount", "handlingCharges", "trc", "fastag", "extendedWarranty", "otherCharges"];
  const gvc = Number(ps.exShowroom || 0) + charges.reduce((t, k) => t + Number(ps[k] || 0), 0);

  const submit = async () => {
    if (!canBook || busy) return;
    setBusy(true);
    try {
      if (!form.bookingDate) { toast.error("Booking date is required"); setBusy(false); return; }
      const res = await post(`/leads/${lead.leadId}/convert-booking`, {
        bookingAmount: +form.bookingAmount, paymentMode: form.paymentMode, executive: lead.executive,
        financeRequired: form.financeRequired, exchangeRequired: form.exchangeRequired,
        bookingDate: form.bookingDate,
      });
      // Report the ACTUAL backend sync state, never an assumption from a 200.
      let sync = "Pending";
      try {
        const log = await get("/integrations/gsheets/sync-log", { status: "PENDING" });
        sync = Number(log?.pending) === 0 ? "Synced" : "Pending";
      } catch { sync = "Unknown"; }
      setResult({ booking: res, lead: res.lead || {}, sync });
      toast.success("Booking confirmed");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Booking failed");
      setBusy(false);
    }
  };

  if (result) {
    const l = result.lead || {};
    const rows = [
      ["Price Loaded", Number(l.exShowroom) > 0],
      ["Customer Payable Calculated", Number(l.customerPayable) > 0],
      ["Booking Created", Boolean(result.booking?.bookingId)],
    ];
    return (
      <MiniModal title="Booking Confirmed" onClose={onDone} onSubmit={onDone} submitLabel="Done" testid="booking-done-btn">
        <div className="space-y-1.5 text-sm" data-testid="booking-summary">
          {rows.map(([label, ok]) => (
            <div key={label} className="flex justify-between"><span className="text-ink-soft">{label}</span><span>{ok ? "✓" : "—"}</span></div>
          ))}
          <div className="flex justify-between"><span className="text-ink-soft">Google Sheet Sync</span><span data-testid="booking-sync-status">{result.sync}</span></div>
          <div className="border-t border-line mt-2 pt-2 flex justify-between font-semibold">
            <span>Customer Payable</span><span>{inr(l.customerPayable)}</span>
          </div>
          <div className="flex justify-between"><span className="text-ink-soft">Booking ID</span><span>{result.booking?.bookingId || "—"}</span></div>
        </div>
      </MiniModal>
    );
  }

  return (
    <MiniModal title="Convert to Booking" onClose={onClose} onSubmit={submit} submitLabel={busy ? "Booking…" : "Confirm Booking"} testid="confirm-booking-btn" submitDisabled={!canBook || loading || busy}>
      {loading && <p className="text-xs text-ink-soft mb-3" data-testid="price-loading">Loading price from Price Master…</p>}

      {!loading && preview && preview.found === false && (
        <div className="mb-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="price-error">
          {preview.message || `Price Master entry not found for ${lead.interestedModel || "—"} / ${lead.variant || "—"}.`}
          {" "}Please select a valid vehicle or update Price Master.
        </div>
      )}
      {!loading && preview === null && (
        <div className="mb-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="price-error">{previewError}</div>
      )}

      {!loading && preview && preview.found && (
        <div className="mb-3 rounded-lg border border-line bg-paper px-3 py-2 text-sm" data-testid="price-preview">
          <div className="font-semibold text-ink mb-1">{lead.interestedModel} · {lead.variant}</div>
          <div className="flex justify-between"><span className="text-ink-soft">Ex-Showroom</span><span>{inr(ps.exShowroom)}</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">RTO</span><span>{inr(ps.rto)}</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Insurance</span><span>{inr(ps.insuranceAmount)}</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Other Charges</span><span>{inr(gvc - Number(ps.exShowroom || 0) - Number(ps.rto || 0) - Number(ps.insuranceAmount || 0))}</span></div>
          <div className="border-t border-line mt-1 pt-1 flex justify-between font-semibold"><span>Gross Vehicle Cost</span><span data-testid="preview-gvc">{inr(gvc)}</span></div>
          <p className="text-xs text-ink-faint mt-1">Scheme benefits and final Customer Payable are computed by the backend on booking.</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Booking Date"><Input data-testid="booking-date" type="date" value={form.bookingDate} onChange={set("bookingDate")} /></Field>
        <Field label="Booking advance (₹)">
          <Input data-testid="booking-amount" type="number" min="0" value={form.bookingAmount} onChange={set("bookingAmount")} />
        </Field>
        <p className="col-span-2 text-xs text-ink-soft -mt-1">Use 0 when the customer pays the full amount with no separate booking advance (default is 0, not ₹5,000).</p>
        <Field label="Payment Mode"><Select value={form.paymentMode} onChange={set("paymentMode")}>{["Cash","UPI","Cheque","NEFT","Card"].map((m) => <option key={m}>{m}</option>)}</Select></Field>
        <Field label="Finance Required"><Select value={form.financeRequired} onChange={set("financeRequired")}><option>No</option><option>Yes</option></Select></Field>
        <Field label="Exchange Required"><Select value={form.exchangeRequired} onChange={set("exchangeRequired")}><option>No</option><option>Yes</option></Select></Field>
      </div>
    </MiniModal>
  );
}

function CloseModal({ lead, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [closedDate, setClosedDate] = useState(todayISO());
  const [rc, setRc] = useState(lead.rcStatus === "Yes" || lead.rcStatus === "Done" ? "Done" : "");
  const [plate, setPlate] = useState(lead.numberPlate || "");
  const delivered = (lead.deliveryStatus || "").toLowerCase() === "delivered" || (lead.currentStatus || "").toLowerCase() === "delivered";
  const submit = async () => {
    if (!reason.trim()) return toast.error("Close Reason is required");
    if (!closedDate) return toast.error("Close date is required");
    try {
      await post(`/leads/${lead.leadId}/close`, { closeReason: reason, rc, numberPlate: plate, closedDate });
      toast.success("Lead closed");
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Close failed");
    }
  };
  return (
    <MiniModal title="Close Lead" onClose={onClose} onSubmit={submit} submitLabel="Close Lead" danger testid="confirm-close-btn">
      {delivered && (
        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="RC">
            <Select data-testid="close-rc" value={rc} onChange={(e) => setRc(e.target.value)}><option value="">Not yet</option><option value="Done">Done</option></Select>
          </Field>
          <Field label="Number Plate"><Input data-testid="close-plate" value={plate} onChange={(e) => setPlate(e.target.value)} /></Field>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Field label="Close Date"><Input data-testid="close-date" type="date" value={closedDate} onChange={(e) => setClosedDate(e.target.value)} /></Field>
        <Field label="Close Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Delivered & settled" /></Field>
      </div>
    </MiniModal>
  );
}

function MiniModal({ title, children, onClose, onSubmit, submitLabel, danger, testid, submitDisabled }) {
  // Title and the action row stay put; only the form body scrolls, so Confirm
  // Booking is always one tap away however long the form gets.
  return (
    <Modal onClose={onClose} width="max-w-lg">
      <h3 className="font-heading text-lg font-bold text-ink px-6 pt-6 pb-4 shrink-0">{title}</h3>
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6">{children}</div>
      <div className="flex justify-end gap-2 px-6 py-4 border-t border-line bg-zinc-50/60 shrink-0">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} data-testid={testid} onClick={onSubmit} disabled={submitDisabled}>{submitLabel}</Button>
      </div>
    </Modal>
  );
}
