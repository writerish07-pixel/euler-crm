"""Migrate Euler Master.xlsx (exported to euler_raw.json) into MongoDB collections."""
import json
import os
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "euler_raw.json"


def _rows(raw, sheet, header_idx):
    data = raw.get(sheet) or []
    if len(data) <= header_idx:
        return [], []
    header = [str(h).strip() if h is not None else "" for h in data[header_idx]]
    out = []
    for r in data[header_idx + 1:]:
        if not any(c not in (None, "", "None") for c in r):
            continue
        if str(r[0]).strip() in ("", "None"):
            continue
        d = {}
        for i, h in enumerate(header):
            if not h:
                continue
            v = r[i] if i < len(r) else None
            d[h] = v
        out.append(d)
    return header, out


def _n(v):
    try:
        if v in (None, "", "None"):
            return 0.0
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _s(v):
    if v in (None, "None"):
        return ""
    return str(v).strip()


def _date(v):
    if v in (None, "", "None"):
        return None
    s = str(v)
    return s.split("T")[0] if "T" in s else s


def _mobile(v):
    if v in (None, "", "None"):
        return ""
    try:
        return str(int(float(v)))
    except (ValueError, TypeError):
        return str(v).strip()


def build_leads(raw):
    _, rows = _rows(raw, "Lead Register", 2)
    out = []
    for d in rows:
        out.append({
            "leadId": _s(d.get("Lead ID")),
            "createdDate": _date(d.get("Created Date")),
            "customerName": _s(d.get("Customer Name")),
            "mobile": _mobile(d.get("Mobile")),
            "altMobile": _mobile(d.get("Alternate Mobile")),
            "village": _s(d.get("Village")),
            "city": _s(d.get("City")),
            "leadSource": _s(d.get("Lead Source")),
            "interestedModel": _s(d.get("Interested Model")),
            "variant": _s(d.get("Variant")),
            "executive": _s(d.get("Executive")),
            "currentStatus": _s(d.get("Current Status")) or "New",
            "priority": _s(d.get("Priority")) or "Normal",
            "budget": _n(d.get("Budget")),
            "nextFollowupDate": _date(d.get("Next Follow-up Date")),
            "nextFollowupTime": _s(d.get("Next Follow-up Time")),
            "bookingDate": _date(d.get("Booking Date")),
            "bookingAmount": _n(d.get("Booking Amount")),
            "financeRequired": _s(d.get("Finance Required")) or "No",
            "exchangeRequired": _s(d.get("Exchange Required")) or "No",
            "deliveryStatus": _s(d.get("Delivery Status")),
            "deliveryDate": _date(d.get("Delivery Date")),
            "outstandingAmount": _n(d.get("Outstanding Amount")),
            "remarks": _s(d.get("Remarks")),
            "lastUpdated": _s(d.get("Last Updated")),
            "lastUpdatedBy": _s(d.get("Last Updated By")),
            "accountStatus": _s(d.get("Account Status")) or "Active",
            "closedDate": _date(d.get("Closed Date")),
            "closeReason": _s(d.get("Close Reason")),
            "finalOutstanding": _n(d.get("Final Outstanding")),
            "exShowroom": _n(d.get("Ex Showroom")),
            "customerPayable": _n(d.get("Customer Payable")),
            "financerName": _s(d.get("Financer Name")),
            "financeFileNumber": _s(d.get("Finance File Number")),
            "lastPaymentMode": _s(d.get("Last Payment Mode")),
            "totalReceived": _n(d.get("Total Received")),
            "consumerDiscount": _n(d.get("Consumer Discount")),
            "exchangeBonus": _n(d.get("Exchange Bonus")),
            "loyaltyBonus": _n(d.get("Loyalty Bonus")),
            "referralBonus": _n(d.get("Referral Bonus")),
            "dsaDiscount": _n(d.get("DSA Bonus")),
            "additionalDiscount": _n(d.get("Additional Discount")),
            "totalDiscount": _n(d.get("Total Discount")),
            "oemSchemeAmount": _n(d.get("OEM Scheme Amount")),
            "dealerSchemeAmount": _n(d.get("Dealer Scheme Amount")),
            "customerOutstanding": _n(d.get("Customer Outstanding")),
            "companyOutstanding": _n(d.get("Company Outstanding")),
            "insurerName": _s(d.get("Insurer Name")),
            "invoiceNumber": _s(d.get("Invoice Number")),
            "numberPlate": _s(d.get("Number Plate")),
            "insuranceStatus": _s(d.get("Insurance Status")),
            "registrationStatus": _s(d.get("Registration Status")),
            "invoiceStatus": _s(d.get("Invoice Status")),
            "rcStatus": _s(d.get("RC Status")),
            "pdiStatus": _s(d.get("PDI Status")),
            "rto": _n(d.get("RTO")),
            "insuranceAmount": _n(d.get("Insurance Amount")),
            "accessoriesAmount": _n(d.get("Accessories Amount")),
            "handlingCharges": _n(d.get("Handling Charges")),
            "trc": _n(d.get("TRC")),
            "fastag": _n(d.get("Fastag")),
            "extendedWarranty": _n(d.get("Extended Warranty")),
            "otherCharges": _n(d.get("Other Charges")),
            "grossVehicleCost": _n(d.get("Gross Vehicle Cost")),
            "chassisNumber": _s(d.get("Chassis Number")),
        })
    return out


