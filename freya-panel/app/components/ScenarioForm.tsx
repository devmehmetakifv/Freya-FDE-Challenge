"use client";

import { useEffect, useState, type ReactNode } from "react";
import { errorText, fetchJson } from "@/lib/api";
import type { Scenario, SimMeta } from "@/lib/types";
import SetupBookingsEditor from "./SetupBookingsEditor";
import { Button, ErrorNote } from "./ui";

const INPUT_CLASS = "w-full rounded border border-zinc-300 px-2 py-1 text-sm disabled:bg-zinc-100";

// Starting point for a new scenario; customer_id 0 means "not picked yet".
const EMPTY_SCENARIO: Scenario = {
  id: "",
  title: "",
  description: "",
  customer_id: 0,
  situation: "",
  expected_outcomes: [],
  allowed_slots: [],
  setup_bookings: [],
  is_cardholder: false,
};

interface ScenarioFormProps {
  initial: Scenario | null; // null = create a new scenario
  onSaved: () => void;
  onCancel: () => void;
}

// Add the value if missing, drop it if present; returns a new array.
function toggleIn<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

// Labeled block so every field lines up the same way.
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
    </div>
  );
}

// Create (POST) or edit (PUT) one scenario; the sim server validates and its message is shown inline.
export default function ScenarioForm({ initial, onSaved, onCancel }: ScenarioFormProps) {
  const isNew = initial === null;
  // Merge onto the empty shape so a scenario missing newer fields still renders.
  const [draft, setDraft] = useState<Scenario>({ ...EMPTY_SCENARIO, ...initial });
  const [meta, setMeta] = useState<SimMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Dropdown and checkbox options come from the sim server's /meta.
  useEffect(() => {
    fetchJson<SimMeta>("/api/sim/meta")
      .then(setMeta)
      .catch((err) => setError(errorText(err)));
  }, []);

  function update<K extends keyof Scenario>(key: K, value: Scenario[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  // Send the whole scenario; on success the parent closes the form and reloads the list.
  async function save() {
    setError(null);
    setSaving(true);
    const url = isNew ? "/api/sim/scenarios" : `/api/sim/scenarios/${encodeURIComponent(draft.id)}`;
    try {
      await fetchJson<Scenario>(url, {
        method: isNew ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      onSaved();
    } catch (err) {
      setError(errorText(err));
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded border border-zinc-300 bg-zinc-50 p-4">
      <h3 className="font-semibold">{isNew ? "New scenario" : `Edit scenario ${draft.id}`}</h3>
      {error && <ErrorNote message={error} />}
      {!meta ? (
        <p className="text-sm text-zinc-500">{error ? "Form options unavailable." : "Loading form options…"}</p>
      ) : (
        <>
          <Field label="Id (a-z, 0-9, _; 3-40 chars; cannot change later)">
            <input className={INPUT_CLASS} value={draft.id} disabled={!isNew} onChange={(e) => update("id", e.target.value)} />
          </Field>
          <Field label="Title">
            <input className={INPUT_CLASS} value={draft.title} onChange={(e) => update("title", e.target.value)} />
          </Field>
          <Field label="Description">
            <input className={INPUT_CLASS} value={draft.description} onChange={(e) => update("description", e.target.value)} />
          </Field>
          <Field label="Customer">
            <select
              className={INPUT_CLASS}
              value={draft.customer_id}
              onChange={(e) => update("customer_id", Number(e.target.value))}
            >
              <option value={0} disabled>
                Pick a customer…
              </option>
              {meta.customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name} — {c.district}
                </option>
              ))}
            </select>
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.is_cardholder} onChange={(e) => update("is_cardholder", e.target.checked)} />
            Cardholder
          </label>
          <Field label="Situation (instructions for the simulated customer)">
            <textarea
              className={INPUT_CLASS}
              rows={5}
              value={draft.situation}
              onChange={(e) => update("situation", e.target.value)}
            />
          </Field>
          <Field label="Expected outcomes (at least one)">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {meta.outcomes.map((o) => (
                <label key={o} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={draft.expected_outcomes.includes(o)}
                    onChange={() => update("expected_outcomes", toggleIn(draft.expected_outcomes, o))}
                  />
                  {o}
                </label>
              ))}
            </div>
          </Field>
          <Field label='Allowed slots (required if "booked" is expected, otherwise leave empty)'>
            <div className="flex max-h-48 flex-col gap-1 overflow-y-auto rounded border border-zinc-200 bg-white p-2">
              {meta.slots.map((s) => (
                <label key={s.slot_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={draft.allowed_slots.includes(s.slot_id)}
                    onChange={() => update("allowed_slots", toggleIn(draft.allowed_slots, s.slot_id))}
                  />
                  {s.district} {s.day} {s.start_time}-{s.end_time}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Setup bookings (seats taken before the call)">
            <SetupBookingsEditor
              bookings={draft.setup_bookings}
              meta={meta}
              onChange={(next) => update("setup_bookings", next)}
            />
          </Field>
        </>
      )}
      <div className="flex gap-2">
        <Button primary onClick={() => void save()} disabled={!meta || saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}
