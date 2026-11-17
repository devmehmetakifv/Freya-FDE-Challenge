# PROGRESS

Status and decision log for the Freya (YC S25) FDE challenge. Newest log entries on top.
Entries carry a time (HH:MM, local) because the challenge asks us to note when the plan changes.

## Current status
- **Clock:** 2-hour development recording started 16:44 → hard stop **18:44**.
- **Phase:** Build. Step 1/4 (slot service) done. Next: agent core + voice bot.
- **Build order:** 1) slot service → 2) agent core + voice bot → 3) simulation → 4) panel.

## Open questions
- Policy rules still to decide: what to offer when no slot fits (Kadıköy overflow), address-change
  requests, callback handling.
- Assistant language: Turkish (assumed).

## Edge cases
Realistic edge cases only. Status: `handled+tested` / `left out (why)` / `open`.

| Edge case | Area | Status | Test |
|---|---|---|---|
| Wrong birth date 3 times → call locked, outcome `verification_failed` | service | handled+tested | `test_three_wrong_birth_dates_lock_the_call` |
| Malformed date (e.g. "14 Mart") doesn't burn an attempt | service | handled+tested | `test_malformed_birth_date_is_422_and_costs_no_attempt` |
| Slots/booking requested before identity check | service | handled+tested | `test_slots_and_booking_refused_before_verification` |
| Slot from another district | service | handled+tested | `test_booking_slot_in_another_district_is_rejected` |
| Kadıköy overflow: 3rd customer, no seats left | service | handled+tested | `test_kadikoy_overflow_third_customer_gets_no_slots` |
| Two calls racing for the last seat | service | handled+tested | `test_concurrent_calls_cannot_overbook_the_last_seat` |
| Customer changes mind mid-call (re-book) | service | handled+tested | `test_rebooking_moves_the_booking_and_releases_old_seat` |
| Same slot booked twice (retry) | service | handled+tested | `test_booking_same_slot_twice_is_idempotent` |
| Birth date / phone never sent to the LLM or panel | service | handled+tested | `test_open_call_returns_greeting_data_without_pii`, `test_customers_list_has_no_birth_dates` |
| Agent claims "booked" without a booking | service | handled+tested | `test_unknown_outcome_and_booked_outcome_are_rejected` |
| Customer silent → ask once, then `no_response` + hang up | bot | handled (idle timer 8s), voice-tested manually | `test_every_agent_outcome_is_accepted_by_service` (outcome only) |
| Slot service down mid-call → agent told, no crash | agent | handled+tested | `test_service_down_is_reported_not_raised` |
| Service refusal (not verified, bad date) reaches LLM as data | agent | handled+tested | `test_service_errors_become_error_dicts` |
| Phone number never answered at all (no pickup) | dialer | left out: needs real telephony; dialer would record it without the LLM | — |

## Decision log

### 2026-11-17 17:25 — Agent core + voice bot done (step 2/4)
- `agent/`: Turkish system prompt + tool specs + `CallSession` executor, shared by bot and simulator.
  The LLM never sees `call_id`, birth date or phone.
- `bot/bot.py`: Pipecat 1.16 pipeline: SmallWebRTC → Silero VAD → ElevenLabs Realtime STT (tr) →
  Claude (`AGENT_BRAIN_MODEL`) → ElevenLabs TTS `eleven_flash_v2_5` (tr). Outbound call simulated:
  customer "picks up" with "Alo?", agent opens. `end_call` ends the worker after the goodbye.
- **Rules added by us (in the prompt):** no proxy recipients; no address change by phone
  (`needs_human`); no slot fits → `no_suitable_slot` + bank calls back with next plan; gender-neutral
  address (full name, no Hanım/Bey unless the customer uses it). Bank name: "Nova Bank" (fictional).
- 24 tests green, ruff clean. Service + bot smoke-started (ports 8000 / 7860).

### 2026-11-17 17:20 — `no_response` outcome (user's idea)
- **Decision (user):** Add `no_response` for a customer who doesn't respond.
- Voice: silence produces no transcript, so Pipecat's `user_idle_timeout` (8s) injects a silence
  marker; prompt says ask "Beni duyabiliyor musunuz?" once, then record `no_response` and hang up.

