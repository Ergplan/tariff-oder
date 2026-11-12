import { notFound } from "next/navigation";
import { load } from "@/lib/db.ts";
import { SECTIONS, SECTION_KEYS } from "@/lib/sections.ts";
import { DbDown, Crumbs, PageLink } from "../../../ui.tsx";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return { title: `Order ${id} · sections` };
}

type R = Record<string, unknown>;
type Row = { cells: string[]; page: number };
const SHOW = 60; // rows shown before "all rows"

export default async function SectionsPage({ params, searchParams }: {
  params: Promise<{ id: string }>; searchParams: Promise<{ s?: string; u?: string }>;
}) {
  const { id } = await params;
  const { s, u: fromUtility } = await searchParams;
  if (!/^\d{1,12}$/.test(id)) notFound();
  const oid = Number(id);
  const res = await load(async (sql) => {
    const [o] = await sql`SELECT o.order_id, o.title, o.url, o.commission, o.arr_year, o.kind FROM orders o WHERE o.order_id = ${oid}`;
    if (!o) return null;
    const [counts, utils, siblings] = await Promise.all([
      sql`SELECT section, count(*)::int AS tables, sum(n_rows)::int AS rows FROM section_tables WHERE order_id = ${oid} GROUP BY section`,
      sql`SELECT u.code, u.name, u.kind, u.state, s.name AS state_name FROM order_utilities ou JOIN utilities u ON u.code = ou.utility
          JOIN states s ON s.code = u.state WHERE ou.order_id = ${oid} ORDER BY u.code`,
      sql`SELECT o2.order_id, o2.arr_year, o2.title, count(t.*)::int AS tables
          FROM orders o2 JOIN section_tables t ON t.order_id = o2.order_id
          WHERE o2.order_id <> ${oid} AND EXISTS (SELECT 1 FROM order_utilities a JOIN order_utilities b ON a.utility = b.utility
                                                 WHERE a.order_id = o2.order_id AND b.order_id = ${oid})
          GROUP BY o2.order_id ORDER BY o2.arr_year DESC NULLS LAST, o2.order_id DESC`,
    ]);
    const active = s && SECTION_KEYS.includes(s) ? s
      : (SECTIONS.find((x) => counts.some((c) => c.section === x.key))?.key ?? "power_purchase");
    const tables = await sql`SELECT section_table_id, seq, kind, label, category, title, fiscal_year, page, pages, columns, rows, n_rows, reader_version
      FROM section_tables WHERE order_id = ${oid} AND section = ${active} ORDER BY seq`;
    return { o, counts, utils, siblings, active, tables };
  });
  if (!res.ok) return <DbDown state={res} />;
  if (!res.data) notFound();
  const { o, counts, utils, siblings, active, tables } = res.data;
  const url = o.url as string;
  const info = SECTIONS.find((x) => x.key === active)!;
  const count = new Map(counts.map((c) => [c.section as string, c]));
  const crumbU = utils.find((x) => x.code === fromUtility) ?? utils.find((x) => x.kind === "discom") ?? utils[0];
  const q = (k: string) => `/order/${oid}/sections?s=${k}${fromUtility ? `&u=${encodeURIComponent(fromUtility)}` : ""}`;
  // the tariff schedule reads category by category
  const groups: [string | null, R[]][] = [];
  for (const t of tables) {
    const g = active === "tariff_schedule" || active === "tod" ? ((t.category as string) ?? null) : null;
    if (!groups.length || groups[groups.length - 1][0] !== g) groups.push([g, []]);
    groups[groups.length - 1][1].push(t);
  }

  return (
    <>
      <Crumbs items={[["India", "/"],
        ...(crumbU ? [[crumbU.state_name as string, `/state/${crumbU.state}`] as [string, string],
          [crumbU.code as string, `/utility/${encodeURIComponent(crumbU.code as string)}`] as [string, string]] : []),
        [`Order ${oid}`, `/order/${oid}${fromUtility ? `?u=${encodeURIComponent(fromUtility)}` : ""}`], ["Sections", null]]} />
      <section style={{ paddingTop: 20 }}>
        <p className="eyebrow">{o.commission as string} · {(o.arr_year as string) ?? "year not recorded"} · tables as printed in the order</p>
        <h1 className="big" style={{ fontSize: "clamp(1.3rem, 2.6vw, 2rem)", maxWidth: "44ch" }}>{o.title as string}</h1>
        <p className="row"><PageLink url={url}><span className="button">Open the order (PDF)</span></PageLink>
          <span className="note">Utilities: {utils.map((x) => x.code as string).join(", ") || "—"}</span></p>

        <nav className="chips sectiontabs" aria-label="Sections">
          {SECTIONS.map((x) => {
            const c = count.get(x.key);
            return (
              <a key={x.key} href={q(x.key)} className={`chip${x.key === active ? " on" : ""}`} aria-current={x.key === active ? "page" : undefined}>
                {x.name} <span className="tag">{c ? (c.tables as number) : 0}</span>
              </a>
            );
          })}
        </nav>

        <h2 className="sectionhead">{info.name}</h2>
        <p className="plain">{info.about}</p>
        <p className="note">Every cell is the order&apos;s own text, read from the PDF&apos;s text layer inside its ruled table (the Section Reader, {(tables[0]?.reader_version as string) ?? "section-reader"}); every number of every row was checked to be printed on that row&apos;s page. Nothing is computed, converted or reviewed by a person. Click a page number to open the order at that page.</p>

        {tables.length ? (
          <>
            <h3>In this section <span className="tag">{tables.length} tables</span></h3>
            <ol className="toc">
              {tables.map((t) => (
                <li key={t.section_table_id as number}>
                  <a href={`#t${t.section_table_id}`}>{t.label && !(t.title as string).startsWith(t.label as string) ? `${t.label} · ` : ""}{t.title as string}</a>
                  <span className="note"> · p. {pagesText(t.pages as number[])} · {t.n_rows as number} rows</span>
                </li>
              ))}
            </ol>
            {groups.map(([g, ts], gi) => (
              <div key={gi}>
                {g ? <h3 className="cathead">{g}</h3> : null}
                {ts.map((t) => <SectionTable key={t.section_table_id as number} t={t} url={url} />)}
              </div>
            ))}
          </>
        ) : (
          <p className="note">No {info.name.toLowerCase()} table was read from this order. {counts.length ? "See the other sections above." : "The Section Reader has not run on this order, or the order has no text layer (a scanned order)."}</p>
        )}

        {siblings.length ? (
          <>
            <h3>The same sections in other orders <span className="tag">{siblings.length}</span></h3>
            <ul className="toc">
              {siblings.map((x) => (
                <li key={x.order_id as number}><a href={`/order/${x.order_id}/sections?s=${active}${fromUtility ? `&u=${encodeURIComponent(fromUtility)}` : ""}`}>
                  {(x.arr_year as string) ?? "—"} · {x.title as string}</a> <span className="note">· {x.tables as number} tables</span></li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
    </>
  );
}

function pagesText(pages: number[]): string {
  if (!pages?.length) return "—";
  return pages.length > 1 ? `${pages[0]}–${pages[pages.length - 1]}` : String(pages[0]);
}

const FIG = /^\(?[-+–]?\)?\s*\(?-?(Rs\.?\s*)?[\d,]*\d(\.\d+)?\)?\s*%?\*?$/;

function SectionTable({ t, url }: { t: R; url: string }) {
  const cols = t.columns as string[];
  const rows = t.rows as Row[];
  const head = rows.slice(0, SHOW);
  const rest = rows.slice(SHOW);
  const multiPage = (t.pages as number[]).length > 1;
  const body = (rs: Row[]) => rs.map((r, i) => (
    <tr key={i}>
      {r.cells.map((c, j) => <td key={j} className={FIG.test(c) ? "num" : j === 0 ? "" : "cell"}>{c}</td>)}
      {multiPage ? <td className="mono"><PageLink url={url} page={r.page} /></td> : null}
    </tr>
  ));
  return (
    <article className="sectable" id={`t${t.section_table_id}`}>
      <h4>{t.label && !(t.title as string).startsWith(t.label as string) ? <span className="tag">{t.label as string}</span> : null} {t.title as string}</h4>
      <p className="note">
        <PageLink url={url} page={t.page as number}>page {pagesText(t.pages as number[])}</PageLink> · {t.n_rows as number} rows
        {t.fiscal_year ? ` · ${t.fiscal_year}` : ""}{t.kind === "text" ? " · printed as text, not as a table: the lines that state a rate" : ""}
      </p>
      <div className={`tablewrap${rows.length > 25 ? " tall" : ""}`}>
        <table>
          <thead><tr>{cols.map((c, j) => <th key={j} className="wrap">{c || " "}</th>)}{multiPage ? <th>Page</th> : null}</tr></thead>
          <tbody>{body(head)}</tbody>
        </table>
      </div>
      {rest.length ? (
        <details className="more">
          <summary>All {rows.length} rows</summary>
          <div className="tablewrap tall">
            <table>
              <thead><tr>{cols.map((c, j) => <th key={j} className="wrap">{c || " "}</th>)}{multiPage ? <th>Page</th> : null}</tr></thead>
              <tbody>{body(rows)}</tbody>
            </table>
          </div>
        </details>
      ) : null}
    </article>
  );
}
