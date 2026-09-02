import React, { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { get } from "../lib/api";
import LeadDrawer from "../pages/LeadDrawer";

// Every claim row is ultimately a lead. The claim desk was having to note the lead id,
// walk to the Lead Register and search for it; this opens the same 360 drawer in place.
//
// Masters are fetched once per page rather than per row — the drawer's edit forms need
// them, and a null masters would break those forms the moment someone clicked Edit.
export function useLeadDrawer(onChanged) {
  const [active, setActive] = useState(null);
  const [masters, setMasters] = useState(null);

  useEffect(() => {
    let cancelled = false;
    get("/masters")
      .then((m) => { if (!cancelled) setMasters(m); })
      .catch(() => { if (!cancelled) setMasters(null); });
    return () => { cancelled = true; };
  }, []);

  const drawer = active ? (
    <LeadDrawer
      leadId={active}
      masters={masters}
      onClose={() => setActive(null)}
      onChanged={onChanged}
    />
  ) : null;

  return { openLead: (id) => id && setActive(id), drawer, activeLead: active };
}

// A lead id that opens the drawer. Stops propagation so it works inside a clickable row.
export function LeadLink({ leadId, onOpen, subtitle, className = "" }) {
  if (!leadId) return <span className="text-ink-faint text-xs">—</span>;
  return (
    <button
      type="button"
      data-testid={`lead-link-${leadId}`}
      onClick={(e) => { e.stopPropagation(); onOpen(leadId); }}
      className={`text-left group ${className}`}
      title={`Open lead ${leadId}`}
    >
      <span className="font-mono text-xs font-semibold text-cobalt group-hover:underline inline-flex items-center gap-1">
        {leadId}
        <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
      </span>
      {subtitle ? <div className="text-xs text-ink-faint">{subtitle}</div> : null}
    </button>
  );
}
