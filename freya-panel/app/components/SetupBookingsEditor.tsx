import type { SetupBooking, SimMeta } from "@/lib/types";
import { Button } from "./ui";

const SELECT_CLASS = "rounded border border-zinc-300 px-2 py-1 text-sm";

// Editable list of (customer, slot) seats booked before the call, e.g. to make a slot full.
export default function SetupBookingsEditor({
  bookings,
  meta,
  onChange,
}: {
  bookings: SetupBooking[];
  meta: SimMeta;
  onChange: (next: SetupBooking[]) => void;
}) {
  // Replace one side of one pair, leaving the rest of the list untouched.
  function setAt(index: number, part: 0 | 1, value: number) {
    onChange(bookings.map((b, i) => (i !== index ? b : part === 0 ? [value, b[1]] : [b[0], value])));
  }

  // New rows start on the first customer and slot; the user then picks the real ones.
  function add() {
    const first: SetupBooking = [meta.customers[0]?.id ?? 0, meta.slots[0]?.slot_id ?? 0];
    onChange([...bookings, first]);
  }

  return (
    <div className="flex flex-col gap-2">
      {bookings.length === 0 && <p className="text-sm text-zinc-500">None.</p>}
      {bookings.map(([customerId, slotId], i) => (
        <div key={i} className="flex flex-wrap items-center gap-2">
          <select className={SELECT_CLASS} value={customerId} onChange={(e) => setAt(i, 0, Number(e.target.value))}>
            {meta.customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.full_name} — {c.district}
              </option>
            ))}
          </select>
          <select className={SELECT_CLASS} value={slotId} onChange={(e) => setAt(i, 1, Number(e.target.value))}>
            {meta.slots.map((s) => (
              <option key={s.slot_id} value={s.slot_id}>
                {s.district} {s.day} {s.start_time}-{s.end_time}
              </option>
            ))}
          </select>
          <Button onClick={() => onChange(bookings.filter((_, j) => j !== i))}>Remove</Button>
        </div>
      ))}
      <div>
        <Button onClick={add} disabled={meta.customers.length === 0 || meta.slots.length === 0}>
          Add booking
        </Button>
      </div>
    </div>
  );
}
