import React, { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Claims from "./Claims";
import OemClaims from "./OemClaims";
import ClaimsDesk from "./ClaimsDesk";
import { useClaimsDeskMode, writeClaimsDeskMode } from "../lib/claimsDeskMode";

class ClaimsDeskBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    const detail = String(this.state.error?.message || this.state.error || "unknown error");
    return (
      <div className="p-6 max-w-lg" data-testid="claims-desk-crash">
        <p className="font-heading text-lg font-bold text-ink">The new Claims page hit a problem</p>
        <p className="text-sm text-ink-soft mt-2">
          Your files are unchanged. Open the old screens — Scheme Claim Register,
          OEM Claim Settlements, and Missing chassis — and keep working.
        </p>
        <pre className="mt-3 text-[11px] text-ink-faint whitespace-pre-wrap break-words bg-zinc-50 ring-1 ring-line rounded-lg p-3">
          {detail}
        </pre>
        <button
          type="button"
          data-testid="claims-desk-crash-rollback"
          className="mt-4 rounded-lg bg-cobalt px-4 py-2 text-sm font-semibold text-white"
          onClick={() => {
            writeClaimsDeskMode("classic");
            window.location.assign("/claims");
          }}
        >
          Open the old claim screens
        </button>
      </div>
    );
  }
}

export default function ClaimsRoute() {
  const mode = useClaimsDeskMode();
  if (mode === "classic") return <Claims />;
  return (
    <ClaimsDeskBoundary>
      <ClaimsDesk />
    </ClaimsDeskBoundary>
  );
}

export function OemClaimsRoute({ missingVehicleOnly = false }) {
  const mode = useClaimsDeskMode();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  useEffect(() => {
    if (mode !== "simple") return undefined;
    const next = new URLSearchParams(params);
    next.set("view", "euler");
    if (missingVehicleOnly) next.set("job", "missing_chassis");
    const qs = next.toString();
    navigate(`/claims?${qs}`, { replace: true });
    return undefined;
  }, [mode, missingVehicleOnly, params, navigate]);
  if (mode === "simple") return null;
  return <OemClaims missingVehicleOnly={missingVehicleOnly} />;
}
