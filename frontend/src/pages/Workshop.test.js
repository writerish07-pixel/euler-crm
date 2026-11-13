/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const mockGet = jest.fn();
const mockPost = jest.fn();
const mockPut = jest.fn();
jest.mock("../lib/api", () => ({
  get: (...args) => mockGet(...args),
  post: (...args) => mockPost(...args),
  put: (...args) => mockPut(...args),
  apiErrorMessage: (err, fallback) => (err && err.message) || fallback,
}));
const mockAuth = { current: { isOwner: true } };
jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth.current,
}));

import Workshop from "./Workshop";

const EMPTY = {
  lines: [],
  mails: [],
  advances: [],
  advanceTotal: 0,
  warranty: { total: 0, amount: 0, rows: [], breakdown: [] },
  jobs: { openTickets: [], overdue: 0, dueSoon: 0, booked: 0, complaintsOpen: 0, coverage: [] },
  today: [],
  serviceLogin: { configured: false, username: "" },
  syncError: "",
};

const LOADED = {
  ...EMPTY,
  lines: [
    {
      id: "gun",
      code: "CD4C001800",
      part: "WH AC charging gun",
      requestNo: "10412",
      stage: "short",
      stageLabel: "Missing from the box",
      advance: 18400,
      qty: 10,
      note: "The dispatch mail says this part was not sent.",
    },
  ],
  mails: [
    {
      id: "dispatch",
      subject: "Re: Ticket 10412 — dispatch update",
      direction: "Received from the company",
      when: "Unread",
      status: "unread",
      applied: false,
      requestNo: "10412",
      body: "Dispatch update for ticket 10412.\nCD4C001800 is not dispatched.\n₹18,400 is parked as advance.",
      finds: [["Request number", "10412"], ["Missing from the box", "CD4C001800"]],
      result: "Joined to ticket 10412. CD4C001800 marked missing.",
    },
  ],
  advances: [{ requestNo: "10412", amount: 18400, parts: ["WH AC charging gun"] }],
  advanceTotal: 18400,
  today: [{
    id: "mail-dispatch",
    title: "Re: Ticket 10412 — dispatch update",
    detail: "Not read yet.",
    mailId: "dispatch",
  }],
  warranty: {
    total: 18,
    amount: 147807.97,
    rows: [{ claimNumber: 14315, amount: 5337.82, status: "SPD Pickup Requested", part: "Front leaf spring" }],
    breakdown: [{ label: "Pickup requested, received quantity still zero", count: 12 }],
  },
  jobs: {
    openTickets: [{ ticketId: 279680, status: "Service In Progress", type: "Corrective Maintenance", partNotAvailable: true }],
    overdue: 35,
    dueSoon: 25,
    booked: 7,
    complaintsOpen: 61,
    coverage: [{ label: "Out of warranty", count: 320 }],
  },
};

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockPut.mockReset();
  mockAuth.current = { isOwner: true };
  mockGet.mockResolvedValue(EMPTY);
  mockPost.mockImplementation((url) => {
    if (url === "/workshop/sample" || url === "/workshop/mails/dispatch/read") return Promise.resolve(LOADED);
    return Promise.resolve(LOADED);
  });
});

async function render() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Workshop />); });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
  return { host, root };
}

test("workshop desk loads this morning and opens the mail, the part, and the warranty", async () => {
  const { host, root } = await render();
  expect(host.querySelector('[data-testid="workshop-desk"]')).toBeTruthy();
  expect(host.textContent).toContain("Nothing is waiting");

  const load = [...host.querySelectorAll("button")].find((btn) => btn.textContent.includes("Load this morning"));
  await act(async () => { load.click(); });
  await act(async () => { await Promise.resolve(); });
  expect(host.textContent).toContain("Re: Ticket 10412");
  expect(host.textContent).toContain("18,400");

  await act(async () => { host.querySelector('[data-testid="workshop-tab-mail"]').click(); });
  expect(host.textContent).toContain("not dispatched");
  const read = [...host.querySelectorAll("button")].find((btn) => btn.textContent.includes("Read this mail"));
  await act(async () => { read.click(); });
  expect(mockPost).toHaveBeenCalledWith("/workshop/mails/dispatch/read", {}, {});

  await act(async () => { host.querySelector('[data-testid="workshop-tab-buy"]').click(); });
  expect(host.textContent).toContain("WH AC charging gun");
  expect(host.textContent).toContain("Missing from the box");

  await act(async () => { host.querySelector('[data-testid="workshop-tab-warranty"]').click(); });
  expect(host.textContent).toContain("14315");

  await act(async () => { host.querySelector('[data-testid="workshop-tab-jobs"]').click(); });
  expect(host.textContent).toContain("279680");

  await act(async () => { host.querySelector('[data-testid="workshop-tab-money"]').click(); });
  expect(host.textContent).toContain("10412");

  await act(async () => { host.querySelector('[data-testid="workshop-tab-rules"]').click(); });
  expect(host.textContent).toContain("Service Coulson session");
  expect(host.textContent).toContain("coulson_auth");

  act(() => { root.unmount(); });
  host.remove();
});

test("a failed paste keeps the mail in the box", async () => {
  mockPost.mockRejectedValueOnce(new Error("offline"));
  const { host, root } = await render();
  await act(async () => { host.querySelector('[data-testid="workshop-tab-mail"]').click(); });
  const subject = host.querySelector("input");
  const body = host.querySelector("textarea");
  const setValue = (el, value) => {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  };
  await act(async () => {
    setValue(subject, "Re: Ticket 10412");
    setValue(body, "Ticket 10412\nCD4C001800 is not dispatched");
  });
  const add = [...host.querySelectorAll("button")].find((btn) => btn.textContent.includes("Add to the desk"));
  await act(async () => { add.click(); });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector("input").value).toBe("Re: Ticket 10412");
  expect(host.querySelector("textarea").value).toContain("CD4C001800");
  act(() => { root.unmount(); });
  host.remove();
});

test("a person granted only Today does not see People or Gmail", async () => {
  mockAuth.current = { isOwner: false };
  mockGet.mockResolvedValue({ ...EMPTY, access: { owner: false, areas: ["today"] } });
  const { host, root } = await render();
  expect(host.querySelector('[data-testid="workshop-tab-today"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="workshop-tab-people"]')).toBeFalsy();
  expect(host.querySelector('[data-testid="workshop-tab-rules"]')).toBeFalsy();
  expect(host.querySelector('[data-testid="workshop-tab-payments"]')).toBeFalsy();
  act(() => { root.unmount(); });
  host.remove();
});
