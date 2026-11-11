import { notFound } from "next/navigation";
import { load } from "@/lib/db.ts";
import { crore, fmtDate, fmtTime, VOICE_WORDS, consensusWords } from "@/lib/format.ts";
import { DbDown, Crumbs, PageLink, Consensus } from "../../ui.tsx";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return { title: `Order ${id}` };
}

type R = Record<string, unknown>;

const DEFAULT_TABLES = 4;

export default async function OrderPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ table?: string; u?: string }> }) {
  const { id } = await params;
  const { table: tableParam, u: fromUtility } = await searchParams;
  if (!/^\d{1,12}$/.test(id)) notFound();
  const oid = Number(id);
  const res = await load(async (sql) => {
    const [o] = await sql`SELECT o.*, c.name AS commission_name FROM orders o JOIN commissions c ON c.code = o.commission WHERE o.order_id = ${oid}`;
    if (!o) return null;
    const [utils, parses, tables, facts, readings, paragraphs, states] = await Promise.all([
      sql`SELECT u.code, u.name, u.kind, u.state FROM order_utilities ou JOIN utilities u ON u.code = ou.utility WHERE ou.order_id = ${oid} ORDER BY u.code`,
      sql`SELECT p.*, (SELECT count(*) FROM parsed_tables t WHERE t.parse_id = p.parse_id)::int AS tables,
                 (SELECT count(*) FROM arr_values v WHERE v.parse_id = p.parse_id)::int AS readings
          FROM parses p WHERE p.order_id = ${oid} ORDER BY p.reader, p.reader_version`,
      sql`SELECT t.table_id, t.page, t.pages, t.title, t.unit, t.unit_from, jsonb_array_length(t.columns)::int AS ncols, p.reader, p.reader_version
          FROM parsed_tables t JOIN parses p ON p.parse_id = t.parse_id WHERE t.order_id = ${oid} ORDER BY t.page, t.table_id`,
      sql`SELECT f.fact_id, f.utility, f.fiscal_year, f.voice, f.stage, f.head, h.name AS head_name, h.sort, f.label, f.value_crore, f.value,
                 f.unit, f.page, f.quote, f.consensus, f.readers, f.is_headline, f.headline_why, f.set_aside, f.reviewed_by,
                 (SELECT min(v.table_id) FROM fact_readings r JOIN arr_values v ON v.value_id = r.value_id WHERE r.fact_id = f.fact_id AND r.agrees) AS table_id
          FROM facts f JOIN heads h ON h.code = f.head WHERE f.order_id = ${oid}
          ORDER BY f.page, f.utility, f.fiscal_year, f.voice, h.sort, f.fact_id`,
      sql`SELECT r.fact_id, r.agrees, v.reader, p.reader_version, p.is_real, v.value_printed, v.value, v.unit, v.page, v.quote, v.label
          FROM fact_readings r JOIN arr_values v ON v.value_id = r.value_id JOIN parses p ON p.parse_id = v.parse_id
          JOIN facts f ON f.fact_id = r.fact_id
          WHERE f.order_id = ${oid} AND f.consensus = 'conflict' ORDER BY r.fact_id, v.reader`,
      sql`SELECT paragraph_id, page, seq, kind, kind_by, utility, topic, text, summary FROM paragraphs
          WHERE order_id = ${oid} AND kind <> 'text' ORDER BY page, seq`,
      sql`SELECT DISTINCT s.code, s.name FROM order_utilities ou JOIN utilities u ON u.code = ou.utility JOIN states s ON s.code = u.state WHERE ou.order_id = ${oid}`,
    ]);
    return { o, utils, parses, tables, facts, readings, paragraphs, states };
  });
  if (!res.ok) return <DbDown state={res} />;
  if (!res.data) notFound();
  const { o, utils, parses, tables, facts, readings, paragraphs, states } = res.data;
  const url = o.url as string;
  const byTable = new Map<number | null, R[]>();
  for (const f of facts) {
    const k = (f.table_id as number) ?? null;
    if (!byTable.has(k)) byTable.set(k, []);
    byTable.get(k)!.push(f);
  }
  const conflicts = facts.filter((f) => f.consensus === "conflict");
  const readingsOf = new Map<number, R[]>();
  for (const r of readings) {
    if (!readingsOf.has(r.fact_id as number)) readingsOf.set(r.fact_id as number, []);
    readingsOf.get(r.fact_id as number)!.push(r);
  }
  const headlines = facts.filter((f) => f.is_headline);
  const tableList: { key: number | null; title: string; page: number | null; unit: string | null; reader: string }[] = [
    ...tables.filter((t) => byTable.has(t.table_id as number)).map((t) => ({
      key: t.table_id as number, title: (t.title as string) ?? "(untitled table)", page: t.page as number,
      unit: (t.unit as string) ?? null, reader: `${t.reader} ${t.reader_version}`,
    })),
    ...(byTable.has(null) ? [{ key: null, title: "Figures not tied to a table", page: null, unit: null, reader: "" }] : []),
  ];
  // breadcrumb India › State › DISCOM › Order: the utility the visitor came from, else the order's first
  const crumbU = utils.find((u) => u.code === fromUtility) ?? utils.find((u) => u.kind === "discom") ?? utils[0];
  const st = (crumbU && states.find((s) => s.code === crumbU.state)) ?? states[0];
  // Large orders print hundreds of figures: by default show the bottom-line tables and a few
  // more; every other table is one link away.
  const headlineTables = new Set<number | null>(headlines.map((f) => (f.table_id as number) ?? null));
  const chosen = tableParam === "all" ? tableList
    : tableParam && /^\d+$/.test(tableParam) ? tableList.filter((t) => t.key === Number(tableParam))
    : tableParam === "none" ? tableList.filter((t) => t.key === null)
    : [...tableList.filter((t) => headlineTables.has(t.key)), ...tableList.filter((t) => !headlineTables.has(t.key))].slice(0, DEFAULT_TABLES);
  const shown = new Set(chosen.map((t) => t.key));
  const hidden = tableList.filter((t) => !shown.has(t.key));

  return (
    <>
      <Crumbs items={[["India", "/"], ...(st ? [[st.name as string, `/state/${st.code}`] as [string, string]] : []),
        ...(crumbU ? [[crumbU.code as string, `/utility/${encodeURIComponent(crumbU.code as string)}`] as [string, string]] : []), [`Order ${oid}`, null]]} />
      <section style={{ paddingTop: 20 }}>
        <p className="eyebrow">{o.commission as string} · {(o.arr_year as string) ?? "year not recorded"} · {((o.kind as string) ?? "order").replace(/_/g, " ")}</p>
        <h1 className="big" style={{ fontSize: "clamp(1.4rem, 3vw, 2.2rem)", maxWidth: "40ch" }}>{o.title as string}</h1>
        <p className="row"><PageLink url={url}><span className="button">Open the order (PDF)</span></PageLink> <span className="note">on the commission&apos;s website; this site keeps no copy</span></p>
        <dl className="kv">
          <dt>Commission</dt><dd>{o.commission_name as string}</dd>
          <dt>Utilities</dt><dd>{utils.length ? utils.map((u, i) => <span key={u.code as string}>{i ? ", " : ""}<a href={`/utility/${encodeURIComponent(u.code as string)}`}>{u.code as string}</a></span>) : "—"}</dd>
          <dt>ARR year</dt><dd>{(o.arr_year as string) ?? "—"}</dd>
          <dt>Years decided</dt><dd>{((o.years_decided as string[]) ?? []).join(", ") || "—"}</dd>
          <dt>Order date</dt><dd>{fmtDate(o.order_date)}</dd>
          <dt>Read status</dt><dd>{(o.read_status as string).replace(/_/g, " ")}</dd>
          <dt>Pages</dt><dd>{(o.pages as number) ?? "—"}{o.pages_without_text ? ` (${o.pages_without_text} without a text layer)` : ""}</dd>
          <dt>SHA-256</dt><dd className="mono" style={{ fontSize: "0.78rem" }}>{(o.sha256 as string) ?? "not downloaded"}</dd>
          <dt>Found by</dt><dd>{(o.found_by as string) ?? "—"}{o.fetched_on ? ` · fetched ${fmtDate(o.fetched_on)}` : ""}</dd>
          <dt>Source URL</dt><dd className="mono" style={{ fontSize: "0.78rem" }}>{url}</dd>
        </dl>

        <h3>Readers that ran <span className="tag">{parses.length}</span></h3>
        {parses.length ? (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Reader</th><th>Version</th><th>Real or fixture</th><th>Provider / model</th><th>Status</th><th className="num">Tables</th><th className="num">Readings</th><th className="num">Cost (USD)</th><th>When</th></tr></thead>
              <tbody>
                {parses.map((p) => (
                  <tr key={p.parse_id as number}>
                    <td><b>{p.reader as string}</b>{p.note ? <><br /><span className="note">{p.note as string}</span></> : null}</td>
                    <td className="mono">{p.reader_version as string}</td>
                    <td>{p.is_real ? "real run" : <span className="tag warn">fixture</span>}</td>
                    <td>{[p.provider, p.model].filter(Boolean).join(" / ") || "local"}</td>
                    <td>{p.status as string}</td>
                    <td className="num">{p.tables as number}</td>
                    <td className="num">{p.readings as number}</td>
                    <td className="num">{Number(p.cost_usd).toFixed(4)}</td>
                    <td className="mono" style={{ fontSize: "0.76rem" }}>{fmtTime(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="note">No reader has run on this order yet.</p>}

        {headlines.length ? (
          <>
            <h3>Bottom lines <span className="tag">headline ARR</span></h3>
            <div className="tablewrap">
              <table>
                <thead><tr><th>Utility</th><th>Year</th><th>Voice</th><th>Stage</th><th className="num">Rs crore</th><th>Readers</th><th>Page</th><th>Why this row</th></tr></thead>
                <tbody>
                  {headlines.map((f) => (
                    <tr key={f.fact_id as number}>
                      <td>{f.utility as string}</td><td className="mono">{f.fiscal_year as string}</td>
                      <td>{VOICE_WORDS[f.voice as string]}</td><td>{(f.stage as string) ?? "—"}</td>
                      <td className="num">{f.set_aside ? <s>{crore(f.value_crore)}</s> : <a href={`/cite/${f.fact_id}`}>{crore(f.value_crore)}</a>}</td>
                      <td><Consensus c={f.consensus as string} reviewedBy={f.reviewed_by as string} /></td>
                      <td><PageLink url={url} page={f.page as number} /></td>
                      <td className="note" style={{ marginTop: 0 }}>{f.set_aside ? <b>Set aside: {f.set_aside as string}. </b> : null}{(f.headline_why as string) ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}

        {conflicts.length ? (
          <>
            <h3>Conflicts <span className="tag warn">{conflicts.length} readers disagree</span></h3>
            <p className="note">The readers gave different figures. Every candidate is shown; none is chosen silently.</p>
            {conflicts.map((f) => (
              <div key={f.fact_id as number} className="conflictbox">
                <p><b>{f.utility as string}</b> · {f.fiscal_year as string} · {VOICE_WORDS[f.voice as string]} · {f.head_name as string} · row &ldquo;{f.label as string}&rdquo;</p>
                <div className="tablewrap" style={{ marginTop: 8 }}>
                  <table>
                    <thead><tr><th>Reader</th><th className="num">Value as printed</th><th>Agrees</th><th>Page</th><th>Line as read</th></tr></thead>
                    <tbody>
                      {(readingsOf.get(f.fact_id as number) ?? []).map((r, i) => (
                        <tr key={i}>
                          <td>{r.reader as string} <span className="note">{r.reader_version as string}{r.is_real ? "" : " · fixture"}</span></td>
                          <td className="num">{r.value_printed as string}</td>
                          <td>{r.agrees ? "with the shown value" : "no"}</td>
                          <td><PageLink url={url} page={r.page as number} /></td>
                          <td className="quote">{r.quote as string}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </>
        ) : null}

        <h3>Tables read <span className="tag">{tables.length}</span></h3>
        {tables.length ? (
          <div className="tablewrap tall">
            <table>
              <thead><tr><th>Page</th><th>Title as printed</th><th>Unit</th><th className="num">Columns</th><th>Reader</th></tr></thead>
              <tbody>
                {tables.map((t) => (
                  <tr key={t.table_id as number}>
                    <td><PageLink url={url} page={t.page as number} /></td>
                    <td><a href={shown.has(t.table_id as number) ? `#t${t.table_id}` : `?table=${t.table_id}${fromUtility ? `&u=${encodeURIComponent(fromUtility)}` : ""}#t${t.table_id}`}>{(t.title as string) ?? "(untitled)"}</a>{byTable.has(t.table_id as number) ? <span className="note"> · {byTable.get(t.table_id as number)!.length} figures</span> : <span className="note"> · no figures</span>}</td>
                    <td>{(t.unit as string) ?? <span className="muted">not printed</span>}{t.unit_from ? <span className="note"> · {t.unit_from as string}</span> : null}</td>
                    <td className="num">{t.ncols as number}</td>
                    <td className="mono" style={{ fontSize: "0.76rem" }}>{t.reader as string} {t.reader_version as string}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="note">No table has been read from this order{o.read_status !== "read" ? ` (${(o.read_status as string).replace(/_/g, " ")})` : ""}.</p>}

        <h3 id="figures">Figures <span className="tag">{facts.length}</span></h3>
        {facts.length ? <p className="note">Grouped by table, then utility and year. Each figure: the voice (whose figure it is), how many readers agree, the page, and the line as printed. Rs crore where the unit is printed; otherwise the printed value.</p> : <p className="note">No figure has been read from this order.</p>}
        {hidden.length ? (
          <p className="note">Showing the figures of {chosen.length} of {tableList.length} tables{tableParam ? "" : " (the bottom-line tables first)"}. <a href="?table=all#figures">Show all {facts.length} figures</a>{tableParam ? <> · <a href="?#figures">back to the first tables</a></> : null}. Pick another table in the list above.</p>
        ) : null}
        {chosen.map((t, ti) => {
          const rows = byTable.get(t.key) ?? [];
          const groups = new Map<string, R[]>();
          for (const f of rows) {
            const k = `${f.utility} · ${f.fiscal_year}`;
            if (!groups.has(k)) groups.set(k, []);
            groups.get(k)!.push(f);
          }
          return (
            <details key={String(t.key)} id={t.key ? `t${t.key}` : "untabled"} open={ti < 3 || chosen.length < 6} className="evidence">
              <summary><b>{t.title}</b> <span className="note">{t.page ? `page ${t.page}` : ""}{t.unit ? ` · ${t.unit}` : ""} · {rows.length} figures</span></summary>
              {[...groups.entries()].map(([g, fs]) => (
                <div key={g}>
                  <h4>{g}</h4>
                  <div className="tablewrap">
                    <table>
                      <thead><tr><th>Voice</th><th>Head</th><th>Row as printed</th><th className="num">Value</th><th>Readers</th><th>Page</th><th>Line as printed</th></tr></thead>
                      <tbody>
                        {fs.map((f) => (
                          <tr key={f.fact_id as number} className={f.consensus === "conflict" ? "conflict" : undefined}>
                            <td>{VOICE_WORDS[f.voice as string]}{f.stage ? <><br /><span className="note">{f.stage as string}</span></> : null}</td>
                            <td>{f.head_name as string}{f.is_headline ? <><br /><span className="tag acc">bottom line</span></> : null}</td>
                            <td>{f.label as string}</td>
                            <td className="num"><a href={`/cite/${f.fact_id}`}>{f.value_crore !== null ? crore(f.value_crore) : `${crore(f.value)}${f.unit ? ` ${f.unit}` : ""}`}</a>{f.value_crore === null && !f.unit ? <><br /><span className="note">unit not printed</span></> : null}</td>
                            <td><Consensus c={f.consensus as string} reviewedBy={f.reviewed_by as string} /></td>
                            <td><PageLink url={url} page={f.page as number} /></td>
                            <td className="quote">{f.quote as string}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </details>
          );
        })}

        <h3>Key paragraphs <span className="tag">{paragraphs.length}</span></h3>
        {paragraphs.length ? paragraphs.map((p) => (
          <div key={p.paragraph_id as number} className="para">
            <p className="meta mono" style={{ fontSize: "0.72rem" }}>
              <span className="tag">{p.kind as string}</span> <PageLink url={url} page={p.page as number}>page {p.page as number}</PageLink>
              {p.utility ? ` · ${p.utility}` : ""}{p.topic ? ` · ${p.topic}` : ""}{p.kind_by ? ` · classified by ${p.kind_by}` : ""}
            </p>
            {p.summary ? <p className="note">Summary (machine-written; the text below is the evidence): {p.summary as string}</p> : null}
            <p className="text">{p.text as string}</p>
          </div>
        )) : <p className="note">No key paragraph (ruling, directive, reasoning, submission) has been classified for this order yet.</p>}
        <p className="note">{consensusWords("single")}: one reader read the figure; {consensusWords("agreed_2")} / {consensusWords("agreed_3")}: independent readers gave the same figure; {consensusWords("conflict")}: shown with every reader&apos;s value. None of this is a person&apos;s review.</p>
      </section>
    </>
  );
}
