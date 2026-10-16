/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("react-router-dom", () => ({ Link: ({ children }) => children }));
jest.mock("../lib/api", () => ({
  put: () => Promise.resolve({}),
  get: (url) => {
    if (String(url).includes("oem-claims")) return Promise.resolve({ claims: [], schemeRegister: [] });
    if (String(url).includes("scheme-rules")) return Promise.resolve({ rules: {} });
    return Promise.resolve({});
  },
  post: () => Promise.resolve({}),
  del: () => Promise.resolve({}),
  apiErrorMessage: (e, fallback) => fallback,
  apiErrorDetail: () => ({}),
  downloadFile: () => Promise.resolve(),
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
jest.mock("../components/SchemeCircularPic", () => () => null);
jest.mock("../components/TallyPackCheck", () => () => null);
jest.mock("./DealVerify", () => ({ DealVerifyCard: () => null }));

import { Overview, OverviewUnits, SchemeTab, unitSource } from "./LeadDrawer";

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

test("pack overview groups additional dealer discount per unit", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <Overview
        lead={{
          leadId: "LD-PACK-ADDL",
          sameOrderMultiUnit: true,
          cxDemand: 1770000,
          budget: 1770000,
          additionalDiscount: 50000,
          units: [
            { sno: 1, model: "Turbo Max", additionalDiscount: 20000, cxDemand: 580000, customerPayable: 580000 },
            { sno: 2, model: "Storm", additionalDiscount: 30000, cxDemand: 1190000, customerPayable: 1190000 },
          ],
        }}
        c={{ grossVehicleCost: 1800000, tcs: 0, totalDiscount: 50000, totalPassedToCustomer: 50000 }}
        actions={{}}
        onSaved={() => {}}
      />,
    );
  });
  expect(host.querySelector('[data-testid="pack-additional-discount-group"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="owner-field-additionalDiscount-unit-1"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="owner-field-additionalDiscount-unit-2"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Pack Additional/);
  await act(async () => { root.unmount(); });
  host.remove();
});

async function renderScheme({ isOwner = true, dealLocked = true } = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <SchemeTab
        lead={{
          leadId: "LD-SCHEME-ADDL",
          cxDemand: dealLocked ? 960000 : 0,
          budget: dealLocked ? 960000 : 0,
          useDealPrice: dealLocked,
          additionalDiscount: 29500,
          interestedModel: "Storm",
          variant: "Storm TR",
        }}
        c={{}}
        actions={{ canScheme: true }}
        isOwner={isOwner}
        masters={{}}
        onSaved={() => {}}
      />,
    );
  });
  return { host, root };
}

test("owner can edit additional when Cx Demand locks the deal", async () => {
  const { host, root } = await renderScheme({ isOwner: true, dealLocked: true });
  const input = host.querySelector('[data-testid="scheme-additionalDiscount"]');
  expect(input).toBeTruthy();
  expect(input.disabled).toBe(false);
  expect(input.readOnly).toBe(false);
  expect(host.textContent).toMatch(/Owner can set Additional/);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("staff additional stays locked when Cx Demand is the deal", async () => {
  const { host, root } = await renderScheme({ isOwner: false, dealLocked: true });
  const input = host.querySelector('[data-testid="scheme-additionalDiscount"]');
  expect(input).toBeTruthy();
  expect(input.disabled).toBe(true);
  expect(input.readOnly).toBe(true);
  await act(async () => { root.unmount(); });
  host.remove();
});
