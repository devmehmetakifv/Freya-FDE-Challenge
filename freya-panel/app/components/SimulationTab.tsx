"use client";

import { useCallback, useEffect, useState } from "react";
import { errorText, fetchJson } from "@/lib/api";
import type { RunSummary, Scenario, StartRunRequest } from "@/lib/types";
import RunResults from "./RunResults";
import ScenarioForm from "./ScenarioForm";
import { Button, ErrorNote } from "./ui";

const RUNS_PER_SCENARIO_OPTIONS = [1, 2, 3];

// Which scenario the form is open for: "new", an existing one, or closed (null).
type Editing = Scenario | "new" | null;

// Pick scenarios, start a simulated-customer run, and browse past runs.
export default function SimulationTab() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Track what the user unticked, so new scenarios start selected and deleted ones simply vanish.
  const [deselected, setDeselected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Editing>(null);
  const [scenariosKey, setScenariosKey] = useState(0);
  const reloadScenarios = useCallback(() => setScenariosKey((k) => k + 1), []);
  const [runsPerScenario, setRunsPerScenario] = useState(1);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runsKey, setRunsKey] = useState(0);
  const refreshRuns = useCallback(() => setRunsKey((k) => k + 1), []);

  const selectedIds = scenarios.map((s) => s.id).filter((id) => !deselected.has(id));

  // Scenario list: loaded on mount and again after a create, edit or delete.
  useEffect(() => {
    fetchJson<Scenario[]>("/api/sim/scenarios")
      .then(setScenarios)
      .catch((err) => setError(errorText(err)));
  }, [scenariosKey]);

  // Run history: reloaded on mount, on Refresh, after starting a run and when a run finishes.
  useEffect(() => {
    fetchJson<RunSummary[]>("/api/sim/runs")
      .then(setRuns)
      .catch((err) => setError(errorText(err)));
  }, [runsKey]);

  function toggle(id: string) {
    setDeselected((prev) => {
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
      scenario_ids: selectedIds.length === scenarios.length ? null : selectedIds,
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

  // Delete after a confirm; the reload drops it from the list and the run checklist.
  async function deleteScenario(s: Scenario) {
    if (!confirm(`Delete scenario "${s.title}" (${s.id})?`)) return;
    setError(null);
    try {
      await fetchJson<null>(`/api/sim/scenarios/${encodeURIComponent(s.id)}`, { method: "DELETE" });
      reloadScenarios();
    } catch (err) {
      setError(errorText(err));
    }
  }

  // Form saved: close it and pick up the new or changed scenario.
  function onScenarioSaved() {
    setEditing(null);
    reloadScenarios();
  }

  return (
    <div className="flex flex-col gap-6">
      {error && <ErrorNote message={error} />}

      <section className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">Scenarios</h2>
          {editing === null && <Button onClick={() => setEditing("new")}>New scenario</Button>}
        </div>
        {editing !== null && (
          <ScenarioForm
            key={editing === "new" ? "new" : editing.id}
            initial={editing === "new" ? null : editing}
            onSaved={onScenarioSaved}
            onCancel={() => setEditing(null)}
          />
        )}
        {scenarios.map((s) => (
          <div key={s.id} className="flex items-start justify-between gap-2">
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={!deselected.has(s.id)} onChange={() => toggle(s.id)} />
              <span>
                <strong>{s.title}</strong> <span className="text-zinc-500">(customer #{s.customer_id})</span>
                <br />
                <span className="text-zinc-600">{s.description}</span>
              </span>
            </label>
            <div className="flex shrink-0 gap-2">
              <Button onClick={() => setEditing(s)}>Edit</Button>
              <Button onClick={() => void deleteScenario(s)}>Delete</Button>
            </div>
          </div>
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
          <Button primary onClick={() => void startRun()} disabled={selectedIds.length === 0}>
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
