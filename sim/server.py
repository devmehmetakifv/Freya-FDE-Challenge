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
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from sim.runner import SimConfig, run_batch
from sim.scenarios import SCENARIOS, SCENARIOS_BY_ID

load_dotenv()

RESULTS_DIR = Path("sim/results")


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


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [{"id": s.id, "title": s.title, "description": s.description, "customer_id": s.customer_id} for s in SCENARIOS]


# Starts a batch in the background and returns at once; results stream into RUNS as they finish.
@app.post("/runs")
async def start_run(body: RunRequest) -> dict:
    ids = body.scenario_ids or [s.id for s in SCENARIOS]
    unknown = [i for i in ids if i not in SCENARIOS_BY_ID]
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
            await run_batch(AsyncAnthropic(), [SCENARIOS_BY_ID[i] for i in ids], body.runs_per_scenario, config, on_result)
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
