import React, { useEffect, useState, useCallback } from "react";
import { Plus, Phone, ChevronRight, Upload } from "lucide-react";
import { toast } from "sonner";
import { get, post, put } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { PageHeader, Button, Table, Badge, Drawer, Field, Input, Select } from "../components/ui";
import LeadDrawer from "./LeadDrawer";
import LeadImport from "./LeadImport";
import { useAuth } from "../context/AuthContext";

const STATUS_FILTERS = ["all", "New", "Contacted", "Follow-up", "In Progress", "Booked", "Finance Process", "Delivered", "Close Won", "Lost"];

export default function Leads() {
  const { isField } = useAuth();
  const [leads, setLeads] = useState([]);
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [masters, setMasters] = useState(null);

  const load = useCallback(() => {
    get("/leads", { status, q: q || undefined }).then(setLeads);
  }, [status, q]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { get("/masters").then(setMasters); }, []);

  const columns = [
    { key: "leadId", label: "Lead ID", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.leadId}</span> },
    { key: "customerName", label: "Customer", render: (r) => (
      <div>
        <div className="font-semibold text-ink">{r.customerName}</div>
        <div className="text-xs text-ink-faint flex items-center gap-1"><Phone size={10} />{r.mobile || "—"}</div>
      </div>
    )},
    { key: "vehicle", label: "Vehicle", render: (r) => <div className="text-sm"><div>{r.interestedModel || "—"}</div><div className="text-xs text-ink-faint">{r.variant}</div></div> },
    { key: "executive", label: "Executive" },
    { key: "currentStatus", label: "Status", render: (r) => (
      <div className="flex flex-wrap items-center gap-1">
        <Badge>{r.currentStatus}</Badge>
        {/* A lead that has walked away before is worth seeing before the next call —
            including one that has since come back and reads as "New" again. */}
        {Number(r.cancelCount || 0) > 0 && (
          <Badge tone="bg-rose-50 text-rose-700 ring-rose-600/20"
            title={`${r.lastCancelReason || "Cancelled"}${r.lastCancelDate ? ` · ${r.lastCancelDate}` : ""}`}>
            ✕{r.cancelCount}
          </Badge>
        )}
      </div>
    ) },
    ...(!isField ? [
      { key: "customerPayable", label: "Payable", align: "right", mono: true, render: (r) => inr(r.customerPayable) },
      { key: "customerOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.customerOutstanding > 0 ? "text-red-600 font-semibold" : "text-emerald-600"}>{inr(r.customerOutstanding)}</span> },
      // Money held above Customer Payable, and what has already gone back.
      { key: "excessReceived", label: "Excess / Refund", align: "right", mono: true, render: (r) => (
        <div className="text-xs">
          <div className={r.excessReceived > 0 ? "text-amber-700 font-semibold" : "text-ink-faint"}>{inr(r.excessReceived || 0)}</div>
          {r.refundedAmount > 0 && <div className="text-ink-faint">refunded {inr(r.refundedAmount)}</div>}
        </div>
      )},
    ] : []),
    { key: "go", label: "", align: "right", render: () => <ChevronRight size={16} className="text-ink-faint inline" /> },
  ];

  return (
    <div>
      <PageHeader
        title="Lead Register"
        subtitle={`${leads.length} leads in pipeline${isField ? " · field view" : ""}`}
        actions={!isField ? <div className="flex gap-2">
          <Button variant="secondary" data-testid="import-leads-btn" onClick={() => setShowImport(true)}><Upload size={16} /> Import</Button>
          <Button data-testid="new-lead-btn" onClick={() => setShowNew(true)}><Plus size={16} /> New Lead</Button>
        </div> : null}
      />

      <div className="flex flex-col gap-2 mb-4 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex gap-1 overflow-x-auto bg-white rounded-lg p-1 border border-line shadow-card scrollbar-thin -mx-1 px-1 sm:mx-0 sm:flex-wrap">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              data-testid={`filter-${s}`}
              onClick={() => setStatus(s)}
              className={`shrink-0 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${status === s ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}
            >
              {s === "all" ? "All" : s}
            </button>
          ))}
        </div>
        <div className="w-full sm:flex-1 sm:min-w-[200px]">
          <Input data-testid="lead-search" placeholder="Search name / mobile / ID…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <Table
        rowKey="leadId"
        onRowClick={(r) => setActive(r.leadId)}
        columns={columns}
        rows={leads}
        empty="No leads match this filter"
      />

      {active && (
        <LeadDrawer leadId={active} masters={masters} onClose={() => setActive(null)} onChanged={load} />
      )}
      {showNew && (
        <NewLeadDrawer masters={masters} onClose={() => setShowNew(false)} onCreated={(id) => { setShowNew(false); load(); setActive(id); }} />
      )}
      {showImport && (
        <LeadImport onClose={() => setShowImport(false)} onDone={() => { setShowImport(false); load(); }} />
      )}
    </div>
  );
}

function NewLeadDrawer({ masters, onClose, onCreated }) {
  const [form, setForm] = useState({
    customerName: "", mobile: "", city: "", leadSource: "Walk-in", interestedModel: "",
    variant: "", executive: "", priority: "Normal", budget: 0, remarks: "", currentStatus: "New",
    createdDate: todayISO(), nextFollowupDate: "",
  });
  const [variants, setVariants] = useState([]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    if (form.interestedModel) get("/price-master/variants", { model: form.interestedModel }).then(setVariants);
  }, [form.interestedModel]);

  const submit = async () => {
    if (!form.customerName) return toast.error("Customer name is required");
    if (!form.createdDate) return toast.error("Lead date is required");
    try {
      const lead = await post("/leads", { ...form, budget: Number(form.budget) });
      toast.success(`Lead ${lead.leadId} created`);
      onCreated(lead.leadId);
    } catch { toast.error("Failed to create lead"); }
  };

  if (!masters) return null;
  return (
    <Drawer open onClose={onClose} width="max-w-xl" title="New Lead" subtitle="Capture a fresh enquiry"
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-lead-btn" onClick={submit}>Create Lead</Button></div>}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2"><Field label="Customer Name *"><Input data-testid="lead-name" value={form.customerName} onChange={set("customerName")} /></Field></div>
        <Field label="Lead Date"><Input data-testid="lead-date" type="date" value={form.createdDate} onChange={set("createdDate")} /></Field>
        <Field label="Next Follow-up"><Input data-testid="lead-followup" type="date" value={form.nextFollowupDate} onChange={set("nextFollowupDate")} /></Field>
        <Field label="Mobile"><Input data-testid="lead-mobile" value={form.mobile} onChange={set("mobile")} /></Field>
        <Field label="City / Village"><Input value={form.city} onChange={set("city")} /></Field>
        <Field label="Lead Source"><Select value={form.leadSource} onChange={set("leadSource")}>{masters.leadSources.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Executive"><Select value={form.executive} onChange={set("executive")}><option value="">—</option>{masters.executives.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Interested Model"><Select data-testid="lead-model" value={form.interestedModel} onChange={set("interestedModel")}><option value="">—</option>{masters.models.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Variant"><Select value={form.variant} onChange={set("variant")}><option value="">—</option>{variants.map((v) => <option key={v.priceId} value={v.variant}>{v.variant}</option>)}</Select></Field>
        <Field label="Priority"><Select value={form.priority} onChange={set("priority")}>{masters.priorities.map((s) => <option key={s}>{s}</option>)}</Select></Field>
        <Field label="Budget (₹)"><Input type="number" value={form.budget} onChange={set("budget")} /></Field>
        <div className="sm:col-span-2"><Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field></div>
      </div>
    </Drawer>
  );
}
