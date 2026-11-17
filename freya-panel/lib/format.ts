import type { Customer } from "./types";

// Turkish label for the delivery address type.
export function addressLabel(type: Customer["address_type"]): string {
  return type === "home" ? "Ev" : "İş yeri";
}

// "Perşembe 09:00-13:00", or a dash when the customer has no booked slot.
export function slotLabel(day: string | null, start: string | null, end: string | null): string {
  if (!day || !start || !end) return "—";
  return `${day} ${start}-${end}`;
}

// Badge color by outcome: booked is success, identity problems are failures, the rest need follow-up.
export function outcomeColor(outcome: string): string {
  if (outcome === "booked") return "bg-green-100 text-green-800";
  if (outcome === "verification_failed" || outcome === "wrong_person") return "bg-red-100 text-red-800";
  return "bg-amber-100 text-amber-800";
}
