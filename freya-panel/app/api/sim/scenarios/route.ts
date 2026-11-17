import { proxyJson } from "@/lib/proxy";

// List the simulation scenarios the user can pick from.
export async function GET() {
  return proxyJson("sim", "/scenarios");
}
