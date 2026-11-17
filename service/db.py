"""SQLite connection, schema and seeding for the slot service."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from service.seed import CUSTOMERS, SLOTS

# Schema: the CHECK on slots.booked is a last line of defense against overbooking;
# bookings.customer_id is the primary key, so a customer can hold at most one booking.
SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id           INTEGER PRIMARY KEY,
    full_name    TEXT NOT NULL,
    phone        TEXT NOT NULL UNIQUE,
    birth_date   TEXT NOT NULL,
    district     TEXT NOT NULL,
    address_type TEXT NOT NULL CHECK (address_type IN ('home', 'work'))
);
CREATE TABLE IF NOT EXISTS slots (
    id         INTEGER PRIMARY KEY,
    district   TEXT NOT NULL,
    day        TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    capacity   INTEGER NOT NULL CHECK (capacity >= 0),
    booked     INTEGER NOT NULL DEFAULT 0 CHECK (booked >= 0 AND booked <= capacity)
);
CREATE TABLE IF NOT EXISTS calls (
    id              INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id),
    verified        INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    outcome         TEXT,
    note            TEXT,
    started_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS call_outcomes (
    id         INTEGER PRIMARY KEY,
    call_id    INTEGER NOT NULL REFERENCES calls(id),
    outcome    TEXT NOT NULL,
    note       TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookings (
    customer_id INTEGER PRIMARY KEY REFERENCES customers(id),
    slot_id     INTEGER NOT NULL REFERENCES slots(id),
    call_id     INTEGER NOT NULL REFERENCES calls(id),
    created_at  TEXT NOT NULL
);
"""


# One connection per request/thread. Autocommit mode (isolation_level=None) so that
# transactions are explicit via transaction() below, never implicit.
def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=5, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# BEGIN IMMEDIATE takes the write lock up front, so two concurrent bookings are serialized
# instead of both reading "1 seat left" and racing.
@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


# Create tables and load the brief's data once. Re-running is safe: existing rows are kept,
# so bookings survive a service restart.
def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        with transaction(conn):
            conn.executemany("INSERT OR IGNORE INTO customers VALUES (?, ?, ?, ?, ?, ?)", CUSTOMERS)
            conn.executemany(
                "INSERT OR IGNORE INTO slots (id, district, day, start_time, end_time, capacity) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                SLOTS,
            )
            # Calls recorded before the outcome log existed get their single outcome logged once.
            conn.execute(
                "INSERT INTO call_outcomes (call_id, outcome, note, created_at) "
                "SELECT id, outcome, note, started_at FROM calls "
                "WHERE outcome IS NOT NULL AND id NOT IN (SELECT call_id FROM call_outcomes)"
            )
    finally:
        conn.close()
