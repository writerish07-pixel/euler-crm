/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("react-router-dom", () => ({ Link: ({ children }) => children }));
jest.mock("../lib/api", () => ({
  put: jest.fn(() => Promise.resolve({})),
  get: jest.fn(() => Promise.resolve({})),
  post: jest.fn(() => Promise.resolve({})),
  del: jest.fn(() => Promise.resolve({})),
  apiErrorMessage: (e, fallback) => fallback,
  apiErrorDetail: () => ({}),
  downloadFile: jest.fn(() => Promise.resolve()),
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ isOwner: true, isTl: true, isSalesGm: false, isExecutive: false, isAccounts: false, canSeeOwnerCommercials: true }),
}));
jest.mock("./NewLeadDrawer", () => () => null);
jest.mock("./LeadWhatsApp", () => () => null);
jest.mock("../components/LeadDocuments", () => ({
  LeadDocsStrip: () => null,
  kycKinds: () => [],
  extraSupportReady: () => "",
  B2bGstinField: () => null,
  RefundChequePick: () => null,
  PrintDealSheetButton: () => null,
}));
jest.mock("../components/CallLink", () => () => null);
jest.mock("../components/CompleteFormatDrawer", () => () => null);
jest.mock("./BookEnquiryDrawer", () => () => null);

import { OverviewUnits, unitSource } from "./LeadDrawer";

function packLead() {
  return {
    leadId: "LD-OVER-UNITS",
    customerPayable: 1580000,
    vehicleCount: 2,
    units: [
      { sno: 1, model: "Turbo Max", variant: "Maxx (DV220)", customerPayable: 790000,
        soldDate: "2026-09-30", deliveryDate: "2026-09-15",
        oemBilledBodyType: "DV220", availableBodyType: "FB" },
      { sno: 2, model: "Turbo Max", variant: "Maxx (FB)", customerPayable: 790000, soldDate: "" },
    ],
  };
}

async function renderUnits(props = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <OverviewUnits
        lead={packLead()}
        canAddPackUnit
        canAddAnotherVehicle
        canEditBilledDate
        onAddPackUnit={() => {}}
        onAddAnotherVehicle={() => {}}
        onOpenUnit={() => {}}
        onSaved={() => {}}
        {...props}
      />,
    );
  });
  return { host, root };
}

test("Details units area has add-unit, add-vehicle and billed-date edit", async () => {
  const { host, root } = await renderUnits();
  expect(host.querySelector('[data-testid="overview-add-pack-unit-btn"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="overview-add-another-vehicle-btn"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="unit-billed-btn-1"]')?.textContent).toMatch(/Billed/i);
  expect(host.querySelector('[data-testid="unit-billed-btn-2"]')?.textContent).toMatch(/Set billed date/i);
  expect(host.querySelector('[data-testid="pack-delivery-date-group"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="unit-delivered-btn-1"]')?.textContent).toMatch(/Delivered|delivery date/i);
  expect(host.querySelector('[data-testid="unit-delivered-btn-2"]')).toBeTruthy();
  expect(host.textContent).toMatch(/billed date/i);
  expect(host.textContent).toMatch(/delivery date/i);
  expect(host.textContent).toMatch(/billed DV220 · available FB/);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("pack unit 1 source keeps own payable not the pack total", () => {
  const lead = {
    sameOrderMultiUnit: true,
    customerPayable: 9645210,
    cxDemand: 9645210,
    budget: 9645210,
    grossVehicleCost: 9645210,
    useDealPrice: true,
    additionalDiscount: 476000,
    units: [
      { sno: 1, model: "Turbo Max", variant: "Maxx (DV220)", additionalDiscount: 59500,
        customerPayable: 790000, exShowroom: 825000 },
      { sno: 2, model: "Turbo Max", variant: "Maxx (DV220)", additionalDiscount: 59500,
        customerPayable: 790000, exShowroom: 825000 },
    ],
  };
  const u1 = unitSource(lead, lead.units[0], 0);
  expect(u1.customerPayable).toBe(790000);
  expect(u1.cxDemand).toBeUndefined();
  expect(u1.useDealPrice).toBeUndefined();
  expect(u1.additionalDiscount).toBe(59500);
  const missing = unitSource(lead, { sno: 1, model: "Turbo Max", additionalDiscount: 59500 }, 0);
  expect(missing.customerPayable).toBe(0);
  expect(missing.cxDemand).toBeUndefined();
});
