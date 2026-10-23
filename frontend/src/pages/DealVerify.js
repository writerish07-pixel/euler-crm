/**
 * Owner / Sales GM / Showroom Admin: customer-stated paid amount vs receipts.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PhoneCall } from "lucide-react";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr } from "../lib/format";
import { toast } from "sonner";
import { PageHeader, Table, Badge, Field, Select, Input, Button, Card } from "../components/ui";
import ReportActions from "../components/ReportActions";

const FILTERS = [
  ["mismatch", "Mismatch"],
  ["listening", "Needs listen"],
  ["pending", "Still calling"],
  ["answered", "Answered"],
];

function kindTone(kind) {
  if (kind === "over") return "bg-rose-50 text-rose-800 ring-rose-600/20";
  if (kind === "under") return "bg-amber-50 text-amber-800 ring-amber-600/20";
  return "bg-emerald-50 text-emerald-700 ring-emerald-600/20";
}

export default function DealVerify() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("mismatch");
  const [listen, setListen] = useState({});

  const load = useCallback(() => {
    return get("/deal-verify", { filter, limit: 400 }).then(setRows).catch(() => setRows([]));
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const confirm = async (leadId) => {
    const amount = listen[leadId];
    if (!String(amount || "").trim()) return toast.error("Enter the amount from the recording");
    try {
      await post(`/leads/${leadId}/deal-verify/amount`, { amount });
      toast.success("Amount saved");
      setListen((s) => ({ ...s, [leadId]: "" }));
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save"));
    }
  };

  const callNow = async (leadId) => {
    try {
      await post(`/leads/${leadId}/deal-verify/call`, {});
      toast.success("Verification call started");
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Call did not start"));
    }
  };

  return (
    <div data-testid="deal-verify-page">
      <PageHeader
        title="Deal verify"
        subtitle="Akar Euler Hindi call — amount the customer paid vs receipts in the file"
        actions={<ReportActions onRefresh={load} />}
      />
      <div className="w-full sm:w-56 mb-4">
        <Field label="Show">
          <Select data-testid="deal-verify-filter" value={filter} onChange={(e) => setFilter(e.target.value)}>
            {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
      </div>
      <Table
          rowKey="leadId"
          columns={[
            { key: "customerName", label: "Customer", render: (r) => (
              <div>
                <Link to={`/leads?open=${encodeURIComponent(r.leadId)}`} className="font-medium text-cobalt hover:underline">{r.customerName}</Link>
                <div className="text-[11px] text-ink-faint">{r.leadId} · {r.executive || "—"}</div>
              </div>
            ) },
            { key: "stated", label: "Customer said", render: (r) => r.dealVerifyAmount ? inr(r.dealVerifyAmount) : "—" },
            { key: "received", label: "In app", render: (r) => inr(r.totalReceived) },
            { key: "payable", label: "Cx Demand", render: (r) => inr(r.customerPayable || r.cxDemand || r.budget) },
            { key: "gap", label: "Flag", render: (r) => (
              r.dealVerifyMismatch
                ? <Badge tone={kindTone(r.dealVerifyMismatchKind)}>
                    {r.dealVerifyMismatchKind === "over" ? "Paid more than receipts" : "Paid less than receipts"}
                  </Badge>
                : <Badge>{r.dealVerifyStatus || "—"}</Badge>
            ) },
            { key: "tape", label: "Recording", render: (r) => r.dealVerifyRecordingUrl
              ? <audio controls src={r.dealVerifyRecordingUrl} className="h-8 max-w-[12rem]" />
              : <span className="text-ink-faint">—</span> },
            { key: "listen", label: "From tape", render: (r) => (
              r.dealVerifyStatus === "answered" ? <span className="text-xs text-ink-faint">{r.dealVerifySource || ""}</span> : (
                <div className="flex gap-1">
                  <Input className="!py-1 w-28" data-testid={`deal-verify-amt-${r.leadId}`}
                    value={listen[r.leadId] || ""} placeholder="₹"
                    onChange={(e) => setListen((s) => ({ ...s, [r.leadId]: e.target.value }))} />
                  <Button variant="secondary" className="!py-1 !px-2" onClick={() => confirm(r.leadId)}>Save</Button>
                  <Button variant="secondary" className="!py-1 !px-2" data-testid={`deal-verify-call-${r.leadId}`}
                    onClick={() => callNow(r.leadId)}>Call now</Button>
                </div>
              )
            ) },
          ]}
          rows={rows}
          empty="No files in this list"
        />
    </div>
  );
}

export function DealVerifyCard({ lead, booked, canManage, onSaved }) {
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  if (!booked && !lead.dealVerifyStatus) return null;
  const mismatch = !!lead.dealVerifyMismatch;
  const save = async () => {
    if (!String(amount || "").trim()) return toast.error("Enter the amount the customer paid");
    setBusy(true);
    try {
      await post(`/leads/${lead.leadId}/deal-verify/amount`, { amount });
      toast.success("Amount saved");
      setAmount("");
      onSaved && onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save"));
    } finally { setBusy(false); }
  };
  const callNow = async () => {
    setBusy(true);
    try {
      await post(`/leads/${lead.leadId}/deal-verify/call`, {});
      toast.success("Verification call started — staff phone is not in this path");
      onSaved && onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Call did not start"));
    } finally { setBusy(false); }
  };
  return (
    <Card className={`p-4 sm:col-span-2 ${mismatch ? "ring-1 ring-rose-300 bg-rose-50/40" : ""}`} data-testid="deal-verify-card">
      <div className="flex items-center gap-2 mb-2">
        <PhoneCall size={16} className="text-cobalt" />
        <h4 className="font-heading font-bold text-ink text-sm">Deal verify (Akar Euler)</h4>
        {mismatch && (
          <Badge tone={kindTone(lead.dealVerifyMismatchKind)} data-testid="deal-verify-mismatch">
            {lead.dealVerifyMismatchKind === "over" ? "Paid more than receipts" : "Mismatch"}
          </Badge>
        )}
      </div>
      <p className="text-[11px] text-ink-faint mb-2">
        Hindi call asks what they paid. Typed keypad and spoken recording both count. Retries until an amount is stored.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm mb-2">
        <div><div className="text-[11px] text-ink-faint">Status</div>{lead.dealVerifyStatus || "queued"}</div>
        <div><div className="text-[11px] text-ink-faint">Customer said</div>{lead.dealVerifyAmount ? inr(lead.dealVerifyAmount) : "—"}</div>
        <div><div className="text-[11px] text-ink-faint">Receipts</div>{inr(lead.totalReceived)}</div>
        <div><div className="text-[11px] text-ink-faint">Source</div>{lead.dealVerifySource || "—"}</div>
      </div>
      {lead.dealVerifyRecordingUrl ? (
        <audio controls src={lead.dealVerifyRecordingUrl} className="w-full mb-2" data-testid="deal-verify-audio" />
      ) : null}
      {canManage && (
        <div className="flex flex-wrap gap-2">
          <Input data-testid="deal-verify-amount" className="w-36" value={amount}
            placeholder="Amount paid" onChange={(e) => setAmount(e.target.value)} />
          <Button variant="secondary" onClick={save} disabled={busy}>Save from tape</Button>
          <Button variant="secondary" onClick={callNow} disabled={busy}>Call now</Button>
        </div>
      )}
    </Card>
  );
}
