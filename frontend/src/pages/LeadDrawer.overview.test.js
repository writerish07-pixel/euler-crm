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
}));
jest.mock("../components/CallLink", () => () => null);
jest.mock("../components/CompleteFormatDrawer", () => () => null);

import { OverviewUnits } from "./LeadDrawer";

function packLead() {
  return {
    leadId: "LD-OVER-UNITS",
    customerPayable: 1580000,
    vehicleCount: 2,
    units: [
      { sno: 1, model: "Turbo Max", variant: "Maxx (FB)", customerPayable: 790000, soldDate: "2026-09-30" },
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
  expect(host.textContent).toMatch(/billed date/i);
  await act(async () => { root.unmount(); });
  host.remove();
});
