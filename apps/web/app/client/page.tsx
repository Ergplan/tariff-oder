import Link from "next/link";
import type { ArrCaseOut, CoverageOut, MeOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../components";
import { LEVELS, LEVEL_HELP } from "./levels";
import { ARR_STEPS, Eyebrow, FILING_WORDS, SectionHead, SegBar } from "./studio";

export const dynamic = "force-dynamic";

type Cell = { level: string };
type State = {
  code: string;
  name: string;
  commissions: { code: string; name: string; commission_wide: Record<string, Cell>; licensees: { code: string; cells: Record<string, Cell> }[] }[];
};

const FLOW = [
  { t: "Setup", d: "Choose the licensee and the filing: the next year's ARR, a multi-year control period, a true-up or an APR." },
  { t: "Data", d: "Start from the licensee's reviewed history, each figure with its order and page; supply what the regulations leave to you." },
  { t: "Formulate", d: "Project every line of the ARR. A line without its inputs is blocked, with the reason, never filled in." },
  { t: "Freeze", d: "Lock the assumptions of this version. Revising keeps the frozen version and its drafts on record." },
  { t: "Draft", d: "A petition and its formats, every number traced. Watermarked as a draft: a person edits and files it." },
];

/**
 * The Petition Studio home (ADR-0019, increment 51): your petitions and where each stands, the
 * five steps of preparing one, and how much of every state's regulatory record is available.
 */
export default async function ClientHome() {
  const [me, cases, cov] = await Promise.all([apiTry<MeOut>("/me"), apiTry<ArrCaseOut[]>("/cases"), apiTry<CoverageOut>("/library/coverage")]);
  if (me.error || !me.data) return <ErrorBanner error={me.error!} />;
  const orgs = me.data.organisations ?? [];
  const canStart = orgs.some((o) => o.role !== "viewer");
  const list = cases.data ?? [];
  const states = (cov.data?.states ?? []) as unknown as State[];
  const totals = cov.data?.totals ?? {};
  const located = LEVELS.filter((l) => l !== "missing").reduce((a, l) => a + (totals[l] ?? 0), 0);
  const expected = LEVELS.reduce((a, l) => a + (totals[l] ?? 0), 0);
  const drafts = list.filter((c) => c.draft_id).length;
  return (
    <>
      <section className="hero">
        <Eyebrow>
          Petition studio <span>/</span> {orgs.length ? orgs.map((o) => o.name).join(" · ") : me.data.email}
        </Eyebrow>
        <h1>
          Prepare the ARR petition. <em>Every number traced.</em>
        </h1>
        <p className="lede">
          Start from the licensee&apos;s reviewed regulatory history, formulate the years ahead under the commission&apos;s regulations, and produce a draft petition a person edits and files. Nothing
          is filed by the software.
        </p>
        <div className="cta">
          {canStart ? (
            <Link className="btn primary" href="/client/cases/new">
              Start a petition <span className="arrow">→</span>
            </Link>
          ) : null}
          <Link className="btn" href="/client/atlas">
            Explore the map of India <span className="arrow">→</span>
          </Link>
          <Link className="btn" href="/client/library">
            Open the library <span className="arrow">→</span>
          </Link>
          <Link className="btn" href="/client/benchmarks">
            Benchmarks <span className="arrow">→</span>
          </Link>
        </div>
        {!orgs.length ? <p className="muted">You are not a member of a client organisation yet: an administrator adds you.</p> : null}
      </section>

      <div className="statline">
        <div>
          <div className="num">{states.length}</div>
          <div className="cap">States in the library</div>
        </div>
        <div>
          <div className="num">{located}</div>
          <div className="cap">Documents located of {expected} expected</div>
        </div>
        <div>
          <div className="num">{(totals.reviewed ?? 0) + (totals.published ?? 0)}</div>
          <div className="cap">Documents with reviewed facts</div>
        </div>
        <div>
          <div className="num">{list.length}</div>
          <div className="cap">Your petitions</div>
        </div>
        <div>
          <div className="num">{drafts}</div>
          <div className="cap">Drafts ready to edit</div>
        </div>
      </div>

      <SectionHead num="01" title="Your petitions" aside={list.length ? `${list.length} in progress or drafted` : "none yet"} />
      {cases.error ? (
        <ErrorBanner error={cases.error} />
      ) : (
        <div className="petitions">
          {list.map((c) => {
            const idx = Math.max(0, ARR_STEPS.findIndex((s) => s.key === c.status));
            const years = (c.targets as { fiscal_year: string }[]).map((t) => t.fiscal_year);
            return (
              <Link key={c.id} href={`/client/cases/${c.id}`} className="petition">
                <span className="eyebrow" style={{ margin: 0 }}>
                  {FILING_WORDS[c.filing_kind] ?? c.filing_kind} · {c.commission}
                </span>
                <span className="code">{c.utility}</span>
                <span className="title">{c.title}</span>
                <SegBar steps={ARR_STEPS.length} current={c.status === "closed" ? ARR_STEPS.length : idx} />
                <span className="meta">
                  <span>{c.status === "drafted" ? "Draft ready" : c.status}</span>
                  <span>
                    {years[0]}
                    {years.length > 1 ? ` → ${years[years.length - 1]}` : ""}
                  </span>
                  <span>{new Date(c.updated_at).toLocaleDateString()}</span>
                </span>
              </Link>
            );
          })}
          {canStart ? (
            <Link href="/client/cases/new" className="petition new">
              <span className="plus">+</span>
              <span className="code" style={{ fontSize: "1.4rem" }}>
                New petition
              </span>
              <span className="title">Annual ARR, MYT control period, true-up or APR.</span>
            </Link>
          ) : null}
        </div>
      )}

      <SectionHead num="02" title="How a petition is prepared" aside="five steps, each a person's decision" />
      <div className="flow">
        {FLOW.map((f, i) => (
          <div key={f.t}>
            <span className="n">{String(i + 1).padStart(2, "0")}</span>
            <h3>{f.t}</h3>
            <p>{f.d}</p>
          </div>
        ))}
      </div>

      <SectionHead num="03" title="The regulatory record, state by state" aside={<Link href="/client/atlas">Map of India →</Link>} />
      {states.length === 0 ? (
        <p className="muted">The library is empty: an administrator seeds the expected documents and acquires them.</p>
      ) : (
        <>
          <div className="statemap">
            {states.map((s) => {
              const counts: Record<string, number> = {};
              let n = 0;
              for (const c of s.commissions)
                for (const cell of [...Object.values(c.commission_wide), ...c.licensees.flatMap((l) => Object.values(l.cells))]) {
                  counts[cell.level] = (counts[cell.level] ?? 0) + 1;
                  n += 1;
                }
              const licensees = s.commissions.reduce((a, c) => a + c.licensees.length, 0);
              return (
                <Link key={s.code} href={`/client/states/${encodeURIComponent(s.code)}`}>
                  <span className="st">{s.name}</span>
                  <span className="sub">
                    {s.commissions.map((c) => c.code).join(" · ")} · {licensees} licensee{licensees === 1 ? "" : "s"}
                  </span>
                  <span className="levelbar" aria-label={`${n} documents expected`}>
                    {LEVELS.filter((l) => l !== "missing").map((l) =>
                      counts[l] ? <span key={l} data-level={l} style={{ width: `${(100 * counts[l]) / Math.max(1, n)}%` }} title={`${counts[l]} ${l}`} /> : null,
                    )}
                  </span>
                  <span className="sub">
                    {n - (counts.missing ?? 0)} of {n} documents located
                  </span>
                </Link>
              );
            })}
          </div>
          <div className="legend">
            {LEVELS.filter((l) => l !== "missing").map((l) => (
              <span key={l} title={LEVEL_HELP[l]}>
                <i style={{ background: `var(--${({ located: "info", acquired: "warn", read: "fixture", reviewed: "teal", published: "ok", failed: "bad" } as Record<string, string>)[l]})` }} />
                {l}
              </span>
            ))}
          </div>
        </>
      )}
    </>
  );
}
