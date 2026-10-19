/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockDownloadFile = jest.fn(() => Promise.resolve());
const mockOpen = jest.fn(() => Promise.resolve());

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  api: { get: jest.fn(() => Promise.resolve({ data: new Blob(), headers: {} })) },
  get: () => Promise.resolve([{
    requestId: "LR26000099",
    customerName: "Nihal Chand Gurjar",
    mobile: "9876543210",
    interestedModel: "Turbo Max",
    variant: "Maxx (PV)",
    executive: "Harish Bhatnagar",
    status: "pending",
    budget: 80000,
    kycComplete: true,
    kycMissing: [],
    dealSheetMissing: false,
    oemExtraProofMissing: false,
    documents: [
      { documentId: "DC-SHEET", kind: "deal_sheet", filename: "deal.pdf", contentType: "application/pdf" },
    ],
  }]),
  post: jest.fn(),
  uploadFile: jest.fn(),
  downloadFile: (...args) => mockDownloadFile(...args),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../components/LeadDocuments", () => {
  const actual = jest.requireActual("../components/LeadDocuments");
  return {
    ...actual,
    openDocumentFile: (...args) => mockOpen(...args),
  };
});
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canApproveLeads: true, isExecutive: false, isSalesGm: false }),
}));
jest.mock("../lib/pwa", () => ({ enableApproverPush: () => Promise.resolve({ ok: false }) }));

import Approvals from "./Approvals";

test("print deal sheet opens the uploaded scan on approvals", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Approvals />);
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const btn = host.querySelector('[data-testid="print-deal-sheet-btn"]');
  expect(btn).toBeTruthy();
  await act(async () => { btn.click(); await Promise.resolve(); });
  expect(mockOpen).toHaveBeenCalledWith("DC-SHEET", "deal.pdf");
  expect(mockDownloadFile).not.toHaveBeenCalled();
  await act(async () => { root.unmount(); });
  host.remove();
});
