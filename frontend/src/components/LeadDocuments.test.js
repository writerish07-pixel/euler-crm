/**
 * @jest-environment jsdom
 */
import { extraSupportReady, kycReady } from "./LeadDocuments";

test("extra support proof is required only when amount is filled", () => {
  expect(extraSupportReady(0, {})).toBe("");
  expect(extraSupportReady("", {})).toBe("");
  expect(extraSupportReady(7000, {})).toMatch(/Siddharth Dubey/);
  expect(extraSupportReady(7000, { oem_extra_support: { name: "mail.png" } })).toBe("");
  expect(extraSupportReady(7000, {}, [{ kind: "oem_extra_support" }])).toBe("");
});

test("kycReady still requires Aadhaar and PAN", () => {
  expect(kycReady("Individual", {}, "")).toMatch(/Aadhaar/);
  expect(kycReady("Individual", {
    kyc_aadhaar_front: 1, kyc_aadhaar_back: 1, kyc_pan: 1,
  }, "")).toBe("");
});
