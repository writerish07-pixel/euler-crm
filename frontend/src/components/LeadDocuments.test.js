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

test("kycReady still requires Aadhaar and PAN for individuals", () => {
  expect(kycReady("Individual", {}, "")).toMatch(/Aadhaar/);
  expect(kycReady("Individual", {
    kyc_aadhaar_front: 1, kyc_aadhaar_back: 1, kyc_pan: 1,
  }, "")).toBe("");
});

test("kycReady makes Aadhaar optional for B2B", () => {
  expect(kycReady("B2B", { kyc_pan: 1, kyc_gst: 1 }, "22AAAAA0000A1Z5")).toBe("");
  expect(kycReady("B2B", { kyc_pan: 1, kyc_gst: 1 }, "")).toMatch(/GSTIN/);
  expect(kycReady("B2B", { kyc_pan: 1 }, "22AAAAA0000A1Z5")).toMatch(/GST/);
});
