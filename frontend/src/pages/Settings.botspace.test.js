/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockCfg = { current: {} };
const mockPut = jest.fn(() => Promise.resolve({ ok: true }));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => (String(url).includes("/integrations/botspace")
    ? Promise.resolve(mockCfg.current) : Promise.resolve({})),
  post: jest.fn(() => Promise.resolve({})),
  put: (...args) => mockPut(...args),
  del: jest.fn(() => Promise.resolve({})),
  api: {},
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ isOwner: true }) }));
jest.mock("../components/ChangePasswordCard", () => () => null);

import { BotspaceCard } from "./Settings";

const BASE = "https://euler-crm-production.up.railway.app/api/integrations/botspace/webhook";

async function render() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<BotspaceCard />); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { host, root };
}

afterEach(() => { document.body.innerHTML = ""; mockPut.mockClear(); });

test("no saved secret: warning shown and plain webhook URL", async () => {
  mockCfg.current = { configured: true, webhookUrl: BASE, webhookSecret: "" };
  const { host, root } = await render();
  expect(host.querySelector('[data-testid="botspace-secret-warning"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="botspace-webhook-url"]').textContent).toContain(BASE);
  expect(host.querySelector('[data-testid="botspace-webhook-url"]').textContent).not.toContain("secret=");
  await act(async () => { root.unmount(); });
});

test("saved secret: no warning, copied URL carries the secret, save keeps it", async () => {
  mockCfg.current = { configured: true, webhookUrl: BASE, webhookSecret: "s3cr3t value" };
  const { host, root } = await render();
  expect(host.querySelector('[data-testid="botspace-secret-warning"]')).toBeFalsy();
  expect(host.querySelector('[data-testid="botspace-webhook-url"]').textContent)
    .toContain(`${BASE}?secret=s3cr3t%20value`);
  expect(host.querySelector('[data-testid="botspace-webhook-secret"]').value).toBe("s3cr3t value");
  await act(async () => { host.querySelector('[data-testid="botspace-save-btn"]').click(); });
  expect(mockPut).toHaveBeenCalledWith("/integrations/botspace", expect.objectContaining({
    webhookSecret: "s3cr3t value",
  }));
  await act(async () => { root.unmount(); });
});
