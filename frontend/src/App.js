import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Share from "./pages/Share";
import Dashboard from "./pages/Dashboard";
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

function Protected({ children, ownerOnly }) {
  const { user } = useAuth();
  const loc = useLocation();
  if (user === undefined) return <div className="min-h-screen grid place-items-center text-ink-faint">Loading…</div>;
  if (!user) return <Navigate to="/login" state={{ from: loc }} replace />;
  if (ownerOnly && user.role !== "owner") return <Navigate to="/" replace />;
  return <Layout>{children}</Layout>;
}

function AppRoutes() {
  const P = (el, ownerOnly) => <Protected ownerOnly={ownerOnly}>{el}</Protected>;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/share" element={<Share />} />
      <Route path="/" element={P(<Dashboard />)} />
      <Route path="/leads" element={P(<Leads />)} />
      <Route path="/bookings" element={P(<Bookings />)} />
      <Route path="/quotations" element={P(<Quotations />)} />
      <Route path="/activities" element={P(<Activities />)} />
      <Route path="/payments" element={P(<Payments />)} />
      <Route path="/finance" element={P(<Finance />)} />
      <Route path="/insurance" element={P(<Insurance />)} />
      <Route path="/deliveries" element={P(<Deliveries />)} />
      <Route path="/claims" element={P(<Claims />)} />
      <Route path="/scheme-master" element={P(<SchemeMaster />)} />
      <Route path="/incentive-master" element={P(<IncentiveMaster />)} />
      <Route path="/dealer-earnings" element={P(<DealerEarnings />, true)} />
      <Route path="/insurance-report" element={P(<InsurancePayoutReport />, true)} />
      <Route path="/earnings-report" element={P(<EarningsReport />, true)} />
      <Route path="/owner-commercial" element={P(<OwnerCommercialReport />, true)} />
      <Route path="/oem-claim-dashboard" element={P(<OemClaimDashboard />, true)} />
      <Route path="/claim-exceptions" element={P(<ClaimExceptions />, true)} />
      <Route path="/erp-audit" element={P(<ERPProductionAudit />, true)} />
      <Route path="/price-master" element={P(<PriceMaster />)} />
      <Route path="/settings" element={P(<Settings />)} />
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
