/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url).includes("/lead-requests")) {
      return Promise.resolve([{
        requestId: "LR26000004",
        customerName: "Suresh Choudhary",
        mobile: "7877731163",
        interestedModel: "Turbo Max",
        variant: "Maxx (FB)",
        executive: "Payal",
        status: "pending",
        budget: 795000,
        kycComplete: false,
        kycMissing: ["kyc_pan"],
        dealSheetMissing: true,
        oemExtraProofMissing: false,
        documents: [],
      }]);
    }
    return Promise.resolve([]);
  },
  post: jest.fn(),
  uploadFile: jest.fn(() => Promise.resolve({ documentId: "D1" })),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canApproveLeads: false, isExecutive: true, isSalesGm: false }),
}));
jest.mock("../lib/pwa", () => ({ enableApproverPush: () => Promise.resolve({ ok: false }) }));

import Approvals from "./Approvals";

test("approvals tab offers upload for missing KYC and deal sheet", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Approvals />);
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(host.querySelector('[data-testid="approvals-page"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="missing-uploads-LR26000004"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="upload-LR26000004-deal_sheet-file"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="upload-LR26000004-kyc_pan-file"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="complete-LR26000004"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
  host.remove();
});
