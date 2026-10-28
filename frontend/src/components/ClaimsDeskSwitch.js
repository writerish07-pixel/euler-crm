import React from "react";
import { useNavigate } from "react-router-dom";
import { useClaimsDeskMode, writeClaimsDeskMode } from "../lib/claimsDeskMode";

/** Always visible. Sends the user back to the three original registers, or forward again. */
export default function ClaimsDeskSwitch({ className = "" }) {
  const navigate = useNavigate();
  const mode = useClaimsDeskMode();
  const classic = mode === "classic";
  return (
    <button
      type="button"
      data-testid="claims-desk-switch"
      onClick={() => {
        writeClaimsDeskMode(classic ? "simple" : "classic");
        navigate("/claims");
      }}
      className={className || "text-sm font-medium text-ink-soft hover:text-ink hover:underline"}
    >
      {classic ? "New Claims page" : "Old claim screens"}
    </button>
  );
}
