/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockAuth = {
  canSeeOwnerCommercials: false,
  isExecutive: true,
  isTeamLead: false,
};

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
        schemeMonth: "2026-10",
        schemeOffers: [
          { key: "loyaltyBonus", label: "Loyalty Bonus", schemeAvailable: 10000 },
          { key: "freeInsurance", label: "Free Insurance Up To", schemeAvailable: 10000 },
        ],
        schemePassed: 0,
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
  useAuth: () => mockAuth,
}));
jest.mock("../components/CallLink", () => () => null);

import BookEnquiryDrawer from "./BookEnquiryDrawer";

const SCHEME_LEAD = {
  leadId: "LD26009901",
  customerName: "Walk In",
  mobile: "9876500011",
  executive: "Executive",
  interestedModel: "Turbo Max",
  variant: "Maxx (PV)",
  dealFormat: {
    exShowroom: 785000, rto: 5500, insurance: 19000, priceTotal: 809500,
    netToCx: 809500, priceFound: true,
    schemeMonth: "2026-10",
    schemeOffers: [
      { key: "loyaltyBonus", label: "Loyalty Bonus", schemeAvailable: 10000 },
      { key: "freeInsurance", label: "Free Insurance Up To", schemeAvailable: 10000 },
    ],
  },
};

async function renderBookDrawer(lead = SCHEME_LEAD) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <BookEnquiryDrawer lead={lead} onClose={() => {}} onDone={() => {}} />,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const drawer = document.querySelector('[data-testid="drawer-root"]') || host;
  return { host, root, drawer };
}

test("convert to booking asks for model, deal and KYC — not the old advance-only dialog", async () => {
  mockAuth.isExecutive = true;
  mockAuth.isTeamLead = false;
  const { host, root, drawer } = await renderBookDrawer({
    leadId: "LD26009901", customerName: "Walk In", mobile: "9876500011", executive: "Executive",
  });
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

test("executive convert to booking hides OEM scheme offers and pass-on radios", async () => {
  mockAuth.isExecutive = true;
  mockAuth.isTeamLead = false;
  const { host, root, drawer } = await renderBookDrawer();
  expect(drawer.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="deal-oem-scheme"]')).toBeFalsy();
  expect(drawer.querySelector('[data-testid="pass-yes-loyaltyBonus"]')).toBeFalsy();
  expect(drawer.textContent).not.toMatch(/Loyalty Bonus/i);
  expect(drawer.textContent).not.toMatch(/OEM scheme/i);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("team leader convert to booking hides OEM scheme offers and pass-on radios", async () => {
  mockAuth.isExecutive = false;
  mockAuth.isTeamLead = true;
  const { host, root, drawer } = await renderBookDrawer();
  expect(drawer.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="deal-oem-scheme"]')).toBeFalsy();
  expect(drawer.querySelector('[data-testid="pass-yes-loyaltyBonus"]')).toBeFalsy();
  expect(drawer.textContent).not.toMatch(/Loyalty Bonus/i);
  expect(drawer.textContent).not.toMatch(/OEM scheme/i);
  await act(async () => { root.unmount(); });
  host.remove();
});
