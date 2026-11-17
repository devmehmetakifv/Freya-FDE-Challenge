"""Bank domain rules for the card re-delivery calls. Pure functions over a SQLite connection."""

import sqlite3
from datetime import UTC, date, datetime

from service.db import transaction

MAX_VERIFY_ATTEMPTS = 3

# Outcomes the agent may record. "booked" is not here on purpose: only book_slot() sets it,
# so a call can never claim a booking that doesn't exist.
AGENT_OUTCOMES = (
    "no_suitable_slot",
    "wrong_person",
    "verification_failed",
    "callback_requested",
    "declined",
    "needs_human",
)


# Domain errors carry their HTTP status so the API layer maps them in one place.
class BankError(Exception):
    status_code = 400
    code = "bad_request"


class NotFound(BankError):
    status_code = 404
    code = "not_found"


class NotVerified(BankError):
    status_code = 403
    code = "not_verified"


class VerificationLocked(BankError):
    status_code = 403
    code = "verification_locked"


class SlotFull(BankError):
    status_code = 409
    code = "slot_full"


class WrongDistrict(BankError):
    status_code = 400
    code = "wrong_district"


class AlreadyBooked(BankError):
    status_code = 409
    code = "already_booked"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _get_call(conn: sqlite3.Connection, call_id: int) -> sqlite3.Row:
    call = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
    if call is None:
        raise NotFound(f"call {call_id} not found")
    return call


# Every delivery action goes through this gate: no identity check, no slot data, no booking.
def _get_verified_call(conn: sqlite3.Connection, call_id: int) -> sqlite3.Row:
    call = _get_call(conn, call_id)
    if not call["verified"]:
        raise NotVerified("identity not verified on this call")
    return call


def _customer_district(conn: sqlite3.Connection, customer_id: int) -> str:
    row = conn.execute("SELECT district FROM customers WHERE id = ?", (customer_id,)).fetchone()
    return row["district"]


