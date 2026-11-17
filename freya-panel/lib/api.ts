// Browser-side helpers for calling our own route handlers (/api/...).

// Fetch JSON and turn a non-2xx reply into an Error carrying the handler's message.
export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: "no-store", ...init });
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new Error(readError(data) ?? `Request failed (${res.status})`);
  return data as T;
}

// Read the message out of {error} (our proxy) or {detail} (FastAPI validation errors).
function readError(data: unknown): string | null {
  if (typeof data !== "object" || data === null) return null;
  const body = data as { error?: unknown; detail?: unknown };
  if (typeof body.error === "string") return body.error;
  if (Array.isArray(body.detail)) return body.detail.map(validationMessage).join("; ");
  if (body.detail !== undefined) return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  return null;
}

// FastAPI 422 items look like {loc: ["body", "title"], msg: "..."}; show "title: msg".
function validationMessage(item: unknown): string {
  if (typeof item !== "object" || item === null) return String(item);
  const { loc, msg } = item as { loc?: unknown; msg?: unknown };
  if (typeof msg !== "string") return JSON.stringify(item);
  const field = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
  return field ? `${field}: ${msg}` : msg;
}

// Render any thrown value as a short message for the UI.
export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
