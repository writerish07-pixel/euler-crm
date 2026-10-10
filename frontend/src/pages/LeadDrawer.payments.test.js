/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

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
  useAuth: () => ({ isExecutive: true, isOwner: false, isTl: false, isTeamLead: false }),
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

import { PaymentsTab, receiptPaymentModes } from "./LeadDrawer";

test("receipt modes always include Finance for the executive add-payment form", () => {
  expect(receiptPaymentModes(null)).toContain("Finance");
  expect(receiptPaymentModes({ paymentModes: ["Cash", "UPI"] })).toContain("Finance");
  expect(receiptPaymentModes({ paymentModes: ["Cash", "UPI", "Cheque", "NEFT", "Finance"] })).toContain("Finance");
});

test("executive payments tab lists Finance in the mode dropdown", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <PaymentsTab
        lead={{ leadId: "LD-PAY", customerPayable: 100000, totalReceived: 0, currentStatus: "Booked" }}
        actions={{ canPayment: true, canFinanceReceipt: true, isBooked: true }}
        payments={[]}
        masters={{ paymentModes: ["Cash", "UPI", "Cheque", "NEFT", "Finance"], financers: ["IDFC"] }}
        onSaved={() => {}}
      />,
    );
  });
  const select = host.querySelector('[data-testid="payment-mode"]');
  expect(select).toBeTruthy();
  const options = [...select.querySelectorAll("option")].map((o) => o.textContent);
  expect(options).toContain("Finance");
  await act(async () => { root.unmount(); });
  host.remove();
});
