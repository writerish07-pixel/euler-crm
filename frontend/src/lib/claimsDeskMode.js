/** Which Claims screens are on. The new page is the default. Old screens stay one click away. */

import { useEffect, useState } from "react";

export const CLAIMS_DESK_KEY = "euler.claimsDesk";
export const CLAIMS_DESK_EVENT = "euler-claims-desk";

let memoryMode = "";

export function readClaimsDeskMode() {
  try {
    const stored = window.localStorage.getItem(CLAIMS_DESK_KEY);
    if (stored === "classic" || stored === "simple") {
      memoryMode = stored;
      return stored;
    }
    memoryMode = "";
    return "simple";
  } catch (e) {
    return memoryMode || "simple";
  }
}

export function writeClaimsDeskMode(mode) {
  const next = mode === "classic" ? "classic" : "simple";
  memoryMode = next;
  try {
    window.localStorage.setItem(CLAIMS_DESK_KEY, next);
  } catch (e) {
    /* private mode still switches for this tab via memoryMode */
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CLAIMS_DESK_EVENT));
  }
  return next;
}

export function useClaimsDeskMode() {
  const [mode, setMode] = useState(readClaimsDeskMode);
  useEffect(() => {
    const sync = () => setMode(readClaimsDeskMode());
    window.addEventListener(CLAIMS_DESK_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CLAIMS_DESK_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return mode;
}

/** Drop the two extra menus while the new page is on. Routes stay so bookmarks work. */
export function claimsNavItems(items, mode) {
  if (mode !== "simple") return items;
  return items.flatMap((item) => {
    if (item.to === "/claims") return [{ ...item, label: "Claims" }];
    if (item.to === "/oem-claims" || item.to === "/oem-claims/no-vehicle") return [];
    return [item];
  });
}
