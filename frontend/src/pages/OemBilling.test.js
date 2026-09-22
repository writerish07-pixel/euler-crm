/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockBilling = {
  current: {
    soldCount: 2,
    counts: {
      pending_delivery: 1,
      created_from_oem: 1,
      matched_delivered: 0,
      needs_review: 0,
      unmatched: 0,
    },
    rows: [
      {
        chassis: "MD9PENDUI01",
        invoiceNumber: "INV-1",
        mobile: "9811100111",
        customerName: "Pending Person",
        model: "Turbo Max",
        variant: "Maxx (PV)",
        soldDate: "2026-09-04",
        undated: false,
        bucket: "pending_delivery",
        leadId: "LD-PEND-UI",
        crmStatus: "Booked",
      },
      {
        chassis: "MD9NEWUI01",
        invoiceNumber: "INV-2",
        mobile: "9811100222",
        customerName: "Created Person",
        model: "Hi-Load",
        variant: "XR",
        soldDate: "2026-09-05",
        undated: false,
        bucket: "created_from_oem",
        leadId: "LD-NEW-UI",
        crmStatus: "New",
        oemBillingCreated: true,
      },
    ],
  },
};

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url).includes("/oem-billing")) return Promise.resolve(mockBilling.current);
    if (String(url).includes("/masters")) return Promise.resolve({ models: [] });
    return Promise.resolve({});
  },
  post: jest.fn(() => Promise.resolve(mockBilling.current)),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canEditCommercials: true, isOwner: true }),
}));
jest.mock("../components/LeadLink", () => ({
  useLeadDrawer: () => ({ openLead: jest.fn(), drawer: null }),
  LeadLink: ({ leadId }) => <button type="button" data-testid={`lead-link-${leadId}`}>{leadId}</button>,
}));

import OemBilling from "./OemBilling";

test("OEM billing tab shows pending delivery without asking for chassis", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<OemBilling />);
  });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector('[data-testid="oem-billing"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="oem-bill-card-pending"]').textContent).toMatch(/1/);
  expect(host.querySelector('[data-testid="oem-billing-sync"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Pending Person/);
  expect(host.textContent).not.toMatch(/Select chassis/i);
  await act(async () => { root.unmount(); });
  host.remove();
});
