/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { CLAIMS_DESK_KEY } from "../lib/claimsDeskMode";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canSyncOemClaims: false, isMoneyDesk: false }),
}));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (url === "/claims") {
      return Promise.resolve([{
        claimId: "C1",
        leadId: "LD1",
        customer: "Ramesh",
        component: "Consumer Offer",
        componentKey: "consumerOffer",
        eligibleClaim: 5000,
        receivedAmount: 0,
        chassisNumber: "CHS1",
        invoiceNumber: "INV1",
        oemMatch: { state: "not_filed", claimNumbers: [] },
        claimStatus: "Eligible",
      }]);
    }
    if (url === "/oem-claims") {
      return Promise.resolve([{
        claimNumber: "DN9",
        status: "Submitted",
        claimedAmount: 8000,
        approvedAmount: 0,
        lineItems: [{ lineId: "L1", description: "No vehicle", leadIds: [] }],
        leadIds: [],
        registerMatch: { state: "unknown_lead" },
        terminal: false,
      }]);
    }
    return Promise.resolve([]);
  },
  post: jest.fn(() => Promise.resolve({})),
  apiErrorMessage: (_e, fallback) => fallback,
}));

import ClaimsDesk from "./ClaimsDesk";

beforeEach(() => {
  window.localStorage.removeItem(CLAIMS_DESK_KEY);
});

test("jobs open the unfiled claim and the old screens stay one click away", async () => {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <ClaimsDesk />
      </MemoryRouter>,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(el.textContent).toContain("We have not filed these");
  expect(el.textContent).toContain("Chassis is missing");
  expect(el.querySelector("[data-testid='claims-desk-switch']").textContent).toContain("Old claim screens");
  const open = el.querySelector("[data-testid='claims-job-not_claimed']");
  await act(async () => {
    open.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await act(async () => { await Promise.resolve(); });
  expect(el.textContent).toContain("Ramesh");
  await act(async () => { root.unmount(); });
  el.remove();
});
