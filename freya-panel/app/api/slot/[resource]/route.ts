import { proxyJson } from "@/lib/proxy";

// Read-only views of the slot service the panel is allowed to show.
const RESOURCES = new Set(["customers", "slots", "calls"]);

export async function GET(_req: Request, ctx: RouteContext<"/api/slot/[resource]">) {
  const { resource } = await ctx.params;
  if (!RESOURCES.has(resource)) return Response.json({ error: "Unknown resource" }, { status: 404 });
  return proxyJson("slot", `/${resource}`);
}
