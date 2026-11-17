"""Runs simulated calls: our agent (same prompt, tools, service as the voice bot) vs an LLM customer."""

import asyncio
import json
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from agent.prompt import KICKOFF_MESSAGE, SILENCE_MESSAGE, build_system_prompt
from agent.tools import CallSession, anthropic_tools
from service.app import create_app
from service.db import connect
from service.seed import CUSTOMERS
from sim.checks import CallRecord, run_checks
from sim.customer import (
    SILENT_REPLY,
    customer_reply,
    customer_system_prompt,
    generate_persona,
)
from sim.scenarios import Scenario


@dataclass(frozen=True)
class SimConfig:
    agent_model: str
    customer_model: str
    max_turns: int = 12
    concurrency: int = 4


# Agent side of one turn: call Claude, run any tools, repeat until it speaks without a tool call
# or hangs up. Returns what the agent said out loud this turn.
async def _agent_turn(client, model: str, system: str, session: CallSession, messages: list, transcript: list) -> str:
    spoken = []
    while True:
        response = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            tools=anthropic_tools(),
            output_config={"effort": "low"},
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        if text:
            spoken.append(text)
            transcript.append({"role": "agent", "text": text})

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            return " ".join(spoken)
        results = []
        for block in tool_uses:
            result = await session.execute(block.name, dict(block.input))
            transcript.append({"role": "tool", "text": f"{block.name}({json.dumps(block.input, ensure_ascii=False)}) -> {json.dumps(result, ensure_ascii=False)}"})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})
        if session.ended:
            return " ".join(spoken)


# Book seats before the call when the scenario needs a crowded week (e.g. Kadıköy overflow).
async def _apply_setup(http: httpx.AsyncClient, scenario: Scenario) -> None:
    for customer_id, slot_id in scenario.setup_bookings:
        setup = await CallSession.open(http, customer_id)
        await setup.execute("verify_identity", {"birth_date": CUSTOMERS[customer_id - 1][3]})
        await setup.execute("book_slot", {"slot_id": slot_id})


def _final_state(db_path: Path, call_id: int, customer_id: int) -> tuple[str | None, tuple[str, ...], int | None]:
    conn = connect(db_path)
    try:
        outcome = conn.execute("SELECT outcome FROM calls WHERE id = ?", (call_id,)).fetchone()["outcome"]
        logged = tuple(r["outcome"] for r in conn.execute(
            "SELECT outcome FROM call_outcomes WHERE call_id = ? ORDER BY id", (call_id,)))
        booking = conn.execute("SELECT slot_id FROM bookings WHERE customer_id = ?", (customer_id,)).fetchone()
        return outcome, logged, booking["slot_id"] if booking else None
    finally:
        conn.close()


# One full simulated call on its own throwaway database, scored by the deterministic checks.
async def run_scenario(client, scenario: Scenario, attempt: int, config: SimConfig, workdir: Path) -> dict:
    started = time.monotonic()
    db_path = workdir / f"{scenario.id}-{attempt}.db"
    transport = httpx.ASGITransport(app=create_app(db_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://bank") as http:
        await _apply_setup(http, scenario)
        session = await CallSession.open(http, scenario.customer_id)
        persona = await generate_persona(client, config.customer_model, scenario)
        agent_system = build_system_prompt(session.customer, session.previous_calls, session.current_booking)
        customer_system = customer_system_prompt(scenario, persona)

        transcript = [{"role": "customer", "text": KICKOFF_MESSAGE}]
        agent_messages = [{"role": "user", "content": KICKOFF_MESSAGE}]
        customer_history: list[dict] = []
        turns = 0
        while turns < config.max_turns and not session.ended:
            turns += 1
            agent_said = await _agent_turn(client, config.agent_model, agent_system, session, agent_messages, transcript)
            if session.ended:
                break
            customer_history.append({"role": "user", "content": agent_said or "..."})
            reply = await customer_reply(client, config.customer_model, customer_system, customer_history)
            customer_history.append({"role": "assistant", "content": reply})
            silent = SILENT_REPLY in reply
            transcript.append({"role": "customer", "text": "(sessiz)" if silent else reply})
            agent_messages.append({"role": "user", "content": SILENCE_MESSAGE if silent else reply})

    outcome, outcomes, booked_slot = _final_state(db_path, session.call_id, scenario.customer_id)
    record = CallRecord(
        transcript=tuple(transcript),
        tool_log=tuple(session.tool_log),
        outcome=outcome,
        booked_slot=booked_slot,
        ended_by_agent=session.ended,
        birth_year=str(date.fromisoformat(CUSTOMERS[scenario.customer_id - 1][3]).year),
        outcomes=outcomes,
    )
    checks = run_checks(scenario, record)
    return {
        "scenario_id": scenario.id,
        "title": scenario.title,
        "attempt": attempt,
        "passed": all(c["passed"] for c in checks),
        "outcome": outcome,
        "turns": turns,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "persona": persona,
        "checks": checks,
        "transcript": transcript,
    }


# Run every (scenario, attempt) pair with bounded concurrency. on_result lets the server stream
# results into a run record as they finish. A crashed simulation is reported, not raised.
async def run_batch(client, scenarios: list[Scenario], runs_per_scenario: int, config: SimConfig, on_result=None) -> list[dict]:
    semaphore = asyncio.Semaphore(config.concurrency)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)

        async def one(scenario: Scenario, attempt: int) -> dict:
            async with semaphore:
                try:
                    result = await run_scenario(client, scenario, attempt, config, workdir)
                except Exception as exc:  # noqa: BLE001 - one broken run must not kill the batch
                    result = {
                        "scenario_id": scenario.id, "title": scenario.title, "attempt": attempt,
                        "passed": False, "outcome": None, "turns": 0, "duration_ms": 0, "persona": "",
                        "checks": [{"name": "simulation_error", "passed": False, "detail": repr(exc)}],
                        "transcript": [],
                    }
            if on_result:
                on_result(result)
            return result

        jobs = [one(s, a) for s in scenarios for a in range(1, runs_per_scenario + 1)]
        return await asyncio.gather(*jobs)
