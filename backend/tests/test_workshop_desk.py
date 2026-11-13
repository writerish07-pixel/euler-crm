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


def test_owner_sees_service_and_a_store_person_sees_only_their_grant():
    owner = desk.resolve_access({"role": "owner", "name": "Akar"}, [])
    assert owner["owner"] is True
    assert "users" in owner["areas"]
    assert "gmail" in owner["areas"]
    store = desk.resolve_access(
        {"role": "executive", "name": "Ravi", "userId": "u-ravi"},
        [{"userId": "u-ravi", "staffId": "ST1", "name": "Ravi", "areas": ["today", "buy", "jobs", "users"]}],
    )
    assert store["owner"] is False
    assert store["areas"] == ["today", "buy", "jobs"]
    assert desk.preset_for_role("accounts") == ["today", "money", "payments"]
    view = desk.public_view(desk.sample_state(), None, store)
    assert view["mails"] == []
    assert view["proofs"] == []
    assert any(line["code"] == "CD4C001800" for line in view["lines"])


def test_payment_proof_stays_on_its_ticket_and_prepares_the_reply():
    state = desk.sample_state()
    state["mails"][0]["gmailThreadId"] = "thread-10412"
    state["mails"][0]["replyTo"] = "parts@example.com"
    state["mails"][0]["rfcMessageId"] = "<m@example.com>"
    state["mails"][0]["requestNo"] = "10412"
    state, mail_id = desk.record_payment(state, "10412", "HDFC26110412", 18400, "utr.jpg", "file1")
    gun = next(line for line in state["lines"] if line["code"] == "CD4C001800")
    shoe = next(line for line in state["lines"] if line["code"] == "AAS20004")
    assert gun["stage"] == "paid"
    assert shoe["stage"] == "short"
    mail = next(item for item in state["mails"] if item["id"] == mail_id)
    assert mail["requestNo"] == "10412"
    assert mail["posted"] is False
    assert mail["gmailThreadId"] == "thread-10412"
    assert mail["replyTo"] == "parts@example.com"
    assert "HDFC26110412" in mail["body"]
    assert state["proofs"][0]["filename"] == "utr.jpg"
    state = desk.mark_posted(state, mail_id, "gmail-sent")
    assert state["proofs"][0]["posted"] is True
    try:
        desk.record_payment(state, "99999", "HDFC26110412", None, "utr.jpg", "file2")
    except ValueError as exc:
        assert "not on the desk" in str(exc)
    else:
        raise AssertionError("a missing ticket should be refused")


def test_gmail_reply_carries_the_proof_and_the_thread():
    import base64
    from email import message_from_bytes
    import workshop_gmail as gmail
    url = gmail.auth_url("client", "https://crm.example/service", "state1")
    assert "gmail.modify" in url
    assert "state1" in url
    raw = gmail.build_raw(
        "parts@example.com",
        "Re: Ticket 10412",
        "Payment done for ticket 10412.\nUTR HDFC26110412.",
        in_reply_to="<m@example.com>",
        filename="utr.jpg",
        data=b"jpeg",
        content_type="image/jpeg",
    )
    message = message_from_bytes(base64.urlsafe_b64decode(raw.encode()))
    assert message["To"] == "parts@example.com"
    assert message["In-Reply-To"] == "<m@example.com>"
    body = ""
    attachment = b""
    for part in message.walk():
        if part.get_content_type() == "text/plain":
            body += part.get_payload(decode=True).decode()
        if part.get_filename() == "utr.jpg":
            attachment = part.get_payload(decode=True)
    assert "ticket 10412" in body.lower()
    assert "HDFC26110412" in body
    assert attachment == b"jpeg"


def test_this_morning_only_fills_an_empty_desk():
    assert desk.desk_has_work(desk.empty_state()) is False
    assert desk.desk_has_work(desk.sample_state()) is True


def test_mailbox_pull_keeps_only_a_mail_with_one_request_number():
    assert desk.request_mail("Re: Ticket 10412 — dispatch", "Ticket 10412\nCD4C001800 is not dispatched") == "10412"
    assert desk.request_mail("Parts update", "Request id: 10526\nAA28000800 bush") == "10526"
    assert desk.request_mail("You have done a UPI txn. Check details!", "A payment was made using your Credit Card") == ""
    assert desk.request_mail(
        "Re: [writerish07-pixel/euler-crm] Restore Service Coulson login (PR #281)",
        "pull request #281",
        "notifications@github.com",
    ) == ""
    assert desk.request_mail("Re: two tickets", "Ticket 10412 and ticket 10526") == ""

    state = desk.empty_state()
    state, _ = desk.add_mail(state, "You have done a UPI txn", "Check details", meta={"gmailId": "bank"})
    state, _ = desk.add_mail(
        state, "Re: Ticket 10412", "Ticket 10412 is not dispatched", meta={"gmailId": "parts"},
    )
    state, _ = desk.add_mail(state, "Note for the desk", "No request on this one")
    state, dropped = desk.drop_unmatched_gmail(state)
    subjects = [mail["subject"] for mail in state["mails"]]
    assert dropped == 1
    assert "You have done a UPI txn" not in subjects
    assert "Re: Ticket 10412" in subjects
    assert "Note for the desk" in subjects


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


def test_service_sync_signs_in_with_the_login_id_and_password(monkeypatch):
    import workshop_api

    seen = {}

    def fake_login(username, password):
        seen["username"] = username
        seen["password"] = password
        return "issued-token"

    def fake_get(tok, path, params=None, timeout=None):
        assert tok == "issued-token"
        if path == "store/allowed":
            return {"data": [{"id": "store-1"}]}
        if path.endswith("analytics") or path.endswith("analytics-summary"):
            return {"data": {}}
        return {"data": []}

    monkeypatch.setattr(coulson_client, "login", fake_login)
    monkeypatch.setattr(coulson_client, "get_json", fake_get)
    snapshot = workshop_api.pull_service("service.user", "secret")
    assert seen["username"] == "service.user"
    assert seen["password"] == hashlib.sha256(b"secret").hexdigest()
    assert isinstance(snapshot["lines"], list)


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
