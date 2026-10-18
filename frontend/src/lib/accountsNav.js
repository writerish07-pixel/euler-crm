// Accounts is the money desk, not a sales-only register. Keep Tally, receipts,
// finance, insurance, claims, inventory and both lead lists — hide bookings,
// approvals, WhatsApp and owner-only masters.
export const ACCOUNTS_NAV_PATHS = new Set([
  "/accounts",
  "/monthly",
  "/followup-leads",
  "/leads",
  "/cancellations",
  "/payments",
  "/finance",
  "/insurance",
  "/deliveries",
  "/oem-billing",
  "/claims",
  "/oem-claims",
  "/oem-claims/no-vehicle",
  "/oem-extra-support",
  "/dropped-extra-support",
  "/inventory",
  "/settings",
]);

export function keepNavItem(i, flags = {}) {
  const {
    isOwner, isAccounts, isSalesStaff, isField, isMoneyDesk,
    canViewFinance, canEditCommercials, canManageShowroom, canManageStaff,
    isSalesGm, canApproveLeads, isExecutive, isTeamLead, canViewMonthly,
    canMatchOemClaims,
  } = flags;
  if (isAccounts && !isSalesStaff && !isField && !ACCOUNTS_NAV_PATHS.has(i.to)) return false;
  if (i.ownerOnly && !isOwner) return false;
  if (i.salesOnly && !isSalesStaff) return false;
  if (i.moneyDesk && !isMoneyDesk) return false;
  if (i.oemClaimDesk && !canMatchOemClaims) return false;
  if (i.financeView && !canViewFinance) return false;
  if (i.dealDesk && !canEditCommercials) return false;
  if (i.showroomDesk && !canManageShowroom) return false;
  if (i.staffDesk && !canManageStaff) return false;
  if (i.accountsHome && !isAccounts && !isOwner) return false;
  if (i.fieldHome && !isField && !isOwner) return false;
  if (i.gmHome && !isSalesGm && !isOwner) return false;
  if (i.monthly && !canViewMonthly) return false;
  if (i.approvals && !canApproveLeads && !isExecutive && !isTeamLead) return false;
  return true;
}