def build_price_master(raw):
    _, rows = _rows(raw, "PRICE MASTER", 0)
    out = []
    for i, d in enumerate(rows):
        out.append({
            "priceId": f"PM{i+1:04d}",
            "model": _s(d.get("Model")),
            "variant": _s(d.get("Variant")),
            "bodyType": _s(d.get("Body Type")),
            "exShowroom": _n(d.get("Ex Showroom Price")),
            "rto": _n(d.get("RTO")),
            "insurance": _n(d.get("Insurance")),
            "accessories": _n(d.get("Accessories")),
            "handlingCharges": _n(d.get("Handling Charges")),
            "trc": _n(d.get("TRC")),
            "fastag": _n(d.get("Fastag")),
            "extendedWarranty": _n(d.get("Extended Warranty")),
            "otherCharges": _n(d.get("Other Charges")),
            "gstPercent": _n(d.get("GST %")),
            "tcsApplicable": _s(d.get("TCS Applicable")) or "No",
            "effectiveFrom": _date(d.get("Effective From")),
            "priceVersion": _s(d.get("Price Version")),
            "status": _s(d.get("Status")) or "active",
            "remarks": _s(d.get("Remarks")),
        })
    return out


def build_payments(raw):
    _, rows = _rows(raw, "Payment Ledger", 0)
    out = []
    for d in rows:
        out.append({
            "receiptNumber": _s(d.get("Receipt Number")),
            "leadId": _s(d.get("Lead ID")),
            "customerName": _s(d.get("Customer Name")),
            "date": _date(d.get("Date")),
            "amount": _n(d.get("Amount")),
            "paymentMode": _s(d.get("Payment Mode")),
            "narration": _s(d.get("Narration")),
            "runningTotal": _n(d.get("Running Total")),
            "outstandingBalance": _n(d.get("Outstanding Balance")),
            "paymentId": _s(d.get("Payment ID")),
            "financerName": _s(d.get("Financer Name")),
            "financeFileNumber": _s(d.get("Finance File Number")),
        })
    return out


