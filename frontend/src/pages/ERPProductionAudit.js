import React, { useEffect, useState } from "react";
import { ShieldCheck, CheckCircle2, AlertTriangle, XCircle, RefreshCw, ChevronDown, ChevronRight, Wrench, Eraser } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { Card, PageHeader, Button } from "../components/ui";

const ICON = { PASS: CheckCircle2, WARNING: AlertTriangle, FAIL: XCircle };
const TONE = {
  PASS: "text-emerald-600 bg-emerald-50 ring-emerald-600/20",
  WARNING: "text-amber-600 bg-amber-50 ring-amber-600/20",
  FAIL: "text-red-600 bg-red-50 ring-red-600/20",
};
const SEV_TONE = {
  Critical: "bg-red-600 text-white",
  High: "bg-orange-500 text-white",
  Medium: "bg-amber-400 text-amber-950",
  Low: "bg-slate-300 text-slate-700",
};
const barColor = (s) => (s >= 99 ? "bg-emerald-500" : s >= 80 ? "bg-amber-400" : "bg-red-500");

function CategoryCard({ c, i }) {
  const [open, setOpen] = useState(c.status === "FAIL");
  const Ico = ICON[c.status] || AlertTriangle;
  return (
    <div data-testid={`audit-category-${c.key}`} className="bg-white rounded-lg border border-line shadow-card overflow-hidden">
      <button data-testid={`audit-category-toggle-${c.key}`} onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors">
        {open ? <ChevronDown size={16} className="text-ink-faint" /> : <ChevronRight size={16} className="text-ink-faint" />}
        <span className={`p-1.5 rounded-full ring-1 ring-inset ${TONE[c.status]}`}><Ico size={16} /></span>
        <div className="flex-1">
          <div className="font-heading font-bold text-ink text-sm">{i + 1}. {c.name}</div>
          <div className="text-xs text-ink-soft">{c.description}</div>
        </div>
        <span className="font-mono text-sm font-bold text-ink w-14 text-right">{c.score}%</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ring-1 ring-inset ${TONE[c.status]}`}>{c.status}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-line/60">
          <div className="mt-3 space-y-1.5">
            {c.checks.map((x, j) => {
              const XI = ICON[x.status] || AlertTriangle;
              return (
                <div key={j} className="flex items-start gap-2.5 text-sm">
                  <span className={`mt-0.5 p-1 rounded-full ring-1 ring-inset ${TONE[x.status]}`}><XI size={12} /></span>
                  <div className="flex-1">
                    <span className="font-medium text-ink">{x.label}</span>
                    <span className="text-ink-soft"> — {x.detail}</span>
                  </div>
                  {x.severity && x.status !== "PASS" && (
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${SEV_TONE[x.severity]}`}>{x.severity}</span>
                  )}
                </div>
              );
            })}
          </div>

          {c.affectedModules?.length > 0 && (
            <div className="mt-3 text-xs text-ink-soft">
              <span className="font-semibold text-ink-faint uppercase tracking-wide">Affected modules: </span>
              {c.affectedModules.map((m) => (
                <span key={m} className="inline-block bg-slate-100 text-slate-600 rounded px-1.5 py-0.5 mr-1 font-mono">{m}</span>
              ))}
            </div>
          )}
          {c.missingItems?.length > 0 && (
            <div className="mt-2 text-xs">
              <span className="font-semibold text-red-600 uppercase tracking-wide">Missing: </span>
              <span className="text-ink-soft">{c.missingItems.join(" · ")}</span>
            </div>
          )}
          {c.suggestedFix && (
            <div className="mt-2 flex items-start gap-1.5 text-xs bg-blue-50 text-blue-800 rounded px-2 py-1.5">
              <Wrench size={13} className="mt-0.5 shrink-0" /><span>{c.suggestedFix}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ERPProductionAudit() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);
  const run = () => { setLoading(true); get("/reports/production-audit").then(setD).finally(() => setLoading(false)); };
  useEffect(() => { run(); }, []);
  const resetForGoLive = async () => {
    if (!window.confirm("GO-LIVE RESET: permanently delete ALL leads, bookings, payments, deliveries, finance, insurance, claims and earnings so staff start from zero? Master price/scheme data is kept. This cannot be undone.")) return;
    if (!window.confirm("Are you absolutely sure? All demo/sample transaction data will be erased.")) return;
    try {
      const r = await post("/admin/reset-transactions", {});
      const total = Object.values(r.cleared || {}).reduce((s, n) => s + n, 0);
      toast.success(`Go-live reset done — cleared ${total} records. CRM now starts fresh.`);
      run();
    } catch (e) { toast.error(e?.response?.data?.detail || "Reset failed"); }
  };
  if (!d) return <div className="text-ink-faint text-sm">Running production audit…</div>;

  const go = d.goLive;
  const sev = d.severityCounts || {};
  return (
    <div data-testid="erp-production-audit">
      <PageHeader title="ERP Production Audit" subtitle="Owner · zero-tolerance certification vs the original spreadsheet + Apps Script"
        actions={<div className="flex items-center gap-2">
          <Button variant="secondary" data-testid="reset-golive-btn" onClick={resetForGoLive} className="!text-red-600 hover:!bg-red-50"><Eraser size={15} /> Reset for Go-Live</Button>
          <Button data-testid="rerun-audit-btn" onClick={run} disabled={loading}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Re-run</Button>
        </div>} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className={`p-6 col-span-1 ${go ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`} data-testid="audit-verdict">
          <div className="flex items-center gap-3">
            <ShieldCheck size={32} className={go ? "text-emerald-600" : "text-red-600"} />
            <div>
              <div className="text-xs uppercase tracking-wide text-ink-faint">Verdict</div>
              <div className={`font-heading text-xl font-extrabold leading-tight ${go ? "text-emerald-700" : "text-red-700"}`}>{d.verdict}</div>
            </div>
          </div>
          <div className="mt-4 text-sm text-ink-soft">Production Score <span className="font-mono font-bold text-ink text-lg">{d.score}%</span></div>
          <div className="mt-2 h-2 rounded-full bg-slate-200 overflow-hidden"><div className={`h-full ${barColor(d.score)}`} style={{ width: `${d.score}%` }} /></div>
          <div className="mt-2 text-xs text-ink-faint">{d.goLiveRule}</div>
        </Card>

        <Card className="p-6 col-span-1" data-testid="audit-severity">
          <div className="text-xs uppercase tracking-wide text-ink-faint mb-3">Open issues by severity</div>
          <div className="grid grid-cols-2 gap-3">
            {["Critical", "High", "Medium", "Low"].map((s) => (
              <div key={s} className="flex items-center justify-between">
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${SEV_TONE[s]}`}>{s}</span>
                <span className="font-mono text-xl font-extrabold text-ink">{sev[s] ?? 0}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6 col-span-1 flex items-center justify-around" data-testid="audit-summary">
          {[["Pass", d.summary.pass, "text-emerald-600"], ["Warn", d.summary.warning, "text-amber-600"], ["Fail", d.summary.fail, "text-red-600"], ["Cats", d.summary.total, "text-ink"]].map(([l, n, t]) => (
            <div key={l} className="text-center">
              <div className={`font-mono text-2xl font-extrabold ${t}`}>{n}</div>
              <div className="text-[10px] text-ink-faint uppercase">{l}</div>
            </div>
          ))}
        </Card>
      </div>

      <Card className="p-5 mb-6" data-testid="audit-scorebreakdown">
        <div className="font-heading font-bold text-ink mb-3">Production Readiness by Category</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
          {d.scoreBreakdown.map((s) => (
            <div key={s.category} className="flex items-center gap-3 text-sm">
              <span className="w-48 shrink-0 text-ink-soft truncate">{s.category}</span>
              <div className="flex-1 h-2 rounded-full bg-slate-200 overflow-hidden"><div className={`h-full ${barColor(s.score)}`} style={{ width: `${s.score}%` }} /></div>
              <span className="font-mono text-xs font-bold text-ink w-12 text-right">{s.score}%</span>
            </div>
          ))}
        </div>
      </Card>

      {d.blockers.length > 0 && (
        <Card className="p-4 mb-6 bg-red-50 border-red-200" data-testid="audit-blockers">
          <div className="font-heading font-bold text-red-700 mb-2">Go-Live Blockers ({d.blockers.length}) — Critical / High</div>
          <ul className="space-y-1.5 text-sm text-red-800">
            {d.blockers.map((b, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${SEV_TONE[b.severity]}`}>{b.severity}</span>
                <span><span className="font-semibold">{b.category}:</span> {b.detail}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="space-y-2">
        {d.categories.map((c, i) => <CategoryCard key={c.key} c={c} i={i} />)}
      </div>
      <div className="text-xs text-ink-faint mt-4">Generated {d.generatedAt}</div>
    </div>
  );
}
