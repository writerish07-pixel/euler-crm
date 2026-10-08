import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Landmark } from "lucide-react";
import { get, post, apiErrorMessage } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { PageHeader, Table, Badge, Button, Field, Input, Select, Card, Modal } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useLeadDrawer, LeadLink } from "../components/LeadLink";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { usePeriodState } from "../lib/period";

function financerRollup(rows) {
  const map = new Map();
  for (const r of rows || []) {
    const key = (r.financer || "—").trim() || "—";
    const cur = map.get(key) || {
      financer: key,
      files: 0,
      pendingFiles: 0,
      sanctionedAmount: 0,
      receivedAgainstFile: 0,
      fileOutstanding: 0,
    };
    cur.files += 1;
    cur.sanctionedAmount += Number(r.sanctionedAmount) || 0;
    cur.receivedAgainstFile += Number(r.receivedAgainstFile) || 0;
    cur.fileOutstanding += Number(r.fileOutstanding) || 0;
    if ((Number(r.fileOutstanding) || 0) > 0 && r.status !== "Received") cur.pendingFiles += 1;
    map.set(key, cur);
  }
  return [...map.values()].sort((a, b) => b.fileOutstanding - a.fileOutstanding || a.financer.localeCompare(b.financer));
}

function isPendingFile(r) {
  return (Number(r.fileOutstanding) || 0) > 0 && r.status !== "Received";
}

export default function Finance() {
  const { isMoneyDesk, isField, isExecutive } = useAuth();
  const [searchParams] = useSearchParams();
  const [rows, setRows] = useState([]);
  const [view, setView] = useState(() => {
    const q = (searchParams.get("view") || "").toLowerCase();
    return ["pending", "overdue", "all"].includes(q) ? q : "all";
  });
  const [receipt, setReceipt] = useState(false);
  const period = usePeriodState();
  const load = useCallback(() => get("/finance", { view, ...period.params }).then(setRows), [view, period.params]);
  useEffect(() => { load(); }, [load]);
  const views = [["all", "All Files"], ["pending", "Pending"], ["overdue", "Overdue"]];
  const [allFiles, setAllFiles] = useState([]);
  const [financerFilter, setFinancerFilter] = useState("");
  const [pendingOnly, setPendingOnly] = useState(() => searchParams.get("pending") === "1");
  useEffect(() => {
    if (!isMoneyDesk) return undefined;
    get("/finance", { view: "pending" }).then(setAllFiles);
    return undefined;
  }, [receipt, isMoneyDesk]);

  const { openLead, drawer } = useLeadDrawer(load);
  const byFinancer = useMemo(() => financerRollup(rows), [rows]);
  const visible = useMemo(() => {
    let out = rows;
    if (financerFilter) {
      const key = financerFilter.toLowerCase();
      out = out.filter((r) => (r.financer || "").trim().toLowerCase() === key);
    }
    if (pendingOnly) out = out.filter(isPendingFile);
    return out;
  }, [rows, financerFilter, pendingOnly]);
  const pickFinancer = (name, { pending = false } = {}) => {
    const next = (name || "").trim();
    setFinancerFilter((cur) => {
      const same = cur === next;
      if (same && pendingOnly === pending) return "";
      return next;
    });
    setPendingOnly(!!pending && !!next);
  };

  return (
    <div data-testid="finance-register">
      <PageHeader
        title="Finance Register"
        subtitle={isExecutive
          ? "Your finance files only — disbursed vs still outstanding"
          : isField && !isMoneyDesk
          ? "Read-only · which financer has paid vs still outstanding"
          : "Financer files — committed vs disbursed"}
        actions={
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
              {views.map(([k, l]) => (
                <button key={k} onClick={() => setView(k)} className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${view === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>{l}</button>
              ))}
            </div>
            <ReportActions onRefresh={load} />
            {isMoneyDesk && (
              <Button data-testid="record-financer-receipt-btn" onClick={() => setReceipt(true)}>
                <Landmark size={16} /> Record Financer Receipt
              </Button>
            )}
          </div>
        }
      />

      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />

      {byFinancer.length > 0 && (
        <Card className="p-5 mb-6" data-testid="finance-by-financer">
          <h3 className="font-heading font-bold text-ink mb-1">By financer</h3>
          <p className="text-xs text-ink-soft mb-3">
            Click pending or remaining to list only open files. Click the financer name for every file.
          </p>
          <Table
            rowKey="financer"
            onRowClick={(r) => pickFinancer(r.financer, { pending: true })}
            rowClassName={(r) => (financerFilter === r.financer ? "bg-cobalt-tint" : undefined)}
            columns={[
              { key: "financer", label: "Financer", render: (r) => (
                <button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); pickFinancer(r.financer); }}>
                  <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.financer}</Badge>
                </button>
              ) },
              { key: "files", label: "Files", align: "right", render: (r) => (
                <button type="button" className="hover:underline" onClick={(e) => { e.stopPropagation(); pickFinancer(r.financer); }}>
                  {r.files}
                </button>
              ) },
              { key: "pendingFiles", label: "Pending", align: "right", render: (r) => (
                r.pendingFiles ? (
                  <button type="button" data-testid={`finance-pending-${r.financer}`}
                    className="text-amber-700 font-semibold hover:underline"
                    onClick={(e) => { e.stopPropagation(); pickFinancer(r.financer, { pending: true }); }}>
                    {r.pendingFiles}
                  </button>
                ) : "—"
              ) },
              { key: "sanctionedAmount", label: "Committed", align: "right", mono: true, render: (r) => inr(r.sanctionedAmount) },
              { key: "receivedAgainstFile", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedAgainstFile)}</span> },
              { key: "fileOutstanding", label: "Remaining", align: "right", mono: true, render: (r) => (
                <button
                  type="button"
                  data-testid={`finance-remaining-${r.financer}`}
                  onClick={(e) => { e.stopPropagation(); pickFinancer(r.financer, { pending: true }); }}
                  className={`hover:underline ${r.fileOutstanding > 0 ? "text-red-600 font-semibold" : "text-ink"}`}
                  title={`Show ${r.financer} pending files`}
                >
                  {inr(r.fileOutstanding)}
                </button>
              ) },
            ]}
            rows={byFinancer}
          />
        </Card>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 mb-3" data-testid="finance-file-heading">
        <div>
          <h3 className="font-heading font-bold text-ink">
            {financerFilter
              ? `${financerFilter} ${pendingOnly ? "pending files" : "files"}`
              : (pendingOnly ? "Pending files" : "Files")}
          </h3>
          <p className="text-xs text-ink-soft">
            {financerFilter
              ? `${visible.length} file${visible.length === 1 ? "" : "s"} for this financer — click a lead to open it`
              : `${visible.length} files · click pending or remaining above to split the list`}
          </p>
        </div>
        {financerFilter && (
          <Button variant="secondary" data-testid="finance-clear-financer" onClick={() => setFinancerFilter("")}>
            Show all financers
          </Button>
        )}
      </div>

      <Table
        rowKey="fileNumber"
        columns={[
          { key: "fileNumber", label: "File #", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.fileNumber}</span> },
          { key: "leadId", label: "Lead", render: (r) => <LeadLink leadId={r.leadId} onOpen={openLead} /> },
          { key: "customerName", label: "Customer", render: (r) => (
            <div>
              {r.leadId
                ? <button type="button" className="font-semibold text-left hover:underline" onClick={() => openLead(r.leadId)}>{r.customerName}</button>
                : <span className="font-semibold">{r.customerName}</span>}
              {r.executive ? <div className="text-[11px] text-ink-faint">{r.executive}</div> : null}
            </div>
          ) },
          { key: "financer", label: "Financer", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.financer}</Badge> },
          { key: "sanctionedAmount", label: "Committed", align: "right", mono: true, render: (r) => inr(r.sanctionedAmount) },
          { key: "receivedAgainstFile", label: "Disbursed", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedAgainstFile)}</span> },
          { key: "fileOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.fileOutstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.fileOutstanding)}</span> },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
          { key: "lastPaymentDate", label: "Last Receipt", render: (r) => fmtDate(r.lastPaymentDate) },
        ]}
        rows={visible}
        empty={financerFilter
          ? `No files for ${financerFilter} in this view`
          : "No finance files — created automatically when a Finance-mode payment is recorded on a lead"}
      />
      {drawer}
      {receipt && isMoneyDesk && (
        <FinanceReceiptModal files={allFiles} onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />
      )}
    </div>
  );
}

