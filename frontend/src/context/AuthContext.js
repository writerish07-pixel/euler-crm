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

  return <AuthCtx.Provider value={{ user, login, logout, isOwner: user?.role === "owner" }}>{children}</AuthCtx.Provider>;
}
