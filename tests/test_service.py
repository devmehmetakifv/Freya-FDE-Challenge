"""Slot service tests: call flow, identity gate, booking rules and the bank panel reads."""

import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient

from service import bank
from service.app import create_app
from service.db import connect

# Customer ids from the brief: Kadıköy has 3 customers but only 2 slots (ids 1 and 2).
AYSE, MEHMET, ZEYNEP, CAN, ALI = 1, 2, 3, 4, 8
AYSE_DOB = "1988-03-14"
KADIKOY_THU, KADIKOY_FRI, ATASEHIR_THU, BESIKTAS_THU = 1, 2, 3, 5


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "bank.db"


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path))


# Helper: open a call and pass the identity check, the way the agent does.
def verified_call(client: TestClient, customer_id: int, dob: str) -> int:
    call_id = client.post("/calls", json={"customer_id": customer_id}).json()["call_id"]
    assert client.post(f"/calls/{call_id}/verify", json={"birth_date": dob}).json()["verified"]
    return call_id


DOBS = {AYSE: AYSE_DOB, MEHMET: "1975-11-02", ZEYNEP: "1993-06-27", CAN: "1981-01-09", ALI: "1984-07-21"}


# --- Opening a call ---


def test_open_call_returns_greeting_data_without_pii(client):
    body = client.post("/calls", json={"customer_id": AYSE}).json()
    assert body["customer"] == {"full_name": "Ayşe Kaya", "district": "Kadıköy", "address_type": "home"}
    assert "birth_date" not in str(body) and "phone" not in str(body)


def test_open_call_unknown_customer_is_404(client):
    assert client.post("/calls", json={"customer_id": 999}).status_code == 404


# --- Identity check ---


def test_verify_with_correct_birth_date(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    body = client.post(f"/calls/{call_id}/verify", json={"birth_date": AYSE_DOB}).json()
    assert body == {"verified": True, "attempts_left": 3}


def test_three_wrong_birth_dates_lock_the_call(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    lefts = [
        client.post(f"/calls/{call_id}/verify", json={"birth_date": "1990-01-01"}).json()["attempts_left"]
        for _ in range(3)
    ]
    assert lefts == [2, 1, 0]
    # Even the right answer is refused once locked, and the call is closed as failed.
    locked = client.post(f"/calls/{call_id}/verify", json={"birth_date": AYSE_DOB})
    assert locked.status_code == 403 and locked.json()["error"] == "verification_locked"
    assert client.get("/calls").json()[0]["outcome"] == "verification_failed"


def test_malformed_birth_date_is_422_and_costs_no_attempt(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    assert client.post(f"/calls/{call_id}/verify", json={"birth_date": "14 Mart"}).status_code == 422
    body = client.post(f"/calls/{call_id}/verify", json={"birth_date": AYSE_DOB}).json()
    assert body == {"verified": True, "attempts_left": 3}


# --- The identity gate on delivery actions ---


def test_slots_and_booking_refused_before_verification(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    assert client.get(f"/calls/{call_id}/slots").status_code == 403
    assert client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_THU}).status_code == 403


# --- Slots and booking ---


def test_slots_are_only_from_customers_district(client):
    slots = client.get(f"/calls/{verified_call(client, CAN, DOBS[CAN])}/slots").json()
    assert [s["slot_id"] for s in slots] == [ATASEHIR_THU]
    assert slots[0]["remaining"] == 2


def test_booking_takes_a_seat_and_marks_call_booked(client):
    call_id = verified_call(client, AYSE, AYSE_DOB)
    body = client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_THU}).json()
    assert body["booked"] and body["slot"]["remaining"] == 0
    assert client.get("/calls").json()[0]["outcome"] == "booked"


def test_booking_slot_in_another_district_is_rejected(client):
    call_id = verified_call(client, AYSE, AYSE_DOB)
    resp = client.post(f"/calls/{call_id}/book", json={"slot_id": BESIKTAS_THU})
    assert resp.status_code == 400 and resp.json()["error"] == "wrong_district"


def test_kadikoy_overflow_third_customer_gets_no_slots(client):
    # Two Kadıköy customers take both Kadıköy slots; the third must hear "nothing left".
    client.post(f"/calls/{verified_call(client, AYSE, AYSE_DOB)}/book", json={"slot_id": KADIKOY_THU})
    client.post(f"/calls/{verified_call(client, MEHMET, DOBS[MEHMET])}/book", json={"slot_id": KADIKOY_FRI})
    third = verified_call(client, ZEYNEP, DOBS[ZEYNEP])
    assert client.get(f"/calls/{third}/slots").json() == []
    resp = client.post(f"/calls/{third}/book", json={"slot_id": KADIKOY_THU})
    assert resp.status_code == 409 and resp.json()["error"] == "slot_full"


def test_rebooking_moves_the_booking_and_releases_old_seat(client):
    call_id = verified_call(client, AYSE, AYSE_DOB)
    client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_THU})
    client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_FRI})
    remaining = {s["slot_id"]: s["remaining"] for s in client.get("/slots").json()}
    assert remaining[KADIKOY_THU] == 1 and remaining[KADIKOY_FRI] == 0
    customer = client.get("/customers").json()[0]
    assert (customer["day"], customer["start_time"]) == ("Cuma", "14:00")


def test_booking_same_slot_twice_is_idempotent(client):
    call_id = verified_call(client, AYSE, AYSE_DOB)
    client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_THU})
    assert client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_THU}).status_code == 200
    assert client.get("/slots").json()[0]["remaining"] == 0


