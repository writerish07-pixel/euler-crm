import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, LogIn } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";
import { Button, Input, Field } from "../components/ui";
import ConnectionBar from "../components/ConnectionBar";
import { primeLoginApp } from "../lib/pwa";
import { apiErrorMessage } from "../lib/api";

function homeFor(user) {
  const role = user?.role;
  if (role === "accounts") return "/accounts";
  if (role === "asm" || role === "rm") return "/field";
  if (role === "oem_finance") return "/oem-finance";
  return "/";
}

export default function Login() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    primeLoginApp();
  }, []);

  useEffect(() => {
    if (user) nav(homeFor(user), { replace: true });
  }, [user, nav]);

  const submit = async (e) => {
    e.preventDefault();
    // Android password managers fill the DOM, not always React state.
    const fd = e.target && typeof e.target === "object" && "elements" in e.target
      ? new FormData(e.target)
      : null;
    const id = String((fd && fd.get("username")) || email || "").trim();
    const pw = String((fd && fd.get("password")) || password || "");
    if (!id || !pw) {
      const msg = "Enter your user ID and password";
      setFormError(msg);
      return toast.error(msg);
    }
    setBusy(true);
    setFormError("");
    try {
      const u = await login(id, pw);
      toast.success("Welcome back");
      nav(homeFor(u), { replace: true });
    } catch (err) {
      const status = err.response?.status;
      const fromApi = apiErrorMessage(err, "");
      const axiosGeneric = /^Request failed with status code \d+$/i.test(fromApi) || fromApi === "Request failed";
      let msg = "Could not sign in";
      if (err.code === "ECONNABORTED") {
        msg = "The server took too long. Try again.";
      } else if (!err.response) {
        msg = "Could not reach the server. Try again.";
      } else if (status === 401) {
        msg = "Invalid user ID or password";
      } else if (fromApi && !axiosGeneric) {
        msg = fromApi;
      } else if (status === 502 || status === 503 || status === 504) {
        msg = "The server is starting. Try again.";
      }
      setFormError(msg);
      toast.error(msg);
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-[100dvh] bg-app">
      <ConnectionBar />
      <div className="grid lg:grid-cols-2 min-h-[100dvh]">
      <div className="hidden lg:flex flex-col justify-between p-12 bg-ink text-white relative overflow-hidden">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-cobalt/30 blur-3xl" />
        <div className="absolute -left-16 bottom-10 h-72 w-72 rounded-full bg-cobalt/20 blur-3xl" />
        <div className="flex items-center gap-2.5 relative">
          <div className="h-10 w-10 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={22} fill="white" className="text-white" /></div>
          <span className="font-heading text-xl font-extrabold">Euler CRM</span>
        </div>
        <div className="relative">
          <h1 className="font-heading text-4xl font-extrabold leading-tight">Dealership<br />operations</h1>
          <p className="text-zinc-400 mt-4 max-w-sm">Leads, bookings, finance, claims, and earnings in one place.</p>
        </div>
        <div className="text-zinc-500 text-sm relative">Euler Motors · Euler CRM</div>
      </div>

      <div className="flex items-center justify-center p-8 pb-[max(2rem,env(safe-area-inset-bottom))]">
        {/* noValidate: iOS treats some user IDs as invalid emails and blocks submit. */}
        <form onSubmit={submit} noValidate autoComplete="on" className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <div className="h-10 w-10 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={22} fill="white" className="text-white" /></div>
            <span className="font-heading text-xl font-extrabold">Euler CRM</span>
          </div>
          <h2 className="font-heading text-2xl font-extrabold text-ink">Sign in</h2>
          <p className="text-sm text-ink-soft mt-1 mb-6">Enter your credentials to continue</p>
          <div className="space-y-4">
            {/* type="text", not "email" — the browser would refuse to submit a
                plain user ID as an email address. text-base (16px) stops iOS
                zooming the page and hiding Sign In under the keyboard. */}
            <Field label="User ID or email">
              <Input
                id="login-username"
                data-testid="login-email"
                name="username"
                type="text"
                inputMode="text"
                autoComplete="username"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                enterKeyHint="next"
                className="text-base py-3"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setFormError(""); }}
                placeholder="User ID or email"
              />
            </Field>
            <Field label="Password">
              <Input
                id="login-password"
                data-testid="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                enterKeyHint="go"
                className="text-base py-3"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setFormError(""); }}
                placeholder="••••••••"
              />
            </Field>
            {formError && (
              <p data-testid="login-error" className="text-sm text-red-600" role="alert">{formError}</p>
            )}
            <Button data-testid="login-submit" type="submit" disabled={busy} className="w-full min-h-12 text-base">
              <LogIn size={16} /> {busy ? "Signing in…" : "Sign In"}
            </Button>
          </div>
          <p className="text-xs text-ink-faint mt-6 text-center">
            Need an account? Ask the owner.
          </p>
        </form>
      </div>
      </div>
    </div>
  );
}
