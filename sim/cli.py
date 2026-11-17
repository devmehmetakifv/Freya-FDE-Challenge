"""Run simulations from the terminal and print a pass-rate table.
Usage: uv run python -m sim.cli [--runs N] [--scenarios id1,id2]"""

import argparse
import asyncio
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from sim.runner import SimConfig, run_batch
from sim.scenarios import SCENARIOS, SCENARIOS_BY_ID


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--scenarios", default="")
    args = parser.parse_args()

    scenarios = [SCENARIOS_BY_ID[i] for i in args.scenarios.split(",") if i] or list(SCENARIOS)
    config = SimConfig(agent_model=os.environ["AGENT_BRAIN_MODEL"], customer_model=os.environ["SIM_CUSTOMER_MODEL"])
    results = asyncio.run(run_batch(AsyncAnthropic(), scenarios, args.runs, config))

    # Per-scenario pass rate, plus the first failing check of each failed attempt.
    by_scenario = defaultdict(list)
    for r in results:
        by_scenario[r["scenario_id"]].append(r)
    print(f"\nmodel: {config.agent_model}")
    for scenario_id, rs in by_scenario.items():
        passed = sum(r["passed"] for r in rs)
        print(f"{scenario_id:24} {passed}/{len(rs)}")
        for r in rs:
            for c in (c for c in r["checks"] if not c["passed"]):
                print(f"    attempt {r['attempt']}: {c['name']} - {c['detail'][:120]}")
    total = sum(r["passed"] for r in results)
    print(f"{'TOTAL':24} {total}/{len(results)}")

    out = Path("sim/results") / f"cli-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run_id": out.stem, "status": "done", "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
                               "model": config.agent_model, "total": len(results), "passed": total, "results": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
