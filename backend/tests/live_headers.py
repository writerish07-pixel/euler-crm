"""Header rows captured from the LIVE Euler Master workbook (read-only pull).

Column NAMES only. Lead Register is a normal register: header in row 1 starting at
column A (same shape as Booking / Claims / Dealer Earnings). Regenerate only from a
live read-only pull.
"""
LIVE_HEADERS = {
    'Lead Register': (
        1,
        ['Lead ID', 'Created Date', 'Customer Name', 'Mobile', 'Alternate Mobile', 'Village', 'City', 'Lead Source', 'Interested Model', 'Variant', 'Executive', 'Current Status', 'Priority', 'Budget', 'Last Activity', 'Next Follow-up Date', 'Next Follow-up Time', 'Booking Date', 'Booking Amount', 'Finance Required', 'Exchange Required', 'Delivery Status', 'Delivery Date', 'Outstanding Amount', 'Remarks', 'Last Updated', 'Last Updated By', 'Account Status', 'Closed Date', 'Close Reason', 'Final Outstanding', 'Closed By', 'Close Timestamp', 'Ex Showroom', 'RTO', 'Insurance Amount', 'Accessories Amount', 'Handling Charges', 'TRC', 'Fastag', 'Extended Warranty', 'Other Charges', 'Gross Vehicle Cost', 'Customer Payable', 'Financer Name', 'Finance File Number', 'Last Payment Mode', 'Total Received', 'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Insurance Benefit', 'Referral Bonus', 'DSA Bonus', 'Additional Discount', 'Total Discount', 'OEM Scheme Amount', 'Dealer Scheme Amount', 'Customer Outstanding', 'Company Outstanding', 'Insurer Name', 'Invoice Number', 'Chassis Number', 'Number Plate', 'Insurance Status', 'Registration Status', 'Invoice Status', 'RC Status', 'PDI Status', 'OEM Extra Support Received', 'OEM Extra Support Passed To Customer', 'OEM Extra Support Retained', 'Dealer Earnings'],
    ),
    'Activity Log': (
        1,
        ['Activity ID', 'Lead ID', 'Date', 'Time', 'Activity Type', 'Discussion', 'Next Follow-up', 'Reminder', 'Executive', 'Customer Name', 'Mobile', 'Model'],
    ),
    'Booking Register': (
        1,
        ['BookingID', 'LeadID', 'CustomerName', 'Booking Date', 'Vehicle Model', 'Variant', 'Booking Amount', 'Finance Required', 'Exchange Required', 'CommercialSnapshotID', 'Booking Status', 'Created By', 'Created Date', 'Last Updated', 'Amount Received', 'Payment Mode', 'Dealer Earnings'],
    ),
    'Payment Ledger': (
        1,
        ['Receipt Number', 'Lead ID', 'Customer Name', 'Date', 'Amount', 'Payment Mode', 'Narration', 'Running Total', 'Outstanding Balance', 'Payment ID', 'Financer Name', 'Finance File Number'],
    ),
    'Delivery Tracker': (
        1,
        ['Lead ID', 'Customer Name', 'Insurance', 'Registration', 'Invoice', 'Accessories', 'RC', 'Number Plate', 'PDI', 'Delivered', 'Delivery Date', 'Feedback', 'Delivery ID', 'Insurer Name', 'Invoice Number', 'Dealer Earnings', 'Chassis Number'],
    ),
    'Scheme Claim Register': (
        1,
        ['Claim ID', 'Source', 'Booking ID', 'Lead ID', 'Customer', 'Model', 'Variant', 'Booking Date', 'Scheme Month', 'Executive', 'Component', 'Component Key', 'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Insurance Benefit', 'Referral Bonus', 'DSA Discount', 'Additional Discount', 'RTO Benefit', 'RTO Insurance Benefit', 'Total Discount', 'Dealer Discount', 'OEM Discount', 'DSA Approval', 'Claim Required', 'Eligible Claim', 'Claim Amount', 'Received Amount', 'Claim Status', 'Claim Reference Number', 'Claim Submitted Date', 'Claim Approved Date', 'Claim Received Date', 'Claim Ageing (Days)', 'Claim Remarks'],
    ),
    'Insurance Register': (
        1,
        ['Entry ID', 'Lead ID', 'Customer Name', 'Mobile', 'Model', 'Variant', 'Insurance Company', 'Policy Number', 'Insurance Amount', 'Payout Rate %', 'Expected Payout', 'Received Payout', 'Payout Outstanding', 'Status', 'Policy Date', 'Delivery Date', 'Last Updated', 'Remarks', 'Insurance Executive'],
    ),
    'Finance Register': (
        1,
        ['File Number', 'Lead ID', 'Customer Name', 'Financer', 'Sanctioned Amount', 'Received Against File', 'File Outstanding', 'Status', 'Last Payment Date', 'Last Updated'],
    ),
    'Dealer Earnings Register': (
        1,
        ['Lead ID', 'Booking ID', 'Customer Name', 'Executive', 'Team Leader', 'Lead Source', 'Vehicle Model', 'Variant', 'Colour', 'Current Stage', 'Booking Date', 'Delivery Date', 'Invoice Number', 'Customer Payable', 'OEM Eligible Scheme', 'Customer Scheme Benefit Passed', 'Dealer Scheme Retained', 'Insurance Payout', 'Customer Insurance Benefit Passed', 'Dealer Insurance Income', 'Finance Incentive', 'Accessories Margin', 'Exchange Margin', 'Documentation Income', 'Warranty Income', 'RSA Income', 'Referral Income', 'Campaign Incentive', 'Other Income', 'Claim Status', 'Insurance Status', 'Last Updated', 'Created By', 'Modified By', 'Timestamp', 'Remarks', 'Consumer Retained', 'Exchange Retained', 'Loyalty Retained', 'Referral Retained', 'DSA Retained', 'Scheme Retained Breakup', 'Dealer Margin Gross (Incl GST)', 'Dealer Margin GST (5%)', 'Dealer Margin Net (Ex GST)', 'OEM Extra Support Received', 'OEM Extra Support Passed To Customer', 'OEM Extra Support Retained', 'TOTAL DEALER EARNINGS'],
    ),
    'OEM Extra Support Register': (
        1,
        ['Lead ID', 'Booking ID', 'Customer Name', 'Vehicle Model', 'Variant', 'Booking Date',
         'OEM Extra Support Received', 'OEM Extra Support Passed To Customer',
         'OEM Extra Support Retained', 'Status', 'Last Updated', 'Remarks'],
    ),
    'Incentive Register': (
        1,
        ['Incentive ID', 'Scheme Month', 'Executive', 'Lead ID', 'Booking ID', 'Model', 'Variant',
         'Product Category', 'Delivery Date', 'Incentive Amount', 'Status', 'Paid Date',
         'Remarks', 'Last Updated'],
    ),
}
