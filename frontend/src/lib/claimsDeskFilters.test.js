/**
 * @jest-environment node
 */
import { eulerRowVisible, isIncentiveClaim, schemeRowVisible } from "./claimsDeskFilters";

const filed = {
  claimId: "C-OPEN",
  leadId: "LD1",
  customer: "Ramesh",
  claimStatus: "Received",
  component: "Consumer Offer",
  oemMatch: { state: "filed", claimNumbers: ["DN1"] },
};
const incentive = {
  claimId: "C-INC",
  leadId: "LD2",
  componentKey: "executiveIncentive",
  component: "Executive Incentive",
  claimStatus: "Eligible",
  oemMatch: { state: "not_applicable" },
};
const settled = {
  claimNumber: "DN-SETTLED",
  status: "Settled",
  terminal: true,
  linkedLineCount: 1,
  hasDocument: true,
  leadIds: ["LD9"],
  lineItems: [{ chassis: "MD9ABC", sourceInvoiceNumber: "INV9", leadIds: ["LD9"], description: "Referral" }],
  registerMatch: { state: "in_register" },
};
const missing = {
  claimNumber: "DN-MISS",
  status: "Submitted",
  terminal: false,
  linkedLineCount: 0,
  hasDocument: false,
  leadIds: [],
  lineItems: [{ description: "No vehicle", leadIds: [] }],
  registerMatch: { state: "unknown_lead" },
};

test("scheme list keeps received rows and incentive rows", () => {
  expect(schemeRowVisible(filed, { view: "ours" })).toBe(true);
  expect(schemeRowVisible(incentive, { view: "ours" })).toBe(true);
  expect(isIncentiveClaim(incentive)).toBe(true);
  expect(isIncentiveClaim(filed)).toBe(false);
});

test("euler list keeps settled claims and leaves missing chassis for its own job", () => {
  expect(eulerRowVisible(settled, { view: "euler" })).toBe(true);
  expect(eulerRowVisible(missing, { view: "euler" })).toBe(false);
  expect(eulerRowVisible(missing, { view: "euler", job: "missing_chassis" })).toBe(true);
  expect(eulerRowVisible(settled, { view: "euler", q: "md9abc" })).toBe(true);
  expect(eulerRowVisible(settled, { view: "euler", chassis: "md9 abc" })).toBe(true);
  expect(eulerRowVisible(settled, { view: "euler", chassis: "OTHER" })).toBe(false);
  expect(eulerRowVisible(missing, { view: "euler", q: "no vehicle" })).toBe(true);
});