def _slot_view(row: sqlite3.Row) -> dict:
    return {
        "slot_id": row["id"],
        "district": row["district"],
        "day": row["day"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "remaining": row["capacity"] - row["booked"],
    }


# Start of a call. Returns only what the agent needs to greet the customer:
# no birth date, no phone number, so the LLM can never leak them.
def open_call(conn: sqlite3.Connection, customer_id: int) -> dict:
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if customer is None:
        raise NotFound(f"customer {customer_id} not found")
    cursor = conn.execute(
        "INSERT INTO calls (customer_id, started_at) VALUES (?, ?)", (customer_id, _now())
    )
    return {
        "call_id": cursor.lastrowid,
        "customer": {
            "full_name": customer["full_name"],
            "district": customer["district"],
            "address_type": customer["address_type"],
        },
    }


# Identity check: compare the spoken birth date with the record, server-side.
# Wrong answers count toward a 3-strike lock; a lock also closes the call's outcome.
def verify_identity(conn: sqlite3.Connection, call_id: int, birth_date: date) -> dict:
    with transaction(conn):
        call = _get_call(conn, call_id)
        if call["verified"]:
            return {"verified": True, "attempts_left": MAX_VERIFY_ATTEMPTS - call["failed_attempts"]}
        if call["failed_attempts"] >= MAX_VERIFY_ATTEMPTS:
            raise VerificationLocked("too many failed attempts on this call")

        record = conn.execute(
            "SELECT birth_date FROM customers WHERE id = ?", (call["customer_id"],)
        ).fetchone()
        if record["birth_date"] == birth_date.isoformat():
            conn.execute("UPDATE calls SET verified = 1 WHERE id = ?", (call_id,))
            return {"verified": True, "attempts_left": MAX_VERIFY_ATTEMPTS - call["failed_attempts"]}

        failed = call["failed_attempts"] + 1
        conn.execute("UPDATE calls SET failed_attempts = ? WHERE id = ?", (failed, call_id))
        if failed >= MAX_VERIFY_ATTEMPTS:
            conn.execute(
                "UPDATE calls SET outcome = 'verification_failed' WHERE id = ?", (call_id,)
            )
        return {"verified": False, "attempts_left": MAX_VERIFY_ATTEMPTS - failed}


# Free slots in the customer's own district only. Full slots are hidden.
def available_slots(conn: sqlite3.Connection, call_id: int) -> list[dict]:
    call = _get_verified_call(conn, call_id)
    district = _customer_district(conn, call["customer_id"])
    rows = conn.execute(
        "SELECT * FROM slots WHERE district = ? AND booked < capacity ORDER BY id", (district,)
    ).fetchall()
    return [_slot_view(row) for row in rows]


# Atomic booking. The conditional UPDATE takes a seat only if one is left, inside a write
# transaction, so two calls racing for the last seat can't both win. Re-booking moves the
# customer's existing booking (releases the old seat) instead of creating a second one.
def book_slot(conn: sqlite3.Connection, call_id: int, slot_id: int) -> dict:
    with transaction(conn):
        call = _get_verified_call(conn, call_id)
        customer_id = call["customer_id"]
        slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
        if slot is None:
            raise NotFound(f"slot {slot_id} not found")
        if slot["district"] != _customer_district(conn, customer_id):
            raise WrongDistrict("slot is not in the customer's district")

        existing = conn.execute(
            "SELECT slot_id FROM bookings WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        if existing is None or existing["slot_id"] != slot_id:
            taken = conn.execute(
                "UPDATE slots SET booked = booked + 1 WHERE id = ? AND booked < capacity",
                (slot_id,),
            ).rowcount
            if taken == 0:
                raise SlotFull("slot is already full")
            if existing is None:
                conn.execute(
                    "INSERT INTO bookings (customer_id, slot_id, call_id, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (customer_id, slot_id, call_id, _now()),
                )
            else:
                conn.execute(
                    "UPDATE slots SET booked = booked - 1 WHERE id = ?", (existing["slot_id"],)
                )
                conn.execute(
                    "UPDATE bookings SET slot_id = ?, call_id = ?, created_at = ? "
                    "WHERE customer_id = ?",
                    (slot_id, call_id, _now(), customer_id),
                )

        conn.execute("UPDATE calls SET outcome = 'booked' WHERE id = ?", (call_id,))
        booked_slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
        return {"booked": True, "slot": _slot_view(booked_slot)}


# How a call ended when nothing was booked. A booked call keeps "booked" as its outcome.
def record_outcome(conn: sqlite3.Connection, call_id: int, outcome: str, note: str) -> dict:
    with transaction(conn):
        call = _get_call(conn, call_id)
        if call["outcome"] == "booked":
            raise AlreadyBooked("call already ended with a booking")
        conn.execute(
            "UPDATE calls SET outcome = ?, note = ? WHERE id = ?", (outcome, note, call_id)
        )
        return {"call_id": call_id, "outcome": outcome}


# --- Read models for the bank panel (no birth dates leave the service) ---


def list_customers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.id, c.full_name, c.phone, c.district, c.address_type,
               s.day, s.start_time, s.end_time,
               (SELECT outcome FROM calls WHERE customer_id = c.id
                ORDER BY id DESC LIMIT 1) AS last_outcome
        FROM customers c
        LEFT JOIN bookings b ON b.customer_id = c.id
        LEFT JOIN slots s ON s.id = b.slot_id
        ORDER BY c.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def list_slots(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM slots ORDER BY id").fetchall()
    return [{**_slot_view(row), "capacity": row["capacity"]} for row in rows]


def list_calls(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT k.id AS call_id, k.customer_id, c.full_name, k.verified, k.failed_attempts,
               k.outcome, k.note, k.started_at
        FROM calls k JOIN customers c ON c.id = k.customer_id
        ORDER BY k.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
