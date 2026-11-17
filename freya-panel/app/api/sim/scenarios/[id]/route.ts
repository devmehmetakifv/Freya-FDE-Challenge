import { proxyJson } from "@/lib/proxy";

type Ctx = RouteContext<"/api/sim/scenarios/[id]">;

// Replace one scenario; the sim server checks that the body id matches the path id.
export async function PUT(req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const body = await req.text();
  return proxyJson("sim", `/scenarios/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

// Delete one scenario; success is an empty 204 that proxyJson passes through.
export async function DELETE(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  return proxyJson("sim", `/scenarios/${encodeURIComponent(id)}`, { method: "DELETE" });
}
