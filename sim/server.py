"""Simulation API for the panel: list scenarios, start runs, read results.
Run: uv run uvicorn sim.server:app --port 8100"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from service.seed import CUSTOMERS, SLOTS
from sim.runner import SimConfig, run_batch
from sim.store import (
    OUTCOMES,
    ScenarioExists,
    ScenarioModel,
    ScenarioNotFound,
    ScenarioStore,
    scenario_to_dict,
)

load_dotenv()

RESULTS_DIR = Path("sim/results")
STORE = ScenarioStore(Path(os.getenv("SIM_SCENARIOS_PATH", "sim/scenarios.json")))


class RunRequest(BaseModel):
    scenario_ids: list[str] | None = None
    runs_per_scenario: int = Field(default=1, ge=1, le=5)


def _config() -> SimConfig:
    return SimConfig(agent_model=os.environ["AGENT_BRAIN_MODEL"], customer_model=os.environ["SIM_CUSTOMER_MODEL"])


# Past runs are reloaded from disk so the panel still shows them after a restart.
def _load_saved_runs() -> dict[str, dict]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    runs = {}
    for path in RESULTS_DIR.glob("*.json"):
        run = json.loads(path.read_text(encoding="utf-8"))
        runs[run["run_id"]] = run
    return runs


app = FastAPI(title="Simulation Service")
RUNS: dict[str, dict] = _load_saved_runs()
_tasks: set[asyncio.Task] = set()


def _summary(run: dict) -> dict:
    return {k: run[k] for k in ("run_id", "status", "started_at", "model", "total", "passed")}


# --- Scenario CRUD (the panel's editor). Validation lives in ScenarioModel. ---


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [scenario_to_dict(s) for s in STORE.list()]


@app.post("/scenarios", status_code=201)
def create_scenario(body: ScenarioModel) -> dict:
    try:
        return scenario_to_dict(STORE.create(body.to_scenario()))
    except ScenarioExists:
        raise HTTPException(status_code=409, detail=f"scenario '{body.id}' already exists") from None


@app.put("/scenarios/{scenario_id}")
def update_scenario(scenario_id: str, body: ScenarioModel) -> dict:
    if body.id != scenario_id:
        raise HTTPException(status_code=422, detail="scenario id can't be changed")
    try:
        return scenario_to_dict(STORE.update(scenario_id, body.to_scenario()))
    except ScenarioNotFound:
        raise HTTPException(status_code=404, detail="scenario not found") from None


@app.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str) -> Response:
    try:
        STORE.delete(scenario_id)
    except ScenarioNotFound:
        raise HTTPException(status_code=404, detail="scenario not found") from None
    return Response(status_code=204)


# Options for the panel's scenario form.
@app.get("/meta")
def meta() -> dict:
    return {
        "outcomes": list(OUTCOMES),
        "customers": [{"id": c[0], "full_name": c[1], "district": c[4]} for c in CUSTOMERS],
        "slots": [{"slot_id": s[0], "district": s[1], "day": s[2], "start_time": s[3], "end_time": s[4]} for s in SLOTS],
    }


# Starts a batch in the background and returns at once; results stream into RUNS as they finish.
@app.post("/runs")
async def start_run(body: RunRequest) -> dict:
    by_id = {s.id: s for s in STORE.list()}
    ids = body.scenario_ids or list(by_id)
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown scenarios: {unknown}")
    config = _config()
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    run = {
        "run_id": run_id, "status": "running", "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": config.agent_model, "total": len(ids) * body.runs_per_scenario, "passed": 0, "results": [],
    }
    RUNS[run_id] = run

    def on_result(result: dict) -> None:
        run["results"].append(result)
        run["passed"] += int(result["passed"])

    async def execute() -> None:
        try:
            await run_batch(AsyncAnthropic(), [by_id[i] for i in ids], body.runs_per_scenario, config, on_result)
            run["status"] = "done"
        except Exception as exc:  # noqa: BLE001 - surface the failure in the run record
            run["status"] = "failed"
            run["error"] = repr(exc)
        (RESULTS_DIR / f"{run_id}.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")

    task = asyncio.create_task(execute())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"run_id": run_id}


@app.get("/runs")
def runs() -> list[dict]:
    return sorted((_summary(r) for r in RUNS.values()), key=lambda r: r["started_at"], reverse=True)


@app.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict:
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="run not found")
    return RUNS[run_id]
