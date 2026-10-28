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
      return Promise.resolve([
        {
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
        },
        {
          claimId: "C2",
          leadId: "LD2",
          customer: "Sita",
          component: "Consumer Offer",
          componentKey: "consumerOffer",
          eligibleClaim: 2000,
          receivedAmount: 2000,
          oemMatch: { state: "accepted", claimNumbers: ["DN2"] },
          claimStatus: "Received",
        },
      ]);
    }
    if (url === "/claims/oem-only") {
      return Promise.resolve({
        count: 1,
        total: 1000,
        rows: [{ claimNumber: "DN1", lineId: "L9", description: "Referral", amount: 1000, oemStatus: "Submitted", mappedComponent: "referralBonus" }],
      });
    }
    if (url === "/oem-claims/summary") {
      return Promise.resolve({
        total: 1,
        totals: { claimed: 8000, approved: 0, openClaimed: 8000 },
        mirror: { missingVehicle: 1, withVehicle: 0, missingDocument: 1 },
        buckets: [],
        rejected: [],
        invoiceConflicts: [],
      });
    }
    if (url === "/oem-claims") {
      return Promise.resolve([{
        claimNumber: "DN9",
        status: "Submitted",
        claimedAmount: 8000,
        approvedAmount: 0,
        lineItems: [{ lineId: "L1", description: "No vehicle", leadIds: [] }],
        leadIds: [],
        linkedLineCount: 0,
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
  expect(el.querySelector("[data-testid='oem-only-create-DN1']")).toBeTruthy();
  const ours = el.querySelector("[data-testid='claims-desk-tab-ours']");
  await act(async () => {
    ours.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await act(async () => { await Promise.resolve(); });
  expect(el.textContent).toContain("Sita");
  await act(async () => { root.unmount(); });
  el.remove();
});
