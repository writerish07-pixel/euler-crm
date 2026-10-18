/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url) === "/accounts/dashboard") {
      return Promise.resolve({
        lastUpdated: "2026-10-18T10:00:00+00:00",
        kpis: {
          collectedMtd: 1, collectedYtd: 1, deliveriesMtd: 1, deliveriesYtd: 1,
          customerOutstanding: 5000, financeOutstanding: 0, financePendingFiles: 0,
          oemClaimsOpen: 0, oemClaimsOpenCount: 0, insurancePayoutDue: 0, insuranceOpenCount: 0,
          deliveredForTally: 1, cancelledRefundDue: 0, cancelledRefundHeld: 0,
        },
        doNotPost: { note: "Do not add", oemClaimsOutstanding: 0, schemeOrOemExtraRetained: 0 },
        tallyQueue: [{
          leadId: "LD-ACCT-1", customerName: "Pay Me", executive: "Amit",
          invoiceNumber: "INV-1", deliveryDate: "2026-10-01",
          customerPayable: 100000, totalReceived: 10000, customerOutstanding: 90000,
          vehicleCount: 2, tallyInvoicesUploaded: 0, tallyLedgerComplete: false,
        }],
        cancelledRefundQueue: [],
      });
    }
    return Promise.resolve({});
  },
  post: jest.fn(),
  apiErrorMessage: (e, fallback) => fallback || String(e),
}));
jest.mock("../components/ReportActions", () => () => <div />);
jest.mock("../components/YardStockCard", () => () => <div />);
jest.mock("../components/LeadDocuments", () => ({ LeadDocsStrip: () => null, RefundChequePick: () => null }));
jest.mock("../components/TallyUnitBooks", () => {
  const Comp = () => null;
  Comp.TallyPackInvoiceSections = () => null;
  return { __esModule: true, default: Comp, TallyPackInvoiceSections: () => null };
});
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ isOwner: false, isAccounts: true }),
}));

import AccountsDashboard from "./AccountsDashboard";

test("accounts dashboard tells staff how to upload Tally and payments", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<MemoryRouter><AccountsDashboard /></MemoryRouter>);
  });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector('[data-testid="accounts-howto"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Customer money/);
  expect(host.textContent).toMatch(/Tally GST/);
  expect(host.querySelector('[data-testid="record-pay-LD-ACCT-1"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="acct-go-payments"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
  host.remove();
});
