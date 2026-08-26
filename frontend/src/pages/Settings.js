import React, { useEffect, useState, useCallback } from "react";
import { UserPlus, Trash2, CheckCircle2, XCircle, ExternalLink, Copy, RefreshCcw, Plus, ListPlus, KeyRound, MessageCircle } from "lucide-react";
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
  const { isOwner, user } = useAuth();
  const [users, setUsers] = useState([]);
  const [gs, setGs] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "executive" });
  const [backfilling, setBackfilling] = useState(false);
  const [ensuringOem, setEnsuringOem] = useState(false);
  const [ensuringIns, setEnsuringIns] = useState(false);
  const [pwForm, setPwForm] = useState({ currentPassword: "", newPassword: "", confirmPassword: "" });
  const [pwBusy, setPwBusy] = useState(false);

  const loadUsers = useCallback(() => { if (isOwner) get("/auth/users").then(setUsers).catch(() => {}); }, [isOwner]);
  useEffect(() => { loadUsers(); get("/integrations/gsheets").then(setGs).catch(() => {}); }, [loadUsers]);

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

  const addUser = async () => {
    if (!form.email || !form.password) return toast.error("Email & password required");
    try { await post("/auth/users", form); toast.success("User created"); setForm({ email: "", password: "", name: "", role: "executive" }); loadUsers(); }
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

      {isOwner && <BotspaceCard />}

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

      {isOwner && <MastersListCard gsEnabled={gs?.enabled} />}

      {isOwner && (
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">User Accounts <span className="text-xs font-normal text-ink-faint">(Owner only)</span></h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end mb-4">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Email"><Input data-testid="new-user-email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Password"><Input data-testid="new-user-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            <Field label="Role"><Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="executive">Executive</option>
              <option value="accounts">Accounts</option>
              <option value="asm">ASM</option>
              <option value="rm">RM</option>
              <option value="owner">Owner</option>
            </Select></Field>
            <Button data-testid="add-user-btn" onClick={addUser}><UserPlus size={15} /> Add User</Button>
          </div>
          <Table
            rowKey="userId"
            columns={[
              { key: "name", label: "Name", render: (r) => <span className="font-semibold">{r.name || "—"}</span> },
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
    </div>
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
    </Card>
  );
}
