import React, { useCallback, useEffect, useState } from "react";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Card, Table, Badge, Button, Field, Input } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { enableApproverPush } from "../lib/pwa";
import { RequestKycPreview } from "../components/LeadDocuments";

export default function Approvals() {
  const { canApproveLeads, isExecutive } = useAuth();
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("pending");
  const [busy, setBusy] = useState("");
  const [reason, setReason] = useState("");
  const [pushNote, setPushNote] = useState("");

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
      if (kind === "approve") {
        const r = await post(`/lead-requests/${id}/approve`, {});
        toast.success(`Lead ${r.leadId} created`);
      } else {
        await post(`/lead-requests/${id}/reject`, { reason });
        toast.success("Request rejected — no lead created");
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
          ? "A lead is created only after you or the other approver taps Approve. Staff will call if you miss a phone alert."
          : "Call the GM or Owner. They open this screen and tap Approve — only then is the lead created."}
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
      <Card className="p-0 overflow-hidden">
        <Table
          rowKey="requestId"
          empty={isExecutive ? "Nothing waiting" : "No pending requests"}
          columns={[
            { key: "customerName", label: "Customer", render: (r) => (
              <div>
                <div className="font-semibold">{r.customerName}</div>
                <div className="text-xs text-ink-faint">{r.mobile || "—"}</div>
              </div>
            ) },
            { key: "vehicle", label: "Vehicle", render: (r) => (
              <div className="text-sm">{r.interestedModel} <span className="text-ink-faint">{r.variant}</span></div>
            ) },
            { key: "executive", label: "Executive" },
            { key: "budget", label: "Deal amount", align: "right", mono: true, render: (r) => inr(r.budget || r.dealAmount) },
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
              <Badge>{r.status}{r.leadId ? ` · ${r.leadId}` : ""}</Badge>
            ) },
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
      </Card>
    </div>
  );
}
