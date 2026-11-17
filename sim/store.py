"""Scenario store: scenarios live in a JSON file so they can be added, edited and deleted at runtime.
The file is seeded from the built-in scenarios the first time it's missing."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from service.bank import AGENT_OUTCOMES
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


class ScenarioStore:
    def __init__(self, path: Path):
        self.path = path

    def list(self) -> list[Scenario]:
        if not self.path.exists():
            self._save(list(SCENARIOS))
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [ScenarioModel.model_validate(item).to_scenario() for item in raw]

    def get(self, scenario_id: str) -> Scenario:
        for s in self.list():
            if s.id == scenario_id:
                return s
        raise ScenarioNotFound(scenario_id)

    def create(self, scenario: Scenario) -> Scenario:
        scenarios = self.list()
        if any(s.id == scenario.id for s in scenarios):
            raise ScenarioExists(scenario.id)
        self._save([*scenarios, scenario])
        return scenario

    def update(self, scenario_id: str, scenario: Scenario) -> Scenario:
        scenarios = self.list()
        if not any(s.id == scenario_id for s in scenarios):
            raise ScenarioNotFound(scenario_id)
        self._save([scenario if s.id == scenario_id else s for s in scenarios])
        return scenario

    def delete(self, scenario_id: str) -> None:
        scenarios = self.list()
        remaining = [s for s in scenarios if s.id != scenario_id]
        if len(remaining) == len(scenarios):
            raise ScenarioNotFound(scenario_id)
        self._save(remaining)

    # Write to a temp file and swap it in, so a crash mid-write can't leave a half-written file.
    def _save(self, scenarios: list[Scenario]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump([scenario_to_dict(s) for s in scenarios], f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)
