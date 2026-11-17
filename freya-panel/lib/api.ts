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
  if (body.detail !== undefined) return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  return null;
}

// Render any thrown value as a short message for the UI.
export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
