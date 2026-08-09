import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { ArrowRightLeft, Wallet, XCircle, Pencil, Trash2 } from "lucide-react";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { Drawer, Tabs, Badge, Button, Field, Input, Select, Card } from "../components/ui";
import { useAuth } from "../context/AuthContext";

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
  const { isOwner } = useAuth();
  const [data, setData] = useState(null);
  const [tab, setTab] = useState("overview");
  const [editing, setEditing] = useState(false);

  const load = useCallback(() => {
    get(`/leads/${leadId}/360`).then(setData);
  }, [leadId]);
  useEffect(() => { load(); }, [load]);

  const refresh = () => { load(); onChanged && onChanged(); };

  if (!data) return <Drawer open onClose={onClose} title="Loading…"><div className="text-ink-faint text-sm">Fetching lead…</div></Drawer>;

  const lead = data.lead;
  const c = data.commercials;
  const actions = data.actions || {};

  const tabs = [
    { key: "overview", label: "Overview" },
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
      footer={<DrawerActions lead={lead} actions={actions} refresh={refresh} onClose={onClose} />}
    >
      <div className="flex items-center gap-2 mb-4">
        <Badge>{lead.currentStatus}</Badge>
        <Badge>{lead.accountStatus}</Badge>
        <Button variant="secondary" data-testid="edit-lead-btn" onClick={() => setEditing(true)} className="!py-1 !px-2.5 text-xs"><Pencil size={13} /> Edit</Button>
        {isOwner && (
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
        <div className="ml-auto text-right">
          <div className="text-xs text-ink-faint">Outstanding</div>
          <div className={`font-mono font-bold ${lead.customerOutstanding > 0 ? "text-red-600" : "text-emerald-600"}`}>{inr(lead.customerOutstanding)}</div>
        </div>
      </div>

      {editing && <EditLeadModal lead={lead} masters={masters} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); refresh(); }} />}

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === "overview" && <Overview lead={lead} c={c} />}
      {tab === "price" && <PriceStructure lead={lead} actions={actions} onSaved={refresh} />}
      {tab === "scheme" && <SchemeTab lead={lead} c={c} actions={actions} masters={masters} onSaved={refresh} />}
      {tab === "payments" && <PaymentsTab lead={lead} actions={actions} payments={data.payments} masters={masters} onSaved={refresh} />}
      {tab === "delivery" && <DeliveryTab lead={lead} actions={actions} delivery={data.delivery} onSaved={refresh} />}
      {tab === "insurance" && isOwner && <InsuranceTab lead={lead} masters={masters} />}
      {tab === "activity" && <ActivityTab lead={lead} activities={data.activities} masters={masters} onSaved={refresh} />}
    </Drawer>
  );
}

function StepLock({ text }) {
  return <div data-testid="step-lock-notice" className="mb-3 flex items-center gap-2 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">{text}</div>;
}

