import { proxyJson } from "@/lib/proxy";

// Outcomes, customers and slots the scenario form offers as choices.
export async function GET() {
  return proxyJson("sim", "/meta");
}
