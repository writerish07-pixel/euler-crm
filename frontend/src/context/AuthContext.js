import React, { createContext, useContext, useEffect, useState } from "react";
import { api, TOKEN_KEY, post } from "../lib/api";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = checking

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) { setUser(null); return; }
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => { localStorage.removeItem(TOKEN_KEY); setUser(null); });
  }, []);

  const login = async (email, password) => {
    const data = await post("/auth/login", { email, password });
    localStorage.setItem(TOKEN_KEY, data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
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
      isAsm: role === "asm",
      isRm: role === "rm",
      isField: role === "asm" || role === "rm",
      // The OEM's finance desk — an OUTSIDE party. One read-only report and
      // nothing else; the API denies every other route to this role.
      isOemFinance: role === "oem_finance",
      isSalesStaff: role === "owner" || role === "executive",
      // Executives feed leads and booking amounts. Money movements are the
      // owner's or Accounts' — matching MONEY_ROLES on the API.
      isMoneyDesk: role === "owner" || role === "accounts",
      // Commercial steps: price, scheme, delivery, close and cancel are owner-only.
      canEditCommercials: role === "owner",
      // ASM/RM may view Finance Register (disbursed vs remaining); writes stay money-desk.
      canViewFinance: role === "owner" || role === "executive" || role === "accounts"
        || role === "asm" || role === "rm",
    }}>
      {children}
    </AuthCtx.Provider>
  );
}
