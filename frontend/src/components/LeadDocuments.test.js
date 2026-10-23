/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { extraSupportReady, kycReady, dealSheetReady, LocalDealSheetBlock, LocalKycBlock, acceptForKind, hintForKind, fitImageForUpload, DOC_MAX_BYTES, docMatchesUnit, docMatchesUnitSnos } from "./LeadDocuments";

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

test("B2B KYC shows GSTIN and GST certificate instead of required Aadhaar", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <LocalKycBlock
        customerType="B2B"
        files={{}}
        setFiles={() => {}}
        gstin=""
        onGstin={() => {}}
      />,
    );
  });
  expect(host.textContent).toMatch(/B2B needs PAN, GST certificate and GSTIN/);
  expect(host.querySelector('[data-testid="lead-gstin"]')).toBeTruthy();
  expect(host.textContent).toMatch(/GST certificate/);
  expect(host.textContent).toMatch(/Optional for B2B/);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("KYC slots show files already on the lead instead of No file", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <LocalKycBlock
        customerType="Individual"
        files={{}}
        setFiles={() => {}}
        gstin=""
        onGstin={() => {}}
        existingDocs={[
          { kind: "kyc_aadhaar_front", filename: "front.jpg", documentId: "DC1", contentType: "image/jpeg" },
          { kind: "kyc_aadhaar_back", filename: "back.jpg", documentId: "DC2", contentType: "image/jpeg" },
          { kind: "kyc_pan", filename: "pan.jpg", documentId: "DC3", contentType: "image/jpeg" },
        ]}
      />,
    );
  });
  expect(host.textContent).toMatch(/Already attached/i);
  expect(host.textContent).toMatch(/front\.jpg/);
  expect(host.textContent).not.toMatch(/No file/);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("docMatchesUnit treats a legacy file as unit 1 only", () => {
  expect(docMatchesUnit({ kind: "delivery_insurance" }, 1)).toBe(true);
  expect(docMatchesUnit({ kind: "delivery_insurance" }, 2)).toBe(false);
  expect(docMatchesUnit({ kind: "delivery_insurance", unitSno: 2 }, 2)).toBe(true);
  expect(docMatchesUnit({ kind: "delivery_insurance", unitSno: 2 }, 1)).toBe(false);
  expect(docMatchesUnit({ kind: "kyc_pan" }, 0)).toBe(true);
});

test("docMatchesUnitSnos matches a combined ledger group exactly", () => {
  expect(docMatchesUnitSnos({ kind: "tally_ledger", unitSnos: [1, 2] }, [2, 1])).toBe(true);
  expect(docMatchesUnitSnos({ kind: "tally_ledger", unitSno: 1 }, [1])).toBe(true);
  expect(docMatchesUnitSnos({ kind: "tally_ledger", unitSnos: [1, 2] }, [1])).toBe(false);
});

test("dealSheetReady is required unless the file or an existing scan is present", () => {
  expect(dealSheetReady({})).toMatch(/deal sheet/i);
  expect(dealSheetReady({ deal_sheet: { name: "sheet.pdf" } })).toBe("");
  expect(dealSheetReady({}, [{ kind: "deal_sheet" }])).toBe("");
  expect(dealSheetReady({}, [{ kind: "kyc_pan" }])).toMatch(/deal sheet/i);
});

test("two deal-sheet Camera/File pickers do not share the same input", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <>
        <LocalDealSheetBlock files={{}} setFiles={() => {}} />
        <LocalDealSheetBlock files={{}} setFiles={() => {}} />
      </>,
    );
  });
  const fileInputs = [...host.querySelectorAll('input[type="file"]')].filter((el) => !el.hasAttribute("capture"));
  const ids = fileInputs.map((el) => el.id);
  expect(ids.length).toBe(2);
  expect(new Set(ids).size).toBe(2);
  const labels = [...host.querySelectorAll('[data-testid="book-deal-sheet-file"]')];
  expect(labels.length).toBe(2);
  expect(labels[0].getAttribute("for")).not.toBe(labels[1].getAttribute("for"));
  await act(async () => { root.unmount(); });
  host.remove();
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

test("tally invoice slot accepts a ZIP; KYC does not", () => {
  expect(acceptForKind("tally_invoice")).toMatch(/zip/i);
  expect(hintForKind("tally_invoice")).toMatch(/ZIP/);
  expect(acceptForKind("tally_ledger")).toMatch(/zip/i);
  expect(hintForKind("tally_ledger")).toMatch(/ZIP/);
  expect(acceptForKind("kyc_pan")).not.toMatch(/zip/i);
  expect(hintForKind("kyc_pan")).toMatch(/PDF/);
  expect(hintForKind("oem_extra_support")).toMatch(/8 MB/);
  expect(DOC_MAX_BYTES).toBe(8 * 1024 * 1024);
});

test("fitImageForUpload leaves a small PDF alone", async () => {
  const pdf = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "mail.pdf", { type: "application/pdf" });
  const out = await fitImageForUpload(pdf);
  expect(out).toBe(pdf);
});

test("fitImageForUpload leaves a large PDF alone even without a type", async () => {
  const pdf = new File([new Uint8Array(4 * 1024 * 1024)], "mail.pdf", { type: "" });
  const out = await fitImageForUpload(pdf);
  expect(out).toBe(pdf);
});