function DrawerActions({ lead, actions, refresh, onClose }) {
  const [modal, setModal] = useState(null);
  return (
    <div className="flex items-center gap-2">
      {actions.canBook && <Button data-testid="convert-booking-btn" onClick={() => setModal("book")}><ArrowRightLeft size={15} /> Convert to Booking</Button>}
      {actions.isBooked && !actions.canBook && <Badge data-testid="already-booked-badge">Booked ✓</Badge>}
      {actions.isDelivered && <Badge data-testid="already-delivered-badge">Delivered ✓</Badge>}
      {actions.canClose && (
        <Button variant="secondary" data-testid="close-lead-btn" onClick={() => setModal("close")}><XCircle size={15} /> Close Lead</Button>
      )}
      <div className="ml-auto text-sm text-ink-soft">Payable <span className="font-mono font-semibold text-ink">{inr(lead.customerPayable)}</span></div>
      {modal === "book" && <BookingModal lead={lead} onClose={() => setModal(null)} onDone={() => { setModal(null); refresh(); }} />}
      {modal === "close" && <CloseModal lead={lead} onClose={() => setModal(null)} onDone={() => { setModal(null); refresh(); onClose(); }} />}
    </div>
  );
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

function Overview({ lead, c }) {
  return (
    <div className="grid grid-cols-2 gap-5">
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
        <KV label="Dealer Scheme Retained" value={inr(c.dealerSchemeRetained ?? c.dealerRetained)} />
        <KV label="Dealer Margin (Net)" value={inr(c.margin.marginNetExGst)} />
        <KV label="Lead Source" value={lead.leadSource || "—"} tone="text-ink" />
      </Card>
      <Card className="p-4 col-span-2">
        <h4 className="font-heading font-bold text-ink text-sm mb-2">Details</h4>
        <div className="grid grid-cols-3 gap-x-6">
          <KV label="Executive" value={lead.executive || "—"} />
          <KV label="Priority" value={lead.priority} />
          <KV label="Created" value={fmtDate(lead.createdDate)} />
          <KV label="Booking Date" value={fmtDate(lead.bookingDate)} />
          <KV label="Finance" value={lead.financeRequired} />
          <KV label="Exchange" value={lead.exchangeRequired} />
        </div>
        {lead.remarks && <div className="mt-2 text-sm text-ink-soft bg-zinc-50 rounded-lg p-3">{lead.remarks}</div>}
      </Card>
    </div>
  );
}

/* -------------------------------------------------- Price Structure */
function PriceStructure({ lead, actions = {}, onSaved }) {
  const locked = !actions.canPrice;
  const [form, setForm] = useState(() => {
    const f = { tcsApplicable: lead.tcsApplicable || "No", finalExchangeValue: lead.finalExchangeValue || 0 };
    CHARGE_FIELDS.forEach(([k]) => (f[k] = lead[k] || 0));
    return f;
  });
  const [preview, setPreview] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const computePreview = useCallback(() => {
    post("/commercial/compute", {
      exShowroom: +form.exShowroom, accessories: +form.accessoriesAmount, insurance: +form.insuranceAmount,
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
    await put(`/leads/${lead.leadId}/price-structure`, {
      exShowroom: +form.exShowroom, rto: +form.rto, insuranceAmount: +form.insuranceAmount,
      accessoriesAmount: +form.accessoriesAmount, handlingCharges: +form.handlingCharges, trc: +form.trc,
      fastag: +form.fastag, extendedWarranty: +form.extendedWarranty, otherCharges: +form.otherCharges,
      rsaAmc: +form.rsaAmc,
      tcsApplicable: form.tcsApplicable, finalExchangeValue: +form.finalExchangeValue,
    });
    toast.success("Price structure saved");
    onSaved();
  };

  return (
    <div>
      {locked && <StepLock text="This lead is not Active — price structure is read-only." />}
      <div className="grid grid-cols-3 gap-3">
        {CHARGE_FIELDS.map(([k, label]) => (
          <Field key={k} label={label}><Input data-testid={`price-${k}`} type="number" value={form[k]} onChange={set(k)} disabled={locked} /></Field>
        ))}
        <Field label="Final Exchange Value"><Input type="number" value={form.finalExchangeValue} onChange={set("finalExchangeValue")} disabled={locked} /></Field>
        <Field label="TCS Applicable"><Select value={form.tcsApplicable} onChange={set("tcsApplicable")} disabled={locked}><option>No</option><option>Yes</option></Select></Field>
      </div>
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
function SchemeTab({ lead, c, actions = {}, masters, onSaved }) {
  const locked = !actions.canScheme;
  const [rules, setRules] = useState(null);
  const [form, setForm] = useState(() => {
    const f = { benefitMode: lead.benefitMode || "Full Benefit", oemExtraSupportReceived: lead.oemExtraSupportReceived || 0, oemExtraSupportPassed: lead.oemExtraSupportPassed || 0, customerBenefitPassed: lead.customerBenefitPassed || 0 };
    SCHEME_FIELDS.forEach(([k]) => (f[k] = lead[k] || 0));
    return f;
  });
  const [breakup, setBreakup] = useState(() => {
    let b = {};
    try { b = lead.benefitPassedBreakup ? JSON.parse(lead.benefitPassedBreakup) : {}; } catch { b = {}; }
    return b;
  });
  useEffect(() => { get(`/leads/${lead.leadId}/scheme-rules`).then(setRules).catch(() => setRules({ rules: {} })); }, [lead.leadId]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setBk = (k) => (e) => setBreakup((b) => ({ ...b, [k]: e.target.value }));

  // Only components available in Scheme Master for this model/variant are shown (additionalDiscount is always dealer-funded)
  const r = rules?.rules || {};
  const rulesReady = !!rules;
  const visibleFields = SCHEME_FIELDS.filter(([k]) => k === "additionalDiscount" || (r[k] ? r[k].allowed : rulesReady ? false : true));
  const hiddenFields = SCHEME_FIELDS.filter(([k]) => k !== "additionalDiscount" && r[k] && !r[k].allowed);
  const oemVisible = visibleFields.filter(([k]) => k !== "additionalDiscount");

  const save = async () => {
    const payload = {
      benefitMode: form.benefitMode, customerBenefitPassed: +form.customerBenefitPassed,
      oemExtraSupportReceived: +form.oemExtraSupportReceived, oemExtraSupportPassed: +form.oemExtraSupportPassed,
    };
    // send 0 for any component not shown so stale amounts get cleared
    SCHEME_FIELDS.forEach(([k]) => {
      const shown = k === "additionalDiscount" || (r[k] ? r[k].allowed : true);
      payload[k] = shown ? (+form[k] || 0) : 0;
    });
    if (form.benefitMode === "Partial Benefit") {
      const clean = {};
      oemVisible.forEach(([k]) => { if (+breakup[k]) clean[k] = +breakup[k]; });
      payload.benefitPassedBreakup = JSON.stringify(clean);
    } else {
      payload.benefitPassedBreakup = "";
    }
    try {
      await put(`/leads/${lead.leadId}/scheme`, payload);
      toast.success("Scheme updated");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Scheme validation failed");
    }
  };
  return (
    <div>
      {locked && <StepLock text="This lead is not Active — scheme is read-only." />}
      {rules && (
        <div className="text-xs text-ink-soft mb-3" data-testid="scheme-month-note">
          Scheme Master · <span className="font-semibold text-ink">{rules.model} {rules.variant}</span> · {rules.schemeMonth}
          {oemVisible.length === 0 && <span className="text-amber-700"> — no OEM scheme components for this model/variant this month</span>}
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        {visibleFields.map(([k, label]) => (
          <Field key={k} label={r[k]?.maxAmount ? `${label} (max ${inr(r[k].maxAmount)})` : label}>
            <Input data-testid={`scheme-${k}`} type="number" value={form[k]} onChange={set(k)} disabled={locked} />
          </Field>
        ))}
        <Field label="Benefit Mode"><Select data-testid="benefit-mode" value={form.benefitMode} onChange={set("benefitMode")} disabled={locked}>{(masters?.benefitModes || ["Full Benefit","Partial Benefit","No Benefit"]).map((m) => <option key={m}>{m}</option>)}</Select></Field>
        <Field label="OEM Extra Support Received"><Input type="number" value={form.oemExtraSupportReceived} onChange={set("oemExtraSupportReceived")} disabled={locked} /></Field>
        <Field label="OEM Extra Support Passed"><Input type="number" value={form.oemExtraSupportPassed} onChange={set("oemExtraSupportPassed")} disabled={locked} /></Field>
      </div>
      {hiddenFields.length > 0 && (
        <div className="text-[11px] text-ink-faint mt-2" data-testid="scheme-unavailable-note">
          Not available for this model/variant: {hiddenFields.map(([, l]) => l).join(", ")}
        </div>
      )}
      {form.benefitMode === "Partial Benefit" && oemVisible.length > 0 && (
        <Card className="p-4 mt-4 bg-cobalt-tint/30 border-cobalt/20">
          <div className="text-xs font-semibold text-ink mb-2">Partial Benefit — amount of each OEM offer passed to customer</div>
          <div className="grid grid-cols-3 gap-3">
            {oemVisible.map(([k, label]) => (
              <Field key={k} label={`${label} (max ${inr(+form[k] || 0)})`}>
                <Input data-testid={`breakup-${k}`} type="number" value={breakup[k] ?? ""} onChange={setBk(k)} disabled={locked} />
              </Field>
            ))}
          </div>
        </Card>
      )}
      <Card className="p-4 mt-4 bg-amber-50/50 border-amber-200">
        <div className="grid grid-cols-4 gap-3 text-center">
          <Prev label="OEM Eligible" v={c.oemEligible} />
          <Prev label="Dealer Discount" v={c.dealerDiscount} />
          <Prev label="OEM Claimable (Co. Share)" v={c.oemClaimCompanyShare ?? c.claim.claimEligible} />
          <Prev label="Dealer Scheme Retained" v={c.dealerSchemeRetained ?? c.dealerRetained} />
        </div>
      </Card>
      <ExtraIncomeCard lead={lead} locked={locked} onSaved={onSaved} />
      <div className="flex justify-end mt-4"><Button data-testid="save-scheme-btn" onClick={save} disabled={locked}>Update Scheme</Button></div>
    </div>
  );
}

const EXTRA_INCOME_FIELDS = [
  ["documentationIncome", "Documentation"], ["warrantyIncome", "Warranty"],
  ["rsaIncome", "RSA"], ["referralIncome", "Referral"],
  ["otherIncome", "Other Income"], ["customerInsuranceBenefitPassed", "Cust. Insurance Benefit Passed"],
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
  const total = EXTRA_INCOME_FIELDS.reduce((s, [k]) => s + (Number(form[k]) || 0), 0);
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
function PaymentsTab({ lead, actions = {}, payments, masters, onSaved }) {
  const [form, setForm] = useState({ amount: "", paymentMode: "Cash", narration: "", financerName: "", financeFileNumber: "" });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const isFinance = form.paymentMode === "Finance";
  const locked = isFinance ? !actions.canFinanceReceipt : !actions.canPayment;
  const add = async () => {
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    await post(`/leads/${lead.leadId}/payments`, { ...form, amount: +form.amount });
    toast.success(`Receipt added · ${inr(+form.amount)}`);
    setForm({ amount: "", paymentMode: "Cash", narration: "", financerName: "", financeFileNumber: "" });
    onSaved();
  };
  return (
    <div>
      {locked && <StepLock text={isFinance ? "This lead is archived — no receipts allowed." : "This lead is not Active — only Finance receipts are allowed."} />}
      <Card className="p-4 mb-4">
        <div className="grid grid-cols-4 gap-3 items-end">
          <Field label="Amount (₹)"><Input data-testid="payment-amount" type="number" value={form.amount} onChange={set("amount")} /></Field>
          <Field label="Mode"><Select data-testid="payment-mode" value={form.paymentMode} onChange={set("paymentMode")}>{(masters?.paymentModes || []).map((m) => <option key={m}>{m}</option>)}</Select></Field>
          <Field label="Narration"><Input value={form.narration} onChange={set("narration")} /></Field>
          <Button data-testid="add-payment-btn" onClick={add} disabled={locked}><Wallet size={15} /> Add Receipt</Button>
        </div>
        {form.paymentMode === "Finance" && (
          <div className="grid grid-cols-2 gap-3 mt-3">
            <Field label="Financer"><Select value={form.financerName} onChange={set("financerName")}><option value="">—</option>{(masters?.financers || []).map((f) => <option key={f}>{f}</option>)}</Select></Field>
            <Field label="Finance File Number"><Input value={form.financeFileNumber} onChange={set("financeFileNumber")} /></Field>
          </div>
        )}
      </Card>
      <div className="space-y-2">
        {payments.length === 0 && <div className="text-sm text-ink-faint text-center py-6">No payments recorded yet</div>}
        {payments.map((p) => (
          <div key={p.receiptNumber} className="flex items-center justify-between bg-white border border-line rounded-lg px-4 py-2.5">
            <div>
              <div className="text-sm font-semibold text-ink">{inr(p.amount)} <Badge className="ml-1">{p.paymentMode}</Badge></div>
              <div className="text-xs text-ink-faint">{p.receiptNumber} · {fmtDate(p.date)} · {p.narration || "—"}</div>
            </div>
            <div className="text-right text-xs text-ink-soft">
              <div>Running: <span className="font-mono">{inr(p.runningTotal)}</span></div>
              <div>Balance: <span className="font-mono">{inr(p.outstandingBalance)}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------- Delivery */
const DELIV_STEPS = [["insurance", "Insurance"], ["registration", "Registration"], ["invoice", "Invoice"], ["rc", "RC"], ["pdi", "PDI"]];
function DeliveryTab({ lead, actions = {}, delivery, onSaved }) {
  const [form, setForm] = useState(() => {
    const f = { delivered: delivery.delivered || "", invoiceNumber: delivery.invoiceNumber || lead.invoiceNumber || "", chassisNumber: delivery.chassisNumber || "", numberPlate: delivery.numberPlate || "", insurerName: delivery.insurerName || "", deliveryDate: delivery.deliveryDate || "" };
    DELIV_STEPS.forEach(([k]) => (f[k] = delivery[k] || ""));
    return f;
  });
  const toggle = (k) => setForm((f) => ({ ...f, [k]: f[k] === "Done" ? "" : "Done" }));
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const save = async () => {
    try {
      await put(`/leads/${lead.leadId}/delivery`, form);
      toast.success("Delivery status updated");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delivery update failed");
    }
  };
  const alreadyDelivered = actions.isDelivered;
  const canMarkDelivered = actions.canDeliver;   // active + booked + not delivered
  return (
    <div>
      {alreadyDelivered && <StepLock text="Vehicle already delivered — paperwork editable, but it can't be re-delivered." />}
      {!alreadyDelivered && !canMarkDelivered && <StepLock text="Convert this lead to a Booking before it can be delivered." />}
      <div className="flex flex-wrap gap-2 mb-4">
        {DELIV_STEPS.map(([k, label]) => (
          <button key={k} data-testid={`deliv-${k}`} onClick={() => toggle(k)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold ring-1 ring-inset transition-colors ${form[k] === "Done" ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-50 text-ink-soft ring-line"}`}>
            {label} {form[k] === "Done" ? "✓" : ""}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Invoice Number"><Input value={form.invoiceNumber} onChange={set("invoiceNumber")} /></Field>
        <Field label="Chassis Number"><Input value={form.chassisNumber} onChange={set("chassisNumber")} /></Field>
        <Field label="Number Plate"><Input value={form.numberPlate} onChange={set("numberPlate")} /></Field>
        <Field label="Insurer Name"><Input value={form.insurerName} onChange={set("insurerName")} /></Field>
        <Field label="Delivery Date"><Input type="date" value={form.deliveryDate || ""} onChange={set("deliveryDate")} /></Field>
        <Field label="Mark Delivered?">
          <Select data-testid="delivered-select" value={form.delivered} onChange={set("delivered")} disabled={alreadyDelivered || !canMarkDelivered}>
            <option value="">Not yet</option><option value="Yes">Yes — Delivered</option>
          </Select>
        </Field>
      </div>
      <div className="flex justify-end mt-4"><Button data-testid="save-delivery-btn" onClick={save} disabled={!alreadyDelivered && !canMarkDelivered}>Save Delivery</Button></div>
    </div>
  );
}

/* -------------------------------------------------- Edit lead details */
function EditLeadModal({ lead, masters, onClose, onSaved }) {
  const [form, setForm] = useState({
    customerName: lead.customerName || "", mobile: lead.mobile || "", altMobile: lead.altMobile || "",
    village: lead.village || "", city: lead.city || "", leadSource: lead.leadSource || "Walk-in",
    interestedModel: lead.interestedModel || "", variant: lead.variant || "", executive: lead.executive || "",
    currentStatus: lead.currentStatus || "New", priority: lead.priority || "Normal", budget: lead.budget || 0,
    remarks: lead.remarks || "", financeRequired: lead.financeRequired || "No",
    exchangeRequired: lead.exchangeRequired || "No", nextFollowupDate: lead.nextFollowupDate || "",
  });
  const [variants, setVariants] = useState([]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  useEffect(() => { if (form.interestedModel) get("/price-master/variants", { model: form.interestedModel }).then(setVariants); }, [form.interestedModel]);

  const save = async () => {
    if (!form.customerName) return toast.error("Customer name is required");
    try {
      await put(`/leads/${lead.leadId}`, { ...form, budget: Number(form.budget) });
      toast.success("Lead updated");
      onSaved();
    } catch { toast.error("Update failed"); }
  };
  const m = masters || {};
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-2xl p-6 animate-fade-up max-h-[90vh] overflow-y-auto">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Edit Lead — {lead.leadId}</h3>
        <p className="text-xs text-ink-soft mb-4">Correct any details captured against this lead.</p>
        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2"><Field label="Customer Name *"><Input data-testid="edit-name" value={form.customerName} onChange={set("customerName")} /></Field></div>
          <Field label="Status"><Select data-testid="edit-status" value={form.currentStatus} onChange={set("currentStatus")}>{(m.statuses || ["New","Contacted","Follow-up","In Progress","Booked","Finance Process","Delivered","Lost"]).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Mobile"><Input data-testid="edit-mobile" value={form.mobile} onChange={set("mobile")} /></Field>
          <Field label="Alt Mobile"><Input value={form.altMobile} onChange={set("altMobile")} /></Field>
          <Field label="City"><Input value={form.city} onChange={set("city")} /></Field>
          <Field label="Village"><Input value={form.village} onChange={set("village")} /></Field>
          <Field label="Lead Source"><Select value={form.leadSource} onChange={set("leadSource")}>{(m.leadSources || []).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Executive"><Select value={form.executive} onChange={set("executive")}><option value="">—</option>{(m.executives || []).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Model"><Select value={form.interestedModel} onChange={set("interestedModel")}><option value="">—</option>{(m.models || []).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Variant"><Select value={form.variant} onChange={set("variant")}><option value="">—</option>{variants.map((v) => <option key={v.priceId} value={v.variant}>{v.variant}</option>)}</Select></Field>
          <Field label="Priority"><Select value={form.priority} onChange={set("priority")}>{(m.priorities || ["Low","Normal","High","Urgent"]).map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Budget (₹)"><Input type="number" value={form.budget} onChange={set("budget")} /></Field>
          <Field label="Finance Required"><Select value={form.financeRequired} onChange={set("financeRequired")}><option>No</option><option>Yes</option></Select></Field>
          <Field label="Exchange Required"><Select value={form.exchangeRequired} onChange={set("exchangeRequired")}><option>No</option><option>Yes</option></Select></Field>
          <Field label="Next Follow-up"><Input type="date" value={form.nextFollowupDate || ""} onChange={set("nextFollowupDate")} /></Field>
          <div className="col-span-3"><Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field></div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-edit-lead-btn" onClick={save}>Save Changes</Button>
        </div>
      </Card>
    </div>
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
    receivedPayout: 0, insuranceExecutive: lead.executive || "",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setRate = (e) => { setRateTouched(true); setForm((f) => ({ ...f, payoutRate: e.target.value })); };
  const load = useCallback(() => get("/insurance", { lead_id: lead.leadId }).then(setEntries), [lead.leadId]);
  useEffect(() => { load(); }, [load]);

  const premium = Number(form.insuranceAmount) || 0;
  const rate = Number(form.payoutRate) || 0;
  const expected = Math.round(premium * (rate / 100));

  const save = async () => {
    await post("/insurance", {
      leadId: lead.leadId, customerName: lead.customerName, mobile: lead.mobile,
      model: lead.interestedModel, variant: lead.variant,
      insuranceCompany: form.insuranceCompany, policyNumber: form.policyNumber,
      insuranceAmount: +form.insuranceAmount, payoutRate: +form.payoutRate,
      receivedPayout: +form.receivedPayout, insuranceExecutive: form.insuranceExecutive,
    });
    toast.success("Insurance entry added");
    setForm((f) => ({ ...f, policyNumber: "" }));
    load();
  };

  return (
    <div>
      <Card className="p-4 mb-4">
        <p className="text-xs text-ink-soft mb-3">Premium is pre-filled from this lead's price structure. Enter the insurer & payout rate.</p>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Insurer"><Input data-testid="lead-ins-company" value={form.insuranceCompany} onChange={set("insuranceCompany")} /></Field>
          <Field label="Policy Number"><Input value={form.policyNumber} onChange={set("policyNumber")} /></Field>
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
function ActivityTab({ lead, activities, masters, onSaved }) {
  const [form, setForm] = useState({ activityType: "Call", discussion: "", nextFollowup: "" });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const add = async () => {
    if (!form.discussion) return toast.error("Add a discussion note");
    await post(`/leads/${lead.leadId}/activities`, { ...form, executive: lead.executive });
    toast.success("Activity logged");
    setForm({ activityType: "Call", discussion: "", nextFollowup: "" });
    onSaved();
  };
  return (
    <div>
      <Card className="p-4 mb-4">
        <div className="grid grid-cols-4 gap-3 items-end">
          <Field label="Type"><Select value={form.activityType} onChange={set("activityType")}>{(masters?.activityTypes || []).map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <div className="col-span-2"><Field label="Discussion"><Input data-testid="activity-note" value={form.discussion} onChange={set("discussion")} /></Field></div>
          <Button data-testid="add-activity-btn" onClick={add}>Log</Button>
        </div>
      </Card>
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
      </div>
    </div>
  );
}

/* -------------------------------------------------- Modals */
function BookingModal({ lead, onClose, onDone }) {
  const [form, setForm] = useState({ bookingAmount: lead.bookingAmount || 5000, paymentMode: "UPI", financeRequired: lead.financeRequired || "No", exchangeRequired: lead.exchangeRequired || "No" });
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

  const priced = Number(lead.exShowroom) > 0;           // already has a price structure
  const canBook = priced || (preview && preview.found === true);
  const loading = preview === undefined;
  const ps = (preview && preview.priceStructure) || {};
  const charges = ["rto", "insuranceAmount", "accessoriesAmount", "handlingCharges", "trc", "fastag", "extendedWarranty", "otherCharges"];
  const gvc = Number(ps.exShowroom || 0) + charges.reduce((t, k) => t + Number(ps[k] || 0), 0);

  const submit = async () => {
    if (!canBook || busy) return;
    setBusy(true);
    try {
      const res = await post(`/leads/${lead.leadId}/convert-booking`, {
        bookingAmount: +form.bookingAmount, paymentMode: form.paymentMode, executive: lead.executive,
        financeRequired: form.financeRequired, exchangeRequired: form.exchangeRequired,
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

      {priced && preview && preview.found === false && (
        <p className="text-xs text-ink-soft mb-3">This lead already has a saved price structure, so booking is still allowed.</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field label="Advance Amount (₹)"><Input data-testid="booking-amount" type="number" value={form.bookingAmount} onChange={set("bookingAmount")} /></Field>
        <Field label="Payment Mode"><Select value={form.paymentMode} onChange={set("paymentMode")}>{["Cash","UPI","Cheque","NEFT","Card"].map((m) => <option key={m}>{m}</option>)}</Select></Field>
        <Field label="Finance Required"><Select value={form.financeRequired} onChange={set("financeRequired")}><option>No</option><option>Yes</option></Select></Field>
        <Field label="Exchange Required"><Select value={form.exchangeRequired} onChange={set("exchangeRequired")}><option>No</option><option>Yes</option></Select></Field>
      </div>
    </MiniModal>
  );
}

function CloseModal({ lead, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [rc, setRc] = useState(lead.rcStatus === "Yes" || lead.rcStatus === "Done" ? "Done" : "");
  const [plate, setPlate] = useState(lead.numberPlate || "");
  const delivered = (lead.deliveryStatus || "").toLowerCase() === "delivered" || (lead.currentStatus || "").toLowerCase() === "delivered";
  const submit = async () => {
    if (!reason.trim()) return toast.error("Close Reason is required");
    try {
      await post(`/leads/${lead.leadId}/close`, { closeReason: reason, rc, numberPlate: plate });
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
      <Field label="Close Reason"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Delivered & settled" /></Field>
    </MiniModal>
  );
}

function MiniModal({ title, children, onClose, onSubmit, submitLabel, danger, testid, submitDisabled }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-4">{title}</h3>
        {children}
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant={danger ? "danger" : "primary"} data-testid={testid} onClick={onSubmit} disabled={submitDisabled}>{submitLabel}</Button>
        </div>
      </Card>
    </div>
  );
}
