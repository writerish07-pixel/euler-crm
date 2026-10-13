/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

const mockAuth = { isField: false, isExecutive: false, isShowroomAdmin: false };

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url) === "/leads" || String(url).indexOf("/leads") === 0) {
      return Promise.resolve([
        {
          leadId: "LD26001001", customerName: "Approved Singh", currentStatus: "Contacted",
          executive: "Amit", needsUpdate: true,
          updateFlags: [{ code: "kyc", message: "KYC missing: Aadhaar front" }],
        },
        { leadId: "LD26001002", customerName: "Ready Ram", currentStatus: "Contacted", executive: "Amit", needsUpdate: false, updateFlags: [] },
      ]);
    }
    if (String(url) === "/masters") {
      return Promise.resolve({ executives: ["Amit"], models: ["Turbo Max"] });
    }
    return Promise.resolve([]);
  },
  apiErrorMessage: (e, fallback) => fallback || String(e),
}));
jest.mock("../components/ReportActions", () => () => <div />);
jest.mock("../components/PeriodBar", () => () => <div />);
jest.mock("../lib/period", () => {
  const params = {};
  return {
    usePeriodState: () => ({ month: "", year: "", params, onChange: () => {} }),
  };
});
jest.mock("../components/CallLink", () => () => <span />);
jest.mock("./LeadDrawer", () => () => null);
jest.mock("./LeadImport", () => () => null);
jest.mock("./NewLeadDrawer", () => () => null);
jest.mock("../components/CompleteFormatDrawer", () => () => null);
jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

import Leads from "./Leads";

async function renderLeads() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <Leads />
      </MemoryRouter>,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { host, root };
}

afterEach(() => {
  document.body.innerHTML = "";
  mockAuth.isShowroomAdmin = false;
  mockAuth.isExecutive = false;
  mockAuth.isField = false;
});

test("owner lead register still offers the New status filter", async () => {
  const { root } = await renderLeads();
  expect(document.querySelector('[data-testid="filter-New"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
});

test("showroom admin lead register hides New and keeps approved statuses", async () => {
  mockAuth.isShowroomAdmin = true;
  const { root } = await renderLeads();
  expect(document.querySelector('[data-testid="filter-New"]')).toBeFalsy();
  expect(document.querySelector('[data-testid="filter-Contacted"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="filter-all"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
});

test("showroom admin sees exact update gaps and can filter to those leads", async () => {
  mockAuth.isShowroomAdmin = true;
  const { host, root } = await renderLeads();
  expect(host.textContent).toMatch(/KYC missing: Aadhaar front/);
  const chip = document.querySelector('[data-testid="filter-needs-update"]');
  expect(chip).toBeTruthy();
  await act(async () => { chip.click(); });
  expect(host.textContent).toMatch(/Approved Singh/);
  expect(host.textContent).not.toMatch(/Ready Ram/);
  await act(async () => { root.unmount(); });
});
