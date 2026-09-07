/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { Table, PANEL_MAX_H } from "./ui";

test("tables scroll horizontally and grow with the page by default", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(
      <Table
        columns={[{ key: "n", label: "N" }]}
        rows={Array.from({ length: 40 }, (_, i) => ({ n: i }))}
        rowKey="n"
      />,
    );
  });
  const pane = host.querySelector('[data-testid="table-scroll"]');
  expect(pane).toBeTruthy();
  expect(pane.style.maxHeight).toBe("");
  host.remove();
});

test("tables can opt into an internal height cap", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(
      <Table
        columns={[{ key: "n", label: "N" }]}
        rows={[{ n: 1 }]}
        rowKey="n"
        maxHeight={PANEL_MAX_H}
      />,
    );
  });
  const pane = host.querySelector('[data-testid="table-scroll"]');
  expect(pane.style.maxHeight).toBe(PANEL_MAX_H);
  host.remove();
});
