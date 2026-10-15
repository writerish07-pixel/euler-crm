/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: () => Promise.resolve([
    {
      editId: "AUD1", timestamp: "2026-10-15T08:00:00",
      name: "Create TL", user: "tl.create@euler.com", role: "team_lead",
      roleLabel: "Team Leader", action: "update", module: "lead",
      leadId: "LD26009901", customerName: "Desk Cust", executive: "Desk Exec",
      summary: "City: — → Jaipur",
    },
  ]),
}));
jest.mock("../components/ReportActions", () => () => <div />);
jest.mock("../components/PeriodBar", () => () => <div />);
jest.mock("../lib/period", () => {
  const params = {};
  return {
    usePeriodState: () => ({ month: "", year: "", params, onChange: () => {} }),
  };
});

import EditLog from "./EditLog";

test("edit log register lists desk edits", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<MemoryRouter><EditLog /></MemoryRouter>);
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(host.querySelector('[data-testid="edit-log-page"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Edit Log Register/);
  expect(host.textContent).toMatch(/Create TL/);
  expect(host.textContent).toMatch(/Desk Cust/);
  expect(host.textContent).toMatch(/City: — → Jaipur/);
  await act(async () => { root.unmount(); });
});
