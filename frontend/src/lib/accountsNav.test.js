import { ACCOUNTS_NAV_PATHS, keepNavItem } from "./accountsNav";

const ACCOUNTS_FLAGS = {
  isOwner: false,
  isAccounts: true,
  isSalesStaff: false,
  isField: false,
  isMoneyDesk: true,
  canViewFinance: true,
  canEditCommercials: false,
  canManageShowroom: false,
  canManageStaff: false,
  isSalesGm: false,
  canApproveLeads: false,
  isExecutive: false,
  isTeamLead: false,
  canViewMonthly: true,
  canMatchOemClaims: true,
};

const ITEMS = [
  { to: "/accounts", accountsHome: true },
  { to: "/monthly", monthly: true },
  { to: "/followup-leads" },
  { to: "/leads" },
  { to: "/payments", moneyDesk: true },
  { to: "/finance", financeView: true },
  { to: "/insurance", moneyDesk: true },
  { to: "/claims", oemClaimDesk: true },
  { to: "/oem-claims", oemClaimDesk: true },
  { to: "/inventory" },
  { to: "/deliveries" },
  { to: "/settings" },
  { to: "/bookings" },
  { to: "/approvals", salesOnly: true, approvals: true },
  { to: "/whatsapp", salesOnly: true },
  { to: "/", salesOnly: true, end: true },
  { to: "/staff", staffDesk: true },
];

test("accounts desk keeps dashboard, money pages and both lead registers", () => {
  const kept = ITEMS.filter((i) => keepNavItem(i, ACCOUNTS_FLAGS)).map((i) => i.to);
  for (const to of [
    "/accounts", "/payments", "/finance", "/insurance", "/claims", "/oem-claims",
    "/leads", "/followup-leads", "/monthly", "/inventory", "/deliveries", "/settings",
  ]) {
    expect(ACCOUNTS_NAV_PATHS.has(to)).toBe(true);
    expect(kept).toContain(to);
  }
});

test("accounts desk does not keep bookings, approvals or WhatsApp", () => {
  const kept = ITEMS.filter((i) => keepNavItem(i, ACCOUNTS_FLAGS)).map((i) => i.to);
  expect(kept).not.toContain("/bookings");
  expect(kept).not.toContain("/approvals");
  expect(kept).not.toContain("/whatsapp");
  expect(kept).not.toContain("/");
  expect(kept).not.toContain("/staff");
});
