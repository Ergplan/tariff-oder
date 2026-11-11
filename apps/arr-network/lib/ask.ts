import { dbReadonly, type Sql } from "./db.ts";
import { checkSelect } from "./sqlguard.ts";
import { currentFy, type Vocab } from "./nl2sql.ts";

export const ROW_CAP = 2000;
export const TIMEOUT_MS = 5000;

export async function loadVocab(sql: Sql, today = new Date()): Promise<Vocab> {
  const [utilities, commissions, states, latest] = await Promise.all([
    sql`SELECT u.code, u.name, u.aliases, u.state, s.name AS state_name, u.commission, u.kind
        FROM utilities u JOIN states s ON s.code = u.state ORDER BY u.code`,
    sql`SELECT code, name FROM commissions ORDER BY code`,
    sql`SELECT code, name FROM states ORDER BY code`,
    sql`SELECT max(arr_year) AS y FROM orders WHERE read_status = 'read' AND arr_year <= ${currentFy(today)}`,
  ]);
  return {
    utilities: utilities.map((u) => ({
      code: u.code as string, name: u.name as string, aliases: (u.aliases as string[]) ?? [], state: u.state as string,
      state_name: u.state_name as string, commission: u.commission as string, kind: u.kind as string,
    })),
    commissions: commissions.map((c) => ({ code: c.code as string, name: c.name as string })),
    states: states.map((s) => ({ code: s.code as string, name: s.name as string })),
    latestYear: (latest[0]?.y as string) || currentFy(today),
  };
}

export type RunResult =
  | { ok: true; rows: Record<string, unknown>[]; columns: string[]; capped: boolean; ms: number }
  | { ok: false; error: string };

/** Run one SELECT in a READ ONLY transaction with a 5 s timeout, returning at most 2,000 rows. */
export async function runReadOnly(input: string): Promise<RunResult> {
  const c = checkSelect(input);
  if (!c.ok) return { ok: false, error: c.reason };
  const sql = dbReadonly();
  if (!sql) return { ok: false, error: "Database not connected." };
  const t0 = Date.now();
  try {
    const rows = await sql.begin("READ ONLY", async (tx) => {
      await tx.unsafe(`SET LOCAL statement_timeout = ${TIMEOUT_MS}`);
      await tx.unsafe("SET LOCAL idle_in_transaction_session_timeout = 10000");
      // extended protocol (simple: false): the server refuses more than one statement
      return tx.unsafe(`SELECT * FROM (\n${c.sql}\n) AS answer LIMIT ${ROW_CAP + 1}`, [], { simple: false });
    });
    const list = [...rows] as Record<string, unknown>[];
    const columns = rows.columns ? rows.columns.map((x: { name: string }) => x.name) : list[0] ? Object.keys(list[0]) : [];
    return { ok: true, rows: list.slice(0, ROW_CAP), columns, capped: list.length > ROW_CAP, ms: Date.now() - t0 };
  } catch (e) {
    const err = e as { code?: string; message?: string };
    if (err.code === "57014") return { ok: false, error: `The query took longer than ${TIMEOUT_MS / 1000} s and was stopped.` };
    if (err.code === "25006") return { ok: false, error: "Only reading is allowed here." };
    return { ok: false, error: `SQL error: ${err.message ?? String(e)}` };
  }
}
