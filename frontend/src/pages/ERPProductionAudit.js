import React, { useEffect, useState } from "react";
import { ShieldCheck, CheckCircle2, AlertTriangle, XCircle, RefreshCw } from "lucide-react";
import { get } from "../lib/api";
import { Card, PageHeader, Button } from "../components/ui";

const ICON = { PASS: CheckCircle2, WARNING: AlertTriangle, FAIL: XCircle };
const TONE = {
  PASS: "text-emerald-600 bg-emerald-50 ring-emerald-600/20",
  WARNING: "text-amber-600 bg-amber-50 ring-amber-600/20",
  FAIL: "text-red-600 bg-red-50 ring-red-600/20",
};

export default function ERPProductionAudit() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);
  const run = () => { setLoading(true); get("/reports/production-audit").then(setD).finally(() => setLoading(false)); };
  useEffect(() => { run(); }, []);
  if (!d) return <div className="text-ink-faint text-sm">Running production audit…</div>;

  const go = d.goLive;
  return (
    <div data-testid="erp-production-audit">
      <PageHeader title="ERP Production Audit" subtitle="Owner · live certification vs the original spreadsheet + Apps Script"
        actions={<Button data-testid="rerun-audit-btn" onClick={run} disabled={loading}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Re-run</Button>} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <Card className={`p-6 col-span-1 ${go ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`} data-testid="audit-verdict">
          <div className="flex items-center gap-3">
            <ShieldCheck size={32} className={go ? "text-emerald-600" : "text-red-600"} />
            <div>
              <div className="text-xs uppercase tracking-wide text-ink-faint">Verdict</div>
              <div className={`font-heading text-2xl font-extrabold ${go ? "text-emerald-700" : "text-red-700"}`}>{d.verdict}</div>
            </div>
          </div>
          <div className="mt-4 text-sm text-ink-soft">Readiness Score <span className="font-mono font-bold text-ink">{d.score}%</span> <span className="text-ink-faint">(GO-LIVE needs ≥ 99% & zero FAIL)</span></div>
        </Card>
        <Card className="p-6 flex items-center justify-around col-span-2">
          {[["Pass", d.summary.pass, "text-emerald-600"], ["Warning", d.summary.warning, "text-amber-600"], ["Fail", d.summary.fail, "text-red-600"], ["Total", d.summary.total, "text-ink"]].map(([l, n, t]) => (
            <div key={l} className="text-center">
              <div className={`font-mono text-3xl font-extrabold ${t}`}>{n}</div>
              <div className="text-xs text-ink-faint uppercase">{l}</div>
            </div>
          ))}
        </Card>
      </div>

      {d.blockers.length > 0 && (
        <Card className="p-4 mb-6 bg-red-50 border-red-200" data-testid="audit-blockers">
          <div className="font-heading font-bold text-red-700 mb-2">Go-Live Blockers ({d.blockers.length})</div>
          <ul className="list-disc pl-5 text-sm text-red-800 space-y-1">
            {d.blockers.map((b, i) => <li key={i}><span className="font-semibold">{b.category}:</span> {b.detail}</li>)}
          </ul>
        </Card>
      )}

      <div className="space-y-2">
        {d.checks.map((c, i) => {
          const Ico = ICON[c.status] || AlertTriangle;
          return (
            <div key={i} data-testid={`audit-check-${i}`} className="flex items-center gap-3 bg-white rounded-lg border border-line px-4 py-3 shadow-card">
              <span className={`p-1.5 rounded-full ring-1 ring-inset ${TONE[c.status]}`}><Ico size={16} /></span>
              <div className="flex-1">
                <div className="font-semibold text-ink text-sm">{c.category}</div>
                <div className="text-xs text-ink-soft">{c.detail}</div>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ring-1 ring-inset ${TONE[c.status]}`}>{c.status}</span>
            </div>
          );
        })}
      </div>
      <div className="text-xs text-ink-faint mt-4">Generated {d.generatedAt}</div>
    </div>
  );
}
