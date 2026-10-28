/**
 * @jest-environment node
 */
import {
  claimHasVehicle,
  eulerClaimJob,
  extraSupportLeadOptions,
  extraSupportMatchUnitSnos,
  looksCombinedSupport,
  matchRegisterLeadRows,
  matchableExtraUnitRows,
  registerMatchKeys,
  schemeClaimJob,
} from "./claimMatch";

test("Additional Discount Claim matches Extra Support register rows", () => {
  expect(registerMatchKeys("additionalDiscount")).toEqual(["oemExtraSupport"]);
  expect(registerMatchKeys("oemExtraSupport")).toEqual(["oemExtraSupport"]);
  expect(registerMatchKeys("loyaltyBonus")).toEqual(["loyaltyBonus"]);
  expect(registerMatchKeys("")).toEqual([]);
});

test("match dropdown lists Extra Support when OEM chip is Additional Discount", () => {
  const pool = [
    { leadId: "LD26000893", componentKey: "oemExtraSupport", customer: "Kapoor", unitSno: 1 },
    { leadId: "LD2", componentKey: "loyaltyBonus", customer: "Other", unitSno: 0 },
  ];
  const rows = matchRegisterLeadRows(pool, "additionalDiscount");
  expect(rows).toHaveLength(1);
  expect(rows[0].leadId).toBe("LD26000893");
});

test("match dropdown falls back to unmatched files when the OEM type has no rows", () => {
  const pool = [
    { leadId: "LD26000893", componentKey: "oemExtraSupport", customer: "Kapoor" },
  ];
  const rows = matchRegisterLeadRows(pool, "loyaltyBonus");
  expect(rows).toEqual(pool);
});

test("pack Extra Support units stay matchable until each one is connected", () => {
  const register = [
    { leadId: "LD26000554", componentKey: "oemExtraSupport", unitSno: 1, claimAmount: 48000 },
    { leadId: "LD26000554", componentKey: "oemExtraSupport", unitSno: 2, claimAmount: 48000 },
    { leadId: "LD26000554", componentKey: "oemExtraSupport", unitSno: 5, claimAmount: 48000, relinkable: true, linkedOemClaimNumber: "AF-OLD" },
    { leadId: "LD26000554", componentKey: "oemExtraSupport", unitSno: 6, claimAmount: 48000 },
    { leadId: "LD26000554", componentKey: "loyaltyBonus", unitSno: 1 },
  ];
  const open = matchableExtraUnitRows(register, "LD26000554", false).map((r) => r.unitSno);
  expect(open).toEqual([1, 2, 6]);
  const relink = matchableExtraUnitRows(register, "LD26000554", true).map((r) => r.unitSno);
  expect(relink).toEqual([1, 2, 5, 6]);
  expect(extraSupportLeadOptions(register).map((r) => r.leadId)).toEqual(["LD26000554"]);
});

test("one leftover Extra Support unit still sends that unit sno", () => {
  const leftover = [{ leadId: "LD26000893", unitSno: 2, claimAmount: 4000 }];
  expect(extraSupportMatchUnitSnos(leftover, [], null)).toEqual([2]);
  expect(extraSupportMatchUnitSnos(leftover, [2], null)).toEqual([2]);
  expect(extraSupportMatchUnitSnos(
    [{ unitSno: 1 }, { unitSno: 2 }], [], null)).toEqual([]);
  expect(extraSupportMatchUnitSnos(
    [{ unitSno: 1 }, { unitSno: 2 }], [2], null)).toEqual([2]);
});

test("invoice copy & mail is not a combined Extra Support amount", () => {
  expect(looksCombinedSupport({
    description: "Additiniol support documents invoice copy & mail approval",
    customerName: "Kapoor Freight Carriers pvt ltd",
  })).toBe(false);
  expect(looksCombinedSupport({
    description: "5000+5000=10000",
    customerName: "A & B",
  })).toBe(true);
  expect(looksCombinedSupport({
    description: "Extra Support",
    customerName: "Swapna Creations & Swarna Creations",
  })).toBe(true);
});

test("claim jobs split unfiled, rejected, no lead, and missing chassis", () => {
  expect(schemeClaimJob({ oemMatch: { state: "not_filed" } })).toBe("not_claimed");
  expect(schemeClaimJob({ oemMatch: { state: "rejected" } })).toBe("rejected");
  expect(schemeClaimJob({ oemMatch: { state: "filed" } })).toBe("");
  const missing = { leadIds: [], lineItems: [{ description: "No vehicle" }] };
  expect(claimHasVehicle(missing)).toBe(false);
  expect(eulerClaimJob(missing)).toBe("missing_chassis");
  const noLead = {
    leadIds: [],
    lineItems: [{ chassis: "MD9XYZ", sourceInvoiceNumber: "INV1" }],
  };
  expect(eulerClaimJob(noLead)).toBe("no_lead");
  expect(eulerClaimJob({
    leadIds: ["LD1"],
    lineItems: [{ chassis: "MD9XYZ", leadIds: ["LD1"] }],
  })).toBe("");
});
