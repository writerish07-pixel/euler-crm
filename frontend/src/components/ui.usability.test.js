/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { Button, Drawer, Modal, Input } from "./ui";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(el) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  act(() => { root.render(el); });
  return { host, root, cleanup: () => { act(() => root.unmount()); host.remove(); } };
}

test("an async button ignores a second tap until the save finishes", async () => {
  let finish;
  const onClick = jest.fn(() => new Promise((r) => { finish = r; }));
  const { host, cleanup } = mount(<Button data-testid="save" onClick={onClick}>Save</Button>);
  const btn = host.querySelector('[data-testid="save"]');
  await act(async () => { btn.click(); });
  await act(async () => { btn.click(); });
  expect(onClick).toHaveBeenCalledTimes(1);
  expect(btn.disabled).toBe(true);
  await act(async () => { finish(); });
  expect(btn.disabled).toBe(false);
  await act(async () => { btn.click(); });
  expect(onClick).toHaveBeenCalledTimes(2);
  cleanup();
});

test("a plain button is not disabled after a click", async () => {
  const onClick = jest.fn();
  const { host, cleanup } = mount(<Button data-testid="go" onClick={onClick}>Go</Button>);
  const btn = host.querySelector('[data-testid="go"]');
  await act(async () => { btn.click(); btn.click(); });
  expect(onClick).toHaveBeenCalledTimes(2);
  expect(btn.disabled).toBe(false);
  cleanup();
});

test("Escape closes only the top-most overlay", async () => {
  const closeDrawer = jest.fn();
  const closeModal = jest.fn();
  const { cleanup } = mount(
    <>
      <Drawer open title="Lead" onClose={closeDrawer}>body</Drawer>
      <Modal onClose={closeModal}>confirm</Modal>
    </>,
  );
  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });
  expect(closeModal).toHaveBeenCalledTimes(1);
  expect(closeDrawer).not.toHaveBeenCalled();
  cleanup();
});

test("number inputs get the number pad on phones", () => {
  const { host, cleanup } = mount(<Input data-testid="amt" type="number" defaultValue="" />);
  expect(host.querySelector('[data-testid="amt"]').getAttribute("inputmode")).toBe("decimal");
  cleanup();
});
