/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    const path = String(url || "");
    if (path.indexOf("/masters") >= 0) {
      return Promise.resolve({ models: ["Turbo Max", "Storm"] });
    }
    if (path.indexOf("price-master/variants") >= 0) {
      return Promise.resolve([{ priceId: "p1", variant: "Maxx (PV)", inYard: 1 }]);
    }
    if (path.indexOf("commercial/deal-preview") >= 0) {
      return Promise.resolve({
        exShowroom: 785000, rto: 5500, insurance: 19000, priceTotal: 809500,
        netToCx: 809500, priceFound: true, needsApproval: false,
      });
    }
    if (path.indexOf("/documents") >= 0) return Promise.resolve([]);
    return Promise.resolve({});
  },
  post: jest.fn(() => Promise.resolve({ bookingId: "BK1", lead: { customerPayable: 809500 } })),
  downloadPost: jest.fn(() => Promise.resolve()),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../components/LeadDocuments", () => ({
  LocalKycBlock: () => <div data-testid="kyc-block" />,
  LocalOemExtraBlock: () => <div data-testid="oem-extra-proof-block" />,
  kycReady: () => "",
  extraSupportReady: () => "",
  dealSheetReady: () => "",
  LocalDealSheetBlock: () => <div data-testid="deal-sheet-block" />,
  PrintDealSheetButton: () => <button type="button">Print</button>,
  uploadKycFiles: () => Promise.resolve(),
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canSeeOwnerCommercials: false, isExecutive: true }),
}));
jest.mock("../components/CallLink", () => () => null);

import BookEnquiryDrawer from "./BookEnquiryDrawer";

test("convert to booking asks for model, deal and KYC — not the old advance-only dialog", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <BookEnquiryDrawer
        lead={{ leadId: "LD26009901", customerName: "Walk In", mobile: "9876500011", executive: "Executive" }}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const drawer = document.querySelector('[data-testid="drawer-root"]') || host;
  expect(drawer.querySelector('[data-testid="book-enquiry-drawer"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="book-model"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="book-variant"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="kyc-block"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="confirm-booking-btn"]')).toBeTruthy();
  expect(drawer.textContent).toMatch(/KYC/i);
  await act(async () => { root.unmount(); });
  host.remove();
});
