/** Lead Register holds booked files. Follow-up Lead Register holds enquiries. */

export function isBookedRegisterLead(lead) {
  const st = String(lead?.currentStatus || lead?.status || "").toLowerCase();
  if (st.includes("book") || st.includes("finance") || st.includes("deliver") || st.includes("close won")) {
    return true;
  }
  return Boolean(lead?.bookingDate || lead?.bookingId);
}

export function openLeadPath(leadId, lead) {
  const id = encodeURIComponent(String(leadId || lead?.leadId || ""));
  if (!id) return "/followup-leads";
  if (lead && isBookedRegisterLead(lead)) return `/leads?open=${id}`;
  return `/followup-leads?open=${id}`;
}
