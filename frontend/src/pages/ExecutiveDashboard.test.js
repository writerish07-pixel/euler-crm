/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

const mockAuth = { isTl: false, isExecutive: true };

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url).indexOf("/executive/dashboard") >= 0) {
      return Promise.resolve({
        kpis: { myLeadsMtd: 2, myBookingsMtd: 1, myDeliveriesMtd: 0, conversion: 50 },
        scope: { note: "My pipeline", matchedLeads: 2 },
        worklist: [],
        funnel: [],
        sourceMix: [],
        modelMix: [],
      });
    }
    if (String(url) === "/masters") {
      return Promise.resolve({ executives: ["Executive"], models: ["Turbo Max"], leadSources: ["Walk-in"], priorities: ["Normal"] });
    }
    return Promise.resolve({});
  },
}));
jest.mock("../components/ReportActions", () => () => <div />);
jest.mock("../components/YardStockCard", () => () => <div />);
jest.mock("./NewLeadDrawer", () => (props) => (
  <div data-testid="new-lead-drawer">{props.masters ? "ready" : "no-masters"}</div>
));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

import ExecutiveDashboard from "./ExecutiveDashboard";

async function renderDash(teamView = false) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <ExecutiveDashboard teamView={teamView} />
      </MemoryRouter>,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { host, root };
}

afterEach(() => {
  document.body.innerHTML = "";
  mockAuth.isTl = false;
  mockAuth.isExecutive = true;
});

test("executive dashboard has a visible Request lead control", async () => {
  const { root } = await renderDash();
  const btn = document.querySelector('[data-testid="exec-new-lead-btn"]');
  expect(btn).toBeTruthy();
  expect(btn.textContent).toMatch(/Request lead/);
  await act(async () => { btn.click(); });
  expect(document.querySelector('[data-testid="new-lead-drawer"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
});

test("TL team pipeline uses New Lead on the same dashboard", async () => {
  mockAuth.isTl = true;
  mockAuth.isExecutive = false;
  const { root } = await renderDash(true);
  const btn = document.querySelector('[data-testid="exec-new-lead-btn"]');
  expect(btn).toBeTruthy();
  expect(btn.textContent).toMatch(/New Lead/);
  await act(async () => { btn.click(); });
  expect(document.querySelector('[data-testid="new-lead-drawer"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
});
