import { load } from "@/lib/db.ts";
import { search, type SearchOut } from "@/lib/search.ts";
import { crore, VOICE_WORDS } from "@/lib/format.ts";
import { PARAGRAPH_KINDS } from "@/lib/ingest/validate.ts";
import { DbDown, PageLink, Consensus } from "../ui.tsx";

export const dynamic = "force-dynamic";
export const metadata = { title: "Search" };

type SP = { q?: string; state?: string; utility?: string; year?: string; kind?: string };
const clean = (v: string | undefined, re: RegExp) => (v && re.test(v) ? v : undefined);

export default async function SearchPage({ searchParams }: { searchParams: Promise<SP> }) {
  const sp = await searchParams;
  const q = (sp.q ?? "").trim().slice(0, 300);
  const f = {
    state: clean(sp.state, /^[A-Z]{2}$/),
    utility: clean(sp.utility, /^[A-Za-z0-9&._-]{1,40}$/),
    year: clean(sp.year, /^FY\d{4}-\d{2}$/),
    kind: clean(sp.kind, new RegExp(`^(${PARAGRAPH_KINDS.join("|")})$`)),
  };
  const res = await load(async (sql) => {
    const [states, utilities, years] = await Promise.all([
      sql`SELECT code, name FROM states ORDER BY name`,
      sql`SELECT code, name FROM utilities ORDER BY code`,
      sql`SELECT DISTINCT fiscal_year AS y FROM facts ORDER BY 1 DESC`,
    ]);
    const out: SearchOut | null = q ? await search(sql, q, f) : null;
    return { states, utilities, years, out };
  });
  if (!res.ok) return <DbDown state={res} />;
  const { states, utilities, years, out } = res.data;

  return (
    <section>
      <p className="eyebrow">Search the orders</p>
      <h1 className="big">Search</h1>
      <form className="search" action="/search" role="search" style={{ maxWidth: "none" }}>
        <label htmlFor="q" className="sr">Search terms</label>
        <input id="q" name="q" type="search" defaultValue={q} placeholder="e.g. power purchase cost disallowed, carrying cost, distribution loss" />
        <button type="submit">Search</button>
      </form>
      <form action="/search" className="filters" aria-label="Filters">
        <input type="hidden" name="q" value={q} />
        <label>State
          <select name="state" defaultValue={f.state ?? ""}>
            <option value="">all</option>
            {states.map((s) => <option key={s.code as string} value={s.code as string}>{s.name as string}</option>)}
          </select>
        </label>
        <label>Utility
          <select name="utility" defaultValue={f.utility ?? ""}>
            <option value="">all</option>
            {utilities.map((u) => <option key={u.code as string} value={u.code as string}>{u.code as string}</option>)}
          </select>
        </label>
        <label>Year
          <select name="year" defaultValue={f.year ?? ""}>
            <option value="">all</option>
            {years.map((y) => <option key={y.y as string} value={y.y as string}>{y.y as string}</option>)}
          </select>
        </label>
        <label>Paragraph kind
          <select name="kind" defaultValue={f.kind ?? ""}>
            <option value="">all (and figures)</option>
            {PARAGRAPH_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <button type="submit">Filter</button>
      </form>

      {!q ? <p className="note" style={{ marginTop: 20 }}>Type words from an order — a head (&ldquo;depreciation&rdquo;), a utility (&ldquo;TPDDL&rdquo;), a phrase (&ldquo;carrying cost&rdquo;). Paragraphs are searched by full text and by meaning; figures by their printed labels.</p> : null}

      {out ? (
        <>
          <p className="note" role="status" style={{ marginTop: 16 }}>
            {out.mode === "hybrid"
              ? `Paragraphs ranked by full-text match and by meaning (BAAI/bge-small-en-v1.5), fused by reciprocal rank. ${out.embedded} of ${out.chunksTotal} indexed passages have an embedding.`
              : `Full-text search only: vector search was not used because ${out.why}.`}
          </p>
          <h3>Passages <span className="tag">{out.chunks.length}</span></h3>
          {out.chunks.length ? out.chunks.map((c) => (
            <div key={c.chunk_id} className="result">
              <p className="meta">
                <a href={`/order/${c.order_id}`}>{c.title}</a> · {c.commission}{c.arr_year ? ` · ${c.arr_year}` : ""} · <PageLink url={c.url} page={c.page}>page {c.page}</PageLink>
                {c.kind && c.kind !== "text" ? <> · <span className="tag">{c.kind}</span></> : null}
                <span className="sr"> · match: {c.fts_rank ? `words #${c.fts_rank}` : ""}{c.vec_rank ? ` meaning #${c.vec_rank}` : ""}</span>
              </p>
              <p className="text">{c.text.length > 900 ? c.text.slice(0, 900) + "…" : c.text}</p>
            </div>
          )) : <p className="note">{out.chunksTotal ? "No passage matches." : "No passage of any order has been indexed yet (the Librarian has not run), so only figures are searched."}</p>}

          {f.kind ? null : (
            <>
              <h3>Figures <span className="tag">{out.facts.length}</span></h3>
              {out.facts.length ? (
                <div className="tablewrap tall">
                  <table>
                    <thead><tr><th>Utility</th><th>Year</th><th>Voice</th><th>Row as printed</th><th className="num">Rs crore</th><th>Readers</th><th>Page</th><th>Order</th></tr></thead>
                    <tbody>
                      {out.facts.map((x) => (
                        <tr key={x.fact_id as number}>
                          <td>{x.utility as string}</td>
                          <td className="mono">{x.fiscal_year as string}</td>
                          <td>{VOICE_WORDS[x.voice as string]}</td>
                          <td>{x.label as string}<br /><span className="note">{x.head_name as string}</span></td>
                          <td className="num"><a href={`/cite/${x.fact_id}`}>{x.value_crore !== null ? crore(x.value_crore) : `${crore(x.value)} ${(x.unit as string) ?? ""}`}</a></td>
                          <td><Consensus c={x.consensus as string} reviewedBy={x.reviewed_by as string} /></td>
                          <td><PageLink url={x.order_url as string} page={x.page as number} /></td>
                          <td><a href={`/order/${x.order_id}`}>{String(x.order_title).slice(0, 80)}</a></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="note">No figure&apos;s printed label matches.</p>}
            </>
          )}
        </>
      ) : null}
    </section>
  );
}
