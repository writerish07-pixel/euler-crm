import React, { useCallback, useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { get, post, put } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Drawer } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { enableApproverPush } from "../lib/pwa";
import { RequestKycPreview, LocalKycBlock, kycReady, uploadKycFiles } from "../components/LeadDocuments";
import DealFormatCard from "../components/DealFormatCard";

export default function Approvals() {
  const { canApproveLeads, isExecutive } = useAuth();
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("pending");
  const [busy, setBusy] = useState("");
  const [reason, setReason] = useState("");
  const [pushNote, setPushNote] = useState("");
  const [complete, setComplete] = useState(null);

  const load = useCallback(() => {
    get("/lead-requests", { status }).then(setRows).catch(() => setRows([]));
  }, [status]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!canApproveLeads) return;
    enableApproverPush({ requestPermission: false }).then((r) => {
      if (r.ok) setPushNote("on");
      else setPushNote("optional");
    });
  }, [canApproveLeads]);

  const turnOnPush = async () => {
    const r = await enableApproverPush({ requestPermission: true });
    if (r.ok) {
      setPushNote("on");
      toast.success("Phone alerts on for this device");
    } else if (r.reason === "denied") {
      toast.error("Notifications are blocked in the browser. Approve in the app instead.");
      setPushNote("blocked");
    } else {
      toast.error("Phone alerts need the Home Screen app. Approve here either way.");
      setPushNote("optional");
    }
  };

  const act = async (id, kind) => {
    setBusy(id + kind);
    try {
      const row = rows.find((r) => r.requestId === id);
      if (kind === "approve") {
        const r = await post(`/lead-requests/${id}/approve`, {});
        toast.success(row?.existingLeadId
          ? `Assignment approved — ${r.leadId} is live for the executive`
          : `Lead ${r.leadId} created`);
      } else {
        await post(`/lead-requests/${id}/reject`, { reason });
        toast.success(row?.existingLeadId
          ? "Assignment rejected — lead returned to unassigned"
          : "Request rejected — no lead created");
        setReason("");
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update request");
    } finally { setBusy(""); }
  };

  return (
    <div data-testid="approvals-page">
      <PageHeader
        title={canApproveLeads ? "Lead approvals" : "Waiting for approval"}
        subtitle={canApproveLeads
          ? "A new enquiry is created only after Approve. Split-assigned imported leads stay on the register; Approve opens them to the executive."
          : "Complete Deal format + KYC, then call GM or Owner. They tap Approve on this screen."}
      />
      {canApproveLeads && (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          {pushNote === "on" ? (
            <p className="text-xs text-ink-soft">Phone alerts are on for this installed app.</p>
          ) : (
            <>
              <Button variant="secondary" data-testid="enable-push-btn" onClick={turnOnPush}>
                Turn on phone alerts
              </Button>
              <p className="text-xs text-ink-soft">
                Optional. Works when Euler CRM is installed on the phone (Home Screen). Approve here either way.
              </p>
            </>
          )}
        </div>
      )}
      <div className="flex gap-2 mb-4">
        {["pending", "approved", "rejected"].map((s) => (
          <Button key={s} variant={status === s ? "primary" : "secondary"} onClick={() => setStatus(s)}>
            {s}
          </Button>
        ))}
      </div>
      {canApproveLeads && status === "pending" && (
        <Field label="Reject reason (optional)" className="mb-4 max-w-md">
          <Input data-testid="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      )}
      <Table
        rowKey="requestId"
        maxHeight="28rem"
        empty={isExecutive ? "Nothing waiting" : "No pending requests"}
        columns={[
          { key: "customerName", label: "Customer", render: (r) => (
            <div>
              <div className="font-semibold">{r.customerName}</div>
              <div className="text-xs text-ink-faint">{r.mobile || "—"}</div>
              {r.existingLeadId && (
                <div className="text-[10px] text-cobalt mt-0.5">On register · {r.existingLeadId}</div>
              )}
            </div>
          ) },
          { key: "vehicle", label: "Vehicle", render: (r) => (
            <div className="text-sm">{r.interestedModel} <span className="text-ink-faint">{r.variant}</span></div>
          ) },
          { key: "executive", label: "Executive" },
          { key: "deal", label: "Deal format", render: (r) => (
            <span className="font-mono">{inr(r.budget || r.dealAmount)}</span>
          ) },
          { key: "kyc", label: "KYC", render: (r) => (
            <div>
              <RequestKycPreview documents={r.documents || []} />
              {r.kycComplete === false && (
                <div className="text-[10px] text-rose-700 mt-1">Missing {(r.kycMissing || []).join(", ")}</div>
              )}
              {r.customerType === "B2B" && r.gstin ? <div className="text-[10px] text-ink-faint">{r.gstin}</div> : null}
            </div>
          ) },
          { key: "createdAt", label: "Submitted", render: (r) => fmtDate(r.createdAt) },
          { key: "status", label: "Status", render: (r) => (
            <Badge>{r.status}{r.leadId ? ` · ${r.leadId}` : (r.existingLeadId ? ` · ${r.existingLeadId}` : "")}</Badge>
          ) },
          ...(isExecutive && status === "pending" ? [{
            key: "complete", label: "", align: "right", render: (r) => (
              <Button variant="secondary" data-testid={`complete-${r.requestId}`}
                onClick={() => setComplete(r)}>
                Complete format
              </Button>
            ),
          }] : []),
          ...(canApproveLeads && status === "pending" ? [{
            key: "act", label: "", align: "right", render: (r) => (
              <div className="flex gap-2 justify-end">
                <Button data-testid={`approve-${r.requestId}`} disabled={!!busy || r.kycComplete === false}
                  onClick={() => act(r.requestId, "approve")}>
                  <Check size={14} /> Approve
                </Button>
                <Button variant="secondary" data-testid={`reject-${r.requestId}`} disabled={!!busy}
                  onClick={() => act(r.requestId, "reject")}>
                  <X size={14} /> Reject
                </Button>
              </div>
            ),
          }] : []),
        ]}
        rows={rows}
      />
      {complete && (
        <CompleteFormatDrawer
          row={complete}
          onClose={() => setComplete(null)}
          onSaved={() => { setComplete(null); load(); }}
        />
      )}
    </div>
  );
}

function CompleteFormatDrawer({ row, onClose, onSaved }) {
  const [budget, setBudget] = useState(Number(row.budget || row.dealAmount || 0) || "");
  const [deal, setDeal] = useState(row.dealFormat || null);
  const [dealLoading, setDealLoading] = useState(false);
  const [kyc, setKyc] = useState({});
  const [gstin, setGstin] = useState(row.gstin || "");
  const [busy, setBusy] = useState(false);
  const customerType = row.customerType || "Individual";

  useEffect(() => {
    if (!row.interestedModel || !row.variant) {
      setDeal(row.dealFormat || null);
      return undefined;
    }
    let alive = true;
    setDealLoading(true);
    get("/commercial/deal-preview", {
      model: row.interestedModel, variant: row.variant, cxDemand: Number(budget) || 0,
    }).then((d) => { if (alive) setDeal(d); })
      .catch(() => { if (alive) setDeal(row.dealFormat || null); })
      .finally(() => { if (alive) setDealLoading(false); });
    return () => { alive = false; };
  }, [row.interestedModel, row.variant, row.dealFormat, budget]);

  const save = async () => {
    if (!(Number(budget) > 0)) return toast.error("Enter Cx Demand — the final amount given to the customer");
    const kycErr = kycReady(customerType, kyc, gstin);
    if (kycErr) return toast.error(kycErr);
    setBusy(true);
    try {
      await put(`/lead-requests/${row.requestId}`, { budget: Number(budget), gstin });
      await uploadKycFiles(`/lead-requests/${row.requestId}/documents`, kyc);
      toast.success("Sent for GM / Owner Approve — the lead stays on the register until they tap Approve");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save the approval format");
    } finally { setBusy(false); }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-2xl"
      title="Complete approval format"
      subtitle={`${row.customerName} · ${row.existingLeadId || row.requestId}`}
      footer={<div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button data-testid="save-approval-format-btn" onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Send for approval"}
        </Button>
      </div>}
    >
      <div className="space-y-4">
        <p className="text-sm text-ink-soft">
          This customer is already on the Lead Register under your name. Fill Deal format and KYC
          the same way as a new enquiry. GM / Owner Approve then lets you work the lead.
        </p>
        <DealFormatCard
          snapshot={deal}
          cxDemand={budget}
          onCxDemand={setBudget}
          loading={dealLoading}
          missingPrice={!row.interestedModel || !row.variant}
        />
        <LocalKycBlock customerType={customerType} files={kyc} setFiles={setKyc} gstin={gstin} onGstin={setGstin} />
      </div>
    </Drawer>
  );
}
