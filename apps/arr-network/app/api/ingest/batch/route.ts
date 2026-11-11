import { ingestGuard, dbError } from "@/lib/ingest/http.ts";
import { checkEnvelope } from "@/lib/ingest/validate.ts";
import { writeBatch } from "@/lib/ingest/write.ts";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(req: Request) {
  const g = await ingestGuard(req, true);
  if (g instanceof Response) return g;
  const env = checkEnvelope(g.json);
  if (!env.ok) return Response.json({ error: env.error }, { status: env.status });
  try {
    const { written, rejected } = await writeBatch(g.sql, env.kind, env.rows);
    return Response.json({ kind: env.kind, written, rejected });
  } catch (e) {
    return dbError(e);
  }
}
