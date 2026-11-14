import { notFound } from "next/navigation";
import { load } from "@/lib/db.ts";
import { stateCoverage, stateOrders } from "@/lib/queries.ts";
import { KIND_WORDS } from "@/lib/format.ts";
import { DbDown, Crumbs, PageLink } from "../../ui.tsx";
import { SECTIONS } from "@/lib/sections.ts";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return { title: code.toUpperCase() };
}

const GROUPS: [string, string, (k: string) => boolean][] = [
  ["discom", "DISCOMs: choose one for its ARR", (k) => k === "discom"],
  ["transco", "Transmission utilities (TRANSCOs)", (k) => k === "transco"],
  ["other", "Other utilities", (k) => k !== "discom" && k !== "transco"],
];

export default async function StatePage({ params }: { params: Promise<{ code: string }> }) {
  const { code: raw } = await params;
  const code = raw.toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) notFound();
  const res = await load(async (sql) => {
    const [state] = await sql`SELECT code, name, kind FROM states WHERE code = ${code}`;
    if (!state) return null;
    const [commissions, utilities, orders, years, sectioned] = await Promise.all([
      sql`SELECT c.code, c.name, c.website, c.website_reachable, c.checked_on,
                 (SELECT string_agg(s2.name, ', ' ORDER BY s2.name) FROM commission_states x JOIN states s2 ON s2.code = x.state WHERE x.commission = c.code) AS covers
          FROM commissions c JOIN commission_states cs ON cs.commission = c.code WHERE cs.state = ${code} ORDER BY c.code`,
      stateCoverage(sql, code),
      stateOrders(sql, code),
      sql`SELECT utility, fiscal_year, string_agg(DISTINCT voice, ',') AS voices
          FROM v_arr WHERE state = ${code} GROUP BY utility, fiscal_year ORDER BY fiscal_year`,
      sql`SELECT o.order_id, o.arr_year, o.title,
                 (SELECT string_agg(ou.utility, ', ' ORDER BY ou.utility) FROM order_utilities ou WHERE ou.order_id = o.order_id) AS utilities,
                 count(*) FILTER (WHERE t.section = 'power_purchase')::int AS power_purchase,
                 count(*) FILTER (WHERE t.section = 're_portfolio')::int AS re_portfolio,
                 count(*) FILTER (WHERE t.section = 'tariff_schedule')::int AS tariff_schedule,
                 count(*) FILTER (WHERE t.section = 'wheeling')::int AS wheeling,
                 count(*) FILTER (WHERE t.section = 'tod')::int AS tod
          FROM section_tables t JOIN orders o ON o.order_id = t.order_id
          WHERE EXISTS (SELECT 1 FROM order_utilities ou JOIN utilities u ON u.code = ou.utility WHERE ou.order_id = o.order_id AND u.state = ${code})
          GROUP BY o.order_id ORDER BY o.arr_year DESC NULLS LAST, o.order_id DESC`,
    ]);
    return { state, commissions, utilities, orders, years, sectioned };
  });
  if (!res.ok) return <DbDown state={res} />;
  if (!res.data) notFound();
  const { state, commissions, utilities, orders, years, sectioned } = res.data;
  const fys = [...new Set(years.map((y) => y.fiscal_year as string))].sort();
  const yv = new Map(years.map((y) => [`${y.utility}|${y.fiscal_year}`, String(y.voices)]));

  return (
    <>
      <Crumbs items={[["India", "/"], [state.name as string, null]]} />
      <section style={{ paddingTop: 20 }}>
        <p className="eyebrow">{state.kind === "union_territory" ? "Union territory" : "State"} · {code}</p>
        <h1 className="big">{state.name as string}</h1>

        {sectioned.length ? (
          <>
            <h3 id="sections">Power purchase, renewables, tariff schedule, wheeling & TOD <span className="tag">{sectioned.length} orders</span></h3>
            <p className="note">Tables as printed in each order, section by section. Newest ARR year first; the number is the tables read in that section.</p>
            <div className="tablewrap">
              <table>
                <thead><tr><th>ARR year</th><th>Order</th><th>Utilities</th>{SECTIONS.map((x) => <th key={x.key} className="num">{x.short}</th>)}</tr></thead>
                <tbody>
                  {sectioned.map((o) => (
                    <tr key={o.order_id as number}>
                      <td className="mono">{(o.arr_year as string) ?? "—"}</td>
                      <td className="long"><a href={`/order/${o.order_id}/sections`}>{o.title as string}</a></td>
                      <td className="mono">{o.utilities as string}</td>
                      {SECTIONS.map((x) => (
                        <td key={x.key} className="num">{(o[x.key] as number) ? <a href={`/order/${o.order_id}/sections?s=${x.key}`}>{o[x.key] as number}</a> : <span className="muted">0</span>}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}

        {GROUPS.map(([key, title, test]) => {
          const rows = utilities.filter((u) => test(u.kind as string));
          return (
            <div key={key}>
              <h3>{title} <span className="tag">{rows.length}</span></h3>
              {rows.length ? (
                <div className="tablewrap">
                  <table>
                    <thead><tr><th>Utility</th>{key === "other" ? <th>Kind</th> : null}<th>Ownership</th><th className="num">Orders</th><th className="num">Orders read</th><th className="num">Years with ARR</th><th>Latest approved year</th></tr></thead>
                    <tbody>
                      {rows.map((u) => (
                        <tr key={u.utility as string}>
                          <td><a href={`/utility/${encodeURIComponent(u.utility as string)}`}><b>{u.utility as string}</b> → ARR</a><br /><span className="muted">{u.name as string}</span></td>
                          {key === "other" ? <td>{KIND_WORDS[u.kind as string] ?? (u.kind as string)}</td> : null}
                          <td>{u.ownership as string}</td>
                          <td className="num">{u.orders as number}</td>
                          <td className="num">{u.orders_read as number}</td>
                          <td className="num">{u.years_with_arr as number}</td>
                          <td>{(u.latest_approved_year as string) ?? <span className="muted">—</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="note">None listed in the reference registry{key === "transco" ? " yet: transmission utilities are added in a later build step" : ""}.</p>}
            </div>
          );
        })}

        {fys.length ? (
          <>
            <h3>ARR coverage by year</h3>
            <div className="tablewrap">
              <table>
                <caption>C: a claimed ARR figure is held; A: an approved one. Blank: none read.</caption>
                <thead><tr><th>Utility</th>{fys.map((y) => <th key={y} className="num">{y.replace(/^FY/, "")}</th>)}</tr></thead>
                <tbody>
                  {[...new Set(years.map((y) => y.utility as string))].sort().map((u) => (
                    <tr key={u}>
                      <td>{u === "TOTAL" ? "State total" : <a href={`/utility/${encodeURIComponent(u)}`}>{u}</a>}</td>
                      {fys.map((y) => {
                        const v = yv.get(`${u}|${y}`) ?? "";
                        const mark = [v.includes("claimed") ? "C" : "", v.split(",").includes("approved") ? "A" : ""].join("");
                        return <td key={y} className="num mono">{mark || ""}<span className="sr">{mark ? `${v}` : "none"}</span></td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}

        <h3>Commission</h3>
        {commissions.length ? (
          <dl className="kv">
            {commissions.map((c) => (
              <div key={c.code as string} style={{ display: "contents" }}>
                <dt>{c.code as string}</dt>
                <dd>
                  {c.name as string}
                  {c.covers ? <span className="muted"> · regulates {c.covers as string}</span> : null}
                  <br />
                  {c.website ? <a href={c.website as string} rel="noopener noreferrer nofollow">{c.website as string}</a> : null}
                  <span className="note"> {c.website_reachable === true ? "website reached" : c.website_reachable === false ? "website not reached" : "website not tried"}{c.checked_on ? ` on ${String(c.checked_on instanceof Date ? (c.checked_on as Date).toISOString().slice(0, 10) : c.checked_on)}` : ""}</span>
                </dd>
              </div>
            ))}
          </dl>
        ) : <p className="note">No commission is recorded for this state.</p>}

        <h3>Orders <span className="tag">{orders.length}</span></h3>
        {orders.length ? (
          <div className="tablewrap">
            <table>
              <thead><tr><th>ARR year</th><th>Order</th><th>Commission</th><th>Utilities</th><th>Read</th><th className="num">Figures</th><th>PDF</th></tr></thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.order_id as number}>
                    <td className="mono">{(o.arr_year as string) ?? "—"}</td>
                    <td className="long"><a href={`/order/${o.order_id}`}>{o.title as string}</a>{o.kind ? <><br /><span className="note">{o.kind as string}</span></> : null}</td>
                    <td>{o.commission as string}</td>
                    <td>{(o.utilities as string) ?? "—"}</td>
                    <td>{(o.read_status as string).replace(/_/g, " ")}</td>
                    <td className="num">{o.facts as number}</td>
                    <td><PageLink url={o.url as string}>PDF</PageLink></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="note">The network has found no order for this state yet.</p>}
      </section>
    </>
  );
}
