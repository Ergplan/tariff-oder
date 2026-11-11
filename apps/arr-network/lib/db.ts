// One pooled Postgres client for the whole app (server only).  Works with Neon (pooled
// connection strings: prepared statements are off) and with a local Postgres 16 + pgvector.
import postgres from "postgres";
import { MIGRATIONS } from "./migrations.generated.ts";

export type Sql = postgres.Sql<{}>;

// NUMERIC and BIGINT come back as JS numbers: the app shows crore figures with two decimals
// and counts; neither approaches 2^53.
const types = {
  numeric: { to: 1700, from: [1700], serialize: (x: unknown) => String(x), parse: (x: string) => Number(x) },
  bigint: { to: 20, from: [20], serialize: (x: unknown) => String(x), parse: (x: string) => Number(x) },
};

function make(url: string, max: number): Sql {
  return postgres(url, {
    max,
    prepare: false,
    idle_timeout: 20,
    connect_timeout: 5,
    onnotice: () => {},
    types,
  }) as unknown as Sql;
}

const g = globalThis as unknown as { __arrSql?: Sql | null; __arrSqlRo?: Sql | null };

/** The read-write client, or null when DATABASE_URL is not set. */
export function db(): Sql | null {
  const url = process.env.DATABASE_URL;
  if (!url) return null;
  if (!g.__arrSql) g.__arrSql = make(url, Number(process.env.DATABASE_POOL_MAX || 5));
  return g.__arrSql;
}

/** The client for visitor-written SQL: DATABASE_URL_READONLY when set, else the main one. */
export function dbReadonly(): Sql | null {
  const url = process.env.DATABASE_URL_READONLY;
  if (!url) return db();
  if (!g.__arrSqlRo) g.__arrSqlRo = make(url, 3);
  return g.__arrSqlRo;
}

/** Is this error the database being absent or unreachable (rather than a bug)? */
export function isConnectionError(e: unknown): boolean {
  const err = e as { code?: string; errno?: string; message?: string };
  const code = String(err?.code || err?.errno || "");
  return (
    /^(ECONNREFUSED|ENOTFOUND|ETIMEDOUT|ECONNRESET|EAI_AGAIN|CONNECT_TIMEOUT|CONNECTION_CLOSED|CONNECTION_ENDED|CONNECTION_DESTROYED|57P01|57P03|28P01|28000|3D000)$/.test(code) ||
    /connect|timeout|getaddrinfo/i.test(String(err?.message || ""))
  );
}

export type Loaded<T> = { ok: true; data: T } | { ok: false; reason: "not_configured" | "unreachable" | "not_migrated"; detail: string };

/** Run a page's queries; turn an absent or unreachable database into a value, not a crash. */
export async function load<T>(fn: (sql: Sql) => Promise<T>): Promise<Loaded<T>> {
  const sql = db();
  if (!sql) return { ok: false, reason: "not_configured", detail: "DATABASE_URL is not set." };
  try {
    return { ok: true, data: await fn(sql) };
  } catch (e) {
    const err = e as { code?: string; message?: string };
    if (err?.code === "42P01") return { ok: false, reason: "not_migrated", detail: "The schema has not been applied (POST /api/ingest/migrate)." };
    if (isConnectionError(e)) return { ok: false, reason: "unreachable", detail: "The database could not be reached." };
    throw e;
  }
}

const LOCK = 727_310_001; // advisory lock key for migrations

/** Apply pending migrations in order, each in its own transaction; returns the versions applied. */
export async function migrate(sql: Sql): Promise<{ applied: string[]; current: string | null }> {
  const applied: string[] = [];
  for (const m of MIGRATIONS) {
    const did = await sql.begin(async (tx) => {
      await tx`SELECT pg_advisory_xact_lock(${LOCK})`;
      const [{ exists }] = await tx`SELECT to_regclass('public.schema_migrations') IS NOT NULL AS exists`;
      if (exists) {
        const seen = await tx`SELECT 1 FROM schema_migrations WHERE version = ${m.version}`;
        if (seen.length) return false;
      }
      await tx.unsafe(m.sql);
      await tx`INSERT INTO schema_migrations (version) VALUES (${m.version}) ON CONFLICT (version) DO NOTHING`;
      return true;
    });
    if (did) applied.push(m.version);
  }
  const rows = await sql`SELECT max(version) AS v FROM schema_migrations`;
  return { applied, current: (rows[0]?.v as string) ?? null };
}

export const MIGRATION_VERSIONS = MIGRATIONS.map((m) => m.version);
