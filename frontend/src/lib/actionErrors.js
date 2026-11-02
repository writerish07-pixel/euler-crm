import { toast } from "sonner";
import { apiErrorMessage } from "./api";

/**
 * A save / post / delete that failed with nobody catching it used to fail in
 * silence: the button did nothing and staff tapped again, or assumed it had
 * saved. Report those to the user instead.
 *
 * Only failed *writes* are reported. A background GET that fails is already
 * shown by the connection bar or the page's own empty / error state, and a
 * toast for every poll would be noise.
 */
export function isUnreportedWriteError(err) {
  if (!err || !err.isAxiosError) return false;
  const method = String(err.config?.method || "get").toLowerCase();
  return method !== "get" && method !== "head" && method !== "options";
}

export function reportActionError(err, fallback = "Could not save. Please try again.") {
  if (!isUnreportedWriteError(err)) return false;
  toast.error(apiErrorMessage(err, fallback));
  return true;
}

let installed = false;

/** Install once at start-up: last-chance report for an uncaught failed write. */
export function installActionErrorReporter(target = typeof window !== "undefined" ? window : null) {
  if (installed || !target || typeof target.addEventListener !== "function") return;
  installed = true;
  target.addEventListener("unhandledrejection", (event) => {
    if (reportActionError(event?.reason)) {
      if (typeof event.preventDefault === "function") event.preventDefault();
    }
  });
}
