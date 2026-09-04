import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, LogIn } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { Button, Input, Field } from "../components/ui";

function fmtErr(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  if (typeof detail === "object" && detail.msg) return String(detail.msg);
  return String(detail);
}

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const id = email.trim();
    const pw = password;
    if (!id || !pw) return toast.error("Enter your user ID and password");
    setBusy(true);
    try {
      const u = await login(id, pw);
      toast.success("Welcome back");
      const role = u?.role;
      if (role === "accounts") nav("/accounts");
      else if (role === "asm" || role === "rm") nav("/field");
      else if (role === "sales_gm") nav("/");
      else nav("/");
    } catch (err) {
      const status = err.response?.status;
      const fromApi = fmtErr(err.response?.data?.detail);
      if (!err.response) {
        toast.error("Could not reach the server. Check the network and try again.");
      } else if (fromApi) {
        toast.error(fromApi);
      } else if (status === 401) {
        toast.error("Invalid user ID or password");
      } else {
        toast.error("Could not sign in. Ask the owner to reset this password in Settings.");
      }
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-app">
      <div className="hidden lg:flex flex-col justify-between p-12 bg-ink text-white relative overflow-hidden">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-cobalt/30 blur-3xl" />
        <div className="absolute -left-16 bottom-10 h-72 w-72 rounded-full bg-cobalt/20 blur-3xl" />
        <div className="flex items-center gap-2.5 relative">
          <div className="h-10 w-10 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={22} fill="white" className="text-white" /></div>
          <span className="font-heading text-xl font-extrabold">Euler CRM</span>
        </div>
        <div className="relative">
          <h1 className="font-heading text-4xl font-extrabold leading-tight">EV Dealership<br />Operations Console</h1>
          <p className="text-zinc-400 mt-4 max-w-sm">Leads, bookings, commercial pricing, schemes, claims, finance & dealer earnings — one fast database, synced to your Google Sheet.</p>
        </div>
        <div className="text-zinc-500 text-sm relative">Full-stack migration · v2.4</div>
      </div>

      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <div className="h-10 w-10 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={22} fill="white" className="text-white" /></div>
            <span className="font-heading text-xl font-extrabold">Euler CRM</span>
          </div>
          <h2 className="font-heading text-2xl font-extrabold text-ink">Sign in</h2>
          <p className="text-sm text-ink-soft mt-1 mb-6">Enter your credentials to continue</p>
          <div className="space-y-4">
            {/* type="text", not "email" — the browser would refuse to submit a
                plain user ID as an email address. */}
            <Field label="User ID or email">
              <Input data-testid="login-email" type="text" autoCapitalize="none" autoCorrect="off"
                value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="your user ID (e.g. amit)" />
            </Field>
            <Field label="Password"><Input data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" /></Field>
            <Button data-testid="login-submit" type="submit" disabled={busy} className="w-full"><LogIn size={16} /> {busy ? "Signing in…" : "Sign In"}</Button>
          </div>
          <p className="text-xs text-ink-faint mt-6 text-center">
            Email (owner@euler.com) or the User ID from Settings. You can also type
            your name if it is unique. Ask the owner to reset the password if sign-in
            still fails.
          </p>
        </form>
      </div>
    </div>
  );
}
