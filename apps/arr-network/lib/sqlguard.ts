// Checks a visitor's SQL before it runs: one SELECT or WITH statement, nothing else.
// The database enforces the rest (READ ONLY transaction, statement_timeout, extended protocol
// that refuses a second statement); this check gives a readable reason first.

/** Remove string literals, quoted identifiers and comments, so the checks below see only SQL. */
export function stripLiterals(sql: string): string {
  let out = "";
  for (let i = 0; i < sql.length; ) {
    const c = sql[i], d = sql[i + 1];
    if (c === "-" && d === "-") { const j = sql.indexOf("\n", i); i = j < 0 ? sql.length : j; out += " "; continue; }
    if (c === "/" && d === "*") { const j = sql.indexOf("*/", i + 2); i = j < 0 ? sql.length : j + 2; out += " "; continue; }
    if (c === "'" || c === '"') {
      let j = i + 1;
      for (; j < sql.length; j++) { if (sql[j] === c) { if (sql[j + 1] === c) { j++; continue; } break; } }
      i = j + 1; out += c === "'" ? "''" : '""'; continue;
    }
    if (c === "$") {
      const m = /^\$([A-Za-z_][A-Za-z0-9_]*)?\$/.exec(sql.slice(i));
      if (m) { const j = sql.indexOf(m[0], i + m[0].length); i = j < 0 ? sql.length : j + m[0].length; out += "''"; continue; }
    }
    out += c; i++;
  }
  return out;
}

const FORBIDDEN = /\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze|cluster|reindex|lock|listen|notify|call|do|set|reset|discard|prepare|execute|deallocate|begin|commit|rollback|savepoint|release|refresh|comment|security|into)\b|\b(set_config|pg_sleep\w*|pg_read\w*|pg_ls_dir|pg_stat_file|lo_\w+|dblink\w*|pg_terminate_backend|pg_cancel_backend|pg_advisory\w*|txid_\w+|pg_reload_conf|pg_notify|query_to_xml\w*|xmlparse)\s*\(/i;

export function checkSelect(input: string): { ok: true; sql: string } | { ok: false; reason: string } {
  const sql = input.trim().replace(/;\s*$/, "");
  if (!sql) return { ok: false, reason: "No SQL to run." };
  if (sql.length > 20_000) return { ok: false, reason: "The SQL is longer than 20,000 characters." };
  const bare = stripLiterals(sql);
  if (!/^\s*\(?\s*(select|with)\b/i.test(bare)) return { ok: false, reason: "Only one SELECT (or WITH … SELECT) statement is run." };
  if (bare.includes(";")) return { ok: false, reason: "Only one statement is run: remove the semicolon in the middle." };
  const bad = FORBIDDEN.exec(bare);
  if (bad) return { ok: false, reason: `Only reading is allowed here; "${(bad[1] || bad[2]).toLowerCase()}" is not.` };
  return { ok: true, sql };
}
