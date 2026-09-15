"""Concurrent Google Sheet upserts must not share httplib2 SSL state."""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gsheets  # noqa: E402


def test_http_lock_exists():
    assert gsheets._http_lock.acquire(blocking=False)
    gsheets._http_lock.release()


def test_with_retry_serializes_concurrent_calls():
    inside = 0
    max_inside = 0
    gate = threading.Lock()

    def fn():
        nonlocal inside, max_inside
        with gate:
            inside += 1
            max_inside = max(max_inside, inside)
        time.sleep(0.04)
        with gate:
            inside -= 1
        return True

    threads = [
        threading.Thread(target=lambda: gsheets._with_retry(fn, attempts=1))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert max_inside == 1


def test_upsert_sync_serializes_concurrent_calls():
    inside = 0
    max_inside = 0
    gate = threading.Lock()
    orig = gsheets._upsert_sync_body

    def body(entity, doc):
        nonlocal inside, max_inside
        with gate:
            inside += 1
            max_inside = max(max_inside, inside)
        time.sleep(0.04)
        with gate:
            inside -= 1
        return {"ok": True, "operation": "updated", "entity": entity}

    gsheets._upsert_sync_body = body
    try:
        threads = [
            threading.Thread(target=lambda: gsheets._upsert_sync("claims", {"claimId": "C1"}))
            for _ in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive()
    finally:
        gsheets._upsert_sync_body = orig
    assert max_inside == 1
