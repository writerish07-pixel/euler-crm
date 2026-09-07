import React from "react";
import { Phone } from "lucide-react";
import { telHref, digitsLast10 } from "../lib/format";
import { cx } from "./ui";

/** Tap-to-call on a mobile. Stops row-click so a table cell does not open the drawer. */
export default function CallLink({ mobile, compact = false, className, label }) {
  const href = telHref(mobile);
  const shown = digitsLast10(mobile) || String(mobile || "").trim();
  if (!href) {
    return <span className={cx("text-ink-faint", className)}>{shown || "—"}</span>;
  }
  return (
    <a
      href={href}
      data-testid="call-btn"
      aria-label={`Call ${shown}`}
      className={cx(
        "inline-flex items-center gap-1 font-medium",
        compact
          ? "text-xs text-cobalt hover:text-cobalt-hover hover:underline"
          : "text-sm rounded-lg px-2.5 py-1.5 bg-cobalt text-white hover:bg-cobalt-hover shadow-sm",
        className,
      )}
      onClick={(e) => e.stopPropagation()}
    >
      <Phone size={compact ? 11 : 14} />
      {label || (compact ? shown : `Call ${shown}`)}
    </a>
  );
}
