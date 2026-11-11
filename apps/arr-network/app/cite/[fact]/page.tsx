import { notFound } from "next/navigation";
import { siteOrigin } from "@/lib/origin.ts";
import { load } from "@/lib/db.ts";
import { bibtex, citationText, amount, type FactRow } from "@/lib/cite.ts";
import { VOICE_WORDS, fmtTime } from "@/lib/format.ts";
import { DbDown, Crumbs, PageLink, Consensus } from "../../ui.tsx";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ fact: string }> }) {
  const { fact } = await params;
  return { title: `Figure ${fact}` };
}

export default async function CitePage({ params }: { params: Promise<{ fact: string }> }) {
  const { fact } = await params;
  if (!/^\d{1,12}$/.test(fact)) notFound();
  const res = await load(async (sql) => {
    const [f] = await sql`SELECT v.*, c.name AS commission_name, o.order_date
                          FROM v_facts v JOIN commissions c ON c.code = v.commission JOIN orders o ON o.order_id = v.order_id
                          WHERE v.fact_id = ${Number(fact)}`;
    return (f as unknown as FactRow) ?? null;
  });
  if (!res.ok) return <DbDown state={res} />;
  const f = res.data;
  if (!f) notFound();
  const permalink = `${await siteOrigin()}/cite/${f.fact_id}`;
  const accessed = new Date().toISOString().slice(0, 10);

  return (
    <>
      <Crumbs items={[["India", "/"], ...(f.state && f.state_name ? [[f.state_name, `/state/${f.state}`] as [string, string]] : []),
        ...(f.utility !== "TOTAL" ? [[f.utility, `/utility/${encodeURIComponent(f.utility)}`] as [string, string]] : []),
        [`Order ${f.order_id}`, `/order/${f.order_id}${f.utility !== "TOTAL" ? `?u=${encodeURIComponent(f.utility)}` : ""}`], [`Figure ${f.fact_id}`, null]]} />
      <section style={{ paddingTop: 20 }}>
        <p className="eyebrow">Cite one figure</p>
        <h1 className="big" style={{ fontSize: "clamp(1.6rem, 3.6vw, 2.6rem)" }}>{amount(f)}</h1>
        <p className="plain">{f.utility === "TOTAL" ? "State total" : <>{f.utility_name ?? f.utility} <span className="mono">({f.utility})</span></>} · {f.fiscal_year} · {VOICE_WORDS[f.voice]}{f.stage ? ` · ${f.stage}` : ""} · {f.head_name}</p>
        <p className="row"><Consensus c={f.consensus} reviewedBy={f.reviewed_by} />{f.reviewed_by ? <span className="note">reviewed {fmtTime(f.reviewed_at)}</span> : <span className="note">not reviewed by a person</span>}</p>

        <h3>The line as printed</h3>
        <blockquote>{f.quote}</blockquote>
        <p>Row label <b>&ldquo;{f.label}&rdquo;</b>, page {f.page} of <a href={`/order/${f.order_id}`}>{f.order_title}</a> — <PageLink url={f.order_url} page={f.page}>open the order at page {f.page}</PageLink>.</p>
        <p className="note">Read by: {(f.readers || []).join(", ")}.</p>

        <h3>Citation</h3>
        <pre className="cite" aria-label="Plain-text citation">{citationText(f, permalink, accessed)}</pre>
        <h3>BibTeX</h3>
        <pre className="cite" aria-label="BibTeX">{bibtex(f, permalink, accessed)}</pre>
        <h3>Permanent link</h3>
        <p className="mono"><a href={permalink}>{permalink}</a></p>
        <p className="note">JSON: <a href={`/api/v1/orders/${f.order_id}`}>/api/v1/orders/{f.order_id}</a></p>
      </section>
    </>
  );
}
