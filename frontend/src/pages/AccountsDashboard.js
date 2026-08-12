import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Wallet, Landmark, ReceiptText, ShieldCheck, Truck, AlertCircle,
  IndianRupee, Printer, FileText, ExternalLink,
} from "lucide-react";
import { toast } from "sonner";
import { get } from "../lib/api";
import { inr, compactInr, fmtDate } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button } from "../components/ui";

export default function AccountsDashboard() {
  const [d, setD] = useState(null);
  const [summary, setSummary] = useState(null);

  const load = () => get("/accounts/dashboard").then(setD).catch(() => toast.error("Could not load accounts dashboard"));
  useEffect(() => { load(); }, []);

  const openSummary = async (leadId) => {
    try {
      const s = await get(`/leads/${leadId}/billing-summary`);
      setSummary(s);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Billing summary not available");
    }
  };

  const printSummary = () => {
    const el = document.getElementById("accounts-billing-print");
    if (!el || !summary) return;
    const w = window.open("", "_blank", "noopener,noreferrer,width=900,height=1000");
    if (!w) return toast.error("Allow pop-ups to print");
    w.document.write(`<!DOCTYPE html><html><head><title>Billing Summary ${summary.leadId}</title>
      <style>
        body{font-family:ui-sans-serif,system-ui,sans-serif;padding:24px;max-width:800px;margin:0 auto;color:#111}
        h1{font-size:18px;margin:0 0 8px} table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
        td{padding:6px 4px;border-bottom:1px solid #eee} td.num{text-align:right;font-variant-numeric:tabular-nums}
        .warn{background:#fffbeb;border:1px solid #fcd34d;padding:8px 10px;font-size:12px;margin-bottom:12px}
        h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;margin:16px 0 6px;color:#444}
      </style></head><body>${el.innerHTML}<script>window.onload=function(){window.print()}</script></body></html>`);
    w.document.close();
  };

  if (!d) return <div className="text-ink-faint text-sm">Loading accounts dashboard…</div>;
  const k = d.kpis || {};
  const dn = d.doNotPost || {};

  return (
    <div data-testid="accounts-dashboard">
      <PageHeader
        title="Accounts Dashboard"
        subtitle={`Tally cross-check · money desk · updated ${d.lastUpdated ? new Date(d.lastUpdated).toLocaleTimeString("en-IN") : "—"}`}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Customer outstanding" value={compactInr(k.customerOutstanding)} icon={IndianRupee} tone="text-red-600" />
        <StatCard label="Finance pending" value={compactInr(k.financeOutstanding)}
          sub={`${k.financePendingFiles || 0} open files`} icon={Landmark} tone="text-violet-600" />
        <StatCard label="OEM claims open" value={compactInr(k.oemClaimsOpen)}
          sub={`${k.oemClaimsOpenCount || 0} claim lines`} icon={ReceiptText} tone="text-amber-600" />
        <StatCard label="Insurance payout due" value={compactInr(k.insurancePayoutDue)}
          sub={`${k.insuranceOpenCount || 0} policies`} icon={ShieldCheck} tone="text-cobalt" />
      </div>

      <div className="flex flex-wrap gap-2 mt-5">
        <Link to="/payments"><Button variant="secondary" data-testid="acct-go-payments"><Wallet size={14} /> Payments</Button></Link>
        <Link to="/finance"><Button variant="secondary" data-testid="acct-go-finance"><Landmark size={14} /> Finance</Button></Link>
        <Link to="/claims"><Button variant="secondary" data-testid="acct-go-claims"><ReceiptText size={14} /> OEM Claims</Button></Link>
        <Link to="/insurance"><Button variant="secondary" data-testid="acct-go-insurance"><ShieldCheck size={14} /> Insurance</Button></Link>
        <Link to="/deliveries"><Button variant="secondary" data-testid="acct-go-deliveries"><Truck size={14} /> Deliveries</Button></Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-heading font-bold text-ink">For Tally</h3>
              <p className="text-xs text-ink-soft">Delivered deals — open billing summary, then enter the final bill in Tally</p>
            </div>
            <Badge>{k.deliveredForTally || 0} delivered</Badge>
          </div>
          <Table
            rowKey="leadId"
            empty="No delivered leads yet"
            columns={[
              { key: "invoiceNumber", label: "Invoice", mono: true, render: (r) => r.invoiceNumber || "—" },
              { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
              { key: "deliveryDate", label: "Delivered", render: (r) => fmtDate(r.deliveryDate) || "—" },
              { key: "customerPayable", label: "Payable", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
              { key: "totalReceived", label: "Received", align: "right", mono: true, render: (r) => inr(r.totalReceived) },
              { key: "customerOutstanding", label: "Balance", align: "right", mono: true, render: (r) => (
                <span className={Number(r.customerOutstanding) > 0 ? "text-red-600 font-semibold" : "text-emerald-600"}>{inr(r.customerOutstanding)}</span>
              ) },
              { key: "act", label: "", align: "right", render: (r) => (
                <Button variant="secondary" className="!py-1 !px-2 text-xs" data-testid={`open-summary-${r.leadId}`}
                  onClick={(e) => { e.stopPropagation(); openSummary(r.leadId); }}>
                  <FileText size={13} /> Summary
                </Button>
              ) },
            ]}
            rows={d.tallyQueue || []}
          />
        </Card>

        <div className="space-y-4">
          <Card className="p-5 border-amber-200 bg-amber-50/40">
            <div className="flex items-center gap-2 mb-2">
              <AlertCircle size={16} className="text-amber-600" />
              <h3 className="font-heading font-bold text-ink text-sm">Do not post on customer bill</h3>
            </div>
            <p className="text-xs text-ink-soft mb-3">{dn.note}</p>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-ink-soft">OEM claims outstanding</span><span className="font-mono font-semibold">{inr(dn.oemClaimsOutstanding)}</span></div>
              <div className="flex justify-between"><span className="text-ink-soft">Retained (scheme / OEM extra)</span><span className="font-mono font-semibold">{inr(dn.schemeOrOemExtraRetained)}</span></div>
            </div>
          </Card>
          <Card className="p-5">
            <h3 className="font-heading font-bold text-ink text-sm mb-2">How to use</h3>
            <ol className="text-xs text-ink-soft space-y-1.5 list-decimal list-inside">
              <li>Open <b>Summary</b> for a delivered invoice</li>
              <li>Print / check charges &amp; passed discounts only</li>
              <li>Create the GST invoice in <b>Tally</b></li>
              <li>Record customer / finance / OEM / insurance money here</li>
            </ol>
          </Card>
        </div>
      </div>

      {summary && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="billing-summary-modal"
          onClick={() => setSummary(null)}>
          <div className="bg-white rounded-xl border border-line shadow-drawer max-w-2xl w-full max-h-[90vh] overflow-y-auto p-5"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <h3 className="font-heading font-bold text-ink">Delivery Billing Summary</h3>
                <p className="text-xs text-amber-800 mt-1">{summary.disclaimer}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <Button variant="secondary" className="!py-1.5 !px-2.5 text-xs" onClick={printSummary} data-testid="print-accounts-summary">
                  <Printer size={14} /> Print
                </Button>
                <Button variant="secondary" className="!py-1.5 !px-2.5 text-xs" onClick={() => setSummary(null)}>Close</Button>
              </div>
            </div>
            <div id="accounts-billing-print">
              <h1>Delivery Billing Summary</h1>
              <div className="warn">{summary.disclaimer}</div>
              <div className="text-sm mb-3 grid grid-cols-2 gap-2">
                <div>
                  <div className="font-semibold">{summary.customer?.name}</div>
                  <div className="text-xs text-ink-soft">{summary.leadId} · {summary.vehicle?.model} {summary.vehicle?.variant}</div>
                </div>
                <div className="text-right text-sm">
                  <div className="font-mono font-semibold">INV {summary.invoiceNumber || "—"}</div>
                  <div className="text-xs text-ink-soft">{fmtDate(summary.deliveryDate)}</div>
                </div>
              </div>
              <h2>A. Charges</h2>
              <table>{(summary.chargeLines || []).map((ln) => (
                <tr key={ln.code}><td>{ln.label}</td><td className="num">{inr(ln.amount)}</td></tr>
              ))}
                <tr><td><b>Gross</b></td><td className="num"><b>{inr(summary.totals?.grossVehicleCost)}</b></td></tr>
              </table>
              <h2>B. Customer discounts (passed)</h2>
              <table>
                {(summary.discountLines || []).length === 0 && <tr><td colSpan={2}>None</td></tr>}
                {(summary.discountLines || []).map((ln) => (
                  <tr key={ln.code + ln.label}><td>{ln.label}</td><td className="num">{inr(ln.amount)}</td></tr>
                ))}
              </table>
              <h2>C. Settlement (enter in Tally)</h2>
              <table>
                <tr><td>Customer Payable</td><td className="num"><b>{inr(summary.totals?.customerPayable)}</b></td></tr>
                <tr><td>Received</td><td className="num">{inr(summary.totals?.totalReceived)}</td></tr>
                <tr><td>Outstanding</td><td className="num">{inr(summary.totals?.customerOutstanding)}</td></tr>
              </table>
              {(summary.doNotPostInTally || []).length > 0 && (
                <>
                  <h2>Do not post on customer bill</h2>
                  <table>
                    {(summary.doNotPostInTally || []).map((ln, i) => (
                      <tr key={i}><td>{ln.label}</td><td className="num">{inr(ln.amount)}</td></tr>
                    ))}
                  </table>
                </>
              )}
            </div>
            <a href={`/payments`} className="inline-flex items-center gap-1 text-xs text-cobalt mt-3">
              Record payment <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
