/**
 * @jest-environment node
 */
import {
  looksCombinedSupport,
  matchRegisterLeadRows,
  registerMatchKeys,
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
