import { ingestGuard, dbError } from "@/lib/ingest/http.ts";
import { migrate } from "@/lib/db.ts";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: Request) {
  const g = await ingestGuard(req, false);
  if (g instanceof Response) return g;
  try {
    return Response.json(await migrate(g.sql));
  } catch (e) {
    return dbError(e);
  }
}
