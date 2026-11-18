/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api", () => ({
  get: () => Promise.resolve({
    activeBookings: 1,
    newThisMonth: 1,
    retailThisMonth: 0,
    todayBookings: 0,
    totalLeads: 1,
    month: "November 2026",
    lastUpdated: "2026-11-18T09:00:00+00:00",
    byModel: [{ model: "Storm EV", count: 1 }],
    recentBookings: [{ date: "2026-11-02", model: "Storm EV", variant: "City", status: "Booked" }],
    recentRetail: [],
    allLeads: [{ date: "2026-11-01", model: "Storm EV", variant: "City", status: "New" }],
  }),
}));

import Share from "./Share";

test("share board renders rows that have no customer name", async () => {
  const el = document.createElement("div");
  document.body.appendChild(el);
  await act(async () => { createRoot(el).render(<Share />); });
  await act(async () => { await Promise.resolve(); });
  expect(el.textContent).toContain("Storm EV");
  expect(el.textContent).toContain("1");
  expect(el.querySelectorAll(".row-name").length).toBeGreaterThan(0);
  expect(el.textContent).not.toContain("Ramesh");
  el.remove();
});
