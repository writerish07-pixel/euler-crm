/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";
import { postForm } from "../lib/api";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: () => Promise.resolve({ shares: [], totalPct: 0 }),
  downloadFile: jest.fn(),
  postForm: jest.fn(),
  apiErrorMessage: (err, fallback) => err?.message || fallback || "err",
}));

import LeadImport from "./LeadImport";

const PREVIEW = {
  detectedHeaders: ["Customer Name", "Mobile"],
  targetFields: [{ label: "Customer Name", field: "customerName" }],
  suggestedMapping: { customerName: "Customer Name" },
  rowCount: 529,
  validCount: 168,
  errorCount: 2,
  alreadyCount: 359,
  sample: [],
  errors: [],
  alreadyInApp: [],
  executivePrompts: [],
  requiredFields: ["customerName", "mobile"],
};

async function renderImport() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(<LeadImport onClose={() => {}} onDone={() => {}} />);
  });
  return host;
}

async function chooseFile() {
  const input = document.querySelector('[data-testid="import-file-input"]');
  const file = new File(["x"], "Devang Sharma.csv", { type: "text/csv" });
  await act(async () => {
    Object.defineProperty(input, "files", { value: [file] });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

test("import drawer renders the upload dropzone", async () => {
  await renderImport();
  expect(document.querySelector('[data-testid="import-dropzone"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="download-template-btn"]')).toBeTruthy();
});

test("a timed-out import does not retry and tells the user leads may already be saved", async () => {
  postForm.mockImplementation((url) => {
    if (String(url).includes("preview")) return Promise.resolve(PREVIEW);
    return Promise.reject(Object.assign(new Error("timeout of 180000ms exceeded"), { code: "ECONNABORTED" }));
  });
  await renderImport();
  await chooseFile();
  expect(document.querySelector('[data-testid="import-already-count"]')?.textContent).toBe("359");
  await act(async () => {
    document.querySelector('[data-testid="commit-import-btn"]').click();
  });
  expect(postForm).toHaveBeenCalledWith(
    "/leads/import/commit",
    expect.any(FormData),
    { timeout: 180000, retry: false },
  );
  expect(toast.error).toHaveBeenCalledWith(
    expect.stringMatching(/still saving on the server/i),
  );
});
