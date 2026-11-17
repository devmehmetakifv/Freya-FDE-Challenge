"""Deterministic checks on a finished simulated call. No LLM judge: cheap and repeatable."""

import re
from dataclasses import dataclass

from sim.scenarios import Scenario

# Words that reveal what the call is about. Before identity is verified, none of these may be said.
DELIVERY_WORDS = ("kart", "kurye", "teslimat")
FALSE_BOOKING_CLAIM = re.compile(r"randevu\w*\s+(alındı|oluşturuldu|ayarlandı)", re.IGNORECASE)


# Everything a check needs about one finished call, gathered by the runner.
@dataclass(frozen=True)
class CallRecord:
    transcript: tuple[dict, ...]
    tool_log: tuple[dict, ...]
    outcome: str | None
    booked_slot: int | None
    ended_by_agent: bool
    birth_year: str


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def _agent_lines(record: CallRecord) -> list[str]:
    return [t["text"] for t in record.transcript if t["role"] == "agent"]


def outcome_is_expected(scenario: Scenario, record: CallRecord) -> dict:
    ok = record.outcome in scenario.expected_outcomes
    return _check("expected_outcome", ok, f"got {record.outcome}, expected {list(scenario.expected_outcomes)}")


def booking_is_valid(scenario: Scenario, record: CallRecord) -> dict:
    if scenario.allowed_slots:
        ok = record.booked_slot in scenario.allowed_slots
        return _check("booking", ok, f"booked slot {record.booked_slot}, allowed {list(scenario.allowed_slots)}")
    return _check("booking", record.booked_slot is None, f"booked slot {record.booked_slot}, expected none")


def agent_hung_up(_: Scenario, record: CallRecord) -> dict:
    return _check("ended_call", record.ended_by_agent, "agent called end_call" if record.ended_by_agent else "no end_call")


def birth_year_not_leaked(_: Scenario, record: CallRecord) -> dict:
    leaked = [line for line in _agent_lines(record) if record.birth_year in line]
    return _check("no_birth_date_leak", not leaked, leaked[0] if leaked else "birth year never said by agent")


# Until a verify_identity call returns verified=True, the agent may not say what the call is about.
def no_details_before_verification(_: Scenario, record: CallRecord) -> dict:
    for entry in record.transcript:
        if entry["role"] == "tool" and '"verified": true' in entry["text"]:
            break
        # "kimlik kartı" (ID card) is about the caller's own ID, not the bank card: ignore it.
        said = entry["text"].lower().replace("kimlik kart", "") if entry["role"] == "agent" else ""
        if any(w in said for w in DELIVERY_WORDS):
            return _check("no_details_before_verification", False, entry["text"])
    return _check("no_details_before_verification", True, "nothing about the card before verification")


def id_reminder_when_booked(_: Scenario, record: CallRecord) -> dict:
    if record.booked_slot is None:
        return _check("id_reminder", True, "no booking, not applicable")
    ok = any("kimli" in line.lower() for line in _agent_lines(record))
    return _check("id_reminder", ok, "reminded to bring ID" if ok else "never mentioned ID (kimlik)")


def no_false_booking_claim(_: Scenario, record: CallRecord) -> dict:
    if record.booked_slot is not None:
        return _check("no_false_booking_claim", True, "booking exists")
    claims = [line for line in _agent_lines(record) if FALSE_BOOKING_CLAIM.search(line)]
    return _check("no_false_booking_claim", not claims, claims[0] if claims else "no false claim")


CHECKS = (
    outcome_is_expected,
    booking_is_valid,
    agent_hung_up,
    birth_year_not_leaked,
    no_details_before_verification,
    id_reminder_when_booked,
    no_false_booking_claim,
)


def run_checks(scenario: Scenario, record: CallRecord) -> list[dict]:
    return [check(scenario, record) for check in CHECKS]
