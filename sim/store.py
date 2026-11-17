"""Scenario store: scenarios live in the simulator's SQLite DB so they can be added, edited and
deleted at runtime. The table is seeded from the built-in scenarios when it's first created."""

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from service.bank import AGENT_OUTCOMES
from service.db import connect, transaction
from service.seed import CUSTOMERS, SLOTS
from sim.scenarios import SCENARIOS, Scenario

OUTCOMES = ("booked", *AGENT_OUTCOMES)
CUSTOMER_IDS = {c[0] for c in CUSTOMERS}
SLOT_IDS = {s[0] for s in SLOTS}


class ScenarioNotFound(KeyError):
    pass


class ScenarioExists(ValueError):
    pass


# Validation at the boundary: everything a scenario file or the panel sends goes through here.
class ScenarioModel(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{3,40}$")
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    customer_id: int
    situation: str = Field(min_length=10, max_length=1000)
    expected_outcomes: list[Literal[OUTCOMES]] = Field(min_length=1)  # type: ignore[valid-type]
    allowed_slots: list[int] = []
    setup_bookings: list[tuple[int, int]] = []
    is_cardholder: bool = True

    # Cross-field rules the checks depend on: real ids, and "booked" iff there are allowed slots.
    @model_validator(mode="after")
    def check_references(self) -> "ScenarioModel":
        if self.customer_id not in CUSTOMER_IDS:
            raise ValueError(f"unknown customer_id {self.customer_id}")
        if not set(self.allowed_slots) <= SLOT_IDS:
            raise ValueError(f"unknown slot in allowed_slots {self.allowed_slots}")
        for customer_id, slot_id in self.setup_bookings:
            if customer_id not in CUSTOMER_IDS or slot_id not in SLOT_IDS:
                raise ValueError(f"unknown customer or slot in setup_bookings ({customer_id}, {slot_id})")
        if ("booked" in self.expected_outcomes) != bool(self.allowed_slots):
            raise ValueError("allowed_slots must be set exactly when 'booked' is an expected outcome")
        return self

    def to_scenario(self) -> Scenario:
        return Scenario(
            id=self.id, title=self.title, description=self.description, customer_id=self.customer_id,
            situation=self.situation, expected_outcomes=tuple(self.expected_outcomes),
            allowed_slots=tuple(self.allowed_slots), setup_bookings=tuple(self.setup_bookings),
            is_cardholder=self.is_cardholder,
        )


def scenario_to_dict(scenario: Scenario) -> dict:
    data = asdict(scenario)
    return {k: list(v) if isinstance(v, tuple) else v for k, v in data.items()} | {
        "setup_bookings": [list(pair) for pair in scenario.setup_bookings]
    }


# Scenarios table in the simulator's own SQLite DB (separate from the bank's data/bank.db).
# Scalars are columns; the three lists are JSON text. position keeps the display order.
SCHEMA = """
CREATE TABLE IF NOT EXISTS scenarios (
    id                TEXT PRIMARY KEY,
    position          INTEGER NOT NULL,
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    customer_id       INTEGER NOT NULL,
    situation         TEXT NOT NULL,
    expected_outcomes TEXT NOT NULL,
    allowed_slots     TEXT NOT NULL,
    setup_bookings    TEXT NOT NULL,
    is_cardholder     INTEGER NOT NULL
)
"""
COLUMNS = (
    "id", "title", "description", "customer_id", "situation",
    "expected_outcomes", "allowed_slots", "setup_bookings", "is_cardholder",
)


def _to_row(scenario: Scenario) -> tuple:
    d = scenario_to_dict(scenario)
    return (
        d["id"], d["title"], d["description"], d["customer_id"], d["situation"],
        json.dumps(d["expected_outcomes"]), json.dumps(d["allowed_slots"]),
        json.dumps(d["setup_bookings"]), int(d["is_cardholder"]),
    )


# Rows are validated on the way out too, so a hand-edited DB can't feed a broken scenario to a run.
def _from_row(row: sqlite3.Row) -> Scenario:
    data = {k: row[k] for k in COLUMNS}
    for key in ("expected_outcomes", "allowed_slots", "setup_bookings"):
        data[key] = json.loads(data[key])
    data["is_cardholder"] = bool(data["is_cardholder"])
    return ScenarioModel.model_validate(data).to_scenario()


class ScenarioStore:
    # Creating the table seeds it with the built-in scenarios once; deleting them later sticks.
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = connect(path)
        try:
            with transaction(conn):
                is_new = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'scenarios'"
                ).fetchone() is None
                conn.execute(SCHEMA)
                if is_new:
                    for position, scenario in enumerate(SCENARIOS):
                        self._insert(conn, scenario, position)
        finally:
            conn.close()

    def list(self) -> list[Scenario]:
        with closing(connect(self.path)) as conn:
            return [_from_row(r) for r in conn.execute("SELECT * FROM scenarios ORDER BY position")]

    def get(self, scenario_id: str) -> Scenario:
        with closing(connect(self.path)) as conn:
            row = conn.execute("SELECT * FROM scenarios WHERE id = ?", (scenario_id,)).fetchone()
        if row is None:
            raise ScenarioNotFound(scenario_id)
        return _from_row(row)

    def create(self, scenario: Scenario) -> Scenario:
        with closing(connect(self.path)) as conn, transaction(conn):
            position = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM scenarios").fetchone()[0]
            try:
                self._insert(conn, scenario, position)
            except sqlite3.IntegrityError:
                raise ScenarioExists(scenario.id) from None
        return scenario

    def update(self, scenario_id: str, scenario: Scenario) -> Scenario:
        assignments = ", ".join(f"{c} = ?" for c in COLUMNS[1:])
        with closing(connect(self.path)) as conn, transaction(conn):
            changed = conn.execute(
                f"UPDATE scenarios SET {assignments} WHERE id = ?", (*_to_row(scenario)[1:], scenario_id)
            ).rowcount
        if changed == 0:
            raise ScenarioNotFound(scenario_id)
        return scenario

    def delete(self, scenario_id: str) -> None:
        with closing(connect(self.path)) as conn, transaction(conn):
            if conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,)).rowcount == 0:
                raise ScenarioNotFound(scenario_id)

    @staticmethod
    def _insert(conn: sqlite3.Connection, scenario: Scenario, position: int) -> None:
        conn.execute(
            f"INSERT INTO scenarios (position, {', '.join(COLUMNS)}) VALUES (?, {', '.join('?' * len(COLUMNS))})",
            (position, *_to_row(scenario)),
        )
