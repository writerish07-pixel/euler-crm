import React, { useCallback, useEffect, useMemo, useState } from "react";
import { MessageCircle, Search, RefreshCcw, AlertTriangle, Clock } from "lucide-react";
import { toast } from "sonner";
import { get, post } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Table, Badge, Button, Card, Input, Select } from "../components/ui";
import LeadWhatsApp from "./LeadWhatsApp";

const FILTERS = [
  ["all", "All"],
  ["needs-reply", "Needs reply"],
  ["unread", "Unread"],
  ["active", "Active"],
];

const KINDS = [
  ["", "All types"],
  ["booking", "Booking confirm"],
  ["delivery", "Delivery review"],
  ["followup", "3-day follow-up"],
  ["staff_reply", "Staff reply"],
];

const KIND_LABEL = Object.fromEntries(KINDS.slice(1));

// "2m", "4h", "3d" — a conversation list needs elapsed time, not a date.
function ago(iso) {
  if (!iso) return "";
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(secs)) return "";
  if (secs < 60) return "now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h`;
  if (secs < 604800) return `${Math.floor(secs / 86400)}d`;
  return fmtDate(String(iso).slice(0, 10));
}

export default function WhatsAppInbox() {
  const [tab, setTab] = useState("inbox");
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [data, setData] = useState({ total: 0, threads: [] });
  const [summary, setSummary] = useState(null);
  const [active, setActive] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    get("/whatsapp/threads", { filter, q })
      .then((d) => setData(d))
      .catch(() => toast.error("Could not load conversations"))
      .finally(() => setLoading(false));
    get("/whatsapp/summary").then(setSummary).catch(() => {});
  }, [filter, q]);

  useEffect(() => { load(); }, [load]);
  // Nothing pushes to the browser, so poll while the page is open.
  useEffect(() => {
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const openThread = async (t) => {
    setActive(t);
    if (t.unread) {
      try { await post(`/whatsapp/threads/${t.leadId}/read`, {}); load(); } catch { /* non-fatal */ }
    }
  };

  const s = summary || {};

  return (
    <div data-testid="whatsapp-inbox">
      <PageHeader
        title="WhatsApp"
        subtitle="Every customer conversation in one place"
        actions={
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
              {[["inbox", "Inbox"], ["sent", "Sent"]].map(([k, l]) => (
                <button key={k} data-testid={`wa-tab-${k}`} onClick={() => setTab(k)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${tab === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>
                  {l}
                  {k === "inbox" && s.needsReply ? ` (${s.needsReply})` : ""}
                </button>
              ))}
            </div>
            <Button variant="secondary" data-testid="wa-refresh" onClick={load}>
              <RefreshCcw size={15} /> Refresh
            </Button>
          </div>
        } />

      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          <Stat label="Needs reply" value={s.needsReply} tone="text-amber-700" testid="wa-stat-needs" />
          <Stat label="Unread" value={s.unread} tone="text-cobalt" />
          <Stat label="Open windows" value={s.activeChats} tone="text-emerald-600" sub="can reply freely" />
          <Stat label="Failed sends" value={s.failed} tone={s.failed ? "text-red-600" : "text-ink-faint"} />
        </div>
      )}

      {tab === "sent" ? <SentBox /> : (
        <div className="grid lg:grid-cols-[22rem_1fr] gap-4 items-start">
          <Card className="p-0 overflow-hidden">
            <div className="p-3 border-b border-line space-y-2">
              <div className="relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
                <Input data-testid="wa-search" value={q} onChange={(e) => setQ(e.target.value)}
                  placeholder="Name, mobile or lead ID" className="pl-8" />
              </div>
              <div className="flex flex-wrap gap-1">
                {FILTERS.map(([k, l]) => (
                  <button key={k} data-testid={`wa-filter-${k}`} onClick={() => setFilter(k)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${filter === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100 border border-line"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>

            <div className="max-h-[32rem] overflow-y-auto overscroll-contain" data-testid="wa-thread-list">
              {loading && <div className="p-6 text-sm text-ink-faint text-center">Loading…</div>}
              {!loading && data.threads.length === 0 && (
                <div className="p-6 text-sm text-ink-faint text-center">
                  {q || filter !== "all" ? "No conversations match" : "No WhatsApp conversations yet"}
                </div>
              )}
              {data.threads.map((t) => (
                <button key={t.leadId} data-testid={`wa-thread-${t.leadId}`} onClick={() => openThread(t)}
                  className={`w-full text-left px-3 py-2.5 border-b border-zinc-100 last:border-0 transition-colors ${active?.leadId === t.leadId ? "bg-cobalt-tint" : "hover:bg-zinc-50"}`}>
                  <div className="flex items-baseline gap-2">
                    <span className={`truncate text-sm ${t.unread ? "font-bold text-ink" : "font-medium text-ink"}`}>
                      {t.customerName || t.phone}
                    </span>
                    <span className="ml-auto text-[11px] text-ink-faint shrink-0">{ago(t.lastMessageAt)}</span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {t.lastDirection === "inbound" && <span className="text-[11px] text-amber-700 font-semibold shrink-0">↙</span>}
                    <span className="truncate text-xs text-ink-soft">{t.lastMessageText || "—"}</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1 mt-1">
                    <span className="font-mono text-[10px] text-ink-faint">{t.leadId}</span>
                    {t.unread && <Badge tone="bg-cobalt-tint text-cobalt ring-cobalt/20">New</Badge>}
                    {t.sessionOpen && <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">Open</Badge>}
                    {t.optOut && <Badge tone="bg-zinc-100 text-zinc-600 ring-zinc-500/20">STOP</Badge>}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          <Card className="p-4 min-h-[20rem]">
            {active ? (
              <>
                <div className="flex flex-wrap items-baseline gap-2 pb-3 mb-3 border-b border-line">
                  <h3 className="font-heading font-bold text-ink">{active.customerName || active.phone}</h3>
                  <span className="font-mono text-xs text-ink-faint">{active.leadId}</span>
                  {active.executive && <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{active.executive}</Badge>}
                  {!active.sessionOpen && (
                    <span className="ml-auto flex items-center gap-1 text-xs text-ink-soft">
                      <Clock size={13} /> 24-hour window closed
                    </span>
                  )}
                </div>
                <LeadWhatsApp leadId={active.leadId} />
              </>
            ) : (
              <div className="h-full grid place-items-center py-16 text-center">
                <div>
                  <MessageCircle size={28} className="text-ink-faint mx-auto mb-2" />
                  <p className="text-sm text-ink-soft">Pick a conversation to read and reply</p>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone, sub, testid }) {
  return (
    <Card className="p-3" data-testid={testid}>
      <div className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</div>
      <div className={`text-xl font-bold tabular ${tone}`}>{value ?? "—"}</div>
      {sub && <div className="text-[11px] text-ink-faint mt-0.5">{sub}</div>}
    </Card>
  );
}

function SentBox() {
  const [rows, setRows] = useState([]);
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    get("/whatsapp/messages", { direction: "outbound", kind, status, q })
      .then(setRows).catch(() => setRows([]));
  }, [kind, status, q]);

  const failed = useMemo(() => rows.filter((r) => r.status === "failed").length, [rows]);

  return (
    <div data-testid="wa-sent-box">
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Select data-testid="wa-kind-filter" value={kind} onChange={(e) => setKind(e.target.value)} className="max-w-xs">
          {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </Select>
        <Select data-testid="wa-status-filter" value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-xs">
          <option value="">Any status</option>
          <option value="accepted">Accepted</option>
          <option value="sent">Sent</option>
          <option value="delivered">Delivered</option>
          <option value="read">Read</option>
          <option value="failed">Failed</option>
        </Select>
        <Input data-testid="wa-sent-search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Search customer or text" className="max-w-xs" />
        {failed > 0 && (
          <span className="flex items-center gap-1 text-xs text-red-600 font-semibold">
            <AlertTriangle size={14} /> {failed} failed
          </span>
        )}
      </div>

      <Table
        rowKey="messageId"
        columns={[
          { key: "createdAt", label: "When", render: (r) => (
            <span title={r.createdAt}>{ago(r.createdAt)}</span>
          ) },
          { key: "customerName", label: "Customer", render: (r) => (
            <span className="font-semibold">{r.customerName || r.phone}</span>
          ) },
          { key: "leadId", label: "Lead", mono: true },
          { key: "kind", label: "Type", render: (r) => (
            <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{KIND_LABEL[r.kind] || r.kind}</Badge>
          ) },
          { key: "text", label: "Message", render: (r) => (
            <span className="text-ink-soft">{(r.text || "—").slice(0, 60)}</span>
          ) },
          { key: "status", label: "Status", render: (r) => (
            r.status === "failed"
              ? <Badge tone="bg-red-50 text-red-700 ring-red-600/20">Failed</Badge>
              : <Badge>{r.status}</Badge>
          ) },
        ]}
        rows={rows}
        empty="Nothing sent yet"
      />
      <p className="text-xs text-ink-faint mt-3">
        Outbound only, newest first. A failed row means BotSpace rejected the send — open the
        conversation to retry.
      </p>
    </div>
  );
}
