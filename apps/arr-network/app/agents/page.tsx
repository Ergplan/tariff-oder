import { load } from "@/lib/db.ts";
import { fmtDate, fmtTime, count } from "@/lib/format.ts";
import { Markdown } from "@/lib/markdown.tsx";
import { DbDown } from "../ui.tsx";

export const dynamic = "force-dynamic";
export const metadata = { title: "Agents" };

type R = Record<string, unknown>;
const STATES = ["queued", "claimed", "done", "failed", "parked"];
const usd = (v: unknown) => "$" + Number(v ?? 0).toFixed(4);

function Runs({ rows, empty }: { rows: R[]; empty: string }) {
  if (!rows.length) return <p className="note">{empty}</p>;
  return (
    <div className="tablewrap">
      <table>
        <thead><tr><th>Agent</th><th>Version</th><th>Last run</th><th>Outcome</th><th className="num">Runs</th><th className="num">Rows written</th><th className="num">Rejected</th><th>Provider / model</th><th className="num">Cost</th><th>Note</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td><b>{r.agent as string}</b></td>
              <td className="mono">{r.version as string}</td>
              <td className="mono" style={{ fontSize: "0.76rem" }}>{fmtTime(r.started_at)}</td>
              <td>{r.outcome as string}</td>
              <td className="num">{count(r.runs)}</td>
              <td className="num">{count(r.rows_written)}</td>
              <td className="num">{count(r.rows_rejected)}</td>
              <td>{[r.provider, r.model].filter(Boolean).join(" / ") || "—"}</td>
              <td className="num">{usd(r.cost_usd)}</td>
              <td className="note" style={{ marginTop: 0 }}>{(r.note as string) ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function AgentsPage() {
  const res = await load(async (sql) => {
    const [last, queue, spend, metrics, findings, briefs, totals] = await Promise.all([
      sql`SELECT DISTINCT ON (agent, is_real) agent, version, is_real, started_at, finished_at, outcome, rows_written, rows_rejected,
                 provider, model, cost_usd, note, count(*) OVER (PARTITION BY agent, is_real) AS runs
          FROM agent_runs ORDER BY agent, is_real, started_at DESC, run_id DESC`,
      sql`SELECT kind, state, count(*)::int AS n FROM work_items GROUP BY kind, state ORDER BY kind`,
      sql`SELECT (started_at AT TIME ZONE 'UTC')::date AS day, COALESCE(provider, 'local') AS provider, is_real,
                 sum(cost_usd) AS cost, sum(input_tokens) AS input_tokens, sum(output_tokens) AS output_tokens, count(*)::int AS runs
          FROM agent_runs GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2 LIMIT 120`,
      sql`SELECT DISTINCT ON (name, scope) measured_on, name, scope, numerator, denominator, value, detail
          FROM metrics ORDER BY name, scope, measured_on DESC`,
      sql`SELECT f.finding_id, f.raised_on, f.raised_by, f.severity, f.title, f.detail, f.order_id, o.title AS order_title
          FROM findings f LEFT JOIN orders o ON o.order_id = f.order_id WHERE f.state = 'open'
          ORDER BY CASE f.severity WHEN 'block' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END, f.raised_on DESC, f.finding_id DESC`,
      sql`SELECT DISTINCT ON (is_real) brief_id, written_at, written_by, is_real, body, decisions FROM briefs ORDER BY is_real, written_at DESC, brief_id DESC`,
      sql`SELECT (SELECT count(*) FROM agent_runs WHERE is_real) AS real_runs, (SELECT count(*) FROM agent_runs WHERE NOT is_real) AS fixture_runs,
                 (SELECT COALESCE(sum(cost_usd), 0) FROM agent_runs WHERE is_real) AS real_cost,
                 (SELECT count(*) FROM work_items WHERE state IN ('queued', 'claimed')) AS open_items,
                 (SELECT count(*) FROM parses WHERE NOT is_real) AS fixture_parses`,
    ]);
    return { last, queue, spend, metrics, findings, briefs, totals: totals[0] };
  });
  if (!res.ok) return <DbDown state={res} />;
  const { last, queue, spend, metrics, findings, briefs, totals } = res.data;
  const kinds = [...new Set(queue.map((q) => q.kind as string))];
  const qn = new Map(queue.map((q) => [`${q.kind}|${q.state}`, q.n as number]));
  const shownBriefs = [briefs.find((b) => b.is_real), briefs.find((b) => !b.is_real)].filter((b): b is (typeof briefs)[number] => !!b);

  return (
    <section>
      <p className="eyebrow">The network in the open</p>
      <h1 className="big">Agents</h1>
      <p className="plain">Agents find, fetch, read and check the orders; the Director decides what is worked on and the Auditor measures the result. Runs that called a real provider are shown apart from fixture runs, which test the code on stored responses and never produce a published figure.</p>
      <div className="stats">
        <div><b>{count(totals.real_runs)}</b><span>real runs</span></div>
        <div><b>{count(totals.fixture_runs)}</b><span>fixture runs</span></div>
        <div><b>{usd(totals.real_cost)}</b><span>real spend</span></div>
        <div><b>{count(totals.open_items)}</b><span>open work items</span></div>
      </div>

      <h3>Real runs: each agent&apos;s latest</h3>
      <Runs rows={last.filter((r) => r.is_real)} empty="No agent has recorded a real run yet." />
      <h3>Fixture runs: each agent&apos;s latest <span className="tag warn">not provider results</span></h3>
      <Runs rows={last.filter((r) => !r.is_real)} empty="No fixture run is recorded." />
      {Number(totals.fixture_parses) ? <p className="note">{count(totals.fixture_parses)} parses in the database are fixtures; their orders say so.</p> : null}

      <h3>Queue <span className="tag">work items by kind and state</span></h3>
      {kinds.length ? (
        <div className="tablewrap">
          <table>
            <thead><tr><th>Kind</th>{STATES.map((s) => <th key={s} className="num">{s}</th>)}</tr></thead>
            <tbody>{kinds.map((k) => <tr key={k}><td className="mono">{k}</td>{STATES.map((s) => <td key={s} className="num">{qn.get(`${k}|${s}`) ?? 0}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : <p className="note">The queue is empty: the Director has not created work items yet.</p>}

      <h3>Spend by provider and day</h3>
      {spend.length ? (
        <div className="tablewrap tall">
          <table>
            <thead><tr><th>Day (UTC)</th><th>Provider</th><th>Real or fixture</th><th className="num">Runs</th><th className="num">Input tokens</th><th className="num">Output tokens</th><th className="num">Cost (USD)</th></tr></thead>
            <tbody>{spend.map((s, i) => (
              <tr key={i}><td className="mono">{fmtDate(s.day)}</td><td>{s.provider as string}</td><td>{s.is_real ? "real" : "fixture"}</td>
                <td className="num">{count(s.runs)}</td><td className="num">{count(s.input_tokens)}</td><td className="num">{count(s.output_tokens)}</td><td className="num">{usd(s.cost)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      ) : <p className="note">No spend recorded.</p>}
      <p className="note">From each run&apos;s recorded cost (agent_runs). Local readers cost nothing per run.</p>

      <h3>Measures <span className="tag">latest of each</span></h3>
      {metrics.length ? (
        <div className="tablewrap">
          <table>
            <thead><tr><th>Measure</th><th>Scope</th><th>Measured on</th><th className="num">Numerator</th><th className="num">Denominator</th><th className="num">Value</th></tr></thead>
            <tbody>{metrics.map((m, i) => (
              <tr key={i}><td className="mono">{m.name as string}</td><td>{m.scope as string}</td><td className="mono">{fmtDate(m.measured_on)}</td>
                <td className="num">{(m.numerator as number) ?? "—"}</td><td className="num">{(m.denominator as number) ?? "—"}</td>
                <td className="num">{m.value !== null && m.value !== undefined ? Number(m.value).toLocaleString("en-IN", { maximumFractionDigits: 4 }) : "—"}</td></tr>
            ))}</tbody>
          </table>
        </div>
      ) : <p className="note">The Auditor has not recorded a measure yet, so accuracy is not measured here.</p>}

      <h3>Open findings <span className="tag">{findings.length}</span></h3>
      {findings.length ? findings.map((f) => (
        <div key={f.finding_id as number} className="para">
          <p><span className={"tag" + (f.severity === "block" ? " warn" : f.severity === "warn" ? " acc" : "")}>{f.severity as string}</span> <b>{f.title as string}</b></p>
          <p className="note">{fmtDate(f.raised_on)} · raised by {f.raised_by as string}{f.order_id ? <> · <a href={`/order/${f.order_id}`}>{String(f.order_title ?? `order ${f.order_id}`).slice(0, 80)}</a></> : null}</p>
          <p className="text">{f.detail as string}</p>
        </div>
      )) : <p className="note">No open finding.</p>}

      <h3>The Director&apos;s brief</h3>
      {shownBriefs.length ? shownBriefs.map((b) => (
        <div key={b.brief_id as number} className="evidence">
          <p className="note" style={{ marginTop: 0 }}>{fmtTime(b.written_at)} · {b.written_by as string} · {b.is_real ? "written by a model" : "written by the rule-based fallback (no model)"}</p>
          <div className="brief"><Markdown text={b.body as string} /></div>
        </div>
      )) : <p className="note">The Director has not written a brief yet.</p>}
    </section>
  );
}
