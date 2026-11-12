import { notFound } from "next/navigation";
import { load } from "@/lib/db.ts";
import { utilityArr, utilityOrders } from "@/lib/queries.ts";
import { crore, KIND_WORDS, VOICE_WORDS } from "@/lib/format.ts";
import { DbDown, Crumbs, PageLink, Consensus } from "../../ui.tsx";
import { ArrChart } from "../../chart.tsx";
import { SECTIONS } from "@/lib/sections.ts";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return { title: decodeURIComponent(code) };
}

type R = Record<string, unknown>;

function Fig({ v, fact, c, rev, url, page }: { v: unknown; fact: unknown; c: unknown; rev: unknown; url: unknown; page: unknown }) {
  if (v === null || v === undefined) return <span className="muted">—</span>;
  return (
    <>
      <a href={`/cite/${fact}`} title="cite this figure">{crore(v)}</a>
      <br /><Consensus c={c as string} reviewedBy={rev as string} />{" "}
      <span className="note"><PageLink url={url as string} page={page as number} /></span>
    </>
  );
}

export default async function UtilityPage({ params }: { params: Promise<{ code: string }> }) {
  const { code: raw } = await params;
  const code = decodeURIComponent(raw);
  if (!/^[A-Za-z0-9&._-]{1,40}$/.test(code)) notFound();
  const res = await load(async (sql) => {
    const [u] = await sql`SELECT u.*, s.name AS state_name, c.name AS commission_name
                          FROM utilities u JOIN states s ON s.code = u.state JOIN commissions c ON c.code = u.commission WHERE u.code = ${code}`;
    if (!u) return null;
    const [arr, heads, keyParams, orders, sectioned] = await Promise.all([
      utilityArr(sql, code),
      sql`
        WITH per AS (
          SELECT fiscal_year, order_id, max(order_arr_year) AS oy, count(DISTINCT head) AS nh
          FROM v_facts WHERE utility = ${code} AND voice = 'approved' GROUP BY fiscal_year, order_id),
        pick AS (
          SELECT DISTINCT ON (fiscal_year) fiscal_year, order_id FROM per
          ORDER BY fiscal_year, (nh >= 3) DESC, oy DESC NULLS LAST, order_id DESC),
        hl AS (SELECT order_id, fiscal_year, min(page) AS page FROM v_arr WHERE utility = ${code} AND voice = 'approved' GROUP BY 1, 2)
        SELECT DISTINCT ON (v.fiscal_year, v.head) v.fiscal_year, v.head, v.head_name, h.sort, v.fact_id, v.value_crore, v.value, v.unit,
               v.label, v.consensus, v.reviewed_by, v.page, v.order_id, v.order_url, v.order_arr_year,
               count(*) OVER (PARTITION BY v.fiscal_year, v.head) AS n
        FROM v_facts v
        JOIN pick p ON p.fiscal_year = v.fiscal_year AND p.order_id = v.order_id
        JOIN heads h ON h.code = v.head
        LEFT JOIN hl ON hl.order_id = v.order_id AND hl.fiscal_year = v.fiscal_year
        WHERE v.utility = ${code} AND v.voice = 'approved'
        ORDER BY v.fiscal_year, v.head, (v.page = hl.page) DESC NULLS LAST, v.is_headline DESC, v.fact_id`,
      sql`SELECT p.parameter_id, p.code, d.name, d.grp, d.sort, p.label, p.fiscal_year, p.voice, p.value_printed, p.value, p.unit,
                 p.page, p.quote, p.consensus, p.reviewed_by, p.reader, o.order_id, o.url AS order_url, o.title AS order_title
          FROM parameters p JOIN parameter_defs d ON d.code = p.code JOIN orders o ON o.order_id = p.order_id
          WHERE p.utility = ${code} ORDER BY d.grp, d.sort, p.code, p.fiscal_year, p.voice, o.arr_year DESC NULLS LAST`,
      utilityOrders(sql, code),
      sql`SELECT o.order_id, o.arr_year, o.title, count(*)::int AS tables FROM section_tables t JOIN orders o ON o.order_id = t.order_id
          JOIN order_utilities ou ON ou.order_id = o.order_id AND ou.utility = ${code}
          GROUP BY o.order_id ORDER BY o.arr_year DESC NULLS LAST, o.order_id DESC`,
    ]);
    return { u, arr, heads, keyParams, orders, sectioned };
  });
  if (!res.ok) return <DbDown state={res} />;
  if (!res.data) notFound();
  const { u, arr, heads, keyParams, orders, sectioned } = res.data;
  const years = [...new Set(heads.map((h) => h.fiscal_year as string))].sort().reverse(); // newest first
  const headRows = [...new Map(heads.map((h) => [h.head as string, h])).values()].sort((a, b) => (a.sort as number) - (b.sort as number) || String(a.head).localeCompare(String(b.head)));
  const cell = new Map(heads.map((h) => [`${h.head}|${h.fiscal_year}`, h]));
  const orderOfYear = new Map(heads.map((h) => [h.fiscal_year as string, h]));
  const bars = arr.map((a) => ({ year: a.fiscal_year as string, claimed: (a.claimed_crore as number) ?? null, approved: (a.latest_crore as number) ?? null }));
  const aliases = (u.aliases as string[]) ?? [];

  return (
    <>
      <Crumbs items={[["India", "/"], [u.state_name as string, `/state/${u.state}`], [`${code} (${KIND_WORDS[u.kind as string] ?? u.kind})`, null]]} />
      <section style={{ paddingTop: 20 }}>
        <p className="eyebrow">{KIND_WORDS[u.kind as string] ?? (u.kind as string)} · {u.ownership as string}-owned · {u.commission as string}</p>
        <h1 className="big">{u.name as string}</h1>
        <dl className="kv">
          <dt>Code</dt><dd className="mono">{code}</dd>
          <dt>State</dt><dd><a href={`/state/${u.state}`}>{u.state_name as string}</a></dd>
          <dt>Commission</dt><dd>{u.commission_name as string}</dd>
          {aliases.length ? <><dt>Also printed as</dt><dd>{aliases.join(" · ")}</dd></> : null}
        </dl>

        <h3>ARR by year <span className="tag">Rs crore</span></h3>
        {arr.length ? (
          <div className="stack">
            <div>
              <ArrChart bars={bars} title={`${code}: ARR by financial year, claimed and approved (latest word)`} />
              <p className="note">Bars: outlined, the latest claimed bottom line; filled, the latest approved (the newest order&apos;s word on that year).</p>
            </div>
            <div className="tablewrap">
              <table>
                <thead><tr><th>Year</th><th className="num">Claimed</th><th className="num">Approved (in that year&apos;s order)</th><th className="num">Latest word</th></tr></thead>
                <tbody>
                  {arr.map((a: R) => (
                    <tr key={a.fiscal_year as string}>
                      <td className="mono">{a.fiscal_year as string}</td>
                      <td className="num"><Fig v={a.claimed_crore} fact={a.claimed_fact} c={a.claimed_consensus} rev={a.claimed_reviewed_by} url={a.claimed_url} page={a.claimed_page} /></td>
                      <td className="num"><Fig v={a.approved_crore} fact={a.approved_fact} c={a.approved_consensus} rev={a.approved_reviewed_by} url={a.approved_url} page={a.approved_page} /></td>
                      <td className="num">
                        <Fig v={a.latest_crore} fact={a.latest_fact} c={a.latest_consensus} rev={a.latest_reviewed_by} url={a.latest_url} page={a.latest_page} />
                        {a.latest_crore !== null ? <><br /><span className="note">{(a.latest_stage as string) ?? ""}{a.latest_order ? <> · <a href={`/order/${a.latest_order}?u=${encodeURIComponent(code)}`}>order {a.latest_order_year as string}</a></> : null}</span></> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : <p className="note">No bottom-line ARR figure has been read for {code} yet.</p>}

        <h3>Cost heads by year <span className="tag">approved · Rs crore</span></h3>
        {years.length ? (
          <>
            <div className="tablewrap tall">
              <table>
                <thead>
                  <tr><th className="rowhead">Head</th>{years.map((y) => <th key={y} className="num">{y}<br /><a href={`/order/${orderOfYear.get(y)!.order_id}?u=${encodeURIComponent(code)}`} className="muted" style={{ textTransform: "none" }}>order {(orderOfYear.get(y)!.order_arr_year as string) ?? orderOfYear.get(y)!.order_id as number}</a></th>)}</tr>
                </thead>
                <tbody>
                  {headRows.map((h) => (
                    <tr key={h.head as string}>
                      <td className="rowhead">{h.head_name as string}</td>
                      {years.map((y) => {
                        const c = cell.get(`${h.head}|${y}`);
                        if (!c) return <td key={y} className="num nil">—</td>;
                        return (
                          <td key={y} className="num" title={`printed as: ${c.label}`}>
                            <a href={`/cite/${c.fact_id}`}>{c.value_crore !== null ? crore(c.value_crore) : `${crore(c.value)} ${(c.unit as string) ?? "(unit not printed)"}`}</a>
                            {(c.n as number) > 1 ? <sup title={`${c.n} rows of this head were printed; the one from the main ARR table is shown`}>*</sup> : null}
                            <br /><Consensus c={c.consensus as string} reviewedBy={c.reviewed_by as string} />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">Newest year first. For each year, the approved figures of one order: the newest order that prints at least three heads for that year. * the order prints more than one row for that head; the row from its main ARR table is shown (open the order for all of them). Hover a figure to see its printed label.</p>
          </>
        ) : <p className="note">No approved cost head has been read for {code} yet.</p>}

        <h3>Power purchase, renewables, tariff schedule, wheeling & TOD <span className="tag">{sectioned.length} orders</span></h3>
        {sectioned.length ? (
          <>
            <nav className="chips" aria-label={`Sections of ${code}'s newest order`}>
              {SECTIONS.map((x) => (
                <a key={x.key} className="chip" href={`/order/${sectioned[0].order_id}/sections?s=${x.key}&u=${encodeURIComponent(code)}`}>{x.name}</a>
              ))}
            </nav>
            <p className="note">From the newest order with sections read ({(sectioned[0].arr_year as string) ?? "year not recorded"}): <a href={`/order/${sectioned[0].order_id}/sections?u=${encodeURIComponent(code)}`}>{sectioned[0].title as string}</a>. Earlier orders: {sectioned.slice(1).map((o, i) => (
              <span key={o.order_id as number}>{i ? ", " : ""}<a href={`/order/${o.order_id}/sections?u=${encodeURIComponent(code)}`}>{(o.arr_year as string) ?? `order ${o.order_id}`}</a></span>
            ))}{sectioned.length > 1 ? "." : "none."}</p>
          </>
        ) : <p className="note">No section has been read from {code}&apos;s orders yet.</p>}

        <h3>Key parameters <span className="tag">{keyParams.length}</span></h3>
        {keyParams.length ? (
          <div className="tablewrap">
            <table>
              <thead><tr><th>Parameter</th><th>Year</th><th>Voice</th><th className="num">Value</th><th>Readers</th><th>Page</th><th>As printed</th></tr></thead>
              <tbody>
                {keyParams.map((p) => (
                  <tr key={p.parameter_id as number}>
                    <td>{p.name as string}<br /><span className="note">{p.label as string}</span></td>
                    <td className="mono">{(p.fiscal_year as string) ?? "—"}</td>
                    <td>{p.voice ? VOICE_WORDS[p.voice as string] : "—"}</td>
                    <td className="num">{p.value_printed as string} {p.unit as string}</td>
                    <td><Consensus c={p.consensus as string} reviewedBy={p.reviewed_by as string} /></td>
                    <td><PageLink url={p.order_url as string} page={p.page as number} /></td>
                    <td className="quote">{p.quote as string}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="note">No key parameter (sales, losses, average cost of supply, rates…) has been read for {code} yet. They come from the Extractor, which has not run on these orders.</p>}

        <h3>Orders <span className="tag">{orders.length}</span></h3>
        {orders.length ? (
          <div className="tablewrap">
            <table>
              <thead><tr><th>ARR year</th><th>Order</th><th>Read</th><th className="num">Figures for {code}</th><th>PDF</th></tr></thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.order_id as number}>
                    <td className="mono">{(o.arr_year as string) ?? "—"}</td>
                    <td className="long"><a href={`/order/${o.order_id}?u=${encodeURIComponent(code)}`}>{o.title as string}</a></td>
                    <td>{(o.read_status as string).replace(/_/g, " ")}</td>
                    <td className="num">{o.facts as number}</td>
                    <td><PageLink url={o.url as string}>PDF</PageLink></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="note">No order for {code} has been found yet.</p>}
      </section>
    </>
  );
}
