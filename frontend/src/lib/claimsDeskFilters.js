import { eulerClaimJob, lineChassisList, rowLeadIds, rowLineItems, schemeClaimJob } from "./claimMatch";

/** Same split the Scheme Claim Register uses for its four money cards. */
export function isIncentiveClaim(row) {
  return String(row?.componentKey || "").startsWith("executiveIncentive")
    || /executive incentive/i.test(String(row?.component || row?.claimType || ""));
}

export function normChassis(value) {
  return String(value || "").replace(/\s+/g, "").trim().toUpperCase();
}

function lineBlob(row) {
  const lines = rowLineItems(row);
  return [
    row?.claimNumber,
    row?.status,
    rowLeadIds(row).join(" "),
    lines.flatMap(lineChassisList).join(" "),
    lines.map((li) => li.sourceInvoiceNumber || "").join(" "),
    lines.map((li) => li.leadCustomer || li.customerName || "").join(" "),
    lines.map((li) => li.description || "").join(" "),
  ].join(" ").toLowerCase();
}

function chassisHit(row, chassis) {
  const want = normChassis(chassis);
  if (!want) return true;
  return rowLineItems(row).flatMap(lineChassisList).some((ch) => normChassis(ch) === want);
}

function invoiceHit(row, invoice) {
  const want = String(invoice || "").trim().toLowerCase();
  if (!want) return true;
  return rowLineItems(row).some((li) => String(li.sourceInvoiceNumber || "").trim().toLowerCase() === want);
}

/** Server unlinked filter is linkedLineCount. Fall back to lead ids only when the field was not sent. */
export function eulerUnlinked(row) {
  if (row?.linkedLineCount != null) return !Number(row.linkedLineCount);
  return !rowLeadIds(row).length;
}

/**
 * Euler Claim Settlements list. The main list leaves out claims with no
 * chassis or invoice, unless a search is on or the missing-chassis job is open.
 * Settled, rejected, and cancelled claims stay on the main list.
 */
export function eulerRowVisible(row, {
  view = "euler",
  job = "",
  leadId = "",
  chassis = "",
  invoice = "",
  q = "",
  status = "",
  unlinked = false,
  missingDoc = false,
  registerMatch = "",
} = {}) {
  if (leadId && !rowLeadIds(row).includes(leadId)) return false;
  if (!chassisHit(row, chassis)) return false;
  if (!invoiceHit(row, invoice)) return false;
  if (q && !lineBlob(row).includes(String(q).trim().toLowerCase())) return false;
  if (job === "missing_chassis") return eulerClaimJob(row) === "missing_chassis";
  if (job === "no_lead") return eulerClaimJob(row) === "no_lead";
  if (view !== "euler") return false;
  const join = Boolean(String(q || "").trim() || chassis || invoice || leadId);
  if (!join && eulerClaimJob(row) === "missing_chassis") return false;
  if (status && String(row?.status || "") !== status) return false;
  if (unlinked && !eulerUnlinked(row)) return false;
  if (missingDoc && row?.hasDocument) return false;
  if (registerMatch && String(row?.registerMatch?.state || "") !== registerMatch) return false;
  return true;
}

/** Scheme register list. Every status stays visible. A job or a cross-check chip narrows it. */
export function schemeRowVisible(row, {
  view = "ours",
  job = "",
  leadId = "",
  match = "",
  q = "",
} = {}) {
  if (leadId && row?.leadId !== leadId) return false;
  if (job === "not_claimed" || job === "rejected") return schemeClaimJob(row) === job;
  if (view !== "ours") return false;
  if (match && String(row?.oemMatch?.state || "not_applicable") !== match) return false;
  if (q) {
    const blob = `${row?.customer || ""} ${row?.leadId || ""} ${row?.chassisNumber || ""} ${row?.invoiceNumber || ""} ${row?.component || ""} ${(row?.oemMatch?.claimNumbers || []).join(" ")}`.toLowerCase();
    if (!blob.includes(String(q).trim().toLowerCase())) return false;
  }
  return true;
}
