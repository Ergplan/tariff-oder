import { load } from "@/lib/db.ts";
import { loadVocab, runReadOnly, ROW_CAP, type RunResult } from "@/lib/ask.ts";
import { translate, type Translation } from "@/lib/nl2sql.ts";
import { EXAMPLES } from "@/lib/examples.ts";
import { crore, pct, consensusWords, pageLink } from "@/lib/format.ts";
import { DbDown, Consensus } from "../ui.tsx";

export const dynamic = "force-dynamic";
export const metadata = { title: "Ask" };

type Row = Record<string, unknown>;
const MONEY = /(_crore$|^value$)/;
const HIDE = /(^|_)quote$|^order_title$|^utility_name$|^order_url$|^url$|(^|_)reviewed_by$/;

function Cell({ c, v }: { c: string; v: unknown }) {
  if (v === null || v === undefined) return <td className="nil">—</td>;
  if (/(^|_)consensus$/.test(c)) return <td><span className={`cons ${v}`}>{consensusWords(String(v))}</span></td>;
  if (c === "consensus_classes") return <td>{String(v).split(", ").map((x) => consensusWords(x)).join("; ")}</td>;
  if (/(^|_)fact_id$/.test(c)) return <td className="num"><a href={`/cite/${v}`}>{String(v)}</a></td>;
  if (c === "order_id") return <td className="num"><a href={`/order/${v}`}>{String(v)}</a></td>;
  if (c === "utility" && typeof v === "string" && v !== "TOTAL") return <td><a href={`/utility/${encodeURIComponent(v)}`}>{v}</a></td>;
  if (typeof v === "number" && MONEY.test(c)) return <td className="num">{crore(v)}</td>;
  if (typeof v === "number" && /_pct$|^share/.test(c)) return <td className="num">{pct(v)}</td>;
  if (typeof v === "number") return <td className="num">{v}</td>;
  if (v instanceof Date) return <td className="mono">{v.toISOString().slice(0, 10)}</td>;
  if (Array.isArray(v)) return <td>{v.join(", ")}</td>;
  if (typeof v === "object") return <td className="mono">{JSON.stringify(v).slice(0, 140)}</td>;
  const s = String(v);
  return <td>{s.length > 140 ? s.slice(0, 140) + "…" : s}</td>;
}

/** The evidence a row carries: for each prefix ("", "claimed_", "approved_" …), page + quote + fact. */
function evidenceOf(r: Row) {
  const out: { who: string; page: number; quote: string | null; fact: unknown; consensus: unknown; reviewed: unknown }[] = [];
  for (const k of Object.keys(r)) {
    const m = /^(.*?)(_?)page$/.exec(k);
    if (!m || typeof r[k] !== "number") continue;
    const p = m[1] ? `${m[1]}_` : "";
    out.push({ who: m[1].replace(/_/g, " "), page: r[k] as number, quote: (r[`${p}quote`] as string) ?? null, fact: r[`${p}fact_id`], consensus: r[`${p}consensus`], reviewed: r[`${p}reviewed_by`] });
  }
  return out;
}

