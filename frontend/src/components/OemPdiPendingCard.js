import React, { useEffect, useState } from "react";
import { get, apiErrorMessage } from "../lib/api";
import { fmtDate } from "../lib/format";
import { Card, Table, Badge } from "./ui";

/**
 * Coulson "Sold, PDI pending": vehicles OEM billed whose PDI is still open in
 * the OEM app. Read-only — PDI is completed in the OEM app, not here.
 * Files already delivered or closed in the CRM are listed first.
 */
export default function OemPdiPendingCard({ onOpenLead }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    get("/oem-pdi-pending")
      .then((r) => { if (alive) setData(r && typeof r === "object" ? r : { rows: [], counts: {} }); })
      .catch((e) => { if (alive) setError(apiErrorMessage(e, "Could not load OEM PDI pending")); });
    return () => { alive = false; };
  }, []);

  const counts = (data && data.counts) || {};
  const rows = (data && data.rows) || [];
  return (
    <Card className="p-3 mt-4" data-testid="oem-pdi-pending-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-ink-faint">OEM PDI pending (sold)</div>
          <div className="text-sm text-ink-soft">
            {error ? error : data ? (
              <>
                <span className="text-xl font-bold tabular text-ink" data-testid="oem-pdi-total">{counts.total || 0}</span>
                {" "}sold in the OEM app without PDI ·{" "}
                <span className="font-semibold text-rose-700" data-testid="oem-pdi-delivered">{counts.delivered || 0}</span>
                {" "}already delivered in CRM · {counts.notInCrm || 0} not in CRM
              </>
            ) : "Loading…"}
          </div>
        </div>
        {rows.length > 0 && (
          <button
            type="button"
            data-testid="oem-pdi-toggle"
            onClick={() => setOpen((v) => !v)}
            className="px-3 py-1.5 rounded-full text-xs font-semibold ring-1 ring-inset bg-zinc-50 text-ink-soft ring-line"
          >
            {open ? "Hide list" : "Show list"}
          </button>
        )}
      </div>
      {open && (
        <div className="mt-3">
          <p className="text-[12px] text-ink-faint mb-2">
            Complete PDI in the OEM app. This list refreshes on the next OEM sync.
          </p>
          <Table
            rowKey="chassis"
            columns={[
              { key: "chassis", label: "Chassis", mono: true },
              { key: "oemModel", label: "OEM vehicle", render: (r) => `${r.oemModel || ""} ${r.oemVariant || ""}`.trim() || "—" },
              { key: "soldDate", label: "OEM billed", render: (r) => (r.soldDate ? fmtDate(r.soldDate) : "—") },
              { key: "leadId", label: "CRM file", render: (r) => (r.leadId ? (
                <button type="button" className="text-cobalt font-semibold" onClick={() => onOpenLead && onOpenLead(r.leadId)}>
                  {r.leadId}{r.customerName ? ` · ${r.customerName}` : ""}
                </button>
              ) : "Not in CRM") },
              { key: "crmStatus", label: "CRM status", render: (r) => (
                r.deliveredInCrm
                  ? <Badge tone="bg-rose-50 text-rose-800 ring-rose-600/20">{r.crmStatus || "Delivered"}</Badge>
                  : (r.crmStatus || "—")
              ) },
            ]}
            rows={rows}
            empty="No sold vehicles are waiting for PDI"
          />
        </div>
      )}
    </Card>
  );
}
