// Shared colours for the two-way claim cross-check.
//
// OEM_MATCH colours a Scheme Claim Register row by whether Euler filed it.
// REGISTER_MATCH colours an OEM Claim Settlements row by whether this register
// raised it. They are deliberately different palettes so "we never asked" and
// "they filed something we don't have" cannot be confused with each other.

export const OEM_MATCH = {
  accepted:    { label: "Approved in Euler", tone: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", row: "" },
  filed:       { label: "Filed with Euler",  tone: "bg-blue-50 text-blue-700 ring-blue-600/20",          row: "" },
  resubmitted: { label: "Refiled",           tone: "bg-sky-50 text-sky-700 ring-sky-600/20",             row: "" },
  rejected:    { label: "Rejected — refile", tone: "bg-rose-100 text-rose-800 ring-rose-600/30",         row: "bg-rose-50/60" },
  cancelled:   { label: "Cancelled in OEM",  tone: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",         row: "bg-zinc-50/60" },
  not_filed:   { label: "Not claimed",       tone: "bg-red-50 text-red-700 ring-red-600/20",             row: "bg-red-50/50" },
  unmapped:    { label: "Check match",       tone: "bg-amber-50 text-amber-800 ring-amber-600/20",       row: "bg-amber-50/40" },
  not_applicable: { label: "", tone: "", row: "" },
};

export const REGISTER_MATCH = {
  in_register:      { label: "Matched",                 tone: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", row: "" },
  partial:          { label: "Part matched",            tone: "bg-amber-50 text-amber-800 ring-amber-600/20",      row: "bg-amber-50/40" },
  missing_register: { label: "Not in scheme register",  tone: "bg-violet-50 text-violet-800 ring-violet-600/20",   row: "bg-violet-50/50" },
  unmapped:         { label: "Check match",             tone: "bg-amber-50 text-amber-800 ring-amber-600/20",      row: "bg-amber-50/40" },
  unknown_lead:     { label: "No lead matched",         tone: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",        row: "bg-zinc-50/80" },
};

export const oemMatchOf = (r) => OEM_MATCH[r?.oemMatch?.state] || OEM_MATCH.not_applicable;
export const registerMatchOf = (r) => REGISTER_MATCH[r?.registerMatch?.state] || REGISTER_MATCH.unknown_lead;

const COMPONENT_LABEL = {
  rtoInsuranceBenefit: "RTO + Insurance",
  insuranceBenefit: "Insurance Benefit",
  rtoBenefit: "RTO Benefit",
  referralBonus: "Referral",
  loyaltyBonus: "Loyalty",
  exchangeBonus: "Exchange",
  consumerDiscount: "Consumer Discount",
  dsaDiscount: "DSA",
  oemExtraSupport: "OEM Extra Support",
  additionalDiscount: "Additional Discount",
};

export function componentLabel(key) {
  return COMPONENT_LABEL[key] || key || "";
}

export const CREATE_COMPONENTS = Object.entries(COMPONENT_LABEL);

function asIdList(value) {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (value == null || value === "") return [];
  return [String(value)].filter(Boolean);
}

export function lineLeadIds(li) {
  if (!li || typeof li !== "object") return [];
  const ids = asIdList(li.leadIds);
  if (li.leadId && !ids.includes(String(li.leadId))) ids.unshift(String(li.leadId));
  return ids;
}

export function rowLeadIds(row) {
  return lineLeadIds({ leadIds: row?.leadIds, leadId: row?.leadId });
}

export function rowLineItems(row) {
  const raw = row?.lineItems;
  if (!Array.isArray(raw)) return [];
  return raw.filter((li) => li && typeof li === "object");
}

/** Same rule as the OEM claims list: a chassis or a source invoice counts. */
export function claimHasVehicle(row) {
  return rowLineItems(row).some((li) =>
    lineChassisList(li).length > 0 || String(li?.sourceInvoiceNumber || "").trim());
}

/** Scheme register work. Rejected wins over not-filed. */
export function schemeClaimJob(row) {
  const state = row?.oemMatch?.state || "";
  if (state === "rejected") return "rejected";
  if (state === "not_filed") return "not_claimed";
  return "";
}

/** Euler work. A missing chassis is its own job, even when the lead is also blank. */
export function eulerClaimJob(row) {
  if (!claimHasVehicle(row)) return "missing_chassis";
  if (!rowLeadIds(row).length) return "no_lead";
  return "";
}

export function lineLeadLabel(li, leadId) {
  const ids = lineLeadIds(li);
  const names = li?.leadCustomers || [];
  const i = ids.indexOf(leadId);
  if (i >= 0 && names[i]) return names[i];
  if (li?.leadId === leadId) return li.leadCustomer || "";
  return "";
}

/** Extra Support prose like `5000+5000=10000` + two names joined by &. */
export function lineChassisList(li) {
  if (!li || typeof li !== "object") return [];
  if (Array.isArray(li.chassisList) && li.chassisList.length) {
    return li.chassisList.map((c) => String(c || "").trim()).filter(Boolean);
  }
  const one = String(li.chassis || "").trim();
  return one ? [one] : [];
}

export function looksCombinedSupport(li) {
  const blob = `${li?.description || ""}`;
  if (/\d+\s*\+\s*\d+\s*=/.test(blob)) return true;
  const names = String(li?.customerName || "");
  return /\s+&\s+/.test(names) || /\band\b/i.test(names);
}

/** OEM Additional Discount is dealer-funded and not on the scheme register.
 *  Staff file Extra Support under that Coulson chip — Match must list Extra Support. */
export function registerMatchKeys(relatedKey) {
  const key = String(relatedKey || "").trim();
  if (!key) return [];
  if (key === "additionalDiscount") return ["oemExtraSupport"];
  return [key];
}

/** Lead options for the OEM Match dropdown. Never hide every file because the
 *  OEM chip mapped to a component the register does not use. */
export function matchRegisterLeadRows(poolRows, relatedKey) {
  const rows = Array.isArray(poolRows) ? poolRows : [];
  const keys = registerMatchKeys(relatedKey);
  if (!keys.length) return rows;
  const scoped = rows.filter((r) => keys.includes(r.componentKey));
  return scoped.length ? scoped : rows;
}

export function isOpenRegisterRow(r) {
  return !["Received", "Dropped", "Cancelled"].includes(r?.claimStatus || "") && !r?.relinkable;
}

export function isRelinkableRegisterRow(r) {
  return !!r?.relinkable;
}

/** Extra Support pack units that can still join this OEM claim.
 *  Relink also lists unmatched open units so a newly created debit note can
 *  attach the remaining vehicles of the same lead. */
export function matchableExtraUnitRows(register, leadId, relink = false) {
  const rows = (Array.isArray(register) ? register : []).filter((r) => (
    r.leadId === leadId
    && r.componentKey === "oemExtraSupport"
    && Number(r.unitSno) > 0
  ));
  const picked = rows.filter((r) => (
    relink ? (isRelinkableRegisterRow(r) || isOpenRegisterRow(r)) : isOpenRegisterRow(r)
  ));
  return [...new Map(picked.map((r) => [Number(r.unitSno), r])).values()]
    .sort((a, b) => Number(a.unitSno) - Number(b.unitSno));
}

/** One dropdown option per lead — pack units are ticked separately. */
export function extraSupportLeadOptions(rows) {
  const out = [];
  const seen = new Set();
  for (const r of rows || []) {
    const id = r.leadId;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(r);
  }
  return out;
}

/** Unit sno(s) to send with Extra Support Match. One leftover unit still counts. */
export function extraSupportMatchUnitSnos(packUnits, unitSnos, unitSno) {
  const ticked = (Array.isArray(unitSnos) ? unitSnos : []).map(Number).filter((n) => n > 0);
  if (ticked.length) return [...new Set(ticked)];
  const remaining = (Array.isArray(packUnits) ? packUnits : [])
    .map((r) => Number(r?.unitSno))
    .filter((n) => n > 0);
  if (remaining.length === 1) return remaining;
  const one = Number(unitSno);
  return one > 0 ? [one] : [];
}

export function lineNeedsCreate(row, li) {
  const st = row?.registerMatch?.state || "";
  if (st === "in_register") return false;
  return st === "missing_register" || st === "unknown_lead" || st === "unmapped"
    || st === "partial" || !lineLeadIds(li).length;
}

/** Euler's own wording for a debit-note line (customer, claim type, approver). */
export function oemLineText(li) {
  const desc = String(li?.description || "").trim();
  if (desc) return desc;
  const bits = [li?.claimType, li?.customerName, li?.approvedBy && `Approved By :- ${li.approvedBy}`]
    .filter(Boolean);
  return bits.join(" · ") || componentLabel(li?.componentKey) || "Claim item";
}

export function oemClaimsHref({ q, chassis, invoice, leadId, noVehicle } = {}) {
  if (noVehicle) return "/oem-claims/no-vehicle";
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (chassis) p.set("chassis", chassis);
  if (invoice) p.set("invoice", invoice);
  if (leadId) p.set("leadId", leadId);
  const qs = p.toString();
  return qs ? `/oem-claims?${qs}` : "/oem-claims";
}

export function claimsHref({ leadId } = {}) {
  const p = new URLSearchParams();
  if (leadId) p.set("leadId", leadId);
  const qs = p.toString();
  return qs ? `/claims?${qs}` : "/claims";
}

export function DocFlag({ yes, url, count, lines, documented }) {
  const on = !!yes;
  const n = Number(count) || 0;
  const total = Number(lines) || 0;
  const done = Number(documented) || 0;
  return (
    <div className="flex flex-col items-start gap-0.5">
      <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${
        on ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-red-50 text-red-700 ring-red-600/20"
      }`}>{on ? "Yes" : "No"}</span>
      {total > 1 ? (
        <span className={`text-[10px] leading-tight ${on ? "text-ink-faint" : "text-rose-600"}`}>
          {done} of {total} items
        </span>
      ) : on && n > 0 ? (
        <span className="text-[10px] text-ink-faint">{n} file{n === 1 ? "" : "s"}</span>
      ) : null}
      {!on ? (
        <span className="text-[10px] text-ink-faint max-w-[90px] leading-tight">Upload in OEM app</span>
      ) : null}
      {url ? (
        <a href={url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
          className="text-[10px] text-cobalt hover:underline">PDF</a>
      ) : null}
    </div>
  );
}