export default async function AskPage({ searchParams }: { searchParams: Promise<{ q?: string; sql?: string }> }) {
  const sp = await searchParams;
  const question = (sp.q ?? "").trim().slice(0, 500);
  const edited = (sp.sql ?? "").trim();
  const res = await load(async (sql) => {
    if (!question && !edited) return null;
    const vocab = await loadVocab(sql);
    const t: Translation | null = question ? translate(question, vocab) : null;
    const text = edited || t?.sql || "";
    const run: RunResult = await runReadOnly(text);
    let cover: { covered: number; listed: number } | null = null;
    if (t?.coverage && !edited) {
      const [a, b] = await Promise.all([runReadOnly(t.coverage.covered), runReadOnly(t.coverage.listed)]);
      if (a.ok && b.ok) cover = { covered: Number(a.rows[0]?.n ?? 0), listed: Number(b.rows[0]?.n ?? 0) };
    }
    return { t, text, run, cover, vocab };
  });
  if (!res.ok) return <DbDown state={res} />;
  const d = res.data;

  return (
    <section>
      <p className="eyebrow">Ask in plain English</p>
      <h1 className="big">What did the Commission approve?</h1>
      <form className="search" action="/ask" style={{ maxWidth: "none" }}>
        <label htmlFor="q" className="sr">Your question</label>
        <input id="q" name="q" type="text" defaultValue={question} placeholder="e.g. Which discom has the highest approved ARR in FY2026-27?" />
        <button type="submit">Ask</button>
      </form>
      <div className="chips" aria-label="Example questions">
        {EXAMPLES.map((e) => <a key={e} className="chip" href={`/ask?q=${encodeURIComponent(e)}`}>{e}</a>)}
      </div>
      <p className="note">The question is turned into one SQL query by fixed rules (no AI model): the same question always gives the same query, and every part of it is explained.</p>

      {d ? (
        <>
          {d.t ? (
            <>
              <h3>How the question was read</h3>
              <ol className="explain">
                {d.t.explain.length ? d.t.explain.map((e, i) => <li key={i}><code>{e.what}</code> <span>{e.why}</span></li>)
                  : <li><span>A question about the database itself; the query reads its catalogue.</span></li>}
              </ol>
              <ul className="assumed">
                {d.cover && d.cover.covered < d.cover.listed ? (
                  <li className="warn">This answer can speak for {d.cover.covered} of the {d.cover.listed} utilities in scope; the database has no such figure for the other {d.cover.listed - d.cover.covered}. A ranking or total here is over those {d.cover.covered} only.</li>
                ) : d.cover ? <li>The database has such a figure for all {d.cover.listed} utilities in scope.</li> : null}
                {d.t.assumed.map((a, i) => <li key={i}>{a}</li>)}
                {edited ? <li className="warn">You edited the SQL: the answer below is your query&apos;s, not the translation&apos;s.</li> : null}
              </ul>
            </>
          ) : null}

          <h3>The SQL <span className="tag">editable</span></h3>
          <form action="/ask">
            <input type="hidden" name="q" value={question} />
            <label htmlFor="sql" className="sr">SQL query</label>
            <textarea id="sql" name="sql" rows={Math.min(24, d.text.split("\n").length + 2)} spellCheck={false} defaultValue={d.text} />
            <p className="row">
              <button type="submit">Run SQL</button>
              <span className="note">One SELECT, read-only, 5 s limit, at most {ROW_CAP.toLocaleString("en-IN")} rows. Views: v_facts, v_arr, v_arr_latest, v_coverage.</span>
            </p>
          </form>

          <h3>The answer {d.run.ok ? <span className="tag">{d.run.rows.length} row{d.run.rows.length === 1 ? "" : "s"}{d.run.capped ? " (capped)" : ""}</span> : null}</h3>
          {!d.run.ok ? <p className="conflictbox" role="alert">{d.run.error}</p> : d.run.rows.length === 0 ? (
            <p className="note">No rows. The database holds no figure that answers this; nothing is estimated in its place.</p>
          ) : (
            <>
              <div className="tablewrap tall">
                <table>
                  <thead><tr>{d.run.columns.filter((c) => !HIDE.test(c)).map((c) => <th key={c} className={/_crore$|_pct$|^share|page$|^n$|count|orders|years/.test(c) ? "num" : undefined}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
                  <tbody>
                    {d.run.rows.map((r, i) => (
                      <tr key={i} id={`r${i}`}>{d.run.ok && d.run.columns.filter((c) => !HIDE.test(c)).map((c) => <Cell key={c} c={c} v={r[c]} />)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="note">Rs crore unless a column says otherwise. {d.run.ms} ms. Each row&apos;s evidence follows.</p>
              <h3>Evidence for each row</h3>
              <div className="evlist">
                {d.run.rows.slice(0, 200).map((r, i) => {
                  const ev = evidenceOf(r);
                  const url = (r.order_url ?? r.url) as string | undefined;
                  return (
                    <div key={i} className="evidence">
                      <p className="note" style={{ marginTop: 0 }}>Row {i + 1}{r.utility ? ` · ${r.utility}` : ""}{r.fiscal_year ? ` · ${r.fiscal_year}` : ""}{r.voice ? ` · ${r.voice}` : ""}{r.order_title ? ` · ${r.order_title}` : r.title ? ` · ${r.title}` : ""}</p>
                      {ev.length ? ev.map((e, j) => {
                        const href = pageLink(url, e.page);
                        return (
                          <div key={j}>
                            <p>{e.who ? <b>{e.who}: </b> : null}page {e.page}{href ? <> — <a href={href} target="_blank" rel="noopener noreferrer nofollow">open the order at this page</a></> : null}
                              {e.fact ? <> · <a href={`/cite/${e.fact}`}>cite</a></> : null}{" "}
                              {e.consensus ? <Consensus c={e.consensus as string} reviewedBy={e.reviewed as string} /> : null}</p>
                            {e.quote ? <blockquote>{e.quote}</blockquote> : null}
                          </div>
                        );
                      }) : url ? <p><a href={url} target="_blank" rel="noopener noreferrer nofollow">open the order</a></p> : <p className="muted">This row carries no page reference (an aggregate or catalogue row).</p>}
                    </div>
                  );
                })}
                {d.run.rows.length > 200 ? <p className="note">Evidence is listed for the first 200 rows.</p> : null}
              </div>
            </>
          )}
        </>
      ) : null}
    </section>
  );
}
