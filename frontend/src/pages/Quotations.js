import React, { useEffect, useState, useCallback } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Button, Drawer, Field, Input, Select, Card } from "../components/ui";

const CHARGES = [["exShowroom","Ex-Showroom"],["registrationRto","RTO"],["insurance","Insurance"],["accessories","Accessories"],["handlingCharges","Handling"],["fastag","Fastag"],["trc","TRC"],["extendedWarranty","Ext. Warranty"],["otherCharges","Other"]];
const DISCS = [["consumerDiscount","Consumer"],["exchangeBonus","Exchange"],["loyaltyBonus","Loyalty"],["referralBonus","Referral"],["dsaDiscount","DSA"],["additionalDiscount","Additional"]];

export default function Quotations() {
  const [rows, setRows] = useState([]);
  const [show, setShow] = useState(false);
  const [masters, setMasters] = useState(null);
  const load = useCallback(() => get("/quotations").then(setRows), []);
  useEffect(() => { load(); get("/masters").then(setMasters); }, [load]);

  return (
    <div>
      <PageHeader title="Quotations" subtitle={`${rows.length} saved quotes`}
        actions={<Button data-testid="new-quote-btn" onClick={() => setShow(true)}><Plus size={16} /> New Quotation</Button>} />
      <Table
        rowKey="quoteId"
        columns={[
          { key: "quoteId", label: "Quote ID", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.quoteId}</span> },
          { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "model", label: "Vehicle", render: (r) => <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div> },
          { key: "grossVehicleCost", label: "Gross", align: "right", mono: true, render: (r) => inr(r.grossVehicleCost) },
          { key: "totalDiscount", label: "Discount", align: "right", mono: true, render: (r) => inr(r.totalDiscount) },
          { key: "customerPayable", label: "Payable", align: "right", mono: true, render: (r) => <span className="font-bold text-cobalt">{inr(r.customerPayable)}</span> },
        ]}
        rows={rows}
        empty="No quotations yet"
      />
      {show && <QuoteDrawer masters={masters} onClose={() => setShow(false)} onSaved={() => { setShow(false); load(); }} />}
    </div>
  );
}

function QuoteDrawer({ masters, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    const f = { customerName: "", mobile: "", model: "", variant: "", finalExchangeValue: 0, financer: "", narration: "" };
    [...CHARGES, ...DISCS].forEach(([k]) => (f[k] = 0));
    return f;
  });
  const [variants, setVariants] = useState([]);
  const [preview, setPreview] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => { if (form.model) get("/price-master/variants", { model: form.model }).then(setVariants); }, [form.model]);

  const applyVariant = (variant) => {
    const v = variants.find((x) => x.variant === variant);
    setForm((f) => ({ ...f, variant, ...(v ? { exShowroom: v.exShowroom, registrationRto: v.rto, insurance: v.insurance, accessories: v.accessories, handlingCharges: v.handlingCharges, trc: v.trc, fastag: v.fastag, extendedWarranty: v.extendedWarranty, otherCharges: v.otherCharges } : {}) }));
  };

  useEffect(() => {
    const body = {}; [...CHARGES, ...DISCS].forEach(([k]) => (body[k] = +form[k]));
    body.finalExchangeValue = +form.finalExchangeValue; body.tcsApplicable = "No"; body.benefitMode = "Full Benefit";
    post("/commercial/compute", body).then(setPreview);
  }, [form]);

  const save = async () => {
    if (!form.customerName) return toast.error("Customer name required");
    const body = { customerName: form.customerName, mobile: form.mobile, model: form.model, variant: form.variant, financer: form.financer, narration: form.narration, finalExchangeValue: +form.finalExchangeValue };
    [...CHARGES, ...DISCS].forEach(([k]) => (body[k] = +form[k]));
    await post("/quotations", body);
    toast.success("Quotation saved");
    onSaved();
  };

  if (!masters) return null;
  return (
    <Drawer open onClose={onClose} width="max-w-3xl" title="New Quotation" subtitle="Build a deal quote with live commercial math"
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-quote-btn" onClick={save}>Save Quotation</Button></div>}>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Field label="Customer Name *"><Input data-testid="quote-name" value={form.customerName} onChange={set("customerName")} /></Field>
        <Field label="Mobile"><Input value={form.mobile} onChange={set("mobile")} /></Field>
        <div />
        <Field label="Model"><Select value={form.model} onChange={set("model")}><option value="">—</option>{masters.models.map((m) => <option key={m}>{m}</option>)}</Select></Field>
        <div className="col-span-2"><Field label="Variant (auto-fills price)"><Select value={form.variant} onChange={(e) => applyVariant(e.target.value)}><option value="">—</option>{variants.map((v) => <option key={v.priceId} value={v.variant}>{v.variant}{v.inYard ? ` · ${v.inYard} in yard` : ""}</option>)}</Select></Field></div>
      </div>
      <h4 className="font-heading font-bold text-ink text-sm mb-2">Charges</h4>
      <div className="grid grid-cols-3 gap-3">
        {CHARGES.map(([k, l]) => <Field key={k} label={l}><Input type="number" value={form[k]} onChange={set(k)} /></Field>)}
      </div>
      <h4 className="font-heading font-bold text-ink text-sm mb-2 mt-4">Discounts / Scheme</h4>
      <div className="grid grid-cols-3 gap-3">
        {DISCS.map(([k, l]) => <Field key={k} label={l}><Input type="number" value={form[k]} onChange={set(k)} /></Field>)}
        <Field label="Exchange Value"><Input type="number" value={form.finalExchangeValue} onChange={set("finalExchangeValue")} /></Field>
      </div>
      {preview && (
        <Card className="p-4 mt-4 bg-cobalt-tint/40 border-cobalt/20">
          <div className="grid grid-cols-4 gap-3 text-center">
            <P label="Gross" v={preview.grossVehicleCost} />
            <P label="Total Discount" v={preview.totalDiscount} />
            <P label="OEM Share" v={preview.claim.claimEligible} />
            <P label="Customer Payable" v={preview.customerPayable} hi />
          </div>
        </Card>
      )}
    </Drawer>
  );
}

const P = ({ label, v, hi }) => (
  <div>
    <div className="text-[11px] text-ink-faint uppercase">{label}</div>
    <div className={`font-mono font-bold ${hi ? "text-cobalt text-lg" : "text-ink"}`}>{inr(v)}</div>
  </div>
);