def test_concurrent_calls_cannot_overbook_the_last_seat(db_path):
    # Two customers each open a verified call, then race for Kadıköy Thursday (1 seat).
    create_app(db_path)
    setup = connect(db_path)
    calls = []
    for customer_id in (AYSE, MEHMET):
        call_id = bank.open_call(setup, customer_id)["call_id"]
        bank.verify_identity(setup, call_id, date.fromisoformat(DOBS[customer_id]))
        calls.append(call_id)
    setup.close()

    results = []

    def attempt(call_id: int) -> None:
        conn = connect(db_path)
        try:
            bank.book_slot(conn, call_id, KADIKOY_THU)
            results.append("ok")
        except bank.SlotFull:
            results.append("full")
        finally:
            conn.close()

    threads = [threading.Thread(target=attempt, args=(c,)) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["full", "ok"]


# --- Outcomes ---


def test_record_outcome_for_unbooked_call(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    resp = client.post(f"/calls/{call_id}/outcome", json={"outcome": "wrong_person", "note": "eşi açtı"})
    assert resp.status_code == 200
    assert client.get("/calls").json()[0]["outcome"] == "wrong_person"


def test_unknown_outcome_and_booked_outcome_are_rejected(client):
    call_id = verified_call(client, AYSE, AYSE_DOB)
    assert client.post(f"/calls/{call_id}/outcome", json={"outcome": "booked"}).status_code == 422
    client.post(f"/calls/{call_id}/book", json={"slot_id": KADIKOY_THU})
    resp = client.post(f"/calls/{call_id}/outcome", json={"outcome": "declined"})
    assert resp.status_code == 409


def test_locked_call_outcome_is_final(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    for _ in range(3):
        client.post(f"/calls/{call_id}/verify", json={"birth_date": "1990-01-01"})
    resp = client.post(f"/calls/{call_id}/outcome", json={"outcome": "no_suitable_slot"})
    assert resp.status_code == 403
    assert client.get("/calls").json()[0]["outcome"] == "verification_failed"


# --- Outcome log: every outcome of a call is kept, none hidden by a later one ---


def test_all_outcomes_of_a_call_are_logged_in_order(client):
    call_id = verified_call(client, MEHMET, DOBS[MEHMET])
    client.post(f"/calls/{call_id}/outcome", json={"outcome": "needs_human", "note": "eve teslim istiyor"})
    client.post(f"/calls/{call_id}/outcome", json={"outcome": "no_suitable_slot", "note": "Cuma uymuyor"})
    call = client.get("/calls").json()[0]
    assert [(o["outcome"], o["note"]) for o in call["outcomes"]] == [
        ("needs_human", "eve teslim istiyor"),
        ("no_suitable_slot", "Cuma uymuyor"),
    ]
    assert call["outcome"] == "no_suitable_slot"  # latest, kept for compatibility
    mehmet = client.get("/customers").json()[1]
    assert mehmet["last_outcomes"] == ["needs_human", "no_suitable_slot"]


def test_booking_and_lock_are_logged_too(client):
    booked = verified_call(client, AYSE, AYSE_DOB)
    client.post(f"/calls/{booked}/book", json={"slot_id": KADIKOY_THU})
    locked = client.post("/calls", json={"customer_id": MEHMET}).json()["call_id"]
    for _ in range(3):
        client.post(f"/calls/{locked}/verify", json={"birth_date": "1990-01-01"})
    outcomes = {c["call_id"]: [(o["outcome"], o["note"]) for o in c["outcomes"]] for c in client.get("/calls").json()}
    assert outcomes[booked] == [("booked", "Perşembe 09:00-13:00")]
    assert outcomes[locked] == [("verification_failed", "3 hatalı doğum tarihi denemesi")]


# --- Call history: the next call sees what earlier calls recorded ---


def test_open_call_returns_previous_finished_calls(client):
    assert client.post("/calls", json={"customer_id": AYSE}).json()["previous_calls"] == []
    first = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    client.post(f"/calls/{first}/outcome", json={"outcome": "no_suitable_slot", "note": "Pazar gece 23:30 uygun"})
    history = client.post("/calls", json={"customer_id": AYSE}).json()["previous_calls"]
    # Only finished calls count; the unfinished first call and the new call are excluded.
    assert [(c["outcome"], c["note"]) for c in history] == [("no_suitable_slot", "Pazar gece 23:30 uygun")]
    assert client.post("/calls", json={"customer_id": MEHMET}).json()["previous_calls"] == []


# --- Injection attempts: typed inputs reject them at the edge, bound parameters make them inert ---


def test_sql_injection_payloads_are_rejected(client):
    call_id = client.post("/calls", json={"customer_id": AYSE}).json()["call_id"]
    assert client.post("/calls", json={"customer_id": "1 OR 1=1"}).status_code == 422
    assert client.post(f"/calls/{call_id}/book", json={"slot_id": "1; DROP TABLE slots"}).status_code == 422
    assert client.post(f"/calls/{call_id}/verify", json={"birth_date": "' OR '1'='1"}).status_code == 422
    assert client.get("/calls/1 OR 1=1/slots").status_code == 422
    # A free-text field reaches SQL only as a bound value: stored verbatim, tables intact.
    note = "x'); DROP TABLE customers; --"
    client.post(f"/calls/{call_id}/outcome", json={"outcome": "declined", "note": note})
    assert client.get("/calls").json()[0]["note"] == note
    assert len(client.get("/customers").json()) == 8


# --- Panel reads ---


def test_customers_list_has_no_birth_dates(client):
    customers = client.get("/customers").json()
    assert len(customers) == 8
    assert all("birth_date" not in c for c in customers)
