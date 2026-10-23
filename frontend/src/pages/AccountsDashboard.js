import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Wallet, Landmark, ReceiptText, ShieldCheck, Truck, AlertCircle,
  IndianRupee, Printer, FileText, Warehouse, CalendarDays, Users, ClipboardCheck,
} from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, compactInr, fmtDate, fmtTime, todayISO, num, ytdCount, ytdMoney } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge, Button, Portal, Field, Input, Select } from "../components/ui";
import ReportActions from "../components/ReportActions";
import YardStockCard from "../components/YardStockCard";
import { LeadDocsStrip, RefundChequePick } from "../components/LeadDocuments";
import TallyUnitBooks, { TallyPackInvoiceSections } from "../components/TallyUnitBooks";
import { useAuth } from "../context/AuthContext";

export default function AccountsDashboard() {
  const { isOwner, isAccounts } = useAuth();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [summary, setSummary] = useState(null);
  const [refundRow, setRefundRow] = useState(null);

  const load = () => {
    setErr("");
    return get("/accounts/dashboard").then(setD).catch((e) => {
      setErr(apiErrorMessage(e, "Could not load accounts dashboard"));
      toast.error(apiErrorMessage(e, "Could not load accounts dashboard"));
    });
  };
  useEffect(() => { load(); }, []);

  const openSummary = async (leadId) => {
    try {
      const s = await get(`/leads/${leadId}/billing-summary`);
      setSummary(s);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Billing summary not available"));
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

  if (!d) {
    return (
      <div data-testid="accounts-dashboard">
        <PageHeader title="Accounts Dashboard" subtitle="Tally cross-check"
          actions={<ReportActions onRefresh={load} />} />
        <div className={`text-sm ${err ? "text-red-700" : "text-ink-faint"}`}>
          {err || "Loading accounts dashboard…"}
        </div>
      </div>
    );
  }
  const k = d.kpis || {};
  const dn = d.doNotPost || {};
  const canTallyUpload = isOwner || isAccounts;
  const canRefunded = isOwner || isAccounts;

  return (
    <div data-testid="accounts-dashboard">
      <PageHeader
        title="Accounts Dashboard"
        subtitle={`Tally cross-check · MTD + YTD · updated ${d.lastUpdated ? fmtTime(d.lastUpdated) : "—"}`}
        actions={<ReportActions onRefresh={load} />}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="acct-period-kpis">
        <StatCard label="Collected (MTD)" value={compactInr(k.collectedMtd)} sub={ytdMoney(k.collectedYtd)} icon={Wallet} tone="text-cobalt" />
        <StatCard label="Deliveries (MTD)" value={num(k.deliveriesMtd)} sub={ytdCount(k.deliveriesYtd)} icon={Truck} tone="text-teal-600" />
        <StatCard label="Customer outstanding" value={compactInr(k.customerOutstanding)} sub="live · not period-cut" icon={IndianRupee} tone="text-red-600" />
        <Link to="/finance?view=pending" className="block" data-testid="acct-finance-pending">
          <StatCard label="Finance pending" value={compactInr(k.financeOutstanding)}
            sub={`${k.financePendingFiles || 0} open files`} icon={Landmark} tone="text-violet-600" />
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
        <StatCard label="OEM claims open" value={compactInr(k.oemClaimsOpen)}
          sub={`${k.oemClaimsOpenCount || 0} claim lines`} icon={ReceiptText} tone="text-amber-600" />
        <StatCard label="Insurance payout due" value={compactInr(k.insurancePayoutDue)}
          sub={`${k.insuranceOpenCount || 0} policies`} icon={ShieldCheck} tone="text-cobalt" />
      </div>

      <div className="flex flex-wrap gap-2 mt-5">
        <Link to="/followup-leads"><Button variant="secondary" data-testid="acct-go-followup"><ClipboardCheck size={14} /> Follow-up register</Button></Link>
        <Link to="/leads"><Button variant="secondary" data-testid="acct-go-leads"><Users size={14} /> Lead Register</Button></Link>
        <Link to="/monthly"><Button variant="secondary" data-testid="acct-go-monthly"><CalendarDays size={14} /> Monthly Register</Button></Link>
        <Link to="/payments"><Button variant="secondary" data-testid="acct-go-payments"><Wallet size={14} /> Payments</Button></Link>
        <Link to="/finance"><Button variant="secondary" data-testid="acct-go-finance"><Landmark size={14} /> Finance</Button></Link>
        <Link to="/claims"><Button variant="secondary" data-testid="acct-go-claims"><ReceiptText size={14} /> OEM Claims</Button></Link>
        <Link to="/insurance"><Button variant="secondary" data-testid="acct-go-insurance"><ShieldCheck size={14} /> Insurance</Button></Link>
        <Link to="/inventory"><Button variant="secondary" data-testid="acct-go-inventory"><Warehouse size={14} /> Inventory</Button></Link>
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
              { key: "invoiceNumber", label: "Invoice", mono: true, render: (r) => (
                <div>
                  <span className="font-mono">{r.invoiceNumber || "—"}</span>
                  {Number(r.vehicleCount) > 1 ? (
                    <div className="text-[11px] text-ink-faint" data-testid={`tally-cov-${r.leadId}`}>
                      {r.vehicleCount} units · invoices {r.tallyInvoicesUploaded || 0}/{r.vehicleCount}
                      {r.tallyLedgerComplete ? " · ledger ok" : " · ledger due"}
                    </div>
                  ) : null}
                </div>
              ) },
              { key: "customerName", label: "Customer", render: (r) => (
                <div>
                  <span className="font-semibold">{r.customerName}</span>
                  {r.executive ? <div className="text-[11px] text-ink-faint">{r.executive}</div> : null}
                </div>
              ) },
              { key: "deliveryDate", label: "Delivered", render: (r) => fmtDate(r.deliveryDate) || "—" },
              { key: "customerPayable", label: "Payable", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
              { key: "totalReceived", label: "Received", align: "right", mono: true, render: (r) => inr(r.totalReceived) },
              { key: "customerOutstanding", label: "Balance", align: "right", mono: true, render: (r) => (
                <span className={Number(r.customerOutstanding) > 0 ? "text-red-600 font-semibold" : "text-emerald-600"}>{inr(r.customerOutstanding)}</span>
              ) },
              { key: "act", label: "", align: "right", render: (r) => (
                <div className="flex flex-wrap justify-end gap-1">
                  <Button variant="secondary" className="!py-1 !px-2 text-xs" data-testid={`open-summary-${r.leadId}`}
                    onClick={(e) => { e.stopPropagation(); openSummary(r.leadId); }}>
                    <FileText size={13} /> Summary
                  </Button>
                  <Link to={`/payments?leadId=${encodeURIComponent(r.leadId)}`} onClick={(e) => e.stopPropagation()}>
                    <Button variant="secondary" className="!py-1 !px-2 text-xs" data-testid={`record-pay-${r.leadId}`}>
                      <Wallet size={13} /> Payment
                    </Button>
                  </Link>
                </div>
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
            <h3 className="font-heading font-bold text-ink text-sm mb-2">How Accounts uploads</h3>
            <ol className="text-xs text-ink-soft space-y-1.5 list-decimal list-inside" data-testid="accounts-howto">
              <li><b>Tally GST</b> — open <b>Summary</b> on a delivered file. Post one GST invoice per unit, then combine selected units on the ledger or keep them separate. Upload the scans here.</li>
              <li><b>Customer money</b> — tap <b>Payment</b> on the row (or Summary → Record payment). Cash / UPI / cheque / NEFT / Finance go on Payment Ledger, including after delivery while the file is Active. For a pack, open the lead → Payments tab to club or split units.</li>
              <li><b>Finance / insurance / claims</b> — use Finance Register, Insurance Payouts, and Scheme / OEM Claim Register in the sidebar. Inventory and Monthly Register stay on this desk too.</li>
              <li>Print Summary first so Tally only has charges &amp; passed discounts — never OEM claims or retained scheme.</li>
            </ol>
          </Card>
        </div>
      </div>

      <Card className="p-5 mt-6" data-testid="cancelled-refund-queue">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-heading font-bold text-ink">Cancelled — refund due</h3>
            <p className="text-xs text-ink-soft">Money still held on cancelled deals. Not a Tally bill — return it, then tap Refunded.</p>
          </div>
          <Badge>{k.cancelledRefundDue || 0} · {inr(k.cancelledRefundHeld || 0)}</Badge>
        </div>
        <Table
          rowKey="leadId"
          empty="No cancelled deals holding money"
          columns={[
            { key: "customerName", label: "Customer", render: (r) => (
              <div>
                <span className="font-semibold">{r.customerName}</span>
                {r.executive ? <div className="text-[11px] text-ink-faint">{r.executive}</div> : null}
              </div>
            ) },
            { key: "cancelDate", label: "Cancelled", render: (r) => fmtDate(r.cancelDate) || "—" },
            { key: "cancelReason", label: "Reason" },
            { key: "excessReceived", label: "Held", align: "right", mono: true, render: (r) => <span className="text-amber-700 font-semibold">{inr(r.excessReceived)}</span> },
            { key: "act", label: "", align: "right", render: (r) => (
              <Button variant="secondary" className="!py-1 !px-2 text-xs" data-testid={`open-refund-${r.leadId}`}
                onClick={(e) => { e.stopPropagation(); setRefundRow(r); }}>
                Refund summary
              </Button>
            ) },
          ]}
          rows={d.cancelledRefundQueue || []}
        />
      </Card>

      {summary && (
        <Portal>
        <div className="fixed inset-0 z-50 h-[100dvh] bg-black/40 flex items-center justify-center p-4" data-testid="billing-summary-modal"
          onClick={() => setSummary(null)}>
          <div className="bg-white rounded-xl border border-line shadow-drawer max-w-2xl w-full max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain p-5"
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
              <TallyPackInvoiceSections summary={summary} />
              <h2>B. Other heads — not on Tally (no GST)</h2>
              <table>
                {(summary.offTallyLines || []).length === 0 && <tr><td colSpan={2}>None</td></tr>}
                {(summary.offTallyLines || []).map((ln) => (
                  <tr key={ln.code}><td>{ln.label}</td><td className="num">{inr(ln.amount)}</td></tr>
                ))}
                <tr><td>Off-Tally total</td><td className="num">{inr(summary.totals?.offTallyTotal)}</td></tr>
              </table>
              <h2>C. Customer payable (Tally + other heads)</h2>
              <table>
                <tr><td>Customer collect</td><td className="num">{inr(summary.totals?.customerCollectTotal ?? summary.totals?.customerPayable)}</td></tr>
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
            <LeadDocsStrip
              leadId={summary.leadId}
              kinds={["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "kyc_gst", "delivery_insurance", "delivery_rto", "refund_cheque"]}
              canUploadKinds={[]}
              title="Documents"
            />
            <TallyUnitBooks
              leadId={summary.leadId}
              units={summary.units || []}
              canUpload={canTallyUpload}
              documents={summary.documents}
            />
            <Link to={`/payments?leadId=${encodeURIComponent(summary.leadId)}`} data-testid="record-payment-link">
              <Button className="mt-3 !py-1.5 !px-3 text-xs"><Wallet size={13} /> Record payment</Button>
            </Link>
          </div>
        </div>
        </Portal>
      )}

      {refundRow && (
        <RefundSummaryModal
          row={refundRow}
          canRefunded={canRefunded}
          onClose={() => setRefundRow(null)}
          onDone={() => { setRefundRow(null); load(); }}
        />
      )}

      <div className="mt-6">
        <YardStockCard />
      </div>
    </div>
  );
}

function RefundSummaryModal({ row, canRefunded, onClose, onDone }) {
  const [pos, setPos] = useState(null);
  const [form, setForm] = useState({ amount: "", paymentMode: "Cash", date: todayISO(), reference: "", narration: "Cancelled deal refund" });
  const [chequeId, setChequeId] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    get(`/leads/${row.leadId}/refund-position`).then((p) => {
      setPos(p);
      setForm((f) => ({ ...f, amount: String(p.excessReceived || row.excessReceived || "") }));
    }).catch(() => setPos({ excessReceived: row.excessReceived }));
  }, [row.leadId, row.excessReceived]);
  const held = Number((pos && pos.excessReceived) ?? row.excessReceived ?? 0);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!canRefunded) return;
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a refund amount");
    if (form.paymentMode === "Cheque" && !chequeId) return toast.error("Photograph the refund cheque first");
    setBusy(true);
    try {
      await post(`/leads/${row.leadId}/refund`, { ...form, amount: +form.amount, documentId: chequeId });
      toast.success(`Refunded ${inr(+form.amount)} — Payment Ledger and the lead are updated`);
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Refund failed"));
    } finally { setBusy(false); }
  };
  return (
    <Portal>
      <div className="fixed inset-0 z-50 h-[100dvh] bg-black/40 flex items-center justify-center p-4" data-testid="refund-summary-modal" onClick={onClose}>
        <div className="bg-white rounded-xl border border-line shadow-drawer max-w-lg w-full max-h-[calc(100dvh-2rem)] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <h3 className="font-heading font-bold text-ink">Refund summary</h3>
              <p className="text-xs text-ink-soft mt-1">{row.customerName} · {row.leadId} · not a Tally bill</p>
            </div>
            <Button variant="secondary" className="!py-1.5 !px-2.5 text-xs" onClick={onClose}>Close</Button>
          </div>
          <div className="text-sm space-y-1 mb-3">
            <div className="flex justify-between"><span className="text-ink-soft">Reason</span><span>{row.cancelReason || "—"}</span></div>
            <div className="flex justify-between"><span className="text-ink-soft">Still held</span><span className="font-mono font-semibold text-amber-700">{inr(held)}</span></div>
            <div className="flex justify-between"><span className="text-ink-soft">Already refunded</span><span className="font-mono">{inr(row.refundedAmount)}</span></div>
          </div>
          <LeadDocsStrip
            leadId={row.leadId}
            kinds={["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "kyc_gst", "refund_cheque"]}
            canUploadKinds={[]}
            title="Documents"
          />
          {canRefunded && held > 0.01 && (
            <div className="mt-4 pt-3 border-t border-line space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Refund (₹)"><Input data-testid="acct-refund-amount" type="number" value={form.amount} onChange={set("amount")} /></Field>
                <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
                <Field label="Mode">
                  <Select data-testid="acct-refund-mode" value={form.paymentMode} onChange={set("paymentMode")}>
                    {["Cash", "UPI", "Cheque", "NEFT"].map((m) => <option key={m}>{m}</option>)}
                  </Select>
                </Field>
                <Field label="Reference"><Input value={form.reference} onChange={set("reference")} /></Field>
              </div>
              {form.paymentMode === "Cheque" && (
                <RefundChequePick leadId={row.leadId} documentId={chequeId} onUploaded={setChequeId} />
              )}
              <Button data-testid="acct-refunded-btn" onClick={submit} disabled={busy}>
                {busy ? "Recording…" : "Refunded"}
              </Button>
            </div>
          )}
        </div>
      </div>
    </Portal>
  );
}
