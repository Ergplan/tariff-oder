import { api } from "@/lib/api.ts";
import { search } from "@/lib/search.ts";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const p = new URL(req.url).searchParams;
  const q = (p.get("q") ?? "").trim().slice(0, 300);
  if (!q) return Response.json({ error: "q is required" }, { status: 400 });
  const f = { state: p.get("state") || undefined, utility: p.get("utility") || undefined, year: p.get("year") || undefined, kind: p.get("kind") || undefined };
  return api(async (sql) => {
    const out = await search(sql, q, f);
    return { q, filters: f, ...out };
  });
}
