import React from "react";
import { clearSiteDataAndReload } from "../lib/pwa";

/** A render crash must not leave OPPO/vivo on a white screen. */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    const compact = Boolean(this.props.compact);
    const raw = this.state.error;
    const detail = String((raw && (raw.message || raw.reason)) || raw || "unknown error");
    return (
      <div
        className={compact ? "p-6 text-center" : "min-h-screen grid place-items-center p-6 text-center"}
        data-testid="app-error"
      >
        <div>
          <p className="font-heading text-lg font-bold text-ink">Something went wrong</p>
          <p className="text-sm text-ink-soft mt-2 max-w-sm mx-auto">
            Tap Reload. On OPPO or vivo, use Clear cache — then open Euler CRM in Chrome,
            not the home-screen icon.
          </p>
          <pre className="mt-3 max-w-sm mx-auto text-left text-[11px] leading-snug text-ink-faint whitespace-pre-wrap break-words bg-zinc-50 ring-1 ring-line rounded-lg p-3">
            {detail}
          </pre>
          <div className="mt-4 flex flex-wrap gap-2 justify-center">
            <button
              type="button"
              className="rounded-lg bg-cobalt px-4 py-2 text-sm font-semibold text-white"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
            <button
              type="button"
              className="rounded-lg bg-white ring-1 ring-line px-4 py-2 text-sm font-semibold text-ink"
              onClick={() => clearSiteDataAndReload()}
            >
              Clear cache
            </button>
          </div>
        </div>
      </div>
    );
  }
}
