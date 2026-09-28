/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockGet = jest.fn();
const mockDownloadFile = jest.fn(() => Promise.resolve());

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (...args) => mockGet(...args),
  downloadFile: (...args) => mockDownloadFile(...args),
  apiErrorMessage: (e, fallback) => fallback,
}));

import ExportDialog from "./ExportDialog";

const CATALOG = {
  fallbackTab: "leads",
  pathToTab: { "/leads": "leads", "/bookings": "bookings" },
  tabs: [
    {
      key: "leads",
      label: "Lead Register",
      hasPeriod: true,
      hasSearch: true,
      statusField: "currentStatus",
      statuses: ["New", "Booked"],
      columns: [
        { key: "leadId", label: "Lead ID", default: true },
        { key: "customerName", label: "Customer", default: true },
        { key: "remarks", label: "Remarks", default: false },
      ],
    },
    {
      key: "bookings",
      label: "Booking Register",
      hasPeriod: true,
      hasSearch: true,
      statusField: "bookingStatus",
      statuses: ["Active"],
      columns: [
        { key: "bookingId", label: "Booking ID", default: true },
        { key: "customerName", label: "Customer", default: true },
      ],
    },
  ],
};

function setField(el, value) {
  const proto = el.tagName === "SELECT"
    ? Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value")
    : Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
  proto.set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

async function renderDialog(pathname = "/bookings") {
  mockGet.mockResolvedValue(CATALOG);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<ExportDialog open onClose={() => {}} pathname={pathname} />);
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { host, root };
}

afterEach(() => {
  document.body.innerHTML = "";
  mockGet.mockReset();
  mockDownloadFile.mockReset();
});

test("export dialog opens on the current tab with that tab's default columns", async () => {
  const { root } = await renderDialog("/bookings");
  const select = document.querySelector('[data-testid="export-tab"]');
  expect(select.value).toBe("bookings");
  expect(document.querySelector('[data-testid="export-col-bookingId"]').checked).toBe(true);
  expect(document.querySelector('[data-testid="export-col-leadId"]')).toBeFalsy();
  await act(async () => { root.unmount(); });
});

test("confirm downloads only the selected tab, columns and filters", async () => {
  const { root } = await renderDialog("/leads");
  await act(async () => {
    setField(document.querySelector('[data-testid="export-status"]'), "Booked");
    setField(document.querySelector('[data-testid="export-q"]'), "ramesh");
    document.querySelector('[data-testid="export-col-remarks"]').click();
  });
  await act(async () => {
    document.querySelector('[data-testid="export-confirm"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(mockDownloadFile).toHaveBeenCalledWith(
    "/export",
    expect.stringMatching(/^euler_leads_/),
    expect.objectContaining({
      tab: "leads",
      status: "Booked",
      q: "ramesh",
    }),
  );
  const params = mockDownloadFile.mock.calls[0][2];
  expect(params.columns.split(",")).toEqual(expect.arrayContaining(["leadId", "customerName", "remarks"]));
  await act(async () => { root.unmount(); });
});

test("unmapped screens note the fallback register", async () => {
  const { root } = await renderDialog("/settings");
  expect(document.querySelector('[data-testid="export-fallback-note"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="export-tab"]').value).toBe("leads");
  await act(async () => { root.unmount(); });
});
