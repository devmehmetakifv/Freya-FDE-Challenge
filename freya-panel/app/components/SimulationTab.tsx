"use client";

import { useCallback, useEffect, useState } from "react";
import { errorText, fetchJson } from "@/lib/api";
import type { RunSummary, Scenario, StartRunRequest } from "@/lib/types";
import RunResults from "./RunResults";
import { Button, ErrorNote } from "./ui";

const RUNS_PER_SCENARIO_OPTIONS = [1, 2, 3];

// Pick scenarios, start a simulated-customer run, and browse past runs.
export default function SimulationTab() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [runsPerScenario, setRunsPerScenario] = useState(1);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runsKey, setRunsKey] = useState(0);
  const refreshRuns = useCallback(() => setRunsKey((k) => k + 1), []);

  // On mount: load scenarios, all selected by default.
  useEffect(() => {
    fetchJson<Scenario[]>("/api/sim/scenarios")
      .then((list) => {
        setScenarios(list);
        setSelected(new Set(list.map((s) => s.id)));
      })
      .catch((err) => setError(errorText(err)));
  }, []);

  // Run history: reloaded on mount, on Refresh, after starting a run and when a run finishes.
  useEffect(() => {
    fetchJson<RunSummary[]>("/api/sim/runs")
      .then(setRuns)
      .catch((err) => setError(errorText(err)));
  }, [runsKey]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Start a run; sending null means "all scenarios" to the sim server.
  async function startRun() {
    setError(null);
    const body: StartRunRequest = {
      scenario_ids: selected.size === scenarios.length ? null : [...selected],
      runs_per_scenario: runsPerScenario,
    };
    try {
      const { run_id } = await fetchJson<{ run_id: string }>("/api/sim/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setActiveRunId(run_id);
      refreshRuns();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {error && <ErrorNote message={error} />}

      <section className="flex flex-col gap-2">
        <h2 className="font-semibold">Scenarios</h2>
        {scenarios.map((s) => (
          <label key={s.id} className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={selected.has(s.id)} onChange={() => toggle(s.id)} />
            <span>
              <strong>{s.title}</strong> <span className="text-zinc-500">(customer #{s.customer_id})</span>
              <br />
              <span className="text-zinc-600">{s.description}</span>
            </span>
          </label>
        ))}
        <div className="mt-2 flex items-center gap-3">
          <label className="text-sm">
            Runs per scenario{" "}
            <select
              className="rounded border border-zinc-300 px-2 py-1"
              value={runsPerScenario}
              onChange={(e) => setRunsPerScenario(Number(e.target.value))}
            >
              {RUNS_PER_SCENARIO_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <Button primary onClick={() => void startRun()} disabled={selected.size === 0}>
            Run
          </Button>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">Runs</h2>
          <Button onClick={refreshRuns}>Refresh</Button>
        </div>
        {runs.length === 0 && <p className="text-sm text-zinc-500">No runs yet.</p>}
        <ul className="flex flex-col gap-1 text-sm">
          {runs.map((r) => (
            <li key={r.run_id}>
              <button
                type="button"
                onClick={() => setActiveRunId(r.run_id)}
                className={`w-full rounded px-2 py-1 text-left hover:bg-zinc-100 ${r.run_id === activeRunId ? "bg-zinc-100 font-medium" : ""}`}
              >
                {r.started_at} · {r.status} · {r.passed}/{r.total} passed · {r.model}
              </button>
            </li>
          ))}
        </ul>
      </section>

      {activeRunId && <RunResults key={activeRunId} runId={activeRunId} onFinished={refreshRuns} />}
    </div>
  );
}
