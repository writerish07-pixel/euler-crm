"""Backend tests for Euler EV-Dealership CRM."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # try frontend .env
    from pathlib import Path
    envf = Path("/app/frontend/.env")
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break

assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# ----------------------------------------------------- basic health
def test_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ----------------------------------------------------- dashboard
def test_dashboard(s):
    r = s.get(f"{API}/dashboard")
    assert r.status_code == 200
    d = r.json()
    assert "kpis" in d and "payments" in d and "outstanding" in d and "modelPerformance" in d
    kpis = d["kpis"]
    assert kpis["totalLeads"] == 10
    assert kpis["activeBookings"] == 3
    assert "conversion" in kpis
    # payments modes present
    for k in ("Cash", "UPI", "Finance", "Other"):
        assert k in d["payments"]
    assert isinstance(d["modelPerformance"], list) and len(d["modelPerformance"]) >= 1


# ----------------------------------------------------- leads listing
def test_leads_list(s):
    r = s.get(f"{API}/leads")
    assert r.status_code == 200
    leads = r.json()
    assert len(leads) == 10
    ids = {l["leadId"] for l in leads}
    for i in range(1, 11):
        assert f"LD2600000{i}" in ids or f"LD260000{i:02d}" in ids


def test_leads_status_filter(s):
    r = s.get(f"{API}/leads", params={"status": "New"})
    assert r.status_code == 200
    for l in r.json():
        assert l.get("currentStatus") == "New"


def test_leads_search(s):
    all_leads = s.get(f"{API}/leads").json()
    name_snip = all_leads[0]["customerName"].split()[0][:3]
    r = s.get(f"{API}/leads", params={"q": name_snip})
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ----------------------------------------------------- 360
def test_lead_360(s):
    r = s.get(f"{API}/leads/LD26000001/360")
    assert r.status_code == 200
    d = r.json()
    for k in ("lead", "commercials", "payments", "activities"):
        assert k in d
    assert d["lead"]["leadId"] == "LD26000001"
    assert "customerPayable" in d["commercials"]


# ----------------------------------------------------- masters / registers
@pytest.mark.parametrize("path,expected_min", [
    ("/price-master", 69),
    ("/scheme-master", 33),
    ("/incentive-master", 1),
    ("/bookings", 3),
    ("/payments", 1),
    ("/finance", 0),
    ("/insurance", 0),
    ("/deliveries", 0),
    ("/activities", 1),
    ("/claims", 0),
    ("/quotations", 0),
])
def test_registers(s, path, expected_min):
    r = s.get(f"{API}{path}")
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    body = r.json()
    if isinstance(body, list):
        assert len(body) >= expected_min, f"{path}: got {len(body)} expected>={expected_min}"


def test_dealer_earnings(s):
    r = s.get(f"{API}/dealer-earnings")
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d and "total" in d


def test_masters_endpoint(s):
    r = s.get(f"{API}/masters")
    assert r.status_code == 200
    d = r.json()
    assert "models" in d and isinstance(d["models"], list)


def test_price_variants_turbo_max(s):
    r = s.get(f"{API}/price-master/variants", params={"model": "Turbo Max"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1


# ----------------------------------------------------- workflows: create lead
def test_create_lead(s):
    payload = {"customerName": "TEST_Auto Lead", "mobile": "9999900001",
               "interestedModel": "Turbo Max", "variant": "Standard", "executive": "TEST_Exec"}
    r = s.post(f"{API}/leads", json=payload)
    assert r.status_code == 200
    lead = r.json()
    assert lead["leadId"].startswith("LD26")
    assert lead["customerName"] == "TEST_Auto Lead"
    # verify persisted
    got = s.get(f"{API}/leads/{lead['leadId']}").json()
    assert got["leadId"] == lead["leadId"]
    # creation activity logged
    acts = s.get(f"{API}/activities", params={"lead_id": lead["leadId"]}).json()
    assert any("created" in (a.get("discussion") or "").lower() for a in acts)


# ----------------------------------------------------- workflows: full journey on a fresh lead
@pytest.fixture(scope="module")
def journey_lead():
    r = requests.post(f"{API}/leads", json={
        "customerName": "TEST_Journey", "mobile": "9999900002",
        "interestedModel": "Turbo Max", "variant": "Standard",
        "executive": "TEST_Exec", "currentStatus": "New",
    })
    assert r.status_code == 200
    return r.json()["leadId"]


def test_journey_convert_booking(journey_lead):
    r = requests.post(f"{API}/leads/{journey_lead}/convert-booking",
                      json={"bookingAmount": 5000, "executive": "TEST_Exec", "paymentMode": "Cash"})
    assert r.status_code == 200
    d = r.json()
    assert d["lead"]["currentStatus"] == "Booked"
    # payment auto-created
    pays = requests.get(f"{API}/payments", params={"lead_id": journey_lead}).json()
    assert any(p["amount"] == 5000 for p in pays)


def test_journey_price_structure(journey_lead):
    r = requests.put(f"{API}/leads/{journey_lead}/price-structure", json={
        "exShowroom": 100000, "rto": 5000, "insuranceAmount": 4000,
        "accessoriesAmount": 2000, "handlingCharges": 1000, "trc": 500,
        "fastag": 500, "extendedWarranty": 1000, "otherCharges": 0,
        "tcsApplicable": "No", "finalExchangeValue": 0,
    })
    assert r.status_code == 200
    lead = r.json()
    expected_gross = 100000 + 5000 + 4000 + 2000 + 1000 + 500 + 500 + 1000
    assert abs(lead["grossVehicleCost"] - expected_gross) < 0.01
    # customerPayable = gross - already received (5000 booking) accounted in outstanding, not payable
    assert abs(lead["customerPayable"] - expected_gross) < 0.01
    assert abs(lead["customerOutstanding"] - (expected_gross - 5000)) < 0.01


def test_journey_scheme(journey_lead):
    r = requests.put(f"{API}/leads/{journey_lead}/scheme", json={
        "consumerDiscount": 3000, "exchangeBonus": 1000, "loyaltyBonus": 0,
        "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 500,
        "benefitMode": "Full Benefit",
    })
    assert r.status_code == 200
    lead = r.json()
    # OEM eligible = consumer+exchange+loyalty+referral+dsa (4000). Dealer = additional (500)
    assert abs(lead["oemSchemeAmount"] - 4000) < 0.01
    assert abs(lead["dealerSchemeAmount"] - 500) < 0.01
    # companyOutstanding = claimEligible = 4000 (no approval required for consumer/exchange)
    assert abs(lead["companyOutstanding"] - 4000) < 0.01


def test_journey_payment_finance(journey_lead):
    r = requests.post(f"{API}/leads/{journey_lead}/payments", json={
        "amount": 20000, "paymentMode": "Finance",
        "financerName": "HDFC", "financeFileNumber": f"FN-{journey_lead}",
    })
    assert r.status_code == 200
    # finance file created
    fin = requests.get(f"{API}/finance").json()
    assert any(f["fileNumber"] == f"FN-{journey_lead}" for f in fin)


def test_journey_delivery(journey_lead):
    r = requests.put(f"{API}/leads/{journey_lead}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "accessories": "Yes", "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "invoiceNumber": "INV-TEST-1", "chassisNumber": "CHS1", "numberPlate": "TEST01",
    })
    assert r.status_code == 200
    lead = r.json()
    assert lead["currentStatus"] == "Delivered"
    assert lead["deliveryStatus"] == "Delivered"


def test_journey_close(journey_lead):
    r = requests.post(f"{API}/leads/{journey_lead}/close", json={"closeReason": "TEST completed"})
    assert r.status_code == 200
    assert r.json()["accountStatus"] == "Closed"


# ----------------------------------------------------- commercial compute
def test_commercial_compute(s):
    body = {
        "exShowroom": 100000, "accessories": 2000, "insurance": 4000,
        "registrationRto": 5000, "fastag": 500, "handlingCharges": 1000,
        "trc": 500, "extendedWarranty": 1000, "otherCharges": 0,
        "tcsApplicable": "No", "consumerDiscount": 3000, "exchangeBonus": 1000,
        "additionalDiscount": 500, "benefitMode": "Full Benefit", "finalExchangeValue": 0,
    }
    r = s.post(f"{API}/commercial/compute", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["grossVehicleCost"] == 114000
    assert d["totalDiscount"] == 4500  # 3000+1000+500
    # customerPayable = 114000 - (3000+1000+500 full benefit) = 109500
    assert d["customerPayable"] == 109500
    assert d["claim"]["claimEligible"] == 4000  # only OEM claimable
    assert "margin" in d


# ----------------------------------------------------- quotation
def test_quotation_create(s):
    r = s.post(f"{API}/quotations", json={
        "customerName": "TEST_Quote", "mobile": "9999900003",
        "model": "Turbo Max", "variant": "Standard",
        "exShowroom": 100000, "insurance": 4000, "registrationRto": 5000,
        "consumerDiscount": 2000, "benefitMode": "Full Benefit",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["quoteId"].startswith("QT26")
    assert d["customerPayable"] == 100000 + 4000 + 5000 - 2000


# ----------------------------------------------------- claim settle
def test_claim_settle(s):
    # First find any existing claim
    claims = s.get(f"{API}/claims").json()
    if not claims:
        pytest.skip("No claims derived (leads may have no discounts)")
    c = claims[0]
    r = s.post(f"{API}/claims/settle", json={
        "leadId": c["leadId"], "componentKey": c["componentKey"],
        "claimStatus": "Received", "receivedAmount": c["claimAmount"],
        "claimReference": "TEST-REF",
    })
    assert r.status_code == 200
    assert r.json().get("ok") is True
