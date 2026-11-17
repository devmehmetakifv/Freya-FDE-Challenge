"use client";

import { useEffect, useState } from "react";
import { errorText, fetchJson } from "@/lib/api";
import { addressLabel, slotLabel } from "@/lib/format";
import type { Call, CallOutcome, Customer, Slot } from "@/lib/types";
import { Button, ErrorNote, OutcomeBadge, Table, Td } from "./ui";

interface SlotData {
  customers: Customer[];
  slots: Slot[];
  calls: Call[];
}

// Load all three lists together through our /api/slot proxy.
async function fetchSlotData(): Promise<SlotData> {
  const [customers, slots, calls] = await Promise.all([
    fetchJson<Customer[]>("/api/slot/customers"),
    fetchJson<Slot[]>("/api/slot/slots"),
    fetchJson<Call[]>("/api/slot/calls"),
  ]);
  return { customers, slots, calls };
}

// Live view of the slot service: customers, slot capacity and recent calls.
export default function CustomersTab() {
  const [data, setData] = useState<SlotData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Refetch on mount and whenever Refresh bumps the key.
  useEffect(() => {
    fetchSlotData()
      .then((next) => {
        setData(next);
        setError(null);
      })
      .catch((err) => setError(errorText(err)));
  }, [reloadKey]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button onClick={() => setReloadKey((k) => k + 1)}>Refresh</Button>
      </div>
      {error && <ErrorNote message={error} />}
      {!data && !error && <p className="text-sm text-zinc-500">Loading…</p>}
      {data && (
        <>
          <CustomersTable customers={data.customers} />
          <SlotsTable slots={data.slots} />
          <CallsTable calls={data.calls} />
        </>
      )}
    </div>
  );
}

function CustomersTable({ customers }: { customers: Customer[] }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">Customers</h2>
      <Table headers={["Name", "Phone", "District", "Address", "Booked slot", "Last call outcomes"]}>
        {customers.map((c) => (
          <tr key={c.id}>
            <Td>{c.full_name}</Td>
            <Td>{c.phone}</Td>
            <Td>{c.district}</Td>
            <Td>{addressLabel(c.address_type)}</Td>
            <Td>{slotLabel(c.day, c.start_time, c.end_time)}</Td>
            <Td>
              {/* Show every outcome of the latest call so a needs_human is never hidden. */}
              {c.last_outcomes.length === 0 ? (
                <OutcomeBadge outcome={null} />
              ) : (
                <div className="flex flex-wrap gap-1">
                  {c.last_outcomes.map((o, i) => (
                    <OutcomeBadge key={i} outcome={o} />
                  ))}
                </div>
              )}
            </Td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

function SlotsTable({ slots }: { slots: Slot[] }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">Slots</h2>
      <Table headers={["District", "Day", "Window", "Remaining / capacity"]}>
        {slots.map((s) => (
          <tr key={s.slot_id}>
            <Td>{s.district}</Td>
            <Td>{s.day}</Td>
            <Td>
              {s.start_time}-{s.end_time}
            </Td>
            <Td>
              <span className={s.remaining === 0 ? "text-red-700" : ""}>
                {s.remaining} / {s.capacity}
              </span>
            </Td>
          </tr>
        ))}
      </Table>
    </section>
  );
}

// A call's outcome log: one badge + note per recorded outcome, in the order they happened.
function OutcomeLog({ outcomes }: { outcomes: CallOutcome[] }) {
  if (outcomes.length === 0) return <OutcomeBadge outcome={null} />;
  return (
    <ul className="flex flex-col gap-1">
      {outcomes.map((o, i) => (
        <li key={i} className="flex flex-col gap-0.5">
          <OutcomeBadge outcome={o.outcome} />
          {o.note && <span className="text-xs text-zinc-600">{o.note}</span>}
        </li>
      ))}
    </ul>
  );
}

function CallsTable({ calls }: { calls: Call[] }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">Recent calls</h2>
      {calls.length === 0 && <p className="text-sm text-zinc-500">No calls yet.</p>}
      {calls.length > 0 && (
        <Table headers={["ID", "Name", "Verified", "Failed attempts", "Outcomes (oldest first)", "Time"]}>
          {calls.map((k) => (
            <tr key={k.call_id}>
              <Td>{k.call_id}</Td>
              <Td>{k.full_name}</Td>
              <Td>{k.verified ? "Yes" : "No"}</Td>
              <Td>{k.failed_attempts}</Td>
              <Td>
                <OutcomeLog outcomes={k.outcomes} />
              </Td>
              <Td>{k.started_at}</Td>
            </tr>
          ))}
        </Table>
      )}
    </section>
  );
}
