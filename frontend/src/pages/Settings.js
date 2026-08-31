import React, { useEffect, useState, useCallback } from "react";
import { UserPlus, Trash2, CheckCircle2, XCircle, ExternalLink, Copy, RefreshCcw, Plus, ListPlus, KeyRound, MessageCircle, Ban, Users, Warehouse } from "lucide-react";
import { toast } from "sonner";
import { get, post, del, put } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Card, Button, Field, Input, Select, Badge, Table } from "../components/ui";

const MASTER_LIST_CATEGORIES = [
  ["executives", "Executives"],
  ["financers", "Financers"],
  ["leadSources", "Lead Sources"],
  ["priorities", "Priorities"],
  ["activityTypes", "Activity Types"],
];

export default function Settings() {
  const { isOwner, user, isOemFinance } = useAuth();
  const [users, setUsers] = useState([]);
  const [gs, setGs] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "executive", loginId: "" });
  const [backfilling, setBackfilling] = useState(false);
  const [ensuringOem, setEnsuringOem] = useState(false);
  const [ensuringIns, setEnsuringIns] = useState(false);
  const [ensuringCancel, setEnsuringCancel] = useState(false);
  const [pwForm, setPwForm] = useState({ currentPassword: "", newPassword: "", confirmPassword: "" });
  const [pwBusy, setPwBusy] = useState(false);

  const loadUsers = useCallback(() => { if (isOwner) get("/auth/users").then(setUsers).catch(() => {}); }, [isOwner]);
  useEffect(() => {
    loadUsers();
    // The OEM role is denied every route but its own report, so do not even ask.
    if (!isOemFinance) get("/integrations/gsheets").then(setGs).catch(() => {});
  }, [loadUsers, isOemFinance]);

  const changePassword = async () => {
    if (!pwForm.currentPassword || !pwForm.newPassword) {
      return toast.error("Enter current and new password");
    }
    if (pwForm.newPassword.length < 6) {
      return toast.error("New password must be at least 6 characters");
    }
    if (pwForm.newPassword !== pwForm.confirmPassword) {
      return toast.error("New password and confirmation do not match");
    }
    setPwBusy(true);
    try {
      await post("/auth/change-password", {
        currentPassword: pwForm.currentPassword,
        newPassword: pwForm.newPassword,
      });
      toast.success("Password updated — use it next time you sign in");
      setPwForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not change password");
    } finally {
      setPwBusy(false);
    }
  };

  const runBackfill = async () => {
    setBackfilling(true);
    try {
      const r = await post("/integrations/gsheets/backfill", {});
      if (r.ok) {
        const total = Object.values(r.result || {}).reduce((s, x) => s + (x.appended || 0), 0);
        toast.success(`Backfill done — ${total} new rows added to the sheet`);
      } else {
        toast.error(r.reason || "Sheet not writable yet — grant Editor access first");
      }
    } catch { toast.error("Backfill failed"); }
    finally { setBackfilling(false); }
  };

  const ensureOemExtraColumns = async () => {
    setEnsuringOem(true);
    try {
      const r = await post("/integrations/gsheets/ensure-oem-extra-columns", {});
      if (r.ok === false) {
        toast.error(r.reason || "Could not update sheet headers");
        return;
      }
      const added = (r.tabs || []).flatMap((t) => t.added || []);
      if (r.changed) {
        toast.success(`OEM Extra Support columns ready${added.length ? ` — added ${added.length} header(s)` : ""}`);
      } else {
        toast.success("OEM Extra Support columns already present on all related tabs");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add OEM Extra Support columns");
    } finally { setEnsuringOem(false); }
  };

  const ensureInsuranceAgentColumns = async () => {
    setEnsuringIns(true);
    try {
      const r = await post("/integrations/gsheets/ensure-insurance-agent-columns", {});
      if (r.ok === false) {
        toast.error(r.reason || "Could not update the Insurance Register header");
        return;
      }
      const added = (r.tabs || []).flatMap((t) => t.added || []);
      if (r.changed) {
        toast.success(`Insurance Register updated — added ${added.join(", ")}`);
      } else {
        toast.success("Insurance Agent columns are already present");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add Insurance Agent columns");
    } finally { setEnsuringIns(false); }
  };

  const ensureCancelColumns = async () => {
    setEnsuringCancel(true);
    try {
      const r = await post("/integrations/gsheets/ensure-cancel-columns", {});
      if (r.ok === false) {
        toast.error(r.reason || "Could not update the Lead Register header");
        return;
      }
      const added = (r.tabs || []).flatMap((t) => t.added || []);
      if (r.changed) {
        toast.success(`Lead Register updated — added ${added.join(", ")}`);
      } else {
        toast.success("Cancellation columns are already present");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add Cancellation columns");
    } finally { setEnsuringCancel(false); }
  };

  const addUser = async () => {
    if (!form.email || !form.password) return toast.error("Email & password required");
    try { await post("/auth/users", form); toast.success("User created"); setForm({ email: "", password: "", name: "", role: "executive", loginId: "" }); loadUsers(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };
  const removeUser = async (id) => { await del(`/auth/users/${id}`); toast.success("User removed"); loadUsers(); };

  const shareUrl = `${window.location.origin}/share`;

  return (
    <div>
      <PageHeader title="Settings" subtitle="Users, integrations & sharing" />

      <Card className="p-5 mb-6" data-testid="change-password-card">
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={16} className="text-ink-soft" />
          <h3 className="font-heading font-bold text-ink">Change password</h3>
        </div>
        <p className="text-sm text-ink-soft mb-3">
          Signed in as <span className="font-mono text-ink">{user?.email}</span>
          {user?.role ? ` (${user.role})` : ""}. Each user can change their own login password.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
          <Field label="Current password">
            <Input data-testid="current-password" type="password" autoComplete="current-password"
              value={pwForm.currentPassword}
              onChange={(e) => setPwForm({ ...pwForm, currentPassword: e.target.value })} />
          </Field>
          <Field label="New password">
            <Input data-testid="new-password" type="password" autoComplete="new-password"
              value={pwForm.newPassword}
              onChange={(e) => setPwForm({ ...pwForm, newPassword: e.target.value })} />
          </Field>
          <Field label="Confirm new password">
            <Input data-testid="confirm-password" type="password" autoComplete="new-password"
              value={pwForm.confirmPassword}
              onChange={(e) => setPwForm({ ...pwForm, confirmPassword: e.target.value })} />
          </Field>
          <Button data-testid="change-password-btn" onClick={changePassword} disabled={pwBusy}>
            <KeyRound size={15} /> {pwBusy ? "Saving…" : "Update password"}
          </Button>
        </div>
      </Card>

      {/* Outside party: password only. Everything below is dealership business. */}
      {isOemFinance && (
        <p className="text-sm text-ink-faint">
          This account can open the Retail Finance report and change its own password.
        </p>
      )}
      {!isOemFinance && (
      <>
      {isOwner && <BotspaceCard />}
      {isOwner && <CoulsonCard />}

      <Card className="p-5 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <h3 className="font-heading font-bold text-ink">Google Sheet Sync</h3>
          {gs && <Badge tone={gs.enabled ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-amber-50 text-amber-700 ring-amber-600/20"}>{gs.enabled ? "Connected" : "Not configured"}</Badge>}
        </div>
        {gs && (
          <div className="text-sm text-ink-soft space-y-1">
            <div className="flex items-center gap-2">{gs.enabled ? <CheckCircle2 size={15} className="text-emerald-500" /> : <XCircle size={15} className="text-amber-500" />}<span>{gs.reason}</span></div>
            <div>Spreadsheet: <a href={`https://docs.google.com/spreadsheets/d/${gs.spreadsheetId}/edit`} target="_blank" rel="noreferrer" className="text-cobalt inline-flex items-center gap-1">Euler Master <ExternalLink size={12} /></a></div>
            {gs.email && <div>Service account: <span className="font-mono text-xs break-all">{gs.email}</span></div>}
            {!gs.enabled && gs.canRead && gs.canWrite === false && (
              <div className="text-xs text-ink mt-2 bg-amber-50 rounded-lg p-3 ring-1 ring-amber-200">
                The sheet is shared as <b>Viewer</b>. Open your Euler Master sheet → <b>Share</b> → find <span className="font-mono">{gs.email}</span> → change its access to <b>Editor</b>. Sync then appends every new Lead, Booking, Payment, Delivery & Claim automatically.
              </div>
            )}
            {!gs.enabled && !gs.canRead && (
              <div className="text-xs text-ink-faint mt-2 bg-amber-50 rounded-lg p-3 ring-1 ring-amber-200">
                On Railway set <span className="font-mono">GSHEET_CREDENTIALS_JSON</span> to the full service-account JSON
                (and remove a bad <span className="font-mono">GSHEET_CREDENTIALS_PATH</span>). Or place the key file at{" "}
                <span className="font-mono">/app/backend/gsheets_credentials.json</span>. Share the Euler Master sheet
                with the service account email as <b>Editor</b>.
              </div>
            )}
            {gs.enabled && (
              <div className="text-xs text-emerald-700 mt-2 bg-emerald-50 rounded-lg p-3 ring-1 ring-emerald-200">
                Live — new Leads, Bookings, Payments, Deliveries & Claims are appended to your Euler Master sheet automatically.
              </div>
            )}
            {isOwner && (
              <div className="pt-2 space-y-2">
                <div>
                  <Button variant="secondary" data-testid="ensure-oem-extra-cols-btn"
                    onClick={ensureOemExtraColumns} disabled={ensuringOem || !gs?.enabled}>
                    <ListPlus size={14} /> {ensuringOem ? "Adding columns…" : "Add OEM Extra Support columns"}
                  </Button>
                  <span className="text-xs text-ink-faint ml-2">
                    Places Received / Passed / Retained before Dealer Earnings (total last) on Lead Register & Dealer Earnings; creates OEM Extra Support Register if missing
                  </span>
                </div>
                <div>
                  <Button variant="secondary" data-testid="ensure-insurance-agent-cols-btn"
                    onClick={ensureInsuranceAgentColumns} disabled={ensuringIns || !gs?.enabled}>
                    <ListPlus size={14} /> {ensuringIns ? "Adding columns…" : "Add Insurance Agent columns"}
                  </Button>
                  <span className="text-xs text-ink-faint ml-2">
                    Adds "Insurance Agent" to the Lead Register (beside Insurer Name), and Insurance Agent / Rate Source / Last Payout Date to the Insurance Register. Append-only — safe to run twice
                  </span>
                </div>
                <div>
                  <Button variant="secondary" data-testid="ensure-cancel-cols-btn"
                    onClick={ensureCancelColumns} disabled={ensuringCancel || !gs?.enabled}>
                    <ListPlus size={14} /> {ensuringCancel ? "Adding columns…" : "Add Cancellation columns"}
                  </Button>
                  <span className="text-xs text-ink-faint ml-2">
                    Adds Cancel Count / Last Cancel Date / Last Cancel Reason / Last Cancel Stage / Revive On to the Lead Register. Append-only — safe to run twice
                  </span>
                </div>
                <div>
                  <Button variant="secondary" data-testid="backfill-btn" onClick={runBackfill} disabled={backfilling}>
                    <RefreshCcw size={14} /> {backfilling ? "Backfilling…" : "Backfill existing data to sheet"}
                  </Button>
                  <span className="text-xs text-ink-faint ml-2">Pushes all current leads, bookings & payments (skips rows already in the sheet)</span>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card className="p-5 mb-6">
        <h3 className="font-heading font-bold text-ink mb-3">Company Share Board</h3>
        <p className="text-sm text-ink-soft mb-3">A public, read-only board for company people — active bookings & monthly retail only. No customer or staff data.</p>
        <div className="flex items-center gap-2">
          <Input readOnly value={shareUrl} className="font-mono text-xs" />
          <Button variant="secondary" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Link copied"); }}><Copy size={14} /> Copy</Button>
          <a href={shareUrl} target="_blank" rel="noreferrer"><Button variant="secondary"><ExternalLink size={14} /> Open</Button></a>
        </div>
      </Card>

      {isOwner && <CancelReasonsCard />}

      {isOwner && <MastersListCard gsEnabled={gs?.enabled} />}

      {isOwner && (
        <Card className="p-5" data-testid="user-accounts-card">
          <h3 className="font-heading font-bold text-ink mb-3">User Accounts <span className="text-xs font-normal text-ink-faint">(Owner only)</span></h3>
          <p className="text-sm text-ink-soft mb-3">
            Staff sign in with the <b>User ID</b> you set here. Email still works, so
            accounts created before user IDs existed are never locked out — give them
            one below whenever you like.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 items-end mb-4">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="User ID">
              <Input data-testid="new-user-loginid" value={form.loginId}
                onChange={(e) => setForm({ ...form, loginId: e.target.value })}
                placeholder="e.g. amit" />
            </Field>
            <Field label="Email"><Input data-testid="new-user-email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Password"><Input data-testid="new-user-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            <Field label="Role"><Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="executive">Executive</option>
              <option value="tl">Team Leader (completes the deal)</option>
              <option value="accounts">Accounts</option>
              <option value="asm">ASM</option>
              <option value="rm">RM</option>
              <option value="owner">Owner</option>
              <option value="oem_finance">OEM Finance (read-only, no contacts)</option>
            </Select></Field>
            <Button data-testid="add-user-btn" onClick={addUser}><UserPlus size={15} /> Add User</Button>
          </div>
          <Table
            rowKey="userId"
            columns={[
              { key: "name", label: "Name", render: (r) => <span className="font-semibold">{r.name || "—"}</span> },
              { key: "loginId", label: "User ID", render: (r) => <LoginIdCell row={r} onSaved={loadUsers} /> },
              { key: "email", label: "Email", mono: true },
              { key: "role", label: "Role", render: (r) => {
                const tone = r.role === "owner"
                  ? "bg-amber-50 text-amber-700 ring-amber-600/20"
                  : r.role === "accounts"
                    ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
                    : r.role === "asm" || r.role === "rm"
                      ? "bg-sky-50 text-sky-700 ring-sky-600/20"
                      : "bg-blue-50 text-blue-700 ring-blue-600/20";
                return <Badge tone={tone}>{r.role}</Badge>;
              } },
              { key: "act", label: "", align: "right", render: (r) => <button data-testid={`del-user-${r.email}`} onClick={() => removeUser(r.userId)} className="text-red-500 hover:text-red-700"><Trash2 size={15} /></button> },
            ]}
            rows={users}
          />
        </Card>
      )}
      </>
      )}
    </div>
  );
}

const REVIVE_MODES = [
  ["now", "Straight back to New"],
  ["days", "After a cool-off"],
  ["never", "Stays cancelled"],
];

/**
 * Cancel reasons, and what each one does to the lead afterwards.
 *
 * The revival policy sits on the reason rather than being one global switch
 * because "postponed purchase" and "bought another brand" deserve opposite
 * treatment. Chasing the second one every third day forever is how a WhatsApp
 * number earns a poor quality rating and loses template access.
 */
function CancelReasonsCard() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ reason: "", revive: "now", reviveAfterDays: 30 });

  const load = useCallback(() => {
    get("/cancel-reasons").then(setRows).catch(() => toast.error("Could not load cancel reasons"));
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!form.reason.trim()) return toast.error("Reason is required");
    try {
      await post("/cancel-reasons", form);
      toast.success("Cancel reason added");
      setForm({ reason: "", revive: "now", reviveAfterDays: 30 });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not add reason"); }
  };

  const patch = async (row, changes) => {
    try {
      await put(`/cancel-reasons/${row.reasonId}`, { ...row, ...changes });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not update"); }
  };

  const remove = async (row) => {
    try {
      await del(`/cancel-reasons/${row.reasonId}`);
      toast.success("Reason removed");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not remove"); }
  };

  return (
    <Card className="p-5 mb-6" data-testid="cancel-reasons-card">
      <div className="flex items-center gap-2 mb-1">
        <Ban size={16} className="text-rose-600" />
        <h3 className="font-heading font-bold text-ink">Cancel Reasons <span className="text-xs font-normal text-ink-faint">(Owner only)</span></h3>
      </div>
      <p className="text-sm text-ink-soft mb-4">
        Why a customer walked away, and whether the lead comes back. A cancelled lead
        always keeps counting against its executive on the Cancellations report — even
        after it returns to the funnel.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end mb-4">
        <Field label="Reason">
          <Input data-testid="new-cancel-reason" value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
            placeholder="e.g. Waiting for subsidy" />
        </Field>
        <Field label="Then what?">
          <Select value={form.revive} onChange={(e) => setForm({ ...form, revive: e.target.value })}>
            {REVIVE_MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Cool-off (days)">
          <Input type="number" min="1" value={form.reviveAfterDays}
            disabled={form.revive !== "days"}
            onChange={(e) => setForm({ ...form, reviveAfterDays: Number(e.target.value) })} />
        </Field>
        <Button data-testid="add-cancel-reason-btn" onClick={add}><Plus size={15} /> Add Reason</Button>
      </div>

      <Table
        rowKey="reasonId"
        rows={rows}
        empty="No cancel reasons yet"
        columns={[
          { key: "reason", label: "Reason", render: (r) => <span className="font-semibold">{r.reason}</span> },
          { key: "revive", label: "Then what?", render: (r) => (
            <Select value={r.revive} className="!py-1 text-xs max-w-[12rem]"
              onChange={(e) => patch(r, { revive: e.target.value })}>
              {REVIVE_MODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          ) },
          { key: "reviveAfterDays", label: "Cool-off", align: "right", render: (r) => (
            r.revive === "days"
              ? <Input type="number" min="1" value={r.reviveAfterDays}
                  className="!py-1 text-xs w-20 text-right"
                  onChange={(e) => patch(r, { reviveAfterDays: Number(e.target.value) })} />
              : <span className="text-ink-faint">—</span>
          ) },
          { key: "status", label: "Status", render: (r) => (
            <button onClick={() => patch(r, { status: r.status === "Active" ? "Inactive" : "Active" })}>
              <Badge tone={r.status === "Active"
                ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
                : "bg-zinc-100 text-zinc-600 ring-zinc-500/20"}>{r.status}</Badge>
            </button>
          ) },
          { key: "reasonId", label: "", align: "right", render: (r) => (
            <Button variant="ghost" className="!py-1 !px-2" onClick={() => remove(r)}>
              <Trash2 size={14} className="text-red-500" />
            </Button>
          ) },
        ]} />
      <p className="text-xs text-ink-faint mt-3">
        A reason already used on a cancelled lead cannot be deleted — set it Inactive
        instead, so the record of why those leads were lost survives.
      </p>
    </Card>
  );
}

function MastersListCard({ gsEnabled }) {
  const [rows, setRows] = useState([]);
  const [newValue, setNewValue] = useState(() => Object.fromEntries(MASTER_LIST_CATEGORIES.map(([k]) => [k, ""])));
  const load = useCallback(() => get("/masters-list").then(setRows).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const byCategory = (cat) => rows.filter((r) => r.category === cat);

  const addValue = async (cat) => {
    const value = (newValue[cat] || "").trim();
    if (!value) return;
    try {
      await post("/masters-list", { category: cat, value });
      setNewValue((f) => ({ ...f, [cat]: "" }));
      toast.success(`Added to ${cat}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to add");
    }
  };
  const removeValue = async (id) => {
    try { await del(`/masters-list/${id}`); toast.success("Removed"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to remove"); }
  };

  return (
    <Card className="p-5 mb-6">
      <div className="flex items-center gap-2 mb-1">
        <ListPlus size={16} className="text-cobalt" />
        <h3 className="font-heading font-bold text-ink">Master Lists <span className="text-xs font-normal text-ink-faint">(Owner only)</span></h3>
      </div>
      <p className="text-xs text-ink-soft mb-4">
        Executives, Financers, Lead Sources, Priorities & Activity Types shown across the app's dropdowns.
        {gsEnabled ? " Changes sync to the \"Masters\" tab in your Google Sheet." : " Google Sheet sync is not connected — changes stay in the app only."}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {MASTER_LIST_CATEGORIES.map(([cat, label]) => (
          <div key={cat}>
            <div className="text-xs font-semibold text-ink-soft mb-2">{label}</div>
            <div className="flex flex-wrap gap-2 mb-2">
              {byCategory(cat).map((r) => (
                <span key={r.id} data-testid={`master-value-${cat}-${r.value}`}
                  className="inline-flex items-center gap-1.5 text-xs bg-slate-50 ring-1 ring-slate-200 rounded-full px-2.5 py-1">
                  {r.value}
                  <button onClick={() => removeValue(r.id)} className="text-red-400 hover:text-red-600"><Trash2 size={12} /></button>
                </span>
              ))}
              {!byCategory(cat).length && <span className="text-xs text-ink-faint">None yet</span>}
            </div>
            <div className="flex gap-2">
              <Input data-testid={`master-add-${cat}`} placeholder={`Add ${label.toLowerCase()}…`}
                value={newValue[cat]} onChange={(e) => setNewValue((f) => ({ ...f, [cat]: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && addValue(cat)} className="!py-1.5 text-sm" />
              <Button variant="secondary" className="!py-1.5 !px-2.5" onClick={() => addValue(cat)}><Plus size={14} /></Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function BotspaceCard() {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({
    apiKey: "", channelId: "", reviewUrl: "", enabled: true,
    execName: "", execMobile: "", cronToken: "",
  });
  const [execs, setExecs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [bookingBusy, setBookingBusy] = useState(false);
  const webhookUrl = (cfg?.webhookUrl && String(cfg.webhookUrl).startsWith("http")
    && !String(cfg.webhookUrl).includes("onrender.com"))
    ? cfg.webhookUrl
    : "https://euler-crm-production.up.railway.app/api/integrations/botspace/webhook";

  const load = useCallback(() => {
    get("/integrations/botspace").then((d) => {
      setCfg(d);
      setExecs(d.executives || []);
      setForm((f) => ({
        ...f,
        apiKey: d.apiKeyMasked || "",
        channelId: d.channelId || "",
        reviewUrl: d.reviewUrl || "",
        enabled: d.enabled !== false,
        cronToken: d.cronToken || "",
      }));
    }).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const body = {
        channelId: form.channelId,
        reviewUrl: form.reviewUrl,
        enabled: true,
        executives: execs,
        cronToken: form.cronToken,
      };
      if (form.apiKey && !form.apiKey.includes("…") && !form.apiKey.startsWith("•")) {
        body.apiKey = form.apiKey;
      }
      await put("/integrations/botspace", body);
      toast.success("WhatsApp settings saved");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally { setBusy(false); }
  };

  const runJobs = async () => {
    try {
      const r = await post("/integrations/botspace/run-jobs", {});
      toast.success(`Jobs ran — follow-ups ${r.follow?.sent || 0}, finance ${r.finance?.sent || 0}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Job failed");
    }
  };

  const sendReviews = async () => {
    if (!window.confirm("Send the Google review WhatsApp to every delivered Euler lead that has not received it yet? Already-sent leads are skipped.")) return;
    setReviewBusy(true);
    try {
      const r = await post("/integrations/botspace/send-delivery-reviews", { force: false });
      toast.success(`Google review WhatsApp: sent ${r.sent || 0}, already sent ${r.skipped || 0}, failed ${r.failed || 0}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send Google review messages");
    } finally {
      setReviewBusy(false);
    }
  };

  const sendBookings = async () => {
    if (!window.confirm("Send the booking confirmation WhatsApp to every booked Euler lead that has not received it yet? Already-sent leads are skipped.")) return;
    setBookingBusy(true);
    try {
      const r = await post("/integrations/botspace/send-booking-confirms", { force: false });
      toast.success(`Booking WhatsApp: sent ${r.sent || 0}, already sent ${r.skipped || 0}, failed ${r.failed || 0}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send booking WhatsApp");
    } finally {
      setBookingBusy(false);
    }
  };

  const addExec = () => {
    if (!form.execName || !form.execMobile) return toast.error("Executive name and mobile required");
    setExecs((xs) => [...xs.filter((x) => x.name !== form.execName), { name: form.execName, mobile: form.execMobile }]);
    setForm((f) => ({ ...f, execName: "", execMobile: "" }));
  };

  return (
    <Card className="p-5 mb-6" data-testid="botspace-settings">
      <div className="flex items-center gap-2 mb-1">
        <MessageCircle size={16} className="text-cobalt" />
        <h3 className="font-heading font-bold text-ink">WhatsApp (BotSpace)</h3>
      </div>
      <p className="text-sm text-ink-soft mb-3">
        Euler lead chats only — numbers not in this CRM (Tata etc.) are ignored.
        Paste the BotSpace API key and Channel ID. Templates must be Meta-approved before auto-send works.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="API key">
          <Input data-testid="botspace-api-key" type="password" value={form.apiKey}
            onChange={(e) => setForm({ ...form, apiKey: e.target.value })} placeholder="botspace_…" />
        </Field>
        <Field label="Channel ID">
          <Input data-testid="botspace-channel-id" value={form.channelId}
            onChange={(e) => setForm({ ...form, channelId: e.target.value })} placeholder="From BotSpace channel settings" />
        </Field>
        <Field label="Google review URL">
          <Input data-testid="botspace-review-url" value={form.reviewUrl}
            onChange={(e) => setForm({ ...form, reviewUrl: e.target.value })} placeholder="https://g.page/r/…" />
        </Field>
        <Field label="Cron token (optional)">
          <Input value={form.cronToken} onChange={(e) => setForm({ ...form, cronToken: e.target.value })}
            placeholder="For Railway / cron-job.org" />
        </Field>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="text-xs text-ink-faint font-mono break-all" data-testid="botspace-webhook-url">
          BotSpace webhook URL: {webhookUrl}
        </div>
        <Button variant="ghost" className="!py-1 !px-2 text-xs" onClick={() => {
          navigator.clipboard.writeText(webhookUrl).then(
            () => toast.success("Webhook URL copied — paste it in BotSpace → Webhooks"),
            () => toast.error("Could not copy"),
          );
        }}><Copy size={12} /> Copy</Button>
      </div>
      <p className="text-xs text-ink-faint mt-1">
        Paste this in BotSpace as the callback / webhook URL (POST). Use the Railway API host, not the Euler website address.
      </p>
      <div className="mt-3 text-xs text-ink-soft bg-zinc-50 rounded-lg p-3 ring-1 ring-line">
        Executive WhatsApp numbers now live on <b>Settings → Staff &amp; Reports</b>, together with
        role, monthly target and which daily reports each person receives. Names come from the
        staff master, so a typo can no longer stop someone being messaged.
      </div>
      <div className="flex flex-wrap gap-2 mt-4">
        <Button data-testid="botspace-save-btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save WhatsApp settings"}</Button>
        <Button variant="secondary" onClick={runJobs}>Run follow-up jobs now</Button>
        <Button variant="secondary" data-testid="send-all-booking-confirms-btn" onClick={sendBookings} disabled={bookingBusy}>
          {bookingBusy ? "Sending…" : "Send booking WhatsApp to booked leads"}
        </Button>
        <Button variant="secondary" data-testid="send-all-delivery-reviews-btn" onClick={sendReviews} disabled={reviewBusy}>
          {reviewBusy ? "Sending…" : "Send Google review to delivered leads"}
        </Button>
        <span className="text-xs text-ink-faint self-center">{cfg?.configured ? "Configured" : "Needs API key + channel ID"}</span>
      </div>
      <p className="text-xs text-ink-faint mt-2">
        Bulk send covers already-booked / already-delivered Euler leads that never got the WhatsApp. Future Convert to Booking and Mark Delivered still send automatically.
      </p>
      <ModelAskCampaign />
    </Card>
  );
}

/**
 * The app's only Marketing-category send. Everything else is Utility, which is
 * why this one gets a preview instead of a plain button: a marketing blast
 * cannot be recalled, and enough spam reports cost you template access for the
 * booking and delivery messages too.
 */
function ModelAskCampaign() {
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      setPreview(await get("/integrations/botspace/model-ask/preview"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not build the preview");
    } finally { setBusy(false); }
  };

  const send = async () => {
    if (!window.confirm(
      `Send the model-interest WhatsApp to ${preview.eligible} lead(s)?\n\n`
      + "This is a Marketing template. It cannot be recalled once sent.")) return;
    setSending(true);
    try {
      const r = await post("/integrations/botspace/model-ask?confirm=true", {});
      toast.success(`Sent ${r.sent || 0}, queued for morning ${r.queued || 0}, failed ${r.failed || 0}`);
      setPreview(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Campaign failed");
    } finally { setSending(false); }
  };

  return (
    <div className="mt-5 pt-4 border-t border-line" data-testid="model-ask-campaign">
      <h4 className="font-heading font-bold text-ink text-sm mb-1">Model interest campaign</h4>
      <p className="text-xs text-ink-soft mb-3">
        Asks Active leads with no vehicle recorded which model they want, and writes a
        confident reply straight onto the lead. Opted-out, booked and delivered customers are
        never included, and nobody is asked twice within 45 days.{" "}
        <b>This is a Marketing template</b> — send it deliberately, not on a schedule.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" data-testid="model-ask-preview-btn" onClick={load} disabled={busy}>
          <Users size={14} /> {busy ? "Checking…" : "Preview recipients"}
        </Button>
        {preview && (
          <Button data-testid="model-ask-send-btn" onClick={send}
            disabled={sending || !preview.eligible}>
            {sending ? "Sending…" : `Send to ${preview.eligible} lead(s)`}
          </Button>
        )}
      </div>
      {preview && (
        <div className="mt-3 text-xs bg-zinc-50 rounded-lg p-3 ring-1 ring-line">
          {preview.eligible === 0 ? (
            <span className="text-ink-soft">Every active lead already has a model recorded — nothing to send.</span>
          ) : (
            <>
              <div className="text-ink-soft mb-1">
                <b>{preview.eligible} lead(s)</b> would receive it. Menu they will see:{" "}
                <span className="font-mono">{preview.menu}</span>
              </div>
              <div className="text-ink-faint">
                {preview.targets.slice(0, 12).map((t) => t.customerName || t.leadId).join(" · ")}
                {preview.targets.length > 12 && ` … +${preview.targets.length - 12} more`}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * The ID this person types at the login screen.
 *
 * Editable in place because every account that existed before login IDs has an
 * empty one — and until it is filled, that person can only sign in with their
 * email. Showing the gap in the table is what makes it get fixed.
 */
function LoginIdCell({ row, onSaved }) {
  const [value, setValue] = useState(row.loginId || "");
  const [busy, setBusy] = useState(false);
  const dirty = value.trim() !== (row.loginId || "");

  const save = async () => {
    setBusy(true);
    try {
      await put(`/auth/users/${row.userId}/login-id`, { loginId: value.trim() });
      toast.success(value.trim() ? `User ID set to ${value.trim()}` : "User ID cleared");
      onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not set the user ID");
      setValue(row.loginId || "");
    } finally { setBusy(false); }
  };

  return (
    <div className="flex items-center gap-1.5">
      <Input data-testid={`login-id-${row.email}`} value={value} className="!py-1 text-xs w-28"
        placeholder="not set" onChange={(e) => setValue(e.target.value)} />
      {dirty && (
        <Button variant="secondary" className="!py-1 !px-2 text-xs" disabled={busy} onClick={save}>
          Save
        </Button>
      )}
    </div>
  );
}

function CoulsonCard() {
  const [cfg, setCfg] = useState(null);
  const [form, setForm] = useState({ username: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(() => {
    get("/integrations/coulson").then((d) => {
      setCfg(d);
      setForm((f) => ({ ...f, username: d.username && !d.username.includes("*") ? d.username : f.username }));
    }).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    if (!form.username && !cfg?.configured) return toast.error("Coulson username is required");
    setBusy(true);
    try {
      const st = await put("/integrations/coulson", { username: form.username, password: form.password });
      setForm((f) => ({ ...f, password: "" }));
      setCfg(st);
      if (st.loginOk) toast.success("Euler OEM login works — you can Sync now");
      else toast.error(st.lastError || "Coulson rejected this username/password");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save Coulson login");
    } finally { setBusy(false); }
  };

  const sync = async () => {
    setSyncing(true);
    try {
      // Sync must pick up whatever is in the form. Clicking Sync without Save
      // used to keep a previously rejected password.
      if (form.username || form.password) {
        const st = await put("/integrations/coulson", { username: form.username, password: form.password });
        setCfg(st);
        setForm((f) => ({ ...f, password: "" }));
        if (st.loginOk === false) {
          toast.error(st.lastError || "Coulson rejected this username/password");
          return;
        }
      }
      const r = await post("/integrations/coulson/sync", {});
      if (r.ok) toast.success(`Pulled ${r.inventoryCount || 0} vehicles · ${r.pricesUpdated || 0} prices`);
      else toast.error(r.reason === "not_configured" ? "Save the Coulson login first" : "Sync did not run");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Coulson sync failed");
    } finally { setSyncing(false); }
  };

  return (
    <Card className="p-5 mb-6" data-testid="coulson-settings">
      <div className="flex items-center gap-2 mb-1">
        <Warehouse size={16} className="text-cobalt" />
        <h3 className="font-heading font-bold text-ink">Euler OEM (Coulson)</h3>
        {cfg && <Badge tone={cfg.configured
          ? (cfg.loginOk === false || cfg.lastSyncOk === false
            ? "bg-red-50 text-red-700 ring-red-600/20"
            : "bg-emerald-50 text-emerald-700 ring-emerald-600/20")
          : "bg-amber-50 text-amber-700 ring-amber-600/20"}>
          {!cfg.configured ? "Not configured"
            : (cfg.loginOk === false || cfg.lastSyncOk === false) ? "Login failed" : "Configured"}
        </Badge>}
      </div>
      <p className="text-sm text-ink-soft mb-3">
        Same username and password as <a className="underline" href="https://coulson.eulerlogistics.com" target="_blank" rel="noreferrer">coulson.eulerlogistics.com</a>.
        Type the password, then Save — we check it with Euler before syncing.
        RTO, insurance and other charges stay on Price Master.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <Field label="Coulson username">
          <Input data-testid="coulson-username" value={form.username} autoComplete="off"
            placeholder={cfg?.username || "dealer username"}
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </Field>
        <Field label="Password">
          <Input data-testid="coulson-password" type="password" autoComplete="new-password"
            placeholder={cfg?.configured ? "unchanged" : "Coulson password"}
            value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button data-testid="coulson-save-btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save login"}</Button>
        <Button variant="secondary" data-testid="coulson-settings-sync-btn" onClick={sync} disabled={syncing}>
          <RefreshCcw size={14} /> {syncing ? "Syncing…" : "Sync now"}
        </Button>
      </div>
      {cfg?.lastSyncAt && (
        <div className="text-xs text-ink-faint mt-3">
          Last sync {cfg.lastSyncOk === false ? "failed" : "ok"} · {cfg.inventoryCount || 0} in yard
          {cfg.lastError ? ` · ${cfg.lastError}` : ""}
        </div>
      )}
    </Card>
  );
}
