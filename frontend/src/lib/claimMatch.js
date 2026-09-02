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
  not_filed:   { label: "Not claimed",       tone: "bg-red-50 text-red-700 ring-red-600/20",             row: "bg-red-50/50" },
  unmapped:    { label: "Check match",       tone: "bg-amber-50 text-amber-800 ring-amber-600/20",       row: "bg-amber-50/40" },
  not_applicable: { label: "", tone: "", row: "" },
};

export const REGISTER_MATCH = {
  in_register:      { label: "In scheme register",      tone: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", row: "" },
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

export function oemClaimsHref({ q, chassis, invoice, leadId } = {}) {
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
