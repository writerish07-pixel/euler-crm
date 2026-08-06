import React, { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Select, Card } from "../components/ui";

export default function Claims() {
  const [rows, setRows] = useState([]);
  const [active, setActive] = useState(null);
  const load = useCallback(() => get("/claims").then(setRows), []);
  useEffect(() => { load(); }, [load]);

  const eligible = rows.reduce((s, r) => s + Number(r.eligibleClaim || 0), 0);

  return (
    <div>
      <PageHeader title="OEM Claim Register" subtitle={`${rows.length} claimable components · ${inr(eligible)} eligible`} />
      <Table
        rowKey="claimId"
        onRowClick={setActive}
        columns={[
          { key: "leadId", label: "Lead", mono: true },
          { key: "customer", label: "Customer", render: (r) => <span className="font-semibold">{r.customer}</span> },
          { key: "model", label: "Vehicle" },
          { key: "component", label: "Component", render: (r) => <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.component}</Badge> },
          { key: "claimAmount", label: "Claim Amount", align: "right", mono: true, render: (r) => inr(r.claimAmount) },
          { key: "eligibleClaim", label: "Eligible", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.eligibleClaim)}</span> },
          { key: "approvalStatus", label: "Approval", render: (r) => <Badge>{r.approvalStatus}</Badge> },
          { key: "claimStatus", label: "Claim Status", render: (r) => <Badge>{r.claimStatus}</Badge> },
          { key: "receivedAmount", label: "Received", align: "right", mono: true, render: (r) => inr(r.receivedAmount) },
        ]}
        rows={rows}
        empty="No claimable scheme components — apply schemes on booked leads first"
      />
      {active && <SettleModal claim={active} onClose={() => setActive(null)} onDone={() => { setActive(null); load(); }} />}
    </div>
  );
}

function SettleModal({ claim, onClose, onDone }) {
  const [form, setForm] = useState({ claimStatus: claim.claimStatus || "Submitted", receivedAmount: claim.receivedAmount || claim.eligibleClaim || 0, claimReference: claim.claimReference || "" });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    await post("/claims/settle", { leadId: claim.leadId, componentKey: claim.componentKey, claimStatus: form.claimStatus, receivedAmount: +form.receivedAmount, claimReference: form.claimReference });
    toast.success("Claim updated");
    onDone();
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Settle Claim</h3>
        <p className="text-xs text-ink-soft mb-4">{claim.customer} · {claim.component} · {inr(claim.claimAmount)}</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Claim Status"><Select data-testid="claim-status" value={form.claimStatus} onChange={set("claimStatus")}>{["Pending","Submitted","Approved","Received","Rejected"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Received Amount"><Input type="number" value={form.receivedAmount} onChange={set("receivedAmount")} /></Field>
          <div className="col-span-2"><Field label="Claim Reference / UTR"><Input value={form.claimReference} onChange={set("claimReference")} /></Field></div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-claim-btn" onClick={submit}>Save</Button>
        </div>
      </Card>
    </div>
  );
}
