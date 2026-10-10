/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { extraSupportReady, kycReady, dealSheetReady, LocalDealSheetBlock } from "./LeadDocuments";

global.IS_REACT_ACT_ENVIRONMENT = true;

test("extra support proof is required only when amount is filled", () => {
  expect(extraSupportReady(0, {})).toBe("");
  expect(extraSupportReady("", {})).toBe("");
  expect(extraSupportReady(7000, {})).toMatch(/Siddharth Dubey/);
  expect(extraSupportReady(7000, { oem_extra_support: { name: "mail.png" } })).toBe("");
  expect(extraSupportReady(7000, {}, [{ kind: "oem_extra_support" }])).toBe("");
  expect(extraSupportReady(7000, {}, [], { copyFromSibling: true })).toBe("");
});

test("kycReady still requires Aadhaar and PAN for individuals", () => {
  expect(kycReady("Individual", {}, "")).toMatch(/Aadhaar/);
  expect(kycReady("Individual", {
    kyc_aadhaar_front: 1, kyc_aadhaar_back: 1, kyc_pan: 1,
  }, "")).toBe("");
});

test("kycReady makes Aadhaar optional for B2B", () => {
  expect(kycReady("B2B", { kyc_pan: 1, kyc_gst: 1 }, "22AAAAA0000A1Z5")).toBe("");
  expect(kycReady("B2B", { kyc_pan: 1, kyc_gst: 1 }, "")).toBe("");
  expect(kycReady("B2B", { kyc_pan: 1 }, "22AAAAA0000A1Z5")).toMatch(/GST/);
});

test("dealSheetReady is required unless the file or an existing scan is present", () => {
  expect(dealSheetReady({})).toMatch(/deal sheet/i);
  expect(dealSheetReady({ deal_sheet: { name: "sheet.pdf" } })).toBe("");
  expect(dealSheetReady({}, [{ kind: "deal_sheet" }])).toBe("");
  expect(dealSheetReady({}, [{ kind: "kyc_pan" }])).toMatch(/deal sheet/i);
});

test("deal sheet block offers print then upload", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const onPrint = jest.fn();
  await act(async () => {
    root.render(
      <LocalDealSheetBlock files={{}} setFiles={() => {}} onPrint={onPrint} />,
    );
  });
  expect(host.textContent).toMatch(/Print the deal sheet, get the customer to sign/i);
  const btn = host.querySelector('[data-testid="print-deal-sheet-btn"]');
  expect(btn).toBeTruthy();
  await act(async () => { btn.click(); });
  expect(onPrint).toHaveBeenCalled();
  await act(async () => { root.unmount(); });
  host.remove();
});
