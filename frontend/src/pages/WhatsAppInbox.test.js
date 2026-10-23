/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const mockGet = jest.fn();
const mockPost = jest.fn();
jest.mock("../lib/api", () => ({
  get: (...args) => mockGet(...args),
  post: (...args) => mockPost(...args),
}));
jest.mock("./LeadWhatsApp", () => () => <div data-testid="lead-wa" />);

import WhatsAppInbox from "./WhatsAppInbox";

beforeEach(() => {
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/whatsapp/threads")) {
      return Promise.resolve({ total: 0, threads: [] });
    }
    if (String(url).includes("/whatsapp/summary")) {
      return Promise.resolve({ needsReply: 0, unread: 0, activeChats: 0, failed: 0 });
    }
    if (String(url).includes("/whatsapp/messages")) {
      return Promise.resolve([{ messageId: "M1", text: "hello", status: "sent", kind: "booking" }]);
    }
    return Promise.resolve({});
  });
  mockPost.mockResolvedValue({});
});

test("header Refresh reloads the Sent tab", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<WhatsAppInbox />); });
  await act(async () => { await Promise.resolve(); });
  await act(async () => {
    host.querySelector('[data-testid="wa-tab-sent"]').click();
  });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector('[data-testid="wa-sent-box"]')).toBeTruthy();
  expect(host.textContent).toMatch(/hello/);
  mockGet.mockClear();
  await act(async () => {
    host.querySelector('[data-testid="wa-refresh"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(mockGet.mock.calls.some((c) => String(c[0]).includes("/whatsapp/messages"))).toBe(true);
  await act(async () => { root.unmount(); });
  host.remove();
});
