import { proxyJson } from "@/lib/proxy";

// List the simulation scenarios the user can pick from.
export async function GET() {
  return proxyJson("sim", "/scenarios");
}

// Create a scenario; the sim server validates the body and replies 409 if the id is taken.
export async function POST(req: Request) {
  const body = await req.text();
  return proxyJson("sim", "/scenarios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