### 2026-11-17 17:22 — ElevenLabs "audio effects" (phone filter + call-center noise): parked
- Research: `audio_effects` exists on ElevenLabs HTTP TTS endpoints, **not** on the WebSocket
  `multi-stream-input` that Pipecat's `ElevenLabsTTSService` uses. Alternative: Pipecat
  `audio_out_filter` (custom band-pass, needs scipy) + `SoundfileMixer` (call-center loop file).
- Parked as polish; revisit if time remains.

### 2026-11-17 17:15 — Slot service done (step 1/4)
- FastAPI + SQLite (`service/`): call-scoped flow `open → verify → slots → book → outcome`, plus
  panel reads `/customers`, `/slots`, `/calls`. 16 pytest tests green, ruff clean.
- **Rules added by us:** 3 birth-date attempts per call; re-booking moves the booking; a customer
  holds at most one booking; outcome `booked` can only be set by an actual booking.

### 2026-11-17 17:07 — Models, env, panel data path
- **Decision (user):** Agent brain = **Claude Haiku 5.5** (`AGENT_BRAIN_MODEL`), later compare with
  **Opus 5.5** (Haiku measured fastest, then Opus, Sonnet slowest). Simulated customer: Haiku 5.5.
- **Decision (user):** Panel reads data **only through the FastAPI service**, never the SQLite file.
- **Decision (user):** Call test section uses the Pipecat JS client against the bot.
- Env vars: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `AGENT_BRAIN_MODEL`,
  `SIM_CUSTOMER_MODEL`, `SLOT_SERVICE_URL`, `BANK_DB_PATH` (see `.env.example`).

### 2026-11-17 16:58 — Add a Next.js panel and a simulation test module (direction change)
- **Decision (user):** Build a one-page Next.js panel (`npx create-next-app@latest freya-panel --yes`)
  with three sections: **Call test** (talk to the voice bot), **Simulation** (run and view simulated
  customer scenarios), **Customers** (customer/slot/booking data from the local SQLite DB).
- **Decision (user):** Build a simulation test suite: simulated customers in different scenarios,
  used to evaluate how well the agent performs.
- **Why:** Measurable evaluation of the agent ("how did you measure that it works" is a required
  video topic) and a single place to demo everything.
- **Changes:** Earlier recommendation of "no web panel" (16:53) is overridden.

### 2026-11-17 16:53 — Proposed architecture (bot → slot service → SQLite)
- Proposed: Pipecat bot calls a FastAPI slot service over HTTP; service owns SQLite; call-scoped
  endpoints so booking is refused until the call passed the DOB check; atomic booking SQL.

### 2026-11-17 16:48 — Own voice pipeline instead of the Freya platform
- **Decision (user):** Build our own pipeline: **Pipecat** for orchestration, **Claude (Anthropic API)**
  as the LLM, **ElevenLabs** for STT (Scribe realtime) and TTS.
- **Why:** Full control and ownership of the code, testable locally, no dependency on waiting for a
  Freya account. Cost of Anthropic/ElevenLabs is ours (user has access).
- **Checked in docs:** Pipecat has `ElevenLabsRealtimeSTTService` (language configurable, Turkish
  supported), ElevenLabs TTS, and `AnthropicLLMService` with function calling and an `effort` setting.
- **Pending:** Claude model choice, demo transport, slot service shape.

### 2026-11-17 16:44 — Development clock started
- Screen recording on. 2-hour limit means a hard stop at 18:44, finished or not.

### 2026-11-17 16:41 — Edge cases are first-class
- **Decision:** Think through realistic edge cases for every service and flow, discuss them, cover
  them in tests, and track them in the Edge cases table above.
- **Why:** User's instruction. A voice agent pipeline has many edge cases, and the video must cover
  what we knowingly left out.

### 2026-11-17 16:38 — Git and code style
- **Decision:** GitHub for source; commit and push as we go, with a quick `git diff` review before each commit.
- **Decision:** A short intent comment above each code block.
- **Why:** User's instructions.

### 2026-11-17 16:36 — Kickoff
- **Decision:** User owns core decisions; Claude operates/implements and maintains `CHALLENGE.md`,
  `PROGRESS.md`, and project memory.
- **Decision:** Every service/functionality ships with a test script. Avoid overengineering.
- **Why:** User's kickoff instructions.