function FinanceReceiptModal({ files, onClose, onDone }) {
  const [fileNumber, setFileNumber] = useState("");
  const [form, setForm] = useState({ amount: "", date: todayISO(), reference: "" });
  const sel = files.find((f) => f.fileNumber === fileNumber);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!sel) return toast.error("Select a finance file");
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    try {
      await post(`/finance/${encodeURIComponent(sel.fileNumber)}/receipt`, { amount: +form.amount, date: form.date, reference: form.reference });
      toast.success("Financer receipt recorded");
      onDone();
    } catch (e) { toast.error(apiErrorMessage(e, "Failed")); }
  };
  return (
    <Modal onClose={onClose} width="max-w-lg">
      <div className="overflow-y-auto overscroll-contain p-6">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Record Financer Receipt</h3>
        <p className="text-xs text-ink-soft mb-4">Money actually disbursed by the financer. This does not change the customer's outstanding.</p>
        <Field label="Finance file (financer · customer · outstanding)">
          <Select data-testid="finance-receipt-select" value={fileNumber} onChange={(e) => setFileNumber(e.target.value)}>
            <option value="">— Select —</option>
            {files.map((f) => <option key={f.fileNumber} value={f.fileNumber}>{f.fileNumber} · {f.financer} · {f.customerName} · {inr(f.fileOutstanding)}</option>)}
          </Select>
        </Field>
        {sel && (
          <div className="grid grid-cols-3 gap-3 mt-3">
            <Field label="Amount Received (₹)"><Input data-testid="finance-receipt-amount" type="number" value={form.amount} onChange={set("amount")} placeholder={String(sel.fileOutstanding)} /></Field>
            <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
            <Field label="Reference / UTR"><Input value={form.reference} onChange={set("reference")} /></Field>
          </div>
        )}
        {sel && <p className="text-xs text-ink-soft mt-2">Outstanding: <span className="font-mono font-semibold text-red-600">{inr(sel.fileOutstanding)}</span></p>}
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-finance-receipt-btn" onClick={submit}>Record Receipt</Button>
        </div>
      </div>
    </Modal>
  );
}
