"""Finance P0 safety checks that run without live Mongo/Sheets.

These tests intentionally inspect the production module text because the main
API test suite requires a configured running backend. They protect the Finance
P0 invariants that are easy to regress without external services:

* Finance payments resolve a file before payment insertion.
* New Finance file IDs use the existing FN26 next_id path.
* Startup Finance index failures are not silently swallowed.
* Finance customer payments accrue committed/sanctioned amount, not financer
  receipts/disbursements.
"""
from pathlib import Path


SERVER = Path(__file__).resolve().parents[1] / "server.py"


def _server_source():
    return SERVER.read_text()


def test_finance_payment_resolves_file_before_insert():
    src = _server_source()
    resolve_pos = src.index('finance_file_number = await _resolve_finance_file_for_payment(lead_id, body)')
    insert_pos = src.index('await db.payments.insert_one(doc)')
    payment_field_pos = src.index('"financeFileNumber": finance_file_number')
    assert resolve_pos < payment_field_pos < insert_pos


def test_finance_file_uses_existing_atomic_fn26_id_path():
    src = _server_source()
    assert 'await next_id("finance", "FN26")' in src


def test_finance_index_initialization_not_silently_swallowed():
    src = _server_source()
    assert "FINANCE_UNIQUE_INDEX_AUDIT_ERROR" in src
    assert "FINANCE_UNIQUE_INDEX_ERROR" in src
    assert '"financeIndexes": dict(_finance_index_status)' in src


def test_finance_payment_preserves_disbursement_semantics():
    src = _server_source()
    assert 'committed = ce.round2(ce.num(existing.get("sanctionedAmount")) + body.amount)' in src
    assert 'received = ce.num(existing.get("receivedAgainstFile"))' in src
    assert '"receivedAgainstFile": 0.0' in src
    assert '"committedAmount": f.get("sanctionedAmount")' in src
    assert '"disbursedAmount": f.get("receivedAgainstFile")' in src


def test_finance_register_arithmetic_for_two_payments_then_disbursement():
    sanctioned_amount = 0.0
    received_against_file = 0.0

    sanctioned_amount += 300_654
    file_outstanding = max(0.0, sanctioned_amount - received_against_file)
    assert sanctioned_amount == 300_654
    assert received_against_file == 0
    assert file_outstanding == 300_654

    sanctioned_amount += 50_000
    file_outstanding = max(0.0, sanctioned_amount - received_against_file)
    assert sanctioned_amount == 350_654
    assert received_against_file == 0
    assert file_outstanding == 350_654

    received_against_file += 350_654
    file_outstanding = max(0.0, sanctioned_amount - received_against_file)
    assert received_against_file == 350_654
    assert file_outstanding == 0
