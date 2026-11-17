import { proxyJson } from "@/lib/proxy";

// List past and in-progress simulation runs, newest first.
export async function GET() {
  return proxyJson("sim", "/runs");
}

// Start a new run; the body ({scenario_ids, runs_per_scenario}) is validated by the sim server.
export async function POST(req: Request) {
  const body = await req.text();
  return proxyJson("sim", "/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
