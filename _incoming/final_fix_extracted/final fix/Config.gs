/**
 * CRM Configuration - Single source of truth for sheet names, columns, and settings.
 *
 * v2.2 changes:
 *   ✔ Dashboard VALUE_CELLS: financeOutstanding added at B35.
 *   ✔ Dashboard MIRROR_CELLS: financeOutstanding added at B30.
 *   ✔ menuDealQuotation added to MENU_HANDLERS.
 *   ✔ getModelsForQuotation, getVariantsForQuotationModel, getPriceAndSchemeForQuotation,
 *     saveQuotationFromDialog added to PUBLIC_API.
 */
var CRM = (function () {
  var SHEETS = {
    DASHBOARD: 'Dashboard',
    LEAD_REGISTER: 'Lead Register',
    ACTIVITY_LOG: 'Activity Log',
    PAYMENT_LEDGER: 'Payment Ledger',
    DELIVERY_TRACKER: 'Delivery Tracker',
    MASTERS: 'Masters',
    DASHBOARD_DATA: 'Dashboard Data',
    SETTINGS: 'Settings',
    IMPORT_LOG: 'Import Log',
    AUDIT_LOG: 'Audit Log',
    TRANSACTION_LOG: 'Transaction Log',
    BACKUP_REGISTRY: 'Backup Registry',
    CRASH_REPORT: 'Crash Report',
    PERFORMANCE_LOG: 'Performance Log',
    OBS_HEALTH_REPORT: 'Obs Health Report',
    OBS_PERFORMANCE_REPORT: 'Obs Performance Report',
    OBS_KPI_REPORT: 'Obs KPI Report',
    OBS_GROWTH_REPORT: 'Obs Growth Report',
    OBS_ACTIVITY_REPORT: 'Obs Activity Report',
    OBS_REPORT_INDEX: 'Obs Report Index',
    PEP_DAILY_REPORT: 'PEP Daily Report',
    PEP_BACKUP_VERIFY: 'PEP Backup Verify',
    PEP_CAPACITY: 'PEP Capacity Log',
    PEP_SLA_LOG: 'PEP SLA Log',
    PEP_OPERATOR: 'PEP Operator Summary',
    PEP_DR_VALIDATION: 'PEP DR Validation',
    PEP_ALERTS: 'PEP Alerts',
    COMMERCIAL_SNAPSHOT: 'Commercial Snapshot',
    BOOKING_REGISTER: 'Booking Register',
    RELATIONSHIP_INDEX: 'RelationshipIndex',
    BOOKING_STATUS_HISTORY: 'Booking Status History',
    VEHICLE_ALLOCATION: 'Vehicle Allocation',
    QUOTATION_SCHEMA: 'Quotation Schema',
    EXECUTIVE_SCORECARD: 'Executive Scorecard',
    DEALER_DAILY_REGISTER: 'Dealer Daily Register',
    SCHEME_CLAIM_REGISTER: 'Scheme Claim Register',
    FINANCE_REGISTER: 'Finance Register',
    FINANCE_PENDING: 'Finance Pending',
    FINANCE_OVERDUE: 'Finance Overdue',
    SCHEME_MASTER: 'Scheme Master',
    INCENTIVE_MASTER: 'Incentive Master',
    INCENTIVE_REGISTER: 'Incentive Register',
    OEM_CLAIM_DASHBOARD: 'OEM Claim Dashboard',
    OWNER_COMMERCIAL_REPORT: 'Owner Commercial Report',
    CLAIM_EXCEPTION: 'Claim Exception Report',
    COMMERCIAL_AUDIT: 'Commercial Audit',
    PRICE_MASTER: 'PRICE MASTER',
    QUOTATION_LOG: 'Quotation Log',
    INSURANCE_REGISTER: 'Insurance Register',
    EXTRA_INCOME_REGISTER: 'Dealer Earnings Register',
    EXTRA_INCOME_ANALYTICS: 'Dealer Earnings Analytics',
    DEALER_EARNINGS_REGISTER: 'Dealer Earnings Register',
    DEALER_EARNINGS_ANALYTICS: 'Dealer Earnings Analytics',
    OEM_EXTRA_SUPPORT_REGISTER: 'OEM Extra Support Register'
  };

  var VERSION = 'GO-LIVE-2';
  var PATCH_VERSION = 'v2.2-quotation-finance-fix';
  var SCHEMA_VERSION = '1.0';
  var MIGRATION_VERSION = '1';
  var APPS_SCRIPT_BUILD = '3';

  var TRANSACTION_LOG = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Timestamp', 'User', 'Module', 'Action', 'Lead ID', 'Execution Ms',
      'Status', 'Error Code', 'Message', 'Version'
    ]
  };

  var AUDIT_LOG = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Timestamp', 'User', 'Action', 'Details', 'Version']
  };

  var LEAD = {
    HEADER_ROW: 3,
    DATA_START: 4,
    SEARCH_ROW: 1,
    COLS: [
      'Lead ID', 'Created Date', 'Customer Name', 'Mobile', 'Alternate Mobile',
      'Village', 'City', 'Lead Source', 'Interested Model', 'Variant',
      'Executive', 'Current Status', 'Priority', 'Budget', 'Last Activity',
      'Next Follow-up Date', 'Next Follow-up Time', 'Booking Date',
      'Booking Amount', 'Finance Required', 'Exchange Required', 'Delivery Status',
      'Delivery Date', 'Outstanding Amount', 'Remarks', 'Last Updated', 'Last Updated By',
      'Account Status', 'Closed Date', 'Close Reason', 'Final Outstanding', 'Closed By', 'Close Timestamp',
      'Ex Showroom', 'RTO', 'Insurance Amount', 'Accessories Amount', 'Handling Charges',
      'TRC', 'Fastag', 'Extended Warranty', 'Other Charges', 'Gross Vehicle Cost', 'Customer Payable',
      'Financer Name', 'Finance File Number', 'Last Payment Mode', 'Total Received',
      'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Bonus', 'Additional Discount',
      'Total Discount', 'OEM Scheme Amount', 'Dealer Scheme Amount',
      'Customer Outstanding', 'Company Outstanding',
      'Insurer Name', 'Invoice Number', 'Chassis Number', 'Number Plate',
      'Insurance Status', 'Registration Status', 'Invoice Status', 'RC Status', 'PDI Status',
      'Dealer Earnings'
    ],
    EDITABLE: [
      'Customer Name', 'Mobile', 'Alternate Mobile', 'Village', 'City',
      'Lead Source', 'Interested Model', 'Variant', 'Executive',
      'Priority', 'Budget', 'Current Status', 'Next Follow-up Date',
      'Next Follow-up Time', 'Finance Required', 'Exchange Required',
      'Booking Amount', 'Remarks', 'Financer Name', 'Finance File Number', 'Number Plate',
      'Insurer Name', 'Invoice Number', 'Chassis Number',
      'RTO', 'Insurance Amount', 'Accessories Amount', 'Handling Charges',
      'TRC', 'Fastag', 'Extended Warranty', 'Other Charges'
    ],
    AUTO: [
      'Lead ID', 'Created Date', 'Last Activity', 'Delivery Status',
      'Delivery Date', 'Outstanding Amount', 'Last Updated', 'Last Updated By',
      'Account Status', 'Closed Date', 'Close Reason', 'Final Outstanding', 'Closed By', 'Close Timestamp',
      'Ex Showroom', 'Gross Vehicle Cost', 'Customer Payable', 'Last Payment Mode', 'Total Received',
      'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Bonus', 'Additional Discount',
      'Total Discount', 'OEM Scheme Amount', 'Dealer Scheme Amount',
      'Customer Outstanding', 'Company Outstanding',
      'Insurance Status', 'Registration Status', 'Invoice Status', 'RC Status', 'PDI Status',
      'Dealer Earnings'
    ]
  };

  /** Insurance Register — premium entries + insurer payout tracking.
   * Payout Rate % is always manual / per-entry (rates change). Defaults below are
   * suggestions only when creating a new row (Storm/Turbo 49%, others 36.5%). */
  var INSURANCE_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    SUGGESTED_RATE_STORM_TURBO: 0.49,
    SUGGESTED_RATE_OTHER: 0.365,
    COLS: [
      'Entry ID', 'Lead ID', 'Customer Name', 'Mobile', 'Model', 'Variant',
      'Insurance Company', 'Policy Number', 'Insurance Amount',
      'Payout Rate %', 'Expected Payout', 'Received Payout', 'Payout Outstanding',
      'Status', 'Policy Date', 'Delivery Date', 'Insurance Executive', 'Last Updated', 'Remarks'
    ]
  };

  var ACTIVITY = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Activity ID', 'Lead ID', 'Date', 'Time', 'Activity Type',
      'Discussion', 'Next Follow-up', 'Reminder', 'Executive',
      'Customer Name', 'Mobile', 'Model'
    ],
    EDITABLE: ['Lead ID', 'Activity Type', 'Discussion', 'Next Follow-up', 'Reminder', 'Executive']
  };

  var PAYMENT = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Receipt Number', 'Lead ID', 'Customer Name', 'Date', 'Amount',
      'Payment Mode', 'Financer Name', 'Finance File Number', 'Narration',
      'Running Total', 'Outstanding Balance', 'Payment ID'
    ],
    EDITABLE: ['Lead ID', 'Amount', 'Payment Mode', 'Financer Name', 'Finance File Number', 'Narration']
  };

  var FINANCE_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    /** After delivery, financer disbursement must arrive within this many days. */
    RECEIPT_SLA_DAYS: 2,
    COLS: [
      'File Number', 'Lead ID', 'Customer Name', 'Financer', 'Sanctioned Amount',
      'Received Against File', 'File Outstanding', 'Status', 'Last Payment Date', 'Last Updated'
    ]
  };

  /** Monthly consumer scheme matrix. */
  var SCHEME_MASTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Scheme Month', 'Effective From', 'Effective To', 'Circular Ref', 'Model', 'Variant',
      'Component', 'Component Key', 'Dealer Share', 'Company Share', 'Total Benefit',
      'Status', 'Notes'
    ],
    COMPONENTS: [
      { key: 'consumerDiscount', label: 'Consumer Scheme' },
      { key: 'rtoInsuranceBenefit', label: 'Free RTO + Free Insurance' },
      { key: 'rtoBenefit', label: 'RTO Benefits Up to' },
      { key: 'insuranceBenefit', label: 'Insurance Benefits Up to' },
      { key: 'exchangeBonus', label: 'Exchange Benefit' },
      { key: 'dsaDiscount', label: 'DSA' },
      { key: 'referralBonus', label: 'Referral' },
      { key: 'loyaltyBonus', label: 'Loyalty' }
    ]
  };

  var INCENTIVE_MASTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Scheme Month', 'Effective From', 'Effective To', 'Circular Ref', 'Product Category',
      'Incentive Per Retail', 'Min Retails', 'Max Slab', 'Status', 'Notes'
    ]
  };

  var INCENTIVE_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Incentive ID', 'Scheme Month', 'Executive', 'Lead ID', 'Booking ID', 'Model', 'Variant',
      'Product Category', 'Delivery Date', 'Incentive Amount', 'Status', 'Paid Date', 'Remarks', 'Last Updated'
    ]
  };

  var DELIVERY = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Lead ID', 'Customer Name', 'Insurance', 'Insurer Name', 'Registration', 'Invoice', 'Invoice Number',
      'Chassis Number', 'Accessories', 'RC', 'Number Plate', 'PDI', 'Delivered',
      'Delivery Date', 'Feedback', 'Delivery ID', 'Dealer Earnings'
    ],
    EDITABLE: [
      'Lead ID', 'Insurance', 'Insurer Name', 'Registration', 'Invoice', 'Invoice Number', 'Chassis Number',
      'Accessories', 'RC', 'Number Plate', 'PDI', 'Delivered', 'Delivery Date', 'Feedback'
    ],
    STATUS_COLS: ['Insurance', 'Registration', 'Invoice', 'Accessories', 'RC', 'PDI', 'Delivered']
  };

  var COMMERCIAL = {
    HEADER_ROW: 1,
    DATA_START: 2,
    TCS_RATE: 0.01,
    TCS_THRESHOLD: 1000000,
    DEALER_MARGIN_RATE: 0.04,
    DEALER_MARGIN_GST_RATE: 0.05,
    SNAPSHOT_PREFIX: 'SN26',
    BOOKING_PREFIX: 'BK26',
    CLAIM_PREFIX: 'CLM26',
    COMPONENT_POLICY: {
      consumerDiscount:   { col: 'Consumer Discount',   label: 'Consumer Discount',   payer: 'OEM',    approvalRequired: false, claimable: true },
      exchangeBonus:      { col: 'Exchange Bonus',       label: 'Exchange Bonus',      payer: 'OEM',    approvalRequired: false, claimable: true },
      loyaltyBonus:       { col: 'Loyalty Bonus',        label: 'Loyalty Bonus',       payer: 'OEM',    approvalRequired: false, claimable: true },
      referralBonus:      { col: 'Referral Bonus',       label: 'Referral Bonus',      payer: 'OEM',    approvalRequired: false, claimable: true },
      dsaDiscount:        { col: 'DSA Discount',         label: 'DSA Bonus',           payer: 'OEM',    approvalRequired: true,  claimable: true },
      additionalDiscount: { col: 'Additional Discount',  label: 'Additional Discount', payer: 'Dealer', approvalRequired: true,  claimable: false }
    },
    OFFER_KEYS: ['consumerDiscount', 'exchangeBonus', 'loyaltyBonus', 'referralBonus', 'dsaDiscount', 'additionalDiscount'],
    BENEFIT_MODES: ['Full Benefit', 'Partial Benefit', 'No Benefit'],
    COLS: [
      'Lead ID', 'Booking Date', 'Price List Version', 'Price Master Row ID', 'Price Effective Date', 'Vehicle Model', 'Variant', 'Body Type',
      'Booking Amount', 'Booking Executive', 'Booking Mode', 'Finance Required', 'Exchange Required',
      'Ex Showroom Price', 'Accessories', 'Insurance', 'Registration / RTO', 'Fastag', 'Handling Charges', 'TRC',
      'Extended Warranty', 'RSA / AMC', 'Other Charges', 'GST %', 'TCS Applicable', 'TCS',
      'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Discount', 'Additional Discount',
      'OEM Extra Support Received', 'OEM Extra Support Passed To Customer', 'OEM Extra Support Retained',
      'Total Discount', 'Benefit Mode', 'Customer Benefit Passed',
      'Old Vehicle Brand', 'Old Vehicle Model', 'Registration Number', 'Evaluated Value', 'Final Exchange Value',
      'Financer', 'Loan Amount', 'Down Payment',
      'Gross Vehicle Cost', 'Gross Invoice Amount', 'Net Vehicle Cost', 'Customer Payable',
      'Dealer Margin Gross (Incl GST)', 'Dealer Margin GST (5%)', 'Dealer Margin Net (Ex GST)',
      'Booking Locked', 'Lock Reason',
      'Created At', 'Updated At', 'Updated By',
      'Booking ID', 'Snapshot ID', 'Snapshot Status', 'Superseded By', 'Amendment Reason',
      'Benefit Passed Breakup'
    ]
  };

  /** Owner-only Dealer Earnings Register — evolved from Extra Income. Never customer-facing. */
  var DEALER_EARNINGS_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Lead ID', 'Booking ID', 'Customer Name', 'Executive', 'Team Leader', 'Lead Source',
      'Vehicle Model', 'Variant', 'Colour', 'Current Stage',
      'Booking Date', 'Delivery Date', 'Invoice Number',
      'Customer Payable',
      'OEM Eligible Scheme', 'Customer Scheme Benefit Passed', 'Dealer Scheme Retained',
      'Dealer Margin Gross (Incl GST)', 'Dealer Margin GST (5%)', 'Dealer Margin Net (Ex GST)',
      'OEM Extra Support Received', 'OEM Extra Support Passed To Customer', 'OEM Extra Support Retained',
      'Insurance Payout', 'Customer Insurance Benefit Passed', 'Dealer Insurance Income',
      'Finance Incentive', 'Accessories Margin', 'Exchange Margin',
      'Documentation Income', 'Warranty Income', 'RSA Income',
      'Referral Income', 'Campaign Incentive', 'Other Income',
      'TOTAL DEALER EARNINGS',
      'Claim Status', 'Insurance Status',
      'Last Updated', 'Created By', 'Modified By', 'Timestamp', 'Remarks',
      'Consumer Retained', 'Exchange Retained', 'Loyalty Retained', 'Referral Retained', 'DSA Retained',
      'Scheme Retained Breakup'
    ]
  };
  /** @deprecated alias — same as DEALER_EARNINGS_REGISTER */
  var EXTRA_INCOME_REGISTER = DEALER_EARNINGS_REGISTER;

  var OEM_EXTRA_SUPPORT_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Lead ID', 'Booking ID', 'Customer Name', 'Vehicle Model', 'Variant',
      'Booking Date', 'OEM Extra Support Received', 'OEM Extra Support Passed To Customer',
      'OEM Extra Support Retained', 'Status', 'Last Updated', 'Remarks'
    ]
  };

  var CLAIM_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    LIFECYCLE_COLS: [
      'Source', 'DSA Approval', 'Claim Status', 'Claim Reference Number',
      'Claim Submitted Date', 'Claim Approved Date', 'Claim Received Date',
      'Received Amount', 'Claim Remarks', 'Claim Amount', 'Claim ID'
    ],
    CLAIM_STATUSES: ['Pending', 'Submitted', 'Approved', 'Rejected', 'Received', 'Not Applicable'],
    APPROVAL_STATUSES: ['Pending', 'Approved', 'Rejected'],
    COLS: [
      'Claim ID', 'Source', 'Booking ID', 'Lead ID', 'Customer', 'Model', 'Variant', 'Booking Date', 'Scheme Month', 'Executive',
      'Component', 'Component Key',
      'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Discount', 'Additional Discount',
      'Total Discount', 'Dealer Discount', 'OEM Discount',
      'DSA Approval', 'Claim Required', 'Eligible Claim', 'Claim Amount', 'Received Amount',
      'Claim Status', 'Claim Reference Number',
      'Claim Submitted Date', 'Claim Approved Date', 'Claim Received Date', 'Claim Ageing (Days)', 'Claim Remarks'
    ]
  };

  var COMMERCIAL_AUDIT = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Timestamp', 'User', 'Booking ID', 'Lead ID', 'Field', 'Old Value', 'New Value', 'Reason', 'Approved By', 'Version']
  };

  var BOOKING_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'BookingID', 'LeadID', 'CustomerName', 'Booking Date', 'Vehicle Model', 'Variant',
      'Booking Amount', 'Amount Received', 'Payment Mode', 'Finance Required', 'Exchange Required', 'CommercialSnapshotID',
      'Booking Status', 'Created By', 'Created Date', 'Last Updated', 'Dealer Earnings'
    ]
  };

  var RELATIONSHIP_INDEX = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'LeadID', 'CustomerName', 'Mobile', 'BookingID', 'CommercialSnapshotID',
      'PaymentIDs', 'DeliveryID', 'ClaimID', 'LatestActivityID',
      'Current Status', 'Last Updated'
    ]
  };

  var BOOKING_STATUS_HISTORY = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Timestamp', 'LeadID', 'BookingID', 'Old Status', 'New Status', 'Remark', 'Updated By']
  };

  var VEHICLE_ALLOCATION = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['AllocationID', 'LeadID', 'BookingID', 'VIN', 'Motor Number', 'Chassis Number', 'Allocated Date', 'Status', 'Remark']
  };

  var QUOTATION_SCHEMA = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['QuotationID', 'LeadID', 'BookingID', 'QuotationVersion', 'PriceVersion', 'SchemeVersion', 'CommercialTermsHash', 'Generated At']
  };

  var QUOTATION_LOG = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Quote ID', 'Date', 'Customer Name', 'Mobile', 'Model', 'Variant',
      'Ex Showroom', 'Insurance', 'Registration', 'Accessories', 'Handling',
      'TRC', 'Fastag', 'Ext Warranty', 'Other Charges', 'Gross Vehicle Cost',
      'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus',
      'DSA Bonus', 'Additional Discount', 'Total Discount',
      'Customer Payable', 'OEM Share (Dealer Gets)', 'Finance Required',
      'Exchange Value', 'Financer', 'Narration', 'Generated By', 'Price Version'
    ]
  };

  var EXECUTIVE_SCORECARD = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Executive', 'Assigned Leads', 'Today Activities', 'Pending Follow-ups', 'Bookings', 'Deliveries', 'Outstanding Collections', 'Conversion %', 'Avg Discount', 'Avg Booking Value', 'Updated At']
  };

  var DEALER_DAILY_REGISTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: [
      'Date', 'Leads', 'Bookings', 'Payments Total', 'Cash', 'UPI', 'Finance',
      'Other Payments', 'Deliveries', 'Outstanding', 'Top Executive', 'Updated At'
    ]
  };

  var CLAIM_EXCEPTION = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Generated At', 'Lead ID', 'Booking ID', 'Exception Type', 'Severity', 'Detail', 'Version']
  };

  var PRICE_MASTER = {
    HEADER_ROW: 1,
    DATA_START: 2,
    CACHE_TTL_SEC: 300,
    COLS: [
      'Model', 'Variant', 'Body Type', 'Ex Showroom Price', 'RTO', 'Insurance',
      'Accessories', 'Handling Charges', 'TRC', 'Fastag', 'Extended Warranty', 'Other Charges',
      'GST %', 'TCS Applicable', 'Effective From', 'Effective To', 'Price Version',
      'Status', 'Remarks'
    ]
  };

  var MASTERS = {
    HEADER_ROW: 1,
    SECTIONS: {
      'Lead Sources': ['Walk-in', 'WhatsApp', 'Referral', 'Website', 'Phone', 'Social Media'],
      'Models': [],
      'Variants': [],
      'Status': ['New', 'Contacted', 'Follow-up', 'In Progress', 'Booked', 'Finance Process', 'Delivered', 'Lost'],
      'Account Status': ['Active', 'Closed', 'Cancelled', 'Archived'],
      'Executives': ['Lokesh', 'Sanjay', 'Amit', 'Dharmendra', 'Prasun'],
      'Payment Modes': ['Cash', 'UPI', 'Cheque', 'NEFT', 'Finance', 'Card'],
      'Financers': ['SUNDARAM', 'SHRIRAM', 'HDFC BANK', 'IDFC BANK', 'RAJPUTANA', 'UNION BANK', 'CASH'],
      'Priority': ['Low', 'Normal', 'High', 'Urgent'],
      'Activity Types': ['Call', 'WhatsApp', 'Visit', 'Follow-up', 'Booking', 'Delivery', 'Note']
    }
  };

  var SETTINGS_DEFAULTS = {
    companyName: 'EV Dealership CRM',
    financialYear: '2026-27',
    leadPrefix: 'LD26',
    receiptPrefix: 'RC26',
    bookingPrefix: 'BK26',
    financeFilePrefix: 'FN26',
    nextLeadCounter: 1,
    nextActivityCounter: 1,
    nextReceiptCounter: 1,
    nextFinanceFileCounter: 1,
    nextBookingCounter: 1,
    nextSnapshotCounter: 1,
    nextClaimCounter: 1,
    ownerPriceOverrideEnabled: 'No',
    schemeShareConsumerDiscount: 0,
    schemeShareExchangeBonus: 0,
    schemeShareLoyaltyBonus: 0,
    schemeShareReferralBonus: 0,
    schemeShareDsaDiscount: 0
  };

  /**
   * Dashboard cell map – values written by refreshDashboard_() (no formulas except hyperlinks).
   *
   * Row layout (A column labels):
   *   A26 PAYMENTS (MONTH)  A27 Cash  A28 UPI  A29 Finance  A30 Other
   *   A31 Outstanding (Total Customer)  A32 Customer Outstanding
   *   A33 Company Outstanding  A34 Finance Overdue  A35 Finance Total Outstanding
   *   A36 INSURANCE  A37 Premium Total  A38 Expected Payout  A39 Received  A40 Payout OS
   *   A42 MODEL PERFORMANCE (dynamic table from row 43 — all Price Master / Lead models)
   */
  var DASHBOARD = {
    VALUE_CELLS: {
      lastUpdated:          'B2',
      todayLeads:           'B5',
      todayFollowups:       'B6',
      todayBookings:        'B7',
      todayDeliveries:      'B8',
      pendingDeliveries:    'B11',
      pendingFollowups:     'B12',
      pendingPayments:      'B13',
      monthlyLeads:         'B16',
      monthlyBookings:      'B17',
      monthlyDeliveries:    'B18',
      conversion:           'B19',
      topSource:            'B22',
      topModel:             'B23',
      revenue:              'B24',
      paymentsCash:         'B27',
      paymentsUpi:          'B28',
      paymentsFinance:      'B29',
      paymentsOther:        'B30',
      outstanding:          'B31',
      customerOutstanding:  'B32',
      companyOutstanding:   'B33',
      financeOverdue:       'B34',
      financeOutstanding:   'B35',
      insurancePremium:     'B37',
      insuranceExpected:    'B38',
      insuranceReceived:    'B39',
      insuranceOutstanding: 'B40'
    },
    RECENT_START_ROW: 3,
    RECENT_COUNT: 10,
    RECENT_COLS: { date: 4, leadId: 5, customer: 6, type: 7, discussion: 8, executive: 9 },
    MIRROR_CELLS: {
      lastUpdated:          'B1',
      todayLeads:           'B3',
      todayFollowups:       'B4',
      todayBookings:        'B5',
      todayDeliveries:      'B6',
      pendingDeliveries:    'B8',
      pendingFollowups:     'B9',
      pendingPayments:      'B10',
      monthlyLeads:         'B12',
      monthlyBookings:      'B13',
      monthlyDeliveries:    'B14',
      conversion:           'B15',
      topSource:            'B17',
      topModel:             'B18',
      revenue:              'B19',
      paymentsCash:         'B21',
      paymentsUpi:          'B22',
      paymentsFinance:      'B23',
      paymentsOther:        'B24',
      outstanding:          'B26',
      customerOutstanding:  'B27',
      companyOutstanding:   'B28',
      financeOverdue:       'B29',
      financeOutstanding:   'B30',
      insurancePremium:     'B32',
      insuranceExpected:    'B33',
      insuranceReceived:    'B34',
      insuranceOutstanding: 'B35'
    },
    RECENT_DATA_START_ROW: 25
  };

  var PERFORMANCE_LOG = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Date', 'Operation', 'Avg Ms', 'Max Ms', 'Count', 'Warning']
  };

  var OBSERVABILITY = {
    OWNER_PANEL_COL: 11,
    OWNER_PANEL_START_ROW: 1,
    HEALTH_REPORT: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Status', 'Color', 'Passed', 'Failed', 'Critical', 'Warnings', 'Summary', 'Version'] },
    PERFORMANCE_REPORT: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Operation', 'Avg Ms', 'Max Ms', 'Count', 'Over Threshold', 'Version'] },
    KPI_REPORT: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Metric', 'Value', 'Version'] },
    GROWTH_REPORT: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Sheet', 'Data Rows', 'Version'] },
    ACTIVITY_REPORT: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'User', 'Module', 'Action Count', 'Top Actions', 'Version'] },
    REPORT_INDEX: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Overall Status', 'Health Status', 'Perf Warnings', 'Total Rows', 'Active Users', 'Email Sent', 'Generated At', 'Version'] }
  };

  var EXCELLENCE = {
    PRODUCTION_PANEL_COL: 14,
    PRODUCTION_PANEL_START_ROW: 1,
    CAPACITY: { MAX_ROWS_WARN: 80000, MAX_ROWS_CRITICAL: 95000, MAX_FILE_MB_WARN: 150, EXECUTION_MS_WARN: 300000 },
    KPI_ALERTS: { MIN_DAILY_PAYMENTS: 0, PAYMENT_SPIKE_RATIO: 2.5, OUTSTANDING_SPIKE_RATIO: 1.5, ZERO_ACTIVITY_WARN: true },
    DAILY_REPORT: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Leads', 'Activities', 'Payments', 'Deliveries', 'Outstanding', 'Errors', 'Health', 'SLA Status', 'Capacity Status', 'Version'] },
    BACKUP_VERIFY: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Backup No', 'Passed', 'Row Match', 'Sheets OK', 'Detail', 'Version'] },
    CAPACITY_LOG: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Total Rows', 'File MB', 'Perf Max Ms', 'Quota Risk', 'Warning', 'Version'] },
    SLA_LOG: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Operation', 'Avg Ms', 'Max Ms', 'Threshold', 'SLA Status', 'Version'] },
    OPERATOR_SUMMARY: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'User', 'Leads', 'Activities', 'Payments', 'Deliveries', 'Total Actions', 'Version'] },
    DR_VALIDATION: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Backup No', 'Passed', 'Health', 'Dashboard', 'Reports', 'Detail', 'Version'] },
    ALERTS: { HEADER_ROW: 1, DATA_START: 2, COLS: ['Date', 'Alert Type', 'Severity', 'Message', 'Notified', 'Version'] }
  };

  var BACKUP_REGISTRY = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Backup No', 'Timestamp', 'Version', 'Drive URL', 'Spreadsheet ID', 'Row Count', 'Sheet Count', 'Settings Hash', 'Protection Hash', 'Notes']
  };

  var CRASH_REPORT = {
    HEADER_ROW: 1,
    DATA_START: 2,
    COLS: ['Timestamp', 'User', 'Module', 'Function', 'Lead ID', 'Error Code', 'Message', 'Stack Trace', 'Execution Ms', 'Spreadsheet ID', 'Version']
  };

  var MENU_HANDLERS = [
    'menuNewLead', 'menuUpdateLead', 'menuConvertToBooking', 'menuAddActivity', 'menuAddPayment',
    'menuMarkDelivered', 'menuCloseLead', 'menuSearchLead', 'menuRefreshDashboard',
    'menuHighlightManualInputs', 'menuClearManualHighlights', 'menuRefreshLeadPrices',
    'menuBackupDatabase', 'menuRestoreBackup', 'menuSettings',
    'menuImportHistoricalData', 'menuInitialSetup', 'menuValidateDatabase',
    'menuRunRegressionTests', 'menuImportPriceMaster2026', 'menuMigrateLeadRegister',
    'menuFreshSetup', 'menuFreshStartClearAllData', 'menuRestoreTabOrder', 'menuGoLiveQuickFix', 'menuRemoveBookingStatusColumn',
    'menuRebuildClaimRegister', 'menuOemClaimDashboard', 'menuOwnerCommercialReport',
    'menuReconcileClaims', 'menuOpenClaimRegister', 'menuRecordClaimReceived',
    'menuUpdateClaimStatus', 'menuAddManualClaim', 'menuCertifyCommercial', 'menuCertifyPriceMaster',
    'menuRecordFinancerReceipt', 'menuRefreshFinancePending', 'menuOpenFinanceOverdue',
    'menuRebuildFinanceRegister',
    'menuOpenSchemeMaster', 'menuOpenIncentiveMaster', 'menuOpenIncentiveRegister',
    'menuReseedJuly2026Schemes', 'menuSystemHealthCheck', 'menuDeploymentCertification',
    'menuCertifyDashboard',
    'menuGlobalSearch', 'menuShowCustomer360', 'menuShowCustomer360FromCell',
    'menuRefreshNavLinks', 'menuGenerateNavigationMatrix', 'menuShowNavigationHome',
    'menuNavToLeadRegister', 'menuNavToBookingRegister',
    'menuNavToPaymentLedger', 'menuNavToDeliveryTracker', 'menuNavToFinanceRegister',
    'menuNavToDashboard',
    'menuSyncDashboardNow',
    'menuDealQuotation', 'menuPriceStructure', 'menuEditLead', 'menuSchemeUpdate',
    'menuOpenInsuranceRegister', 'menuAddInsuranceEntry', 'menuRecordInsurancePayout',
    'menuUpdateInsurancePayoutRate',
    'menuOpenDealerEarningsRegister', 'menuOpenDealerEarningsAnalytics', 'menuRebuildDealerEarnings',
    'menuRepairOemExtraSupportHeaders'
  ];

  var PUBLIC_API = [
    'createNewLeadFromDialog', 'addActivityFromDialog', 'addPaymentFromDialog',
    'markDeliveredFromDialog', 'closeLeadFromDialog', 'goToLeadFromDialog',
    'saveBookingFromDialog', 'getBookingLeadContext', 'getPriceForBookingContext',
    'getPriceStructureContext', 'savePriceStructureFromDialog',
    'getEditLeadContext', 'saveEditLeadFromDialog',
    'getDeliveryContextForDialog', 'getCloseLeadContextForDialog', 'getUpdateLeadContext', 'updateLeadFromDialog',
    'getOpenClaimsForDialog', 'getClaimContextForDialog',
    'settleClaimFromDialog', 'updateClaimStatusFromDialog', 'addManualClaimFromDialog',
    'getShareDashboard_',
    'getActiveLeadsForPicker', 'getDuplicateLeadGroups', 'mergeLeadsFromDialog',
    'refreshCrmAfterDialogSave', 'getSchemeRulesForDialog', 'getSchemeRulesForLeadDialog',
    'getPendingFinanceFilesForDialog', 'recordFinanceFileReceiptFromDialog',
    'navGoToLead', 'navGoToBooking', 'navGoToPayment', 'navGoToFinance',
    'navGoToDelivery', 'navGoToActivity', 'navGoToClaim', 'navGoToCommercialSnapshot',
    'navGoToDealerEarnings',
    'navGoToEntity', 'navGoToSheetPublic', 'navOpen360ForLead',
    'getNavigationHistory', 'getNavigationMatrix', 'getBreadcrumb',
    'getCustomer360Data', 'showCustomer360FromPicker',
    'globalSearchQuery',
    // Quotation service
    'getModelsForQuotation', 'getVariantsForQuotationModel',
    'getPriceAndSchemeForQuotation', 'saveQuotationFromDialog',
    'getInsuranceContextForDialog', 'saveInsuranceEntryFromDialog',
    'getPendingInsurancePayoutsForDialog', 'recordInsurancePayoutFromDialog',
    'getAllInsuranceEntriesForDialog', 'updateInsurancePayoutRateFromDialog'
  ];

  var HIDDEN_SHEETS = [
    'DASHBOARD_DATA', 'SETTINGS', 'IMPORT_LOG', 'AUDIT_LOG', 'TRANSACTION_LOG',
    'BACKUP_REGISTRY', 'CRASH_REPORT', 'PERFORMANCE_LOG',
    'OBS_HEALTH_REPORT', 'OBS_PERFORMANCE_REPORT', 'OBS_KPI_REPORT',
    'OBS_GROWTH_REPORT', 'OBS_ACTIVITY_REPORT', 'OBS_REPORT_INDEX',
    'PEP_DAILY_REPORT', 'PEP_BACKUP_VERIFY', 'PEP_CAPACITY', 'PEP_SLA_LOG',
    'PEP_OPERATOR', 'PEP_DR_VALIDATION', 'PEP_ALERTS', 'COMMERCIAL_SNAPSHOT',
    'COMMERCIAL_AUDIT', 'EXTRA_INCOME_ANALYTICS',
    'DEALER_EARNINGS_ANALYTICS'
  ];

  /** Dashboard KPI drill-down tabs — kept for hyperlinks, hidden from tab bar. */
  var DRILL_DOWN_SHEETS = [
    "Today's Leads", "Today's Bookings", "Today's Deliveries", "Today's Follow-ups",
    'Pending Deliveries', 'Pending Follow-ups',
    'Monthly Leads', 'Monthly Bookings', 'Monthly Deliveries', 'Monthly Payments',
    'Payments — Cash (Month)', 'Payments — UPI (Month)',
    'Payments — Finance (Month)', 'Payments — Other (Month)',
    'Outstanding Leads', 'Navigation Matrix'
  ];

  /** User-facing tab order (left → right). All other CRM sheets are hidden. */
  var SHEET_LAYOUT = {
    VISIBLE_ORDER: [
      'Dashboard',
      'Lead Register',
      'Activity Log',
      'Booking Register',
      'Payment Ledger',
      'Delivery Tracker',
      'Finance Register',
      'Finance Pending',
      'Finance Overdue',
      'Insurance Register',
      'Scheme Claim Register',
      'Quotation Log',
      'Scheme Master',
      'Incentive Master',
      'Incentive Register',
      'PRICE MASTER',
      'OEM Claim Dashboard',
      'Owner Commercial Report',
      'Claim Exception Report',
      'Dealer Earnings Register',
      'OEM Extra Support Register'
    ],
    BACKEND: [
      'Masters',
      'RelationshipIndex',
      'Booking Status History',
      'Vehicle Allocation',
      'Quotation Schema',
      'Executive Scorecard',
      'Dealer Daily Register',
      'Dealer Earnings Analytics',
      'Extra Income Analytics',
      'Migration Import Log'
    ]
  };

  var COLORS = {
    TODAY_FOLLOWUP:  '#FFE0B2',
    OVERDUE_FOLLOWUP: '#FFCDD2',
    DELIVERED:       '#C8E6C9',
    BOOKED:          '#BBDEFB',
    PENDING_PAYMENT: '#FFCDD2',
    LOST:            '#E0E0E0'
  };

  return {
    SHEETS: SHEETS,
    DASHBOARD: DASHBOARD,
    TRANSACTION_LOG: TRANSACTION_LOG,
    BACKUP_REGISTRY: BACKUP_REGISTRY,
    CRASH_REPORT: CRASH_REPORT,
    PERFORMANCE_LOG: PERFORMANCE_LOG,
    OBSERVABILITY: OBSERVABILITY,
    EXCELLENCE: EXCELLENCE,
    COMMERCIAL: COMMERCIAL,
    CLAIM_REGISTER: CLAIM_REGISTER,
    COMMERCIAL_AUDIT: COMMERCIAL_AUDIT,
    BOOKING_REGISTER: BOOKING_REGISTER,
    RELATIONSHIP_INDEX: RELATIONSHIP_INDEX,
    BOOKING_STATUS_HISTORY: BOOKING_STATUS_HISTORY,
    VEHICLE_ALLOCATION: VEHICLE_ALLOCATION,
    QUOTATION_SCHEMA: QUOTATION_SCHEMA,
    QUOTATION_LOG: QUOTATION_LOG,
    EXECUTIVE_SCORECARD: EXECUTIVE_SCORECARD,
    DEALER_DAILY_REGISTER: DEALER_DAILY_REGISTER,
    FINANCE_REGISTER: FINANCE_REGISTER,
    SCHEME_MASTER: SCHEME_MASTER,
    INCENTIVE_MASTER: INCENTIVE_MASTER,
    INCENTIVE_REGISTER: INCENTIVE_REGISTER,
    PRICE_MASTER: PRICE_MASTER,
    INSURANCE_REGISTER: INSURANCE_REGISTER,
    EXTRA_INCOME_REGISTER: EXTRA_INCOME_REGISTER,
    DEALER_EARNINGS_REGISTER: DEALER_EARNINGS_REGISTER,
    OEM_EXTRA_SUPPORT_REGISTER: OEM_EXTRA_SUPPORT_REGISTER,
    CLAIM_EXCEPTION: CLAIM_EXCEPTION,
    PATCH_VERSION: PATCH_VERSION,
    VERSION: VERSION,
    SCHEMA_VERSION: SCHEMA_VERSION,
    MIGRATION_VERSION: MIGRATION_VERSION,
    APPS_SCRIPT_BUILD: APPS_SCRIPT_BUILD,
    MENU_HANDLERS: MENU_HANDLERS,
    PUBLIC_API: PUBLIC_API,
    AUDIT_LOG: AUDIT_LOG,
    HIDDEN_SHEETS: HIDDEN_SHEETS,
    DRILL_DOWN_SHEETS: DRILL_DOWN_SHEETS,
    SHEET_LAYOUT: SHEET_LAYOUT,
    LEAD: LEAD,
    ACTIVITY: ACTIVITY,
    PAYMENT: PAYMENT,
    DELIVERY: DELIVERY,
    MASTERS: MASTERS,
    SETTINGS_DEFAULTS: SETTINGS_DEFAULTS,
    COLORS: COLORS,
    MAX_ROWS: 100000
  };
})();
