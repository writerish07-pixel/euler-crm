import React from "react";
import { inr } from "../lib/format";
import { Field, Input } from "./ui";

function Line({ k, v, strong, testid, tone }) {
  return (
    <div className={`flex justify-between gap-3 text-sm ${strong ? "font-semibold" : ""}`} data-testid={testid}>
      <span className="text-ink-soft">{k}</span>
      <span className={`font-mono ${tone || ""}`}>{inr(v)}</span>
    </div>
  );
}

export default function DealFormatCard({
  snapshot,
  cxDemand,
  onCxDemand,
  readOnly = false,
  loading = false,
  missingPrice = false,
}) {
  const d = snapshot || {};
  const demand = cxDemand ?? d.cxDemand ?? 0;
  const support = Number(d.supportRequired ?? ((d.netToCx || 0) - Number(demand || 0)));
  const extra = support < 0;
  return (
    <div className="rounded-lg border border-line bg-paper px-3 py-3 space-y-1.5" data-testid="deal-format-card">
      <div className="text-xs font-semibold uppercase tracking-wide text-ink-soft mb-1">Deal format</div>
      {loading && <p className="text-xs text-ink-faint">Loading Price Master…</p>}
      {missingPrice && (
        <p className="text-xs text-amber-700" data-testid="deal-format-no-price">
          Select model and variant to load RTO, insurance and transport from Price Master.
        </p>
      )}
      <Line k="Ex-showroom" v={d.exShowroom} testid="deal-ex" />
      <Line k="RTO" v={d.rto} testid="deal-rto" />
      <Line k="Insurance" v={d.insurance} testid="deal-insurance" />
      <Line k="Transport" v={d.transport ?? d.handlingCharges} testid="deal-transport" />
      {Number(d.otherCharges) > 0 && <Line k="Other charges" v={d.otherCharges} testid="deal-other" />}
      <Line k="TCS (1% after discount)" v={d.tcs} testid="deal-tcs" />
      <div className="border-t border-line pt-1.5">
        <Line k="Net to customer" v={d.netToCx} strong testid="deal-net-to-cx" />
      </div>
      {readOnly ? (
        <Line k="Cx Demand" v={demand} strong testid="deal-cx-demand" />
      ) : (
        <Field label="Cx Demand (final amount to customer) *">
          <Input
            data-testid="lead-budget"
            type="number"
            min="0"
            value={demand || ""}
            onChange={(e) => onCxDemand && onCxDemand(e.target.value)}
          />
        </Field>
      )}
      <div className={`rounded-md px-2 py-1.5 ${extra ? "bg-emerald-50" : "bg-amber-50"}`}>
        <Line
          k={extra ? "Extra margin" : "Support required"}
          v={extra ? Math.abs(support) : support}
          strong
          testid="deal-support"
          tone={extra ? "text-emerald-700" : "text-amber-800"}
        />
      </div>
      <p className="text-[11px] text-ink-faint">No scheme on this card. Scheme is decided later.</p>
    </div>
  );
}

export function paymentRefLabel(mode) {
  const m = String(mode || "").toLowerCase();
  if (m === "cheque") return "Cheque number";
  if (m === "upi" || m === "neft") return "UTR / transaction number";
  if (m === "card") return "Transaction number";
  return "Transaction number";
}

export function paymentRefRequired(mode, amount) {
  const m = String(mode || "").toLowerCase();
  if (m === "cash" || m === "finance" || !m) return false;
  return Number(amount) > 0;
}
