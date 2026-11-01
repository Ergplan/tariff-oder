import Link from "next/link";
import type { ArrCaseOut, ArrHistoryOut, LibraryEntryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { KIND_SHORT, Level } from "../../levels";
import { ARR_STEPS, Eyebrow, FILING_WORDS, Panel, SegBar } from "../../studio";

export const dynamic = "force-dynamic";

type Fact = { value_type: string; canonical_value: string | null; canonical_unit: string | null; order: string; page: number; source_id: string; category_code: string | null; is_fixture: boolean };
type Line = { line_code: string; label: string; cells: { fiscal_year: string; facts: Fact[] }[] };

// the lines a petition is argued with, in the order a summary prints them
const KEY_LINES = ["E.SALES", "E.LOSS.DIST_PCT", "E.INPUT.DIST", "C.PP", "C.OM", "C.DEP", "C.INT", "C.RETURN", "C.TOTAL", "R.ARR", "R.REV.EXISTING", "R.GAP"];
// the strongest reviewed figure of a year: the final true-up, then the provisional, the approval, the petition
const RANK = ["final_true_up", "provisional_true_up", "approved", "actual", "petitioned"];
const VOICE_SHORT: Record<string, string> = { final_true_up: "trued up", provisional_true_up: "provisional", approved: "approved", actual: "actual", petitioned: "petitioned" };

function best(facts: Fact[]): Fact | undefined {
  return [...facts.filter((f) => !f.category_code && f.canonical_value !== null)].sort((a, b) => RANK.indexOf(a.value_type) - RANK.indexOf(b.value_type))[0];
}

/**
 * One licensee in the Petition Studio (increment 51): its reviewed ARR history at a glance (the
 * strongest reviewed figure of each year, with its order and page), its petitions, and its
 * documents in the library with the official link and how far each has been read.
 */
export default async function LicenseePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const name = decodeURIComponent(code);
  const [res, hist, cases] = await Promise.all([
    apiTry<LibraryEntryOut[]>(`/library/entries?utility=${encodeURIComponent(name)}`),
    apiTry<ArrHistoryOut>(`/arr/utilities/${encodeURIComponent(name)}/history`),
    apiTry<ArrCaseOut[]>("/cases"),
  ]);
  if (res.error) return <ErrorBanner error={res.error} />;
  const entries = [...(res.data ?? [])].sort((a, b) => (b.fiscal_year || "~").localeCompare(a.fiscal_year || "~") || a.document_kind.localeCompare(b.document_kind));
  const h = hist.data;
  const lines = ((h?.lines ?? []) as unknown as Line[]).filter((l) => KEY_LINES.includes(l.line_code)).sort((a, b) => KEY_LINES.indexOf(a.line_code) - KEY_LINES.indexOf(b.line_code));
  const years = (h?.years ?? []).slice(-4);
  const mine = (cases.data ?? []).filter((c) => c.utility === name);
  const commission = mine[0]?.commission;
  return (
    <>
      <p>
        <Link href="/client/library">← Library</Link>
      </p>
      <header className="case-head">
        <Eyebrow>
          Licensee{commission ? ` · ${commission}` : ""}
          {h?.is_fixture ? " · fixture data" : ""}
        </Eyebrow>
        <h1>{name}</h1>
        <p className="muted" style={{ margin: "0 0 1.2rem", fontSize: "1.05rem" }}>
          {h?.utility_name ?? ""}
        </p>
        <div className="cta" style={{ display: "flex", gap: "0.7rem", flexWrap: "wrap" }}>
          <Link className="btn primary" href={`/client/cases/new?utility=${encodeURIComponent(name)}`}>
            Start a petition <span className="arrow">→</span>
          </Link>
          <Link className="btn" href={`/arr/${encodeURIComponent(name)}`}>
            Full ARR history <span className="arrow">→</span>
          </Link>
          <Link className="btn" href={`/client/benchmarks?highlight=${encodeURIComponent(name)}`}>
            Benchmarks <span className="arrow">→</span>
          </Link>
        </div>
      </header>

      <Panel num="01" title="Reviewed ARR history" aside={h ? <span className="badge" data-tone="ok">fact</span> : null}>
        {!h || lines.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No reviewed ARR fact of {name} yet: its orders must be read and reviewed first. A petition can still be started; the studio lists what is missing.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Line</th>
                  {years.map((y) => (
                    <th key={y} style={{ textAlign: "right" }}>
                      {y}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.line_code}>
                    <td>
                      {l.label} <span className="mono muted">{l.line_code}</span>
                    </td>
                    {years.map((y) => {
                      const f = best(l.cells.find((c) => c.fiscal_year === y)?.facts ?? []);
                      return (
                        <td key={y} className="mono" style={{ textAlign: "right" }} title={f ? `${f.order}, p.${f.page}` : ""}>
                          {f ? (
                            <>
                              <Link href={`/sources/${f.source_id}`} style={{ textDecoration: "none" }}>
                                {Number(f.canonical_value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                              </Link>{" "}
                              <span className="muted" style={{ fontSize: "0.72rem" }}>
                                {f.canonical_unit === "INR_crore" ? "Cr" : f.canonical_unit}
                              </span>
                              <div className="muted" style={{ fontSize: "0.66rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                                {VOICE_SHORT[f.value_type] ?? f.value_type}
                              </div>
                            </>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 0 }}>
          Each figure is the strongest reviewed one of its year — the final true-up, else the provisional, the approval, the petition — with its order and page on hover.
        </p>
      </Panel>

      <Panel num="02" title="Petitions" aside={`${mine.length} for ${name}`}>
        {mine.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            None yet. <Link href={`/client/cases/new?utility=${encodeURIComponent(name)}`}>Start one →</Link>
          </p>
        ) : (
          <div className="petitions">
            {mine.map((c) => {
              const idx = Math.max(0, ARR_STEPS.findIndex((s) => s.key === c.status));
              const ys = (c.targets as { fiscal_year: string }[]).map((t) => t.fiscal_year);
              return (
                <Link key={c.id} href={`/client/cases/${c.id}`} className="petition" style={{ minHeight: "9rem" }}>
                  <span className="eyebrow" style={{ margin: 0 }}>
                    {FILING_WORDS[c.filing_kind] ?? c.filing_kind}
                  </span>
                  <span className="title">{c.title}</span>
                  <SegBar steps={ARR_STEPS.length} current={idx} />
                  <span className="meta">
                    <span>{c.status}</span>
                    <span>{ys.join(", ")}</span>
                  </span>
                </Link>
              );
            })}
          </div>
        )}
      </Panel>

      <Panel num="03" title="Documents" aside={`${entries.length} in the library`}>
        {entries.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No document of this licensee is in the library yet.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Document</th>
                  <th>Level</th>
                  <th>Official source</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{e.fiscal_year || "current period"}</td>
                    <td>
                      {KIND_SHORT[e.document_kind] ?? e.document_kind}
                      {e.title ? <div className="muted">{e.title}</div> : null}
                    </td>
                    <td>
                      <Level level={e.reading ?? e.status} />
                    </td>
                    <td>
                      {e.url ? (
                        <a href={e.url} rel="noreferrer noopener" target="_blank">
                          commission website
                        </a>
                      ) : (
                        <span className="muted">not located</span>
                      )}
                      {e.source_id ? (
                        <div>
                          <Link href={`/sources/${e.source_id}`}>registered copy</Link>
                        </div>
                      ) : null}
                    </td>
                    <td className="muted">{e.last_error ?? e.note ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