def build_bookings(raw):
    _, rows = _rows(raw, "Booking Register", 0)
    out = []
    for d in rows:
        out.append({
            "bookingId": _s(d.get("BookingID")),
            "leadId": _s(d.get("LeadID")),
            "customerName": _s(d.get("CustomerName")),
            "bookingDate": _date(d.get("Booking Date")),
            "model": _s(d.get("Vehicle Model")),
            "variant": _s(d.get("Variant")),
            "bookingAmount": _n(d.get("Booking Amount")),
            "amountReceived": _n(d.get("Amount Received")),
            "paymentMode": _s(d.get("Payment Mode")),
            "financeRequired": _s(d.get("Finance Required")),
            "exchangeRequired": _s(d.get("Exchange Required")),
            "snapshotId": _s(d.get("CommercialSnapshotID")),
            "bookingStatus": _s(d.get("Booking Status")) or "Booked",
            "createdBy": _s(d.get("Created By")),
            "createdDate": _date(d.get("Created Date")),
        })
    return out


def build_scheme_master(raw):
    _, rows = _rows(raw, "Scheme Master", 0)
    out = []
    for i, d in enumerate(rows):
        out.append({
            "schemeId": f"SCM{i+1:04d}",
            "schemeMonth": _date(d.get("Scheme Month")),
            "effectiveFrom": _date(d.get("Effective From")),
            "effectiveTo": _date(d.get("Effective To")),
            "circularRef": _s(d.get("Circular Ref")),
            "model": _s(d.get("Model")),
            "variant": _s(d.get("Variant")),
            "component": _s(d.get("Component")),
            "componentKey": _s(d.get("Component Key")),
            "dealerShare": _n(d.get("Dealer Share")),
            "companyShare": _n(d.get("Company Share")),
            "totalBenefit": _n(d.get("Total Benefit")),
            "status": _s(d.get("Status")) or "Active",
            "notes": _s(d.get("Notes")),
        })
    return out


def build_incentive_master(raw):
    _, rows = _rows(raw, "Incentive Master", 0)
    out = []
    for i, d in enumerate(rows):
        out.append({
            "incentiveId": f"INM{i+1:04d}",
            "schemeMonth": _date(d.get("Scheme Month")),
            "effectiveFrom": _date(d.get("Effective From")),
            "effectiveTo": _date(d.get("Effective To")),
            "circularRef": _s(d.get("Circular Ref")),
            "productCategory": _s(d.get("Product Category")),
            "incentivePerRetail": _n(d.get("Incentive Per Retail")),
            "minRetails": _n(d.get("Min Retails")),
            "maxSlab": _n(d.get("Max Slab")),
            "status": _s(d.get("Status")) or "Active",
            "notes": _s(d.get("Notes")),
        })
    return out


def build_activities(raw):
    _, rows = _rows(raw, "Activity Log", 0)
    out = []
    for d in rows:
        out.append({
            "activityId": _s(d.get("Activity ID")),
            "leadId": _s(d.get("Lead ID")),
            "date": _date(d.get("Date")),
            "time": _s(d.get("Time")),
            "activityType": _s(d.get("Activity Type")),
            "discussion": _s(d.get("Discussion")),
            "nextFollowup": _s(d.get("Next Follow-up")),
            "executive": _s(d.get("Executive")),
            "customerName": _s(d.get("Customer Name")),
            "mobile": _mobile(d.get("Mobile")),
            "model": _s(d.get("Model")),
        })
    return out


def build_deliveries(raw):
    _, rows = _rows(raw, "Delivery Tracker", 0)
    out = []
    for d in rows:
        out.append({
            "leadId": _s(d.get("Lead ID")),
            "customerName": _s(d.get("Customer Name")),
            "insurance": _s(d.get("Insurance")),
            "registration": _s(d.get("Registration")),
            "invoice": _s(d.get("Invoice")),
            "accessories": _s(d.get("Accessories")),
            "rc": _s(d.get("RC")),
            "numberPlate": _s(d.get("Number Plate")),
            "pdi": _s(d.get("PDI")),
            "delivered": _s(d.get("Delivered")),
            "deliveryDate": _date(d.get("Delivery Date")),
            "feedback": _s(d.get("Feedback")),
            "deliveryId": _s(d.get("Delivery ID")),
            "insurerName": _s(d.get("Insurer Name")),
            "invoiceNumber": _s(d.get("Invoice Number")),
            "chassisNumber": _s(d.get("Chassis Number")),
        })
    return out


