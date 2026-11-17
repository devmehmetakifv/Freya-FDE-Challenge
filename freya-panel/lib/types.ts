// Response shapes of the three local backends, kept in one place so the UI and proxies agree.

// Slot service (FastAPI, SLOT_SERVICE_URL)
export interface Customer {
  id: number;
  full_name: string;
  phone: string;
  district: string;
  address_type: "home" | "work";
  day: string | null;
  start_time: string | null;
  end_time: string | null;
  last_outcome: string | null;
  // Every outcome logged on the customer's latest call, oldest first.
  // Optional: a slot service older than the outcome log doesn't send it.
  last_outcomes?: string[];
}

// One entry of a call's outcome log; a call can have several (e.g. needs_human + no_suitable_slot).
export interface CallOutcome {
  outcome: string;
  note: string | null;
  created_at: string;
}

export interface Slot {
  slot_id: number;
  district: string;
  day: string;
  start_time: string;
  end_time: string;
  remaining: number;
  capacity: number;
}

export interface Call {
  call_id: number;
  customer_id: number;
  full_name: string;
  verified: 0 | 1;
  failed_attempts: number;
  outcome: string | null;
  note: string | null;
  started_at: string;
  outcomes?: CallOutcome[];
}

// Simulation server (FastAPI, SIM_SERVICE_URL)
// A seat booked before the simulated call starts: (customer_id, slot_id).
export type SetupBooking = [number, number];

export interface Scenario {
  id: string; // ^[a-z0-9_]{3,40}$, immutable after create
  title: string;
  description: string;
  customer_id: number;
  situation: string; // instructions for the simulated customer
  expected_outcomes: string[];
  allowed_slots: number[]; // non-empty iff "booked" is an expected outcome
  setup_bookings: SetupBooking[];
  is_cardholder: boolean;
}

// GET /meta on the simulation server: option lists for the scenario form.
export interface SimMeta {
  outcomes: string[];
  customers: Pick<Customer, "id" | "full_name" | "district">[];
  slots: Omit<Slot, "remaining" | "capacity">[];
}

export type RunStatus = "running" | "done" | "failed";

export interface RunSummary {
  run_id: string;
  status: RunStatus;
  started_at: string;
  model: string;
  total: number;
  passed: number;
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface TranscriptTurn {
  role: "agent" | "customer" | "tool";
  text: string;
}

export interface ScenarioResult {
  scenario_id: string;
  title: string;
  attempt: number;
  passed: boolean;
  outcome: string | null;
  turns: number;
  duration_ms: number;
  persona: string;
  checks: Check[];
  transcript: TranscriptTurn[];
}

export interface RunDetail extends RunSummary {
  results: ScenarioResult[];
}

// Body of POST /runs on the simulation server.
export interface StartRunRequest {
  scenario_ids: string[] | null;
  runs_per_scenario: number;
}

// Error body our route handlers return when a backend is down or replies with an error.
export interface ProxyError {
  error: string;
}
