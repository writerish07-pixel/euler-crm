/**
 * @jest-environment jsdom
 */
import { claimsNavItems, readClaimsDeskMode, writeClaimsDeskMode, CLAIMS_DESK_KEY } from "./claimsDeskMode";

const items = [
  { to: "/claims", label: "Scheme Claim Register" },
  { to: "/oem-claims", label: "OEM Claim Settlements" },
  { to: "/oem-claims/no-vehicle", label: "Missing chassis" },
  { to: "/oem-extra-support", label: "OEM Extra Support" },
];

beforeEach(() => {
  window.localStorage.removeItem(CLAIMS_DESK_KEY);
});

test("the new claims page is on until someone chooses the old screens", () => {
  expect(readClaimsDeskMode()).toBe("simple");
  expect(claimsNavItems(items, "simple").map((i) => i.to)).toEqual(["/claims", "/oem-extra-support"]);
  expect(claimsNavItems(items, "simple")[0].label).toBe("Claims");
});

test("classic mode puts the three registers back", () => {
  writeClaimsDeskMode("classic");
  expect(readClaimsDeskMode()).toBe("classic");
  expect(claimsNavItems(items, "classic").map((i) => i.label)).toEqual([
    "Scheme Claim Register",
    "OEM Claim Settlements",
    "Missing chassis",
    "OEM Extra Support",
  ]);
  writeClaimsDeskMode("simple");
  expect(readClaimsDeskMode()).toBe("simple");
});
