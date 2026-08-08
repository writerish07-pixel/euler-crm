import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { get, put } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function IncentiveMaster() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/incentive-master").then(setRows); }, []);
  return (
    <div>
      <PageHeader title="Incentive Master" subtitle="Executive retail incentive slabs" />
      <Table
        rowKey="incentiveId"
        columns={[
          { key: "productCategory", label: "Category", render: (r) => <span className="font-semibold">{r.productCategory}</span> },
          { key: "incentivePerRetail", label: "Per Retail", align: "right", mono: true, render: (r) => inr(r.incentivePerRetail) },
          { key: "minRetails", label: "Min Retails", align: "right" },
          { key: "maxSlab", label: "Max Slab", align: "right", mono: true, render: (r) => inr(r.maxSlab) },
          { key: "circularRef", label: "Circular", mono: true },
          { key: "effectiveTo", label: "Valid To", render: (r) => fmtDate(r.effectiveTo) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
        ]}
        rows={rows}
      />
      <p className="text-xs text-ink-faint mt-3">{rows[0]?.notes}</p>
      <IncentiveRegister />
    </div>
  );
}

function IncentiveRegister() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const load = useCallback(() => get("/incentive-register").then(setRows).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const markPaid = async (id) => {
    try {
      await put(`/incentive-register/${id}/pay`, {});
      toast.success("Marked paid");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to update");
    }
  };

  if (!rows.length) return null;
  const pending = rows.filter((r) => r.status !== "Paid").reduce((s, r) => s + Number(r.incentiveAmount || 0), 0);

  return (
    <div className="mt-8">
      <PageHeader title="Incentive Register" subtitle={`Auto-created on delivery · ${inr(pending)} pending payout`} />
      <Table
        rowKey="incentiveId"
        columns={[
          { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive || "—"}</span> },
          { key: "leadId", label: "Lead", mono: true },
          { key: "productCategory", label: "Category" },
          { key: "model", label: "Model", render: (r) => `${r.model || ""} ${r.variant || ""}`.trim() || "—" },
          { key: "deliveryDate", label: "Delivered", render: (r) => fmtDate(r.deliveryDate) },
          { key: "incentiveAmount", label: "Amount", align: "right", mono: true, render: (r) => inr(r.incentiveAmount) },
          { key: "status", label: "Status", render: (r) => <Badge tone={r.status === "Paid" ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-amber-50 text-amber-700 ring-amber-600/20"}>{r.status}</Badge> },
          { key: "actions", label: "", render: (r) => (
            r.status !== "Paid" && user?.role === "owner"
              ? <Button variant="secondary" className="!py-1 !px-3 text-xs" onClick={() => markPaid(r.incentiveId)}>Mark Paid</Button>
              : null
          )},
        ]}
        rows={rows}
      />
      <p className="text-xs text-ink-faint mt-3">Eligibility (min retails / month) verified manually by ASM/RM before payout, per scheme circular.</p>
    </div>
  );
}
