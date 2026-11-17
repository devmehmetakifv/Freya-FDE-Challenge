"use client";

import { useEffect, useState } from "react";
import { errorText, fetchJson } from "@/lib/api";
import type { RunDetail, ScenarioResult } from "@/lib/types";
import { ErrorNote, OutcomeBadge, Table, Td } from "./ui";

const POLL_MS = 2000;

// Results of one simulation run, refreshed every 2s while the run is still going.
export default function RunResults({ runId, onFinished }: { runId: string; onFinished: () => void }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll until the run leaves "running"; then tell the parent so the runs list updates.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let sawRunning = false;

    async function poll() {
      try {
        const detail = await fetchJson<RunDetail>(`/api/sim/runs/${encodeURIComponent(runId)}`);
        if (cancelled) return;
        setRun(detail);
        setError(null);
        if (detail.status === "running") {
          sawRunning = true;
          timer = setTimeout(poll, POLL_MS);
        } else if (sawRunning) {
          onFinished();
        }
      } catch (err) {
        if (!cancelled) setError(errorText(err));
      }
    }

    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId, onFinished]);

  if (error) return <ErrorNote message={error} />;
  if (!run) return <p className="text-sm text-zinc-500">Loading run…</p>;

  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-semibold">
        Run {run.run_id} · {run.status} · {run.passed}/{run.total} passed · {run.model}
      </h2>
      <ScenarioSummary results={run.results} />
      <div className="flex flex-col gap-2">
        {run.results.map((r) => (
          <ResultDetails key={`${r.scenario_id}-${r.attempt}`} result={r} />
        ))}
      </div>
    </section>
  );
}

// Pass rate per scenario across its attempts.
function ScenarioSummary({ results }: { results: ScenarioResult[] }) {
  const byScenario = new Map<string, { title: string; passed: number; total: number }>();
  for (const r of results) {
    const row = byScenario.get(r.scenario_id) ?? { title: r.title, passed: 0, total: 0 };
    byScenario.set(r.scenario_id, { ...row, passed: row.passed + (r.passed ? 1 : 0), total: row.total + 1 });
  }

  return (
    <Table headers={["Scenario", "Passed", "Pass rate"]}>
      {[...byScenario.entries()].map(([id, row]) => (
        <tr key={id}>
          <Td>{row.title}</Td>
          <Td>
            {row.passed}/{row.total}
          </Td>
          <Td>
            <span className={row.passed === row.total ? "text-green-700" : "text-red-700"}>
              {Math.round((row.passed / row.total) * 100)}%
            </span>
          </Td>
        </tr>
      ))}
    </Table>
  );
}

// One attempt, collapsed to a pass/fail line; expands to checks, persona and transcript.
function ResultDetails({ result }: { result: ScenarioResult }) {
  return (
    <details className="rounded border border-zinc-200 px-3 py-2 text-sm">
      <summary className="cursor-pointer">
        <span className={result.passed ? "text-green-700" : "text-red-700"}>{result.passed ? "✓ PASS" : "✗ FAIL"}</span>{" "}
        {result.title} (attempt {result.attempt}) · <OutcomeBadge outcome={result.outcome} /> · {result.turns} turns ·{" "}
        {(result.duration_ms / 1000).toFixed(1)}s
      </summary>
      <div className="mt-3 flex flex-col gap-3">
        <ul className="flex flex-col gap-1">
          {result.checks.map((c) => (
            <li key={c.name}>
              <span className={c.passed ? "text-green-700" : "text-red-700"}>{c.passed ? "✓" : "✗"}</span>{" "}
              <strong>{c.name}</strong> <span className="text-zinc-600">{c.detail}</span>
            </li>
          ))}
        </ul>
        <div>
          <h3 className="font-medium">Persona</h3>
          <p className="whitespace-pre-wrap text-zinc-700">{result.persona}</p>
        </div>
        <div>
          <h3 className="font-medium">Transcript</h3>
          {result.transcript.map((t, i) => (
            <p key={i} className={t.role === "tool" ? "font-mono text-xs text-zinc-500" : ""}>
              <span className="font-medium">{t.role}:</span> {t.text}
            </p>
          ))}
        </div>
      </div>
    </details>
  );
}
