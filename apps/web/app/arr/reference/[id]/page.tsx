import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { Eyebrow, Panel } from "../../../client/studio";

export const dynamic = "force-dynamic";

type Counts = Record<string, number>;
type Check = { fiscal_year: string; voice?: string; words: string; output: string; label?: string; filed: string | null; computed: string | null; result: string; why?: string | null };
type Filing = {
  id: string;
  commission: string;
  licensee: string;
  title: string;
  status: string;
  documents: { total: number; hashed: number; by_role: Counts; missing: string[] };
  formats: { binding: string; sheet: string; columns: number; counts: Counts; not_matching: Check[] }[];
  records: { binding?: string; sheet?: string; counts?: Counts; tie?: string; fiscal_year?: string; working?: string; filed?: string; result?: string }[];
  chain: { by_column: Record<string, Counts>; computed: Check[] } | null;
  coverage: {
    sheet: string;
    columns: { column: string; fiscal_year: string; words: string; voice: string }[];
    lines: { row: number; label: string; line_code: string | null; cells: Record<string, { status: string; source: string | null; filed: string | null }> }[];
    summary: Record<string, Counts>;
  } | null;
  findings: { id: string; kind: string; title: string; detail: string; where: string[]; for: string }[];
};

const TONE: Record<string, string> = {
  match: "ok",
  computed: "ok",
  tied: "ok",
  differs: "bad",
  blocked: "warn",
  given: "neutral",
  record: "neutral",
  no_filed_value: "neutral",
  not_a_value: "neutral",
};

const STATUS_HELP: Record<string, string> = {
  computed: "computed by the rules from base records (the chain) or from the format's own lines",
  tied: "a schedule's reproduction gives the figure the ARR carries",
  given: "a filed figure standing in for its computation — never counted as reproduced",
  differs: "computed or tied, and not equal to the filed figure — see the findings",
  record: "an input nobody reproduces yet — taken on trust",
};

function CountBadges({ counts }: { counts: Counts }) {
  return (
    <span style={{ display: "inline-flex", gap: "0.3rem", flexWrap: "wrap" }}>
      {Object.entries(counts).map(([k, n]) => (
        <span key={k} className="badge" data-tone={TONE[k] ?? "neutral"}>
          {n} {k.replace(/_/g, " ")}
        </span>
      ))}
    </span>
  );
}

/**
 * One reference filing (milestone 13): the chain from base records by column, each format's
 * reproduction, the utility's workings tied to the filing, and the findings for the reviewer.
 */
