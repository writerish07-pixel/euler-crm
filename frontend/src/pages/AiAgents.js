import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, RefreshCw, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, fmtTime } from "../lib/format";
import { Card, PageHeader, Badge, Button } from "../components/ui";
import { useLeadDrawer, LeadLink } from "../components/LeadLink";
import { useAuth } from "../context/AuthContext";

const SEV = {
  High: "bg-red-50 text-red-700 ring-red-600/20",
  Medium: "bg-amber-50 text-amber-700 ring-amber-600/20",
  Info: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
};

const CONFIRM_LABEL = {
  write_price_structure: "Write Price Structure",
  connect_oem_sold: "Connect chassis",
  coulson_sync: "Renew + Sync",
  schedule_followup: "Set follow-up",
  acknowledge: "Acknowledge",
};

export default function AiAgents() {
  const { isOwner, isTl } = useAuth();
  const [d, setD] = useState(null);
  const [agent, setAgent] = useState("");
  const [busy, setBusy] = useState("");
  const { openLead, drawer } = useLeadDrawer(() => load());

  const load = useCallback(() => {
    return get("/agents/suggestions", { status: "open", agent: agent || undefined })
      .then(setD)
      .catch(() => toast.error("Could not load AI Agents"));
  }, [agent]);

  useEffect(() => { load(); }, [load]);

  const scan = async () => {
    setBusy("scan");
    try {
      const r = await post("/agents/scan", {});
      setD(r);
      toast.success(`Scan done · ${r.open || 0} open`);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Scan failed"));
    } finally { setBusy(""); }
  };

  const actOn = async (row, verb) => {
    setBusy(row.suggestionId);
    try {
      await post(`/agents/suggestions/${row.suggestionId}/${verb}`, {});
      toast.success(verb === "confirm" ? "Confirmed" : "Dismissed");
      await load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not update suggestion"));
    } finally { setBusy(""); }
  };

  const rows = d?.suggestions || [];
  const filters = useMemo(() => {
    const all = [{ key: "", label: "All" }];
    Object.entries(d?.agents || {}).forEach(([k, lab]) => all.push({ key: k, label: lab }));
    return all;
  }, [d]);

  return (
    <div data-testid="ai-agents-desk">
      <PageHeader
        title="AI Agents"
        subtitle="Finds gaps. You click. Scheme, Ex-Showroom, OEM Extra and Tally are never auto-written."
        actions={(
          <Button data-testid="agents-scan-btn" onClick={scan} disabled={busy === "scan"}>
            <RefreshCw size={14} /> {busy === "scan" ? "Scanning…" : "Scan now"}
          </Button>
        )}
      />
      <p className="text-xs text-ink-soft mb-4">
        Last scan {d?.lastScanAt ? fmtTime(d.lastScanAt) : "—"} · {d?.open ?? 0} open.
        Insurance / RTO PDFs update Price Structure only after Owner or Showroom Admin confirm.
        {!(isOwner || isTl) ? " You can review those; confirm is Owner / Showroom Admin." : ""}
      </p>
      <div className="flex flex-wrap gap-1.5 mb-4" data-testid="agents-filters">
        {filters.map((f) => (
          <button
            key={f.key || "all"}
            type="button"
            data-testid={`agents-filter-${f.key || "all"}`}
            onClick={() => setAgent(f.key)}
            className={`text-xs font-medium rounded-full px-2.5 py-1 ring-1 ring-inset ${
              agent === f.key ? "bg-cobalt-tint text-cobalt ring-cobalt/30" : "bg-white text-ink-soft ring-line hover:bg-zinc-50"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {!d && <div className="text-ink-faint text-sm">Loading AI Agents…</div>}
      {d && rows.length === 0 && (
        <Card className="p-8 flex flex-col items-center gap-3 text-center" data-testid="agents-empty">
          <CheckCircle2 size={40} className="text-emerald-500" />
          <div className="font-heading font-bold text-ink">No open suggestions</div>
          <div className="text-sm text-ink-soft">Scan to look for missing papers, PDF vs Price Structure, OEM gaps, Coulson expiry, follow-ups and Tally type-in lists.</div>
        </Card>
      )}
      <div className="space-y-3">
        {rows.map((row) => (
          <Card key={row.suggestionId} className="p-4" data-testid={`agent-row-${row.suggestionId}`}>
            <div className="flex flex-wrap items-start gap-2">
              <Sparkles size={16} className="text-cobalt mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5 mb-1">
                  <Badge>{row.agentLabel || row.agent}</Badge>
                  <Badge tone={SEV[row.severity] || SEV.Info}>{row.severity || "Info"}</Badge>
                  {row.leadId ? <LeadLink leadId={row.leadId} onOpen={openLead} /> : null}
                </div>
                <div className="font-semibold text-ink text-sm">{row.title}</div>
                <div className="text-sm text-ink-soft mt-0.5 whitespace-normal">{row.detail}</div>
                {row.agent === "pdf_rto_insurance" && row.payload?.toAmount != null && (
                  <div className="text-xs font-mono mt-2 text-ink">
                    {row.payload.field}: {inr(row.payload.fromAmount)} → {inr(row.payload.toAmount)}
                  </div>
                )}
                {row.agent === "tally_prep" && Array.isArray(row.payload?.lines) && (
                  <ol className="mt-2 text-xs font-mono text-ink space-y-0.5" data-testid={`tally-lines-${row.leadId}`}>
                    {row.payload.lines.map((ln, i) => (
                      <li key={`${ln.code}-${i}`}>
                        {ln.section}. {ln.label}: {inr(ln.amount)}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5 shrink-0">
                {row.href ? (
                  <Link to={row.href} className="text-xs text-cobalt underline px-2 py-1.5">Open desk</Link>
                ) : null}
                <Button
                  variant="secondary"
                  data-testid={`agent-dismiss-${row.suggestionId}`}
                  disabled={busy === row.suggestionId}
                  onClick={() => actOn(row, "dismiss")}
                >
                  Dismiss
                </Button>
                {row.canConfirm && (
                  <Button
                    data-testid={`agent-confirm-${row.suggestionId}`}
                    disabled={busy === row.suggestionId}
                    onClick={() => actOn(row, "confirm")}
                  >
                    {CONFIRM_LABEL[row.confirmKind] || "Confirm"}
                  </Button>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>
      {drawer}
    </div>
  );
}
