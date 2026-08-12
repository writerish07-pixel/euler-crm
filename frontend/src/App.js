import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Share from "./pages/Share";
import Dashboard from "./pages/Dashboard";
import AccountsDashboard from "./pages/AccountsDashboard";
import Leads from "./pages/Leads";
import PriceMaster from "./pages/PriceMaster";
import SchemeMaster from "./pages/SchemeMaster";
import IncentiveMaster from "./pages/IncentiveMaster";
import Payments from "./pages/Payments";
import Deliveries from "./pages/Deliveries";
import Finance from "./pages/Finance";
import Insurance from "./pages/Insurance";
import Claims from "./pages/Claims";
import Activities from "./pages/Activities";
import DealerEarnings from "./pages/DealerEarnings";
import Quotations from "./pages/Quotations";
import Bookings from "./pages/Bookings";
import Settings from "./pages/Settings";
import InsurancePayoutReport from "./pages/InsurancePayoutReport";
import EarningsReport from "./pages/EarningsReport";
import OwnerCommercialReport from "./pages/OwnerCommercialReport";
import OemClaimDashboard from "./pages/OemClaimDashboard";
import ClaimExceptions from "./pages/ClaimExceptions";
import ERPProductionAudit from "./pages/ERPProductionAudit";
import AuditLog from "./pages/AuditLog";

function Protected({ children, ownerOnly, salesOnly, accountsOk }) {
  const { user, isOwner, isAccounts, isSalesStaff } = useAuth();
  const loc = useLocation();
  if (user === undefined) return <div className="min-h-screen grid place-items-center text-ink-faint">Loading…</div>;
  if (!user) return <Navigate to="/login" state={{ from: loc }} replace />;
  if (ownerOnly && !isOwner) {
    return <Navigate to={isAccounts ? "/accounts" : "/"} replace />;
  }
  if (salesOnly && !isSalesStaff) {
    return <Navigate to={isAccounts ? "/accounts" : "/"} replace />;
  }
  // accountsOk routes: money desk — available to all authenticated roles
  return <Layout>{children}</Layout>;
}

function HomeRedirect() {
  const { isAccounts } = useAuth();
  if (isAccounts) return <Navigate to="/accounts" replace />;
  return <Dashboard />;
}

function AppRoutes() {
  const P = (el, opts = {}) => (
    <Protected ownerOnly={opts.ownerOnly} salesOnly={opts.salesOnly} accountsOk={opts.accountsOk}>
      {el}
    </Protected>
  );
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/share" element={<Share />} />
      <Route path="/" element={P(<HomeRedirect />)} />
      <Route path="/accounts" element={P(<AccountsDashboard />, { accountsOk: true })} />
      <Route path="/leads" element={P(<Leads />, { salesOnly: true })} />
      <Route path="/bookings" element={P(<Bookings />, { salesOnly: true })} />
      <Route path="/quotations" element={P(<Quotations />, { salesOnly: true })} />
      <Route path="/activities" element={P(<Activities />, { salesOnly: true })} />
      <Route path="/payments" element={P(<Payments />, { accountsOk: true })} />
      <Route path="/finance" element={P(<Finance />, { accountsOk: true })} />
      <Route path="/insurance" element={P(<Insurance />, { accountsOk: true })} />
      <Route path="/deliveries" element={P(<Deliveries />, { accountsOk: true })} />
      <Route path="/claims" element={P(<Claims />, { accountsOk: true })} />
      <Route path="/scheme-master" element={P(<SchemeMaster />, { salesOnly: true })} />
      <Route path="/incentive-master" element={P(<IncentiveMaster />, { salesOnly: true })} />
      <Route path="/dealer-earnings" element={P(<DealerEarnings />, { ownerOnly: true })} />
      <Route path="/insurance-report" element={P(<InsurancePayoutReport />, { ownerOnly: true })} />
      <Route path="/earnings-report" element={P(<EarningsReport />, { ownerOnly: true })} />
      <Route path="/owner-commercial" element={P(<OwnerCommercialReport />, { ownerOnly: true })} />
      <Route path="/oem-claim-dashboard" element={P(<OemClaimDashboard />, { ownerOnly: true })} />
      <Route path="/claim-exceptions" element={P(<ClaimExceptions />, { ownerOnly: true })} />
      <Route path="/erp-audit" element={P(<ERPProductionAudit />, { ownerOnly: true })} />
      <Route path="/audit-log" element={P(<AuditLog />, { ownerOnly: true })} />
      <Route path="/price-master" element={P(<PriceMaster />, { salesOnly: true })} />
      <Route path="/settings" element={P(<Settings />, { accountsOk: true })} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster richColors position="bottom-right" duration={2500} />
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