export default async function ReferenceFiling({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await apiTry<Filing>(`/arr/reference-filings/${encodeURIComponent(id)}`);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const f = res.data;
  return (
    <>
      <p>
        <Link href="/arr/reference">← Reference filings</Link>
      </p>
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>
          Reference filing · {f.licensee} · {f.commission}
          <span className="badge" data-tone="warn">
            draft rules · nothing approved
          </span>
        </Eyebrow>
        <h1>{f.title}</h1>
        <div className="case-meta">
          <span>
            Documents hashed <b>{f.documents.hashed}</b> of <b>{f.documents.total}</b>
          </span>
          {Object.entries(f.documents.by_role).map(([k, n]) => (
            <span key={k}>
              {k.replace(/_/g, " ")} <b>{n}</b>
            </span>
          ))}
        </div>
        {f.documents.missing.length ? <p className="muted">Not in the copy received: {f.documents.missing.join("; ")}</p> : null}
      </header>

      <Panel num="01" title="How each figure is established" aside="the ARR format's petition columns, line by line — what the reproduction covers and what it takes on trust">
        {!f.coverage ? (
          <p className="muted">Not reproduced yet.</p>
        ) : (
          (() => {
            const cov = f.coverage;
            const cols = cov.columns.filter((c) => c.voice === "petitioned");
            return (
              <>
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  {Object.entries(STATUS_HELP).map(([k, v]) => (
                    <span key={k} style={{ marginRight: "0.9rem", display: "inline-block" }}>
                      <span className="badge" data-tone={TONE[k]}>
                        {k}
                      </span>{" "}
                      {v}
                    </span>
                  ))}
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Line</th>
                        {cols.map((c) => (
                          <th key={c.column} style={{ textAlign: "right" }}>
                            {c.fiscal_year}
                            <div className="muted" style={{ fontWeight: 400 }}>
                              {c.words}
                            </div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td className="muted">All lines</td>
                        {cols.map((c) => (
                          <td key={c.column} style={{ textAlign: "right" }}>
                            <CountBadges counts={cov.summary[c.column] ?? {}} />
                          </td>
                        ))}
                      </tr>
                      {cov.lines
                        .filter((l) => cols.some((c) => l.cells[c.column]))
                        .map((l) => (
                          <tr key={l.row}>
                            <td>
                              {l.label}
                              <div className="mono muted">
                                row {l.row}
                                {l.line_code ? ` · ${l.line_code}` : ""}
                              </div>
                            </td>
                            {cols.map((c) => {
                              const cell = l.cells[c.column];
                              return (
                                <td key={c.column} style={{ textAlign: "right" }} title={cell?.source ?? undefined}>
                                  {cell ? (
                                    <>
                                      <span className="mono">{cell.filed ?? "—"}</span>{" "}
                                      <span className="badge" data-tone={TONE[cell.status] ?? "neutral"}>
                                        {cell.status}
                                      </span>
                                      {cell.source ? (
                                        <div className="mono muted" style={{ fontSize: "0.72rem" }}>
                                          {cell.source}
                                        </div>
                                      ) : null}
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
              </>
            );
          })()
        )}
      </Panel>

      <Panel num="02" title="The chain, from base records" aside="one evaluation per column of the ARR format, through every schedule rule">
        {!f.chain ? (
          <p className="muted">Not reproduced yet.</p>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(f.chain.by_column).map(([col, counts]) => (
                    <tr key={col}>
                      <td className="mono">{col}</td>
                      <td>
                        <CountBadges counts={counts} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3 style={{ marginTop: "1.4rem" }}>FY2026-27, computed against filed</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Line</th>
                    <th style={{ textAlign: "right" }}>Filed</th>
                    <th style={{ textAlign: "right" }}>Computed</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {f.chain.computed.map((c, i) => (
                    <tr key={i}>
                      <td>
                        {c.label}
                        <div className="mono muted">{c.output}</div>
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {c.filed ?? "—"}
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {c.computed ?? "—"}
                      </td>
                      <td>
                        <span className="badge" data-tone={TONE[c.result] ?? "neutral"}>
                          {c.result.replace(/_/g, " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <Panel num="03" title="Findings" aside="for the petitioner and the reviewer — none resolved by the build">
        {f.findings.map((x) => (
          <div key={x.id} style={{ padding: "0.7rem 0", borderBottom: "1px solid var(--line)" }}>
            <div className="eyebrow" style={{ margin: 0 }}>
              {x.id} · {x.kind} · for the {x.for}
            </div>
            <strong>{x.title}</strong>
            <p style={{ margin: "0.3rem 0" }}>{x.detail}</p>
            <div className="mono muted" style={{ fontSize: "0.8rem" }}>
              {x.where.join(" · ")}
            </div>
          </div>
        ))}
      </Panel>

      <Panel num="04" title="Each format, reproduced" aside="from its own input rows through the rules of each year">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Format</th>
                <th>Columns</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {f.formats.map((x) => (
                <tr key={x.binding}>
                  <td>
                    {x.sheet}
                    <div className="mono muted">{x.binding}</div>
                  </td>
                  <td className="mono">{x.columns}</td>
                  <td>
                    <CountBadges counts={x.counts} />
                    {x.not_matching.length ? (
                      <details style={{ marginTop: "0.4rem" }}>
                        <summary className="muted">{x.not_matching.length} not matching</summary>
                        <ul style={{ fontSize: "0.82rem", margin: "0.3rem 0" }}>
                          {x.not_matching.map((c, i) => (
                            <li key={i} className="mono">
                              {c.result} · {c.fiscal_year} {c.words?.trim()} · {c.output} · filed {c.filed ?? "—"} · computed {c.computed ?? "—"} {c.why ? `· ${c.why}` : ""}
                            </li>
                          ))}
                        </ul>
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel num="05" title="The utility's workings" aside="records reproduced and tied to the filed formats">
        <div className="table-wrap">
          <table>
            <tbody>
              {f.records.map((r, i) => (
                <tr key={i}>
                  <td>{r.tie ? `ties to ${r.tie} · ${r.fiscal_year}` : `${r.sheet ?? r.binding}`}</td>
                  <td>
                    {r.counts ? (
                      <CountBadges counts={r.counts} />
                    ) : (
                      <>
                        <span className="mono">
                          working {r.working} · filed {r.filed}
                        </span>{" "}
                        <span className="badge" data-tone={TONE[r.result ?? ""] ?? "neutral"}>
                          {r.result}
                        </span>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <p className="muted" style={{ fontSize: "0.82rem" }}>
        {f.status}
      </p>
    </>
  );
}
