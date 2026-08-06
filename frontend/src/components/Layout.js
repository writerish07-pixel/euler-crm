import React, { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, ClipboardList, Wallet, Truck, Landmark,
  ShieldCheck, FileText, Percent, Trophy, Tag, ReceiptText,
  Coins, Activity, Search, Zap, BadgeIndianRupee,
} from "lucide-react";
import { cx } from "./ui";

const NAV = [
  { section: "Overview", items: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  ]},
  { section: "Sales Pipeline", items: [
    { to: "/leads", label: "Lead Register", icon: Users },
    { to: "/bookings", label: "Bookings", icon: ClipboardList },
    { to: "/quotations", label: "Quotations", icon: FileText },
    { to: "/activities", label: "Activity Log", icon: Activity },
  ]},
  { section: "Money", items: [
    { to: "/payments", label: "Payment Ledger", icon: Wallet },
    { to: "/finance", label: "Finance Register", icon: Landmark },
    { to: "/insurance", label: "Insurance Payouts", icon: ShieldCheck },
  ]},
  { section: "Fulfilment", items: [
    { to: "/deliveries", label: "Delivery Tracker", icon: Truck },
  ]},
  { section: "OEM & Commercial", items: [
    { to: "/claims", label: "OEM Claims", icon: ReceiptText },
    { to: "/scheme-master", label: "Scheme Master", icon: Percent },
    { to: "/incentive-master", label: "Incentive Master", icon: Trophy },
    { to: "/dealer-earnings", label: "Dealer Earnings", icon: Coins, owner: true },
  ]},
  { section: "Catalogue", items: [
    { to: "/price-master", label: "Price Master", icon: Tag },
  ]},
];

function Sidebar() {
  return (
    <aside className="w-64 fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line bg-white">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-line shrink-0">
        <div className="h-9 w-9 rounded-lg bg-cobalt flex items-center justify-center">
          <Zap size={20} className="text-white" fill="white" />
        </div>
        <div>
          <div className="font-heading font-extrabold text-ink leading-none tracking-tight">Euler CRM</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-faint mt-0.5">EV Dealership</div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {NAV.map((group) => (
          <div key={group.section}>
            <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">{group.section}</div>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                  className={({ isActive }) =>
                    cx(
                      "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive ? "bg-cobalt-tint text-cobalt" : "text-ink-soft hover:bg-zinc-100 hover:text-ink"
                    )
                  }
                >
                  <item.icon size={17} className="shrink-0" />
                  <span className="truncate">{item.label}</span>
                  {item.owner && <span className="ml-auto text-[9px] font-bold uppercase text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">Owner</span>}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="px-5 py-3 border-t border-line text-[11px] text-ink-faint shrink-0">
        <span className="font-mono">v2.2</span> · Full-stack migration
      </div>
    </aside>
  );
}

function Topbar({ onSearch }) {
  const [q, setQ] = useState("");
  const loc = useLocation();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-line bg-white/80 backdrop-blur px-6">
      <div className="relative flex-1 max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
        <input
          data-testid="global-search"
          value={q}
          onChange={(e) => { setQ(e.target.value); onSearch && onSearch(e.target.value); }}
          placeholder="Search leads by name, mobile, ID…"
          className="w-full rounded-lg bg-zinc-100 border-0 py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-faint focus:ring-2 focus:ring-cobalt focus:bg-white transition-all"
        />
      </div>
      <div className="ml-auto flex items-center gap-3">
        <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 ring-1 ring-inset ring-emerald-600/20">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-medium text-emerald-700">Live Database</span>
        </div>
        <div className="h-9 w-9 rounded-full bg-ink flex items-center justify-center text-white text-sm font-bold font-heading">EM</div>
      </div>
    </header>
  );
}

export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-app">
      <Sidebar />
      <div className="ml-64 flex flex-col min-h-screen">
        <Topbar />
        <main className="flex-1 p-6 lg:p-8 animate-fade-up">{children}</main>
      </div>
    </div>
  );
}
