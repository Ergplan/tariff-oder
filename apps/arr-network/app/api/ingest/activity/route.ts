// The database's own sessions, for the operator: which are running, waiting or holding an open
// transaction.  POST {"terminate": "stuck"} ends this database's sessions that have held a
// transaction open for more than 120 s (an ingest batch whose function was stopped mid-way
// keeps its locks until Postgres notices).  Guarded by the ingest token, like every ingest route.
import { ingestGuard, dbError } from "@/lib/ingest/http.ts";
import type { Sql } from "@/lib/db.ts";

export const dynamic = "force-dynamic";

async function sessions(sql: Sql) {
  return sql`
    SELECT pid, state, wait_event_type, wait_event,
           extract(epoch FROM now() - xact_start)::int AS xact_seconds,
           extract(epoch FROM now() - query_start)::int AS query_seconds,
           left(regexp_replace(query, '\\s+', ' ', 'g'), 160) AS query
      FROM pg_stat_activity
     WHERE datname = current_database() AND pid <> pg_backend_pid() AND backend_type = 'client backend'
     ORDER BY xact_start NULLS LAST`;
}

export async function GET(req: Request) {
  const g = await ingestGuard(req, false);
  if (g instanceof Response) return g;
  try {
    // the function-to-database round trip: five sequential trivial queries
    const times: number[] = [];
    for (let i = 0; i < 5; i++) {
      const t0 = performance.now();
      await g.sql`SELECT 1`;
      times.push(Math.round(performance.now() - t0));
    }
    return Response.json({ round_trip_ms: times, region: process.env.VERCEL_REGION ?? null, sessions: await sessions(g.sql) });
  } catch (e) {
    return dbError(e);
  }
}

export async function POST(req: Request) {
  const g = await ingestGuard(req, true);
  if (g instanceof Response) return g;
  if ((g.json as { terminate?: string })?.terminate !== "stuck")
    return Response.json({ error: 'body must be {"terminate": "stuck"}' }, { status: 400 });
  try {
    const ended = await g.sql`
      SELECT pid, pg_terminate_backend(pid) AS ended
        FROM pg_stat_activity
       WHERE datname = current_database() AND pid <> pg_backend_pid() AND backend_type = 'client backend'
         AND xact_start < now() - interval '120 seconds'`;
    return Response.json({ ended, sessions: await sessions(g.sql) });
  } catch (e) {
    return dbError(e);
  }
}
