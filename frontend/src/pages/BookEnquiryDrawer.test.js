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

const previewState = {
  needsApproval: false,
  additionalDiscount: 0,
  docs: [],
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
        netToCx: 809500, priceFound: true,
        needsApproval: previewState.needsApproval,
        additionalDiscount: previewState.additionalDiscount,
        schemeMonth: "2026-10",
        schemeOffers: [
          { key: "loyaltyBonus", label: "Loyalty Bonus", schemeAvailable: 10000 },
          { key: "freeInsurance", label: "Free Insurance Up To", schemeAvailable: 10000 },
        ],
        schemePassed: 0,
      });
    }
    if (path.indexOf("/documents") >= 0) return Promise.resolve(previewState.docs);
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

import BookEnquiryDrawer, { bookingDealAlreadyApproved } from "./BookEnquiryDrawer";

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
  expect(drawer.querySelector('[data-testid="deal-additional"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("after GM approval convert to booking confirms instead of sending again", async () => {
  mockAuth.isExecutive = true;
  mockAuth.isTeamLead = false;
  previewState.needsApproval = true;
  previewState.additionalDiscount = 44500;
  previewState.docs = [
    { kind: "deal_sheet", filename: "sheet.jpg", documentId: "DC1" },
    { kind: "kyc_aadhaar_front", filename: "front.jpg", documentId: "DC2" },
    { kind: "kyc_aadhaar_back", filename: "back.jpg", documentId: "DC3" },
    { kind: "kyc_pan", filename: "pan.jpg", documentId: "DC4" },
  ];
  const { host, root, drawer } = await renderBookDrawer({
    ...SCHEME_LEAD,
    leadId: "LD26000928",
    customerName: "Ghanshyam saini",
    budget: 945000,
    cxDemand: 945000,
    bookingDealApprovedAt: "2026-10-16T12:00:00+00:00",
    bookingDealCxDemand: 945000,
    bookingDealAdditional: 44500,
  });
  const btn = drawer.querySelector('[data-testid="confirm-booking-btn"]');
  expect(btn.textContent).toMatch(/Confirm Booking/i);
  expect(btn.textContent).not.toMatch(/Send for approval/i);
  expect(drawer.textContent).toMatch(/already approved/i);
  expect(drawer.querySelector('[data-testid="deal-sheet-block"]')).toBeFalsy();
  previewState.needsApproval = false;
  previewState.additionalDiscount = 0;
  previewState.docs = [];
  await act(async () => { root.unmount(); });
  host.remove();
});

test("discounted convert without prior approval still sends for approval", async () => {
  mockAuth.isExecutive = true;
  mockAuth.isTeamLead = false;
  previewState.needsApproval = true;
  previewState.additionalDiscount = 44500;
  const { host, root, drawer } = await renderBookDrawer({
    ...SCHEME_LEAD,
    budget: 945000,
    cxDemand: 945000,
  });
  const btn = drawer.querySelector('[data-testid="confirm-booking-btn"]');
  expect(btn.textContent).toMatch(/Send for approval/i);
  expect(drawer.querySelector('[data-testid="deal-sheet-block"]')).toBeTruthy();
  previewState.needsApproval = false;
  previewState.additionalDiscount = 0;
  await act(async () => { root.unmount(); });
  host.remove();
});

test("bookingDealAlreadyApproved matches Cx Demand and additional within a rupee", () => {
  expect(bookingDealAlreadyApproved({
    bookingDealApprovedAt: "2026-10-16T12:00:00+00:00",
    bookingDealCxDemand: 945000,
    bookingDealAdditional: 44500,
  }, 945000, 44500)).toBe(true);
  expect(bookingDealAlreadyApproved({
    bookingDealApprovedAt: "2026-10-16T12:00:00+00:00",
    bookingDealCxDemand: 945000,
    bookingDealAdditional: 44500,
  }, 900000, 44500)).toBe(false);
  expect(bookingDealAlreadyApproved({}, 945000, 44500)).toBe(false);
});

test("team leader convert to booking hides OEM scheme offers and pass-on radios", async () => {
  mockAuth.isExecutive = false;
  mockAuth.isTeamLead = true;
  const { host, root, drawer } = await renderBookDrawer();
  expect(drawer.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="deal-oem-scheme"]')).toBeFalsy();
  expect(drawer.querySelector('[data-testid="pass-yes-loyaltyBonus"]')).toBeFalsy();
  expect(drawer.textContent).not.toMatch(/Loyalty Bonus/i);
  await act(async () => { root.unmount(); });
  host.remove();
});
