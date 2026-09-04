import React, { createContext, useContext, useEffect, useState } from "react";
import { api, post } from "../lib/api";
import {
  readStoredToken,
  writeStoredToken,
  clearStoredToken,
  jwtExpired,
} from "../lib/authStorage";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = checking

  useEffect(() => {
    const token = readStoredToken();
    if (!token || jwtExpired(token)) {
      if (token) clearStoredToken();
      setUser(null);
      return undefined;
    }
    const ac = new AbortController();
    api.get("/auth/me", { signal: ac.signal, timeout: 12000 })
      .then((r) => {
        if (!ac.signal.aborted) setUser(r.data);
      })
      .catch((err) => {
        if (ac.signal.aborted || err?.code === "ERR_CANCELED") return;
        // Only drop the session we asked about — a login that landed while this
        // request was in flight must keep its new token.
        if (readStoredToken() === token) {
          clearStoredToken();
          setUser(null);
        }
      });
    return () => ac.abort();
  }, []);

  const login = async (email, password) => {
    const data = await post("/auth/login", { email, password });
    writeStoredToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    clearStoredToken();
    setUser(null);
    window.location.href = "/login";
  };

  const role = user?.role || "";
  return (
    <AuthCtx.Provider value={{
      user,
      login,
      logout,
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
