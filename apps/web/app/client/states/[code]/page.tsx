import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { type Norms, type StateDetail, CONVENTION_WORDS, statusWord } from "../../atlas/data";
import { Eyebrow, Journey, Panel } from "../../studio";

export const dynamic = "force-dynamic";

const DRAFT_STEPS = [
  ["Setup", "The licensee, the filing (annual ARR, MYT control period, true-up, APR) and the years."],
  ["Data", "The reviewed history is the base; supply what the regulations leave to the petitioner, each with its source."],
  ["Formulate", "Every ARR line projected by the commission's method. A line without its inputs is blocked, never filled in."],
  ["Freeze", "Lock the assumptions of this version; a revision keeps the frozen one on record."],
  ["Draft", "The petition and its formats (DOCX, XLSX), every number traced and watermarked as a draft."],
];

/**
 * One state (increment 52): its commission and the regulations its ARR mapping names, every
 * distribution licensee with what is on record for it, a summary of the commission's norms and
 * the steps of drafting a petition.
 */
export default async function StatePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const res = await apiTry<StateDetail>(`/atlas/states/${encodeURIComponent(code)}`);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const st = res.data;
  const norms = await Promise.all(st.commissions.map((c) => apiTry<Norms>(`/arr/norms/${encodeURIComponent(c.code)}`)));
  const licensees = st.commissions.flatMap((c) => c.licensees.map((l) => ({ ...l, commission: c.code })));
  const dist = licensees.filter((l) => l.kind === "distribution");
  const first = dist[0];
  return (
    <>
      <Journey steps={[{ label: "India", href: "/client/atlas" }, { label: st.name }]} />
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>
          {st.kind === "union_territory" ? "Union territory" : "State"} · {st.commissions.map((c) => c.code).join(" · ")}
        </Eyebrow>
        <h1>{st.name}</h1>
        <div className="case-meta">
          <span>
            Distribution licensees <b>{dist.length}</b>
          </span>
          <span>
            Documents located <b>{licensees.reduce((a, l) => a + l.documents_located, 0)}</b> of <b>{licensees.reduce((a, l) => a + l.documents, 0)}</b>
          </span>
          <span>
            Orders being read <b>{licensees.reduce((a, l) => a + l.orders_reading, 0)}</b>
          </span>
          <span>
            Reviewed ARR facts <b>{licensees.reduce((a, l) => a + l.reviewed_facts, 0)}</b>
          </span>
        </div>
      </header>

      <Panel num="01" title="Licensees" aside="choose one to see its record and start a petition">
        {licensees.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No licensee of {st.name} is in the registry yet.
          </p>
        ) : (
          <div className="petitions lic">
            {licensees.map((l) => (
              <Link key={l.code} href={`/client/licensees/${encodeURIComponent(l.code)}`} className="petition" style={{ minHeight: "10rem" }}>
                <span className="eyebrow" style={{ margin: 0 }}>
                  {l.commission} · {l.kind}
                  {l.dataset === "fixture" ? <span className="badge" data-tone="fixture">fixture</span> : null}
                </span>
                <span className="code">{l.code}</span>
                <span className="title">{l.name}</span>
                <span className="meta">
                  <span>
                    {l.documents_located}/{l.documents} docs
                  </span>
                  <span>{l.orders_reading} read</span>
                  <span>{l.reviewed_facts ? `${l.reviewed_facts} facts · to ${l.latest_reviewed_year}` : "no reviewed facts"}</span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </Panel>

      {st.commissions.map((c, i) => {
        const n = norms[i].data;
        return (
          <Panel
            key={c.code}
            num="02"
            title={`Tariff norms · ${c.code}`}
            aside={
              n ? (
                <span className="badge" data-tone={n.plan_confirmed && n.mapping_confirmed ? "ok" : "warn"}>
                  {n.plan_confirmed && n.mapping_confirmed ? "confirmed" : "working estimate"}
                </span>
              ) : null
            }
          >
            <p style={{ marginTop: 0 }}>{c.name}</p>
            {n ? (
              <dl className="kv">
                <dt>Regulations</dt>
                <dd>
                  {n.regulations.map((r) => (
                    <div key={r.role + r.title}>
                      {r.title} <span className="muted mono">{r.role.replace(/_/g, " ")}</span>
                    </div>
                  ))}
                  {n.regulations_in_library.length ? (
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      {n.regulations_in_library.length} regulation document{n.regulations_in_library.length === 1 ? "" : "s"} in the library
                    </div>
                  ) : null}
                </dd>
                <dt>Return</dt>
                <dd>{n.conventions.return_basis.value ? n.conventions.return_basis.value.toUpperCase() : <span className="muted">to be confirmed from the regulation</span>}</dd>
                <dt>Revenue gap</dt>
                <dd>{n.conventions.gap_convention.value ? CONVENTION_WORDS[n.conventions.gap_convention.value] : <span className="muted">to be confirmed</span>}</dd>
                <dt>ARR lines</dt>
                <dd>
                  {n.lines.length} lines, plan <span className="mono">{n.plan.id}</span> <span className="muted" title={n.plan.status}>({statusWord(n.plan.status)})</span>
                </dd>
                <dt>Applied</dt>
                <dd>{n.applied?.length ? `${n.applied.length} reviewed norm figures from its orders` : <span className="muted">no reviewed norm figure yet</span>}</dd>
              </dl>
            ) : (
              <p className="muted">The norms could not be loaded.</p>
            )}
            <p style={{ marginBottom: 0 }}>
              <Link className="btn" href={`/client/norms/${encodeURIComponent(c.code)}`}>
                All {c.code} norms <span className="arrow">→</span>
              </Link>
            </p>
          </Panel>
        );
      })}

      <Panel num="03" title="Draft a petition" aside="five steps, each a person's decision">
        <div className="flow" style={{ borderTop: 0 }}>
          {DRAFT_STEPS.map(([t, d], i) => (
            <div key={t}>
              <span className="n">{String(i + 1).padStart(2, "0")}</span>
              <h3>{t}</h3>
              <p>{d}</p>
            </div>
          ))}
        </div>
        {first ? (
          <div className="cta" style={{ display: "flex", gap: "0.7rem", flexWrap: "wrap", marginTop: "1.2rem" }}>
            {dist.map((l) => (
              <Link key={l.code} className={l === first ? "btn primary" : "btn"} href={`/client/cases/new?utility=${encodeURIComponent(l.code)}`}>
                Start for {l.code} <span className="arrow">→</span>
              </Link>
            ))}
          </div>
        ) : null}
      </Panel>
    </>
  );
}
