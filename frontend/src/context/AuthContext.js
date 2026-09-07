import React, { createContext, useContext, useEffect, useState } from "react";
import { api, post } from "../lib/api";
import {
  readStoredToken,
  writeStoredToken,
  clearStoredToken,
  jwtExpired,
  readCachedUser,
  writeCachedUser,
  clearCachedUser,
  isTransientAuthError,
  bootAuthUser,
} from "../lib/authStorage";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => bootAuthUser());
  const [sessionError, setSessionError] = useState("");

  const applyUser = (next) => {
    setUser(next);
    if (next) writeCachedUser(next);
    else clearCachedUser();
  };

  useEffect(() => {
    let live = true;
    const token = readStoredToken();
    if (!token || jwtExpired(token)) {
      if (token) clearStoredToken();
      else clearCachedUser();
      if (live) applyUser(null);
      return () => { live = false; };
    }

    const refresh = async () => {
      for (let attempt = 0; attempt < 4 && live; attempt += 1) {
        try {
          const r = await api.get("/auth/me", { timeout: 12000 });
          if (!live) return;
          // A login that landed while this request was in flight keeps its token.
          if (readStoredToken() && readStoredToken() !== token) return;
          applyUser(r.data);
          setSessionError("");
          return;
        } catch (err) {
          if (!live) return;
          if (isTransientAuthError(err) && attempt < 3) {
            await new Promise((ok) => setTimeout(ok, 400 * (attempt + 1)));
            continue;
          }
          if (readStoredToken() !== token) return;
          const cached = readCachedUser();
          if (cached) {
            // OPPO/vivo abort /auth/me on pull-to-refresh. Keep the shell.
            setUser((cur) => (cur === undefined ? cached : cur));
            setSessionError("Could not refresh the session. Tap retry, or pull down again.");
            return;
          }
          clearStoredToken();
          applyUser(null);
          return;
        }
      }
    };
    refresh();

    // If ColorOS never resolves the XHR, do not sit on Loading… forever.
    const watchdog = setTimeout(() => {
      if (!live) return;
      setUser((cur) => {
        if (cur !== undefined) return cur;
        return readCachedUser() || null;
      });
    }, 16000);

    return () => { live = false; clearTimeout(watchdog); };
  }, []);

  const login = async (email, password) => {
    const data = await post("/auth/login", { email, password });
    writeStoredToken(data.token);
    applyUser(data.user);
    setSessionError("");
    return data.user;
  };

  const retrySession = () => {
    setSessionError("");
    const token = readStoredToken();
    if (!token) {
      applyUser(null);
      return;
    }
    setUser((cur) => cur ?? readCachedUser() ?? undefined);
    api.get("/auth/me", { timeout: 12000 })
      .then((r) => { applyUser(r.data); setSessionError(""); })
      .catch((err) => {
        if (isTransientAuthError(err) && readCachedUser()) {
          setSessionError("Still cannot reach the server.");
          return;
        }
        clearStoredToken();
        applyUser(null);
      });
  };

  const logout = () => {
    clearStoredToken();
    applyUser(null);
    window.location.href = "/login";
  };

  const role = user?.role || "";
  return (
    <AuthCtx.Provider value={{
      user,
      login,
      logout,
      retrySession,
      sessionError,
      isOwner: role === "owner",
      isAccounts: role === "accounts",
      isExecutive: role === "executive",
      isSalesGm: role === "sales_gm",
      isAsm: role === "asm",
      isRm: role === "rm",
      isField: role === "asm" || role === "rm",
      // The OEM's finance desk — an OUTSIDE party. One read-only report and
      // nothing else; the API denies every other route to this role.
      isOemFinance: role === "oem_finance",
      isTl: role === "tl",
      isSalesStaff: role === "owner" || role === "sales_gm" || role === "tl" || role === "executive",
      isMoneyDesk: role === "owner" || role === "tl" || role === "accounts",
      // Price, scheme, delivery, close and cancel — the steps an executive hands
      // over. Mirrors DEAL_DESK_ROLES on the API.
      canEditCommercials: role === "owner" || role === "sales_gm" || role === "tl",
      // ASM/RM / Sales GM may view Finance Register (disbursed vs remaining); writes stay money-desk.
      canViewFinance: role === "owner" || role === "sales_gm" || role === "tl" || role === "executive"
        || role === "accounts" || role === "asm" || role === "rm",
      canApproveLeads: role === "owner" || role === "sales_gm",
      canViewMonthly: role === "owner" || role === "sales_gm" || role === "tl" || role === "accounts"
        || role === "executive" || role === "asm" || role === "rm",
      canExport: role === "owner" || role === "sales_gm" || role === "tl",
      // Match OEM debit notes to the scheme register. Not payments.
      canMatchOemClaims: role === "owner" || role === "tl" || role === "accounts" || role === "sales_gm",
      // Pull the Euler claim mirror. Accounts does not.
      canSyncOemClaims: role === "owner" || role === "tl" || role === "sales_gm",
    }}>
      {children}
    </AuthCtx.Provider>
  );
}
