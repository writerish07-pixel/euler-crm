import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { get, post, apiErrorMessage, apiErrorDetail } from "../lib/api";
import { todayISO, digitsLast10 } from "../lib/format";
import { Button, Drawer, Field, Input, Select, MobileClashDialog } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { LocalKycBlock, kycReady, uploadKycFiles, extraSupportReady, LocalOemExtraBlock } from "../components/LeadDocuments";
import DealFormatCard from "../components/DealFormatCard";

function sameExecName(a, b) {
  return String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
}

/** Create / request a lead. Executives send for approval; TL / owner / GM create live. */
export default function NewLeadDrawer({ masters, onClose, onCreated, initial = {} }) {
  const { isExecutive, isTl, user, canSeeOwnerCommercials } = useAuth();
  const [form, setForm] = useState({
    customerName: initial.customerName || "",
    mobile: initial.mobile || "",
    city: initial.city || "",
    leadSource: initial.leadSource || "Walk-in",
    interestedModel: initial.interestedModel || "",
    variant: initial.variant || "",
    executive: initial.executive || (isExecutive ? (user?.name || "") : ""),
    priority: initial.priority || "Normal",
    budget: initial.budget || 0,
    remarks: initial.remarks || "",
    currentStatus: "New",
    createdDate: todayISO(),
    nextFollowupDate: "",
    customerType: initial.customerType || "Individual",
    gstin: initial.gstin || "",
    oemExtraSupportReceived: initial.oemExtraSupportReceived || "",
  });
  const [kyc, setKyc] = useState({});
  const [extraProof, setExtraProof] = useState({});
  const [busy, setBusy] = useState(false);
  const [variants, setVariants] = useState([]);
  const [deal, setDeal] = useState(null);
  const [dealLoading, setDealLoading] = useState(false);
  const [clash, setClash] = useState(null);
  const [passOn, setPassOn] = useState({});
  const [anotherVehicle, setAnotherVehicle] = useState(!!initial.anotherVehicle);
  const [matches, setMatches] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    if (form.interestedModel) get("/price-master/variants", { model: form.interestedModel }).then(setVariants);
    else setVariants([]);
    setPassOn({});
  }, [form.interestedModel, form.variant]);

  const passOnKeys = Object.keys(passOn).filter((k) => passOn[k]).join(",");

  useEffect(() => {
    if (!form.interestedModel || !form.variant) {
      setDeal(null);
      return undefined;
    }
    let alive = true;
    setDealLoading(true);
    get("/commercial/deal-preview", {
      model: form.interestedModel, variant: form.variant, cxDemand: Number(form.budget) || 0,
      passOnKeys: passOnKeys || undefined,
    }).then((d) => { if (alive) setDeal(d); })
      .catch(() => { if (alive) setDeal(null); })
      .finally(() => { if (alive) setDealLoading(false); });
    return () => { alive = false; };
  }, [form.interestedModel, form.variant, form.budget, passOnKeys]);

  useEffect(() => {
    const mobile = digitsLast10(form.mobile);
    if (!mobile) {
      setMatches(null);
      return undefined;
    }
    let alive = true;
    const t = setTimeout(() => {
      get("/leads/mobile-matches", { mobile })
        .then((d) => { if (alive) setMatches(d); })
        .catch(() => { if (alive) setMatches(null); });
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [form.mobile]);

  const togglePassOn = (key, yes, available) => {
    setPassOn((p) => ({ ...p, [key]: yes }));
    setForm((f) => {
      const cur = Number(f.budget) || Number(deal?.netToCx) || 0;
      const delta = yes ? -(Number(available) || 0) : (Number(available) || 0);
      return { ...f, budget: Math.max(0, cur + delta) };
    });
  };

  const incomingExec = isExecutive ? (user?.name || form.executive) : form.executive;
  const existingUnits = (matches && matches.existing) || [];
  const pendingUnits = (matches && matches.pending) || [];
  const otherExecHold = existingUnits.some((l) => {
    const held = String(l.executive || "").trim();
    if (!held) return false;
    return !sameExecName(held, incomingExec);
  }) || pendingUnits.some((p) => {
    const held = String(p.executive || "").trim();
    if (!held) return false;
    return !sameExecName(held, incomingExec);
  });
  // Executives cannot open a second file on another executive's mobile.
  // TL / owner / GM can add another unit when assigning to the same executive.
  const otherExecLock = isExecutive && otherExecHold;

  const saveLead = async (extra = {}) => {
    setBusy(true);
    try {
      const lead = await post("/leads", {
        ...form,
        budget: Number(form.budget),
        oemExtraSupportReceived: Number(form.oemExtraSupportReceived) || 0,
        schemePassOn: passOn,
        anotherVehicle: !!(extra.anotherVehicle || anotherVehicle),
        ...extra,
      });
      setClash(null);
      try {
        if (lead.pending && lead.requestId) {
          await uploadKycFiles(`/lead-requests/${lead.requestId}/documents`, { ...kyc, ...extraProof });
        } else if (lead.leadId) {
          await uploadKycFiles(`/leads/${lead.leadId}/documents`, { ...kyc, ...extraProof });
        }
      } catch (ue) {
        toast.error(apiErrorMessage(ue, "Lead saved but a KYC file failed — attach it again."));
      }
      if (lead.pending) {
        toast.success("Sent for approval");
        onCreated(null);
        return;
      }
      toast.success(`Lead ${lead.leadId} created`);
      onCreated(lead.leadId);
    } catch (e) {
      const detail = apiErrorDetail(e);
      if (e?.response?.status === 409 && detail && String(detail.code || "").startsWith("mobile_")) {
        setClash(detail);
        return;
      }
      toast.error(apiErrorMessage(e, "Failed to create lead"));
    } finally { setBusy(false); }
  };

  const submit = async () => {
    if (!form.customerName) return toast.error("Customer name is required");
    if (!form.createdDate) return toast.error("Lead date is required");
    if (isTl && !String(form.executive || "").trim()) return toast.error("Pick the executive this lead belongs to");
    if (isExecutive && !digitsLast10(form.mobile)) return toast.error("A 10-digit mobile is required before sending for approval");
    if (isExecutive && !(Number(form.budget) > 0)) return toast.error("Enter Cx Demand");
    if (anotherVehicle && !digitsLast10(form.mobile)) {
      return toast.error("Enter the 10-digit mobile this extra unit belongs to");
    }
    if (anotherVehicle && otherExecLock) {
      return toast.error("This mobile is already with another executive");
    }
    const kycErr = kycReady(form.customerType, kyc, form.gstin);
    if (kycErr) return toast.error(kycErr);
    const extraErr = extraSupportReady(form.oemExtraSupportReceived, extraProof);
    if (extraErr) return toast.error(extraErr);
    await saveLead({ anotherVehicle });
  };

  if (!masters) return null;
  const execOptions = [...(masters.executives || [])];
  if (isExecutive && user?.name && !execOptions.includes(user.name)) execOptions.unshift(user.name);
  const sources = masters.leadSources || [];
  const models = masters.models || [];
  const priorities = masters.priorities || ["Low", "Normal", "High", "Urgent"];
  return (
    <>
    <Drawer open onClose={onClose} width="max-w-2xl" title={isExecutive ? "Request a lead" : "New Lead"}
      subtitle={isExecutive ? "Sent for owner or GM approval" : isTl ? "Live lead assigned to any executive" : "Capture a fresh enquiry"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-lead-btn" onClick={submit} disabled={busy}>{busy ? "Saving…" : (isExecutive ? "Send for approval" : "Create Lead")}</Button></div>}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2"><Field label="Customer Name *"><Input data-testid="lead-name" value={form.customerName} onChange={set("customerName")} /></Field></div>
        <Field label="Lead Date"><Input data-testid="lead-date" type="date" value={form.createdDate} onChange={set("createdDate")} /></Field>
        <Field label="Next Follow-up"><Input data-testid="lead-followup" type="date" value={form.nextFollowupDate} onChange={set("nextFollowupDate")} /></Field>
        <Field label={isExecutive ? "Mobile *" : "Mobile"}><Input data-testid="lead-mobile" value={form.mobile} onChange={set("mobile")} inputMode="numeric" placeholder="10-digit mobile" /></Field>
        <Field label="City / Village"><Input value={form.city} onChange={set("city")} /></Field>
        <Field label="Customer type">
          <Select data-testid="lead-customer-type" value={form.customerType} onChange={set("customerType")}>
            <option>Individual</option>
            <option value="B2B">B2B</option>
          </Select>
        </Field>
        <Field label="Lead Source"><Select value={form.leadSource} onChange={set("leadSource")}>{sources.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label={isTl ? "Executive *" : "Executive"}>
          <Select data-testid="lead-executive" value={form.executive} onChange={set("executive")}>
            <option value="">—</option>
            {execOptions.map((s) => <option key={s}>{s}</option>)}
          </Select>
        </Field>
        <Field label="Interested Model"><Select data-testid="lead-model" value={form.interestedModel} onChange={set("interestedModel")}><option value="">—</option>{models.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Variant"><Select data-testid="lead-variant" value={form.variant} onChange={set("variant")}><option value="">—</option>{variants.map((v) => <option key={v.priceId} value={v.variant}>{v.variant}{v.inYard ? ` · ${v.inYard} in yard` : ""}</option>)}</Select></Field>
        <Field label="Priority"><Select value={form.priority} onChange={set("priority")}>{priorities.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <div className="sm:col-span-2 rounded-lg ring-1 ring-inset ring-line bg-zinc-50/70 p-3 space-y-2" data-testid="another-vehicle-block">
          <div className="text-xs font-semibold text-ink">Multi-unit on this mobile</div>
          <p className="text-[11px] text-ink-soft">
            One file is one vehicle. Same customer buying another unit (fleet / repeat)? Tick below
            so Euler keeps both files on this mobile.
          </p>
          {existingUnits.length > 0 && (
            <ul className="space-y-1" data-testid="mobile-unit-list">
              {existingUnits.map((l) => (
                <li key={l.leadId} className="text-xs text-ink">
                  <span className="font-mono font-semibold text-cobalt">{l.leadId}</span>
                  {" · "}{l.customerName || "—"}
                  {l.interestedModel ? ` · ${l.interestedModel}` : ""}
                  {l.variant ? ` ${l.variant}` : ""}
                  {l.executive ? ` · ${l.executive}` : ""}
                  {l.currentStatus ? ` · ${l.currentStatus}` : ""}
                </li>
              ))}
            </ul>
          )}
          {pendingUnits.length > 0 && (
            <p className="text-[11px] text-ink-soft" data-testid="mobile-pending-units">
              Waiting for approval: {pendingUnits.map((p) => [p.executive, p.requestId].filter(Boolean).join(" · ")).join(", ")}
            </p>
          )}
          {otherExecLock && (
            <p className="text-[11px] text-rose-700" data-testid="mobile-other-exec-lock">
              This mobile is already with another executive. You cannot add another unit here.
            </p>
          )}
          <label className="flex items-start gap-2 text-sm text-ink" data-testid="another-vehicle-check">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={anotherVehicle && !otherExecLock}
              disabled={otherExecLock}
              onChange={(e) => setAnotherVehicle(e.target.checked)}
            />
            <span>This is another vehicle / additional unit on this mobile</span>
          </label>
        </div>
        <div className="sm:col-span-2">
          <DealFormatCard
            snapshot={deal}
            cxDemand={form.budget}
            onCxDemand={(v) => setForm((f) => ({ ...f, budget: v }))}
            loading={dealLoading}
            missingPrice={!form.interestedModel || !form.variant}
            showOwnerPnl={!!canSeeOwnerCommercials}
            passOn={passOn}
            onPassOn={togglePassOn}
          />
        </div>
        <Field label="OEM Extra Support">
          <Input data-testid="lead-oem-extra" type="number" min="0" step="1"
            value={form.oemExtraSupportReceived} onChange={set("oemExtraSupportReceived")} />
        </Field>
        <LocalOemExtraBlock files={extraProof} setFiles={setExtraProof} amount={form.oemExtraSupportReceived} />
        <div className="sm:col-span-2"><Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field></div>
        <LocalKycBlock customerType={form.customerType} files={kyc} setFiles={setKyc} gstin={form.gstin} onGstin={(v) => setForm((f) => ({ ...f, gstin: v }))} />
      </div>
    </Drawer>
    <MobileClashDialog
      clash={clash}
      busy={busy}
      canOpenExisting={!(isExecutive && clash?.code === "mobile_other_executive")}
      onCancel={() => setClash(null)}
      onOpenExisting={(id) => { setClash(null); onCreated(id); }}
      onAnotherVehicle={() => { setAnotherVehicle(true); saveLead({ anotherVehicle: true }); }}
    />
    </>
  );
}