def build_insurance(raw):
    _, rows = _rows(raw, "Insurance Register", 0)
    out = []
    for d in rows:
        out.append({
            "entryId": _s(d.get("Entry ID")),
            "leadId": _s(d.get("Lead ID")),
            "customerName": _s(d.get("Customer Name")),
            "mobile": _mobile(d.get("Mobile")),
            "model": _s(d.get("Model")),
            "variant": _s(d.get("Variant")),
            "insuranceCompany": _s(d.get("Insurance Company")),
            "policyNumber": _s(d.get("Policy Number")),
            "insuranceAmount": _n(d.get("Insurance Amount")),
            "payoutRate": _n(d.get("Payout Rate %")),
            "expectedPayout": _n(d.get("Expected Payout")),
            "receivedPayout": _n(d.get("Received Payout")),
            "payoutOutstanding": _n(d.get("Payout Outstanding")),
            "status": _s(d.get("Status")),
            "policyDate": _date(d.get("Policy Date")),
            "deliveryDate": _date(d.get("Delivery Date")),
            "insuranceExecutive": _s(d.get("Insurance Executive")),
            "remarks": _s(d.get("Remarks")),
        })
    return out


def build_finance(raw):
    _, rows = _rows(raw, "Finance Register", 0)
    out = []
    for d in rows:
        out.append({
            "fileNumber": _s(d.get("File Number")),
            "leadId": _s(d.get("Lead ID")),
            "customerName": _s(d.get("Customer Name")),
            "financer": _s(d.get("Financer")),
            "sanctionedAmount": _n(d.get("Sanctioned Amount")),
            "receivedAgainstFile": _n(d.get("Received Against File")),
            "fileOutstanding": _n(d.get("File Outstanding")),
            "status": _s(d.get("Status")),
            "lastPaymentDate": _date(d.get("Last Payment Date")),
        })
    return out


def build_dealer_earnings(raw):
    _, rows = _rows(raw, "Dealer Earnings Register", 0)
    out = []
    for d in rows:
        out.append({
            "leadId": _s(d.get("Lead ID")),
            "bookingId": _s(d.get("Booking ID")),
            "customerName": _s(d.get("Customer Name")),
            "executive": _s(d.get("Executive")),
            "leadSource": _s(d.get("Lead Source")),
            "model": _s(d.get("Vehicle Model")),
            "variant": _s(d.get("Variant")),
            "currentStage": _s(d.get("Current Stage")),
            "bookingDate": _date(d.get("Booking Date")),
            "deliveryDate": _date(d.get("Delivery Date")),
            "customerPayable": _n(d.get("Customer Payable")),
            "oemEligibleScheme": _n(d.get("OEM Eligible Scheme")),
            "customerSchemeBenefitPassed": _n(d.get("Customer Scheme Benefit Passed")),
            "dealerSchemeRetained": _n(d.get("Dealer Scheme Retained")),
            "insurancePayout": _n(d.get("Insurance Payout")),
            "dealerInsuranceIncome": _n(d.get("Dealer Insurance Income")),
            "financeIncentive": _n(d.get("Finance Incentive")),
            "accessoriesMargin": _n(d.get("Accessories Margin")),
            "exchangeMargin": _n(d.get("Exchange Margin")),
            "otherIncome": _n(d.get("Other Income")),
            "totalDealerEarnings": _n(d.get("TOTAL DEALER EARNINGS")),
            "dealerMarginGrossInclGst": _n(d.get("Dealer Margin Gross (Incl GST)")),
            "dealerMarginGst": _n(d.get("Dealer Margin GST (5%)")),
            "dealerMarginNetExGst": _n(d.get("Dealer Margin Net (Ex GST)")),
            "oemExtraSupportReceived": _n(d.get("OEM Extra Support Received")),
            "oemExtraSupportRetained": _n(d.get("OEM Extra Support Retained")),
            "claimStatus": _s(d.get("Claim Status")),
            "insuranceStatus": _s(d.get("Insurance Status")),
        })
    return out


