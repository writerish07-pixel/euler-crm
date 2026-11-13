"""Workshop desk: a mail joins a Coulson request, and a missing paid part
becomes an advance instead of a second purchase."""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coulson as coulson_client  # noqa: E402
import workshop_desk as desk  # noqa: E402


DISPATCH = (
    "Dispatch update for ticket 10412.\n"
    "The following items are not dispatched, as they are not available:\n"
    "CD4C001800, WH AC charging gun — 10 nos.\n"
    "Payment was received in full.\n"
    "₹18,400 is parked as advance."
)
SPLIT = (
    "Ticket 10526.\n"
    "Dispatched: AA28000800 front shock absorber bush, 5 nos.\n"
    "Dispatched: AN59000100 latch assembly, 5 nos.\n"
    "Not dispatched: AAS20004 lined shoe kit, 2 nos.\n"
    "Not dispatched: AH4C001200 charging gun harness, 2 nos.\n"
    "Advance for the items not dispatched: ₹4,200."
)


def test_dispatch_mail_names_the_request_and_the_missing_part():
    parsed = desk.parse_mail("Re: Ticket 10412 — dispatch update", DISPATCH)
    assert parsed["request_nos"] == ["10412"]
    assert parsed["missing_codes"] == ["CD4C001800"]
    assert parsed["advance"] == 18400
    assert parsed["kind"] == "dispatch"
    assert parsed["qty"]["CD4C001800"] == 10


def test_one_mail_can_send_some_parts_and_hold_others():
    parsed = desk.parse_mail("Re: Ticket 10526 — dispatch", SPLIT)
    assert parsed["request_nos"] == ["10526"]
    assert parsed["sent_codes"] == ["AA28000800", "AN59000100"]
    assert parsed["missing_codes"] == ["AAS20004", "AH4C001200"]
    assert parsed["advance"] == 4200


def test_a_mail_that_names_two_tickets_is_not_joined():
    body = (
        "Ticket 10412 and ticket 10526.\n"
        "Not dispatched: CD4C001800, 10 nos.\n"
        "₹18,400 is parked as advance."
    )
    parsed = desk.parse_mail("Re: two tickets", body)
    assert parsed["request_nos"] == ["10412", "10526"]
    assert parsed["kind"] == "unmatched"
    state, mail_id = desk.add_mail(desk.empty_state(), "Re: two tickets", body)
    state = desk.read_mail(state, mail_id)
    assert state["lines"] == []
    assert state["advances"] == {}
    mail = state["mails"][0]
    assert mail["status"] == "unmatched"
    assert mail["requestNo"] == ""
    assert "10412" in mail["result"] and "10526" in mail["result"]


def test_this_morning_only_fills_an_empty_desk():
    assert desk.desk_has_work(desk.empty_state()) is False
    assert desk.desk_has_work(desk.sample_state()) is True


def test_a_mail_with_no_ticket_is_left_for_a_person():
    parsed = desk.parse_mail("Bank account update", "Please update the bank mandate form.")
    assert parsed["kind"] == "unmatched"
    assert parsed["request_nos"] == []
    parsed = desk.parse_mail(
        "Dispatch",
        "The following items are not dispatched:\nCD4C001800 — 10 nos.\n₹18,400 is parked as advance.",
    )
    assert parsed["kind"] == "unmatched"
    assert parsed["missing_codes"] == ["CD4C001800"]


def test_reading_the_dispatch_parks_the_advance_and_puts_the_part_back():
    state = desk.sample_state()
    gun = next(line for line in state["lines"] if line["code"] == "CD4C001800")
    assert gun["stage"] == "paid"
    state = desk.read_mail(state, "dispatch")
    gun = next(line for line in state["lines"] if line["code"] == "CD4C001800")
    assert gun["stage"] == "short"
    assert state["advances"]["10412"] == 18400
    assert gun["advance"] == 18400
    # Reading the same mail again does not double the advance.
    state = desk.read_mail(state, "dispatch")
    assert state["advances"]["10412"] == 18400


def test_follow_up_uses_the_advance_and_the_box_clears_it():
    state = desk.read_mail(desk.sample_state(), "dispatch")
    gun = next(line for line in state["lines"] if line["code"] == "CD4C001800")
    state = desk.approve_reorder(state, gun["id"])
    gun = next(line for line in state["lines"] if line["code"] == "CD4C001800")
    assert gun["stage"] == "reorder"
    sent = state["mails"][-1]
    assert sent["requestNo"] == "10412"
    assert "Do not raise a new proforma invoice." in sent["body"]
    assert "18,400" in sent["body"]
    state = desk.receive_line(state, gun["id"])
    gun = next(line for line in state["lines"] if line["code"] == "CD4C001800")
    assert gun["stage"] == "received"
    assert "10412" not in state["advances"]
    assert gun["advance"] == 0


