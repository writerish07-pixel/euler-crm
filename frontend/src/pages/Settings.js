import React, { useEffect, useState, useCallback } from "react";
import { UserPlus, Trash2, CheckCircle2, XCircle, ExternalLink, Copy } from "lucide-react";
import { toast } from "sonner";
import { get, post, del } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Card, Button, Field, Input, Select, Badge, Table } from "../components/ui";

export default function Settings() {
  const { isOwner } = useAuth();
  const [users, setUsers] = useState([]);
  const [gs, setGs] = useState(null);
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "executive" });

  const loadUsers = useCallback(() => { if (isOwner) get("/auth/users").then(setUsers).catch(() => {}); }, [isOwner]);
  useEffect(() => { loadUsers(); get("/integrations/gsheets").then(setGs).catch(() => {}); }, [loadUsers]);

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
                Add the service account JSON key at <span className="font-mono">/app/backend/gsheets_credentials.json</span> and share the Euler Master sheet with the service account email as <b>Editor</b>.
              </div>
            )}
            {gs.enabled && (
              <div className="text-xs text-emerald-700 mt-2 bg-emerald-50 rounded-lg p-3 ring-1 ring-emerald-200">
                Live — new Leads, Bookings, Payments, Deliveries & Claims are appended to your Euler Master sheet automatically.
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

      {isOwner && (
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">User Accounts <span className="text-xs font-normal text-ink-faint">(Owner only)</span></h3>
          <div className="grid grid-cols-5 gap-3 items-end mb-4">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Email"><Input data-testid="new-user-email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Password"><Input data-testid="new-user-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
            <Field label="Role"><Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}><option value="executive">Executive</option><option value="owner">Owner</option></Select></Field>
            <Button data-testid="add-user-btn" onClick={addUser}><UserPlus size={15} /> Add User</Button>
          </div>
          <Table
            rowKey="userId"
            columns={[
              { key: "name", label: "Name", render: (r) => <span className="font-semibold">{r.name || "—"}</span> },
              { key: "email", label: "Email", mono: true },
              { key: "role", label: "Role", render: (r) => <Badge tone={r.role === "owner" ? "bg-amber-50 text-amber-700 ring-amber-600/20" : "bg-blue-50 text-blue-700 ring-blue-600/20"}>{r.role}</Badge> },
              { key: "act", label: "", align: "right", render: (r) => <button data-testid={`del-user-${r.email}`} onClick={() => removeUser(r.userId)} className="text-red-500 hover:text-red-700"><Trash2 size={15} /></button> },
            ]}
            rows={users}
          />
        </Card>
      )}
    </div>
  );
}
