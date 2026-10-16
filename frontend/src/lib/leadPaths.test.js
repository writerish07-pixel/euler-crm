import { isBookedRegisterLead, openLeadPath } from "./leadPaths";

test("unbooked enquiry opens on follow-up register", () => {
  const lead = { leadId: "LD1", currentStatus: "New" };
  expect(isBookedRegisterLead(lead)).toBe(false);
  expect(openLeadPath("LD1", lead)).toBe("/followup-leads?open=LD1");
});

test("booked file opens on lead register", () => {
  const lead = { leadId: "LD2", currentStatus: "Booked", bookingDate: "2026-10-10" };
  expect(isBookedRegisterLead(lead)).toBe(true);
  expect(openLeadPath("LD2", lead)).toBe("/leads?open=LD2");
});