def test_10526_advance_stays_until_both_missing_lines_are_in():
    state = desk.sample_state()
    shoe = next(line for line in state["lines"] if line["code"] == "AAS20004")
    harness = next(line for line in state["lines"] if line["code"] == "AH4C001200")
    state = desk.receive_line(state, shoe["id"])
    assert state["advances"]["10526"] == 4200
    harness = next(line for line in state["lines"] if line["code"] == "AH4C001200")
    assert harness["advance"] == 4200
    state = desk.receive_line(state, harness["id"])
    assert "10526" not in state["advances"]


def test_filing_a_stray_mail_does_not_move_money():
    state = desk.sample_state()
    before = desk.advance_rows(state)
    state = desk.file_mail(state, "bank", "10412")
    bank = next(mail for mail in state["mails"] if mail["id"] == "bank")
    assert bank["status"] == "note"
    assert bank["requestNo"] == "10412"
    assert desk.advance_rows(state) == before


def test_today_starts_with_the_unread_dispatch():
    today = desk.build_today(desk.sample_state())
    assert any(item.get("mailId") == "dispatch" for item in today)
    assert any("Gearbox oil" in item["title"] for item in today)
    assert any("35 vehicles" in item["title"] for item in today)


def test_coulson_order_rows_and_open_requests_become_lines():
    snapshot = desk.snapshot_from_coulson(
        store_rows=[{
            "part_code": "AH47001300",
            "part_name": "3.3 kW onboard charger",
            "replenishment_trigger": "Order",
            "final_dispatch_qty": 1.08,
        }, {
            "part_code": "AA5L000300",
            "part_name": "Gearbox oil SAE80W90",
            "replenishment_trigger": "Order",
            "final_dispatch_qty": 123648,
        }, {
            "part_code": "KEEP",
            "part_name": "Steady part",
            "replenishment_trigger": "Do Not Order",
            "final_dispatch_qty": 0,
        }],
        stale_rows=[{
            "request_public_id": 10412,
            "part_code": "CD4C001800",
            "part_name": "WH AC charging gun",
            "outstanding_qty": 10,
            "status_name": "Assigned To SPD",
        }],
        claim_rows=[{"claim_number": 14315, "claim_total_amount": 5337.82, "claim_status": "SPD Pickup Requested"}],
        claim_analytics={"total_claims": 18, "status_breakdown": {"SPD Pickup Requested": 12, "Approved": 4, "Approval Required": 2}},
        due_rows=[{"service_status": "Overdue"}, {"service_status": "Due Soon"}],
        complaint_rows=[{"status": "Under Resolution"}, {"status": "Closed"}],
        ticket_rows=[{"ticket_id": 279680, "status": "Service In Progress", "has_pna": True, "service_ticket_type": "Corrective Maintenance"}],
    )
    codes = {line["code"]: line for line in snapshot["lines"]}
    assert codes["AH47001300"]["stage"] == "need"
    assert codes["AH47001300"]["qty"] == 1
    assert codes["AA5L000300"]["overCap"] is True
    assert "KEEP" not in codes
    assert codes["CD4C001800"]["requestNo"] == "10412"
    assert codes["CD4C001800"]["stage"] == "asked"
    assert snapshot["warranty"]["total"] == 18
    assert snapshot["jobs"]["overdue"] == 1
    assert snapshot["jobs"]["openTickets"][0]["ticketId"] == 279680


def test_a_later_sync_does_not_wipe_a_part_already_marked_missing():
    state = desk.read_mail(desk.sample_state(), "dispatch")
    snapshot = desk.snapshot_from_coulson(
        store_rows=[],
        stale_rows=[{
            "request_public_id": 10412,
            "part_code": "CD4C001800",
            "part_name": "WH AC charging gun",
            "outstanding_qty": 10,
            "status_name": "Assigned To SPD",
        }],
        claim_rows=[],
        claim_analytics={},
        due_rows=[],
        complaint_rows=[],
        ticket_rows=[],
    )
    merged = desk.merge_snapshot(state, snapshot)
    gun = next(line for line in merged["lines"] if line["code"] == "CD4C001800")
    assert gun["stage"] == "short"
    assert merged["advances"]["10412"] == 18400


def test_service_login_sends_the_password_hash_the_portal_expects(monkeypatch):
    seen = {}

    def fake_login(username, password):
        seen["username"] = username
        seen["password"] = password
        return "token"

    monkeypatch.setattr(coulson_client, "login", fake_login)
    assert coulson_client.login_service("Rishabh.Akar", "secret") == "token"
    assert seen["username"] == "Rishabh.Akar"
    assert seen["password"] == hashlib.sha256(b"secret").hexdigest()
    assert seen["password"] != "secret"


def test_pasted_mail_stays_unread_until_someone_reads_it():
    state, mail_id = desk.add_mail(desk.empty_state(), "Re: Ticket 10412", DISPATCH)
    mail = next(item for item in state["mails"] if item["id"] == mail_id)
    assert mail["applied"] is False
    assert mail["requestNo"] == "10412"
    state = desk.read_mail(state, mail_id)
    assert len(state["lines"]) == 1
    assert state["lines"][0]["stage"] == "short"
    assert state["advances"]["10412"] == 18400
