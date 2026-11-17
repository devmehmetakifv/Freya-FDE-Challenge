import { proxyJson } from "@/lib/proxy";

// One run with its per-scenario results (they fill in while the run is still going).
export async function GET(_req: Request, ctx: RouteContext<"/api/sim/runs/[id]">) {
  const { id } = await ctx.params;
  return proxyJson("sim", `/runs/${encodeURIComponent(id)}`);
}