# Sample transaction collections that must NOT be re-seeded after a go-live reset
SAMPLE_TX = {"leads", "payments", "bookings", "activities", "deliveries",
             "insurance", "finance", "dealer_earnings"}
BUILDERS = {
    "leads": build_leads,
    "price_master": build_price_master,
    "payments": build_payments,
    "bookings": build_bookings,
    "scheme_master": build_scheme_master,
    "incentive_master": build_incentive_master,
    "activities": build_activities,
    "deliveries": build_deliveries,
    "insurance": build_insurance,
    "finance": build_finance,
    "dealer_earnings": build_dealer_earnings,
}


async def run_seed(db, force=False):
    if not DATA_FILE.exists():
        return {"seeded": False, "reason": "data file missing"}
    raw = json.loads(DATA_FILE.read_text())
    result = {}
    state = await db["system"].find_one({"_id": "seed_state"}) or {}
    sample_cleared = bool(state.get("sampleCleared"))
    for coll, builder in BUILDERS.items():
        # After a go-live reset, never re-seed the sample transaction data (masters still seed)
        if sample_cleared and coll in SAMPLE_TX and not force:
            result[coll] = "skipped (sample cleared for go-live)"
            continue
        existing = await db[coll].count_documents({})
        if existing > 0 and not force:
            result[coll] = f"skipped ({existing} existing)"
            continue
        if force:
            await db[coll].delete_many({})
        docs = builder(raw)
        if docs:
            await db[coll].insert_many(docs)
        result[coll] = len(docs)
    # counters for ID generation
    if force or await db["counters"].count_documents({}) == 0:
        await db["counters"].delete_many({})
        leads = build_leads(raw)
        max_lead = 0
        for l in leads:
            try:
                max_lead = max(max_lead, int(l["leadId"].replace("LD26", "")))
            except (ValueError, AttributeError):
                pass
        await db["counters"].insert_many([
            {"_id": "lead", "seq": max(max_lead, len(leads))},
            {"_id": "receipt", "seq": 100},
            {"_id": "booking", "seq": 100},
            {"_id": "activity", "seq": 100},
            {"_id": "snapshot", "seq": 100},
            {"_id": "claim", "seq": 100},
            {"_id": "finance", "seq": 100},
            {"_id": "insurance", "seq": 100},
        ])
    return {"seeded": True, "result": result}


MASTERS = {
    "leadSources": ["Walk-in", "WhatsApp", "Referral", "Website", "Phone", "Social Media", "Visit"],
    "statuses": ["New", "Contacted", "Follow-up", "In Progress", "Booked", "Finance Process", "Delivered", "Lost"],
    "accountStatuses": ["Active", "Closed", "Cancelled", "Archived"],
    "executives": ["Lokesh", "Sanjay", "Amit", "Dharmendra", "Prasun", "Harish Bhatnagar"],
    "paymentModes": ["Cash", "UPI", "Cheque", "NEFT", "Finance", "Card"],
    "financers": ["SUNDARAM", "SHRIRAM", "HDFC BANK", "IDFC BANK", "RAJPUTANA", "UNION BANK", "CASH"],
    "priorities": ["Low", "Normal", "High", "Urgent"],
    "activityTypes": ["Call", "WhatsApp", "Visit", "Follow-up", "Booking", "Delivery", "Note"],
    "benefitModes": ["Full Benefit", "Partial Benefit", "No Benefit"],
    "claimStatuses": ["Pending", "Submitted", "Approved", "Rejected", "Received", "Not Applicable"],
}
