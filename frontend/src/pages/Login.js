import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, LogIn } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { Button, Input, Field } from "../components/ui";

function fmtErr(detail) {
  if (!detail) return "Something went wrong";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("owner@euler.com");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(email.trim(), password);
      toast.success("Welcome back");
      nav(u?.role === "accounts" ? "/accounts" : "/");
    } catch (err) {
      toast.error(fmtErr(err.response?.data?.detail) || "Login failed");
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
        <div className="text-zinc-500 text-sm relative">Full-stack migration · v2.2</div>
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
            <Field label="Email"><Input data-testid="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="owner@euler.com" /></Field>
            <Field label="Password"><Input data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" /></Field>
            <Button data-testid="login-submit" type="submit" disabled={busy} className="w-full"><LogIn size={16} /> {busy ? "Signing in…" : "Sign In"}</Button>
          </div>
          <p className="text-xs text-ink-faint mt-6 text-center">
            Owner / Executive / Accounts · pwd euler@123<br />
            accounts@euler.com for the money desk
          </p>
        </form>
      </div>
    </div>
  );
}
