import React, { useEffect, useState } from "react";
import { WifiOff, ArrowDownToLine } from "lucide-react";
import { applyUpdate } from "../lib/pwa";

/**
 * Two things a home-screen app owes the user that a browser tab gives for free:
 * a clear "you are offline" state instead of silently failing requests, and a
 * way to pick up a new build without knowing what a hard refresh is.
 */
export default function ConnectionBar() {
  const [offline, setOffline] = useState(() => typeof navigator !== "undefined" && !navigator.onLine);
  const [updateReady, setUpdateReady] = useState(() => !!window.__eulerUpdateReady);

  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    const upd = () => setUpdateReady(true);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    window.addEventListener("euler:update-ready", upd);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
      window.removeEventListener("euler:update-ready", upd);
    };
  }, []);

  if (offline) {
    return (
      <div data-testid="offline-bar"
        className="sticky top-0 z-40 flex items-center justify-center gap-2 bg-amber-500 px-3 py-1.5 text-xs font-semibold text-white">
        <WifiOff size={14} />
        No connection — figures on screen may be out of date
      </div>
    );
  }

  if (updateReady) {
    return (
      <button data-testid="update-bar" onClick={applyUpdate}
        className="sticky top-0 z-40 flex w-full items-center justify-center gap-2 bg-cobalt px-3 py-1.5 text-xs font-semibold text-white hover:bg-cobalt/90">
        <ArrowDownToLine size={14} />
        A new version is ready — tap to update
      </button>
    );
  }

  return null;
}
