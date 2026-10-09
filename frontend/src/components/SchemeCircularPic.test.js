/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import SchemeCircularPic from "./SchemeCircularPic";

global.IS_REACT_ACT_ENVIRONMENT = true;

async function renderPic(circular) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<SchemeCircularPic circular={circular} />);
  });
  return { host, root };
}

test("shows the billed-month circular and hides other months", async () => {
  const oct = {
    title: "October 2026 Retail Consumer Scheme",
    ref: "EM/10-2026/003",
    imageUrl: "/scheme-circulars/2026-10.png",
    pdfUrl: "/scheme-circulars/2026-10.pdf",
  };
  const { host, root } = await renderPic(oct);
  const pic = host.querySelector('[data-testid="scheme-circular-pic"]');
  expect(pic).toBeTruthy();
  expect(pic.textContent).toMatch(/EM\/10-2026\/003/);
  expect(host.querySelector("img").getAttribute("src")).toBe("/scheme-circulars/2026-10.png");
  expect(host.querySelector("a").getAttribute("href")).toBe("/scheme-circulars/2026-10.pdf");
  await act(async () => { root.unmount(); });
  host.remove();

  const emptyHost = document.createElement("div");
  document.body.appendChild(emptyHost);
  const emptyRoot = createRoot(emptyHost);
  await act(async () => {
    emptyRoot.render(<SchemeCircularPic circular={null} />);
  });
  expect(emptyHost.querySelector('[data-testid="scheme-circular-pic"]')).toBeNull();
  await act(async () => { emptyRoot.unmount(); });
  emptyHost.remove();
});
