import { connection } from "next/server";
import type { ProxyError } from "./types";

// Which backend a route handler forwards to; the base URL stays on the server.
type Backend = "slot" | "sim";

const BACKENDS: Record<Backend, { label: string; env: string }> = {
  slot: { label: "Slot service", env: "SLOT_SERVICE_URL" },
  sim: { label: "Simulation server", env: "SIM_SERVICE_URL" },
};

const REQUEST_TIMEOUT_MS = 5000;

function errorResponse(message: string, status: number): Response {
  const body: ProxyError = { error: message };
  return Response.json(body, { status });
}

// Forward one JSON request to a backend and pass its reply through.
// A down backend becomes a readable 502 message instead of a thrown error.
export async function proxyJson(backend: Backend, path: string, init?: RequestInit): Promise<Response> {
  // Always run at request time: backend data is live and must never be prerendered.
  await connection();

  const { label, env } = BACKENDS[backend];
  const baseUrl = process.env[env];
  if (!baseUrl) return errorResponse(`${label} URL not configured (${env})`, 500);

  let upstream: Response;
  try {
    upstream = await fetch(`${baseUrl}${path}`, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    return errorResponse(`${label} unreachable at ${baseUrl}`, 502);
  }

  // Keep the backend's status; surface its error text if the body is not JSON.
  const text = await upstream.text();
  try {
    return Response.json(JSON.parse(text), { status: upstream.status });
  } catch {
    return errorResponse(`${label} error ${upstream.status}: ${text.slice(0, 200)}`, upstream.status || 502);
  }
}
