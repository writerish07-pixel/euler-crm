/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockOemSold = { current: { matched: false } };

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url).includes("insurance-agents")) return Promise.resolve([]);
    if (String(url).includes("oem-sold")) return Promise.resolve(mockOemSold.current);
    if (String(url).includes("oem-claims")) return Promise.resolve({ claims: [], schemeRegister: [] });
    return Promise.resolve({});
  },
  put: jest.fn(() => Promise.resolve({})),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../components/LeadDocuments", () => ({
  LeadDocsStrip: () => null,
  kycKinds: [],
}));

import { DeliveryTab } from "./LeadDrawer";

function bookedLead(over = {}) {
  return {
    leadId: "LD-DEL-UI",
    customerName: "Delivery Customer",
    interestedModel: "Turbo Max",
    variant: "Maxx (PV)",
    customerOutstanding: 0,
    insuranceArrangedBy: "dealer",
    ...over,
  };
}

async function renderDelivery(props = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <DeliveryTab
        lead={bookedLead()}
        actions={{ canDeliver: true, isDelivered: false, isActive: true }}
        isOwner={false}
        delivery={{}}
        onSaved={() => {}}
        {...props}
      />,
    );
  });
  await act(async () => { await Promise.resolve(); });
  return { host, root };
}

test("TL delivery tab does not ask for a chassis dropdown", async () => {
  mockOemSold.current = { matched: false };
  const { host, root } = await renderDelivery();
  expect(host.querySelector('[data-testid="delivery-oem-ids-hint"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="delivery-oem-waiting"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="delivered-select"]')).toBeTruthy();
  const chassis = host.querySelector('[data-testid="delivery-chassis"]');
  expect(chassis).toBeTruthy();
  expect(chassis.tagName).toBe("INPUT");
  expect(chassis.disabled).toBe(true);
  expect(host.querySelector("option")?.textContent || "").not.toMatch(/Select chassis/i);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("same-order pack shows S.No. chassis table from OEM Sold", async () => {
  mockOemSold.current = {
    matched: true,
    chassis: "MD9PACK1",
    invoiceNumber: "CINV-1",
    units: [
      { sno: 1, chassis: "MD9PACK1", invoiceNumber: "CINV-1", model: "Turbo Max", variant: "Maxx (PV)" },
      { sno: 2, chassis: "MD9PACK2", invoiceNumber: "CINV-2", model: "Turbo Max", variant: "Maxx (PV)" },
      { sno: 3, chassis: "MD9PACK3", invoiceNumber: "CINV-3", model: "Storm", variant: "Storm LR (PV)" },
    ],
  };
  const { host, root } = await renderDelivery({
    lead: bookedLead({
      sameOrderMultiUnit: true,
      vehicleCount: 3,
      units: [
        { sno: 1, model: "Turbo Max", variant: "Maxx (PV)" },
        { sno: 2, model: "Turbo Max", variant: "Maxx (PV)" },
        { sno: 3, model: "Storm", variant: "Storm LR (PV)" },
      ],
    }),
    oemSold: mockOemSold.current,
  });
  expect(host.querySelector('[data-testid="delivery-units-table"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="delivery-unit-chassis-1"]').value).toBe("MD9PACK1");
  expect(host.querySelector('[data-testid="delivery-unit-chassis-2"]').value).toBe("MD9PACK2");
  expect(host.querySelector('[data-testid="delivery-unit-invoice-3"]').value).toBe("CINV-3");
  expect(host.querySelector('[data-testid="delivery-chassis"]')).toBeFalsy();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("OEM Sold match fills chassis without typing", async () => {
  mockOemSold.current = {
    matched: true,
    chassis: "MD9SOLDFILL0001",
    invoiceNumber: "CINV-9001",
  };
  const { host, root } = await renderDelivery({
    oemSold: mockOemSold.current,
  });
  expect(host.querySelector('[data-testid="delivery-sold-match"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="delivery-chassis"]').value).toBe("MD9SOLDFILL0001");
  expect(host.querySelector('[data-testid="delivery-invoice"]').value).toBe("CINV-9001");
  expect(host.querySelector('[data-testid="delivery-oem-waiting"]')).toBeFalsy();
  await act(async () => { root.unmount(); });
  host.remove();
});
