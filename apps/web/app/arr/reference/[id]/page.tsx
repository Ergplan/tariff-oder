import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { Eyebrow, Panel } from "../../../client/studio";
import SignOff from "./sign-off";

export const dynamic = "force-dynamic";

type Counts = Record<string, number>;
type MeOut = { role: string };
type SignRecord = { id: string; scope: string; decision: string; note: string | null; signed_by: string; signed_at: string; current: boolean };
type Acceptance = { reproduction_sha256: string; scopes: string[]; open: string[]; latest: Record<string, SignRecord>; records: SignRecord[] };
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
  pipeline: {
    fiscal_year: string;
    voice: string;
    counts: Counts;
    fed: Record<string, { binding: string; output: string; value: string }>;
    not_fed: string[];
    records: string[];
    checks: { output: string; label: string; filed: string | null; computed: string | null; result: string }[];
  }[];
  coverage: {
    sheet: string;
    columns: { column: string; fiscal_year: string; words: string; voice: string }[];
    lines: { row: number; label: string; line_code: string | null; cells: Record<string, { status: string; source: string | null; filed: string | null }> }[];
    summary: Record<string, Counts>;
  } | null;
  findings: { id: string; kind: string; title: string; detail: string; where: string[]; for: string }[];
  accounting: {
    list: string;
    counts: Counts;
    not_in_index: string[];
    formats: { format: string; title: string; sheet: string | null; alias_why: string | null; status: string }[];
  } | null;
  checklist: {
    checklist: string;
    version: number;
    status: string;
    scope: string;
    regulation: { title: string; path: string; sha256: string };
    counts: Counts;
    items: {
      id: string;
      clause: string;
      page: number;
      quote: string;
      requirement: string;
      proceedings: string[];
      note: string | null;
      result: string;
      evidence: { kind: string; ref: string | null; why: string; weight: string | null; found: boolean | null; where: string | null; context?: string }[];
    }[];
  } | null;
  narrative: {
    status: string;
    min_digits: number;
    documents: Record<string, Counts>;
    untraced_by_table: { document: string; table: string; figures: number }[];
    bound: {
      counts: Counts;
      checks: {
        document: string;
        table: string;
        column: string;
        key: string;
        label: string;
        printed: string;
        format_rounded: string | null;
        cells: string[];
        result: string;
        last_place_units: number | null;
      }[];
    };
  } | null;
};

const TONE: Record<string, string> = {
  reproduced: "ok",
  read: "neutral",
  present: "neutral",
  blank: "warn",
  missing: "bad",
  match: "ok",
  traced: "ok",
  near: "warn",
  opposite_sign: "neutral",
  untraced: "warn",
  uninformative: "neutral",
  not_printed: "warn",
  evidenced: "ok",
  partly: "warn",
  mentioned: "warn",
  not_found: "bad",
  outside_package: "neutral",
  no_format_value: "warn",
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
  const [res, acc, me] = await Promise.all([
    apiTry<Filing>(`/arr/reference-filings/${encodeURIComponent(id)}`),
    apiTry<Acceptance>(`/arr/reference-filings/${encodeURIComponent(id)}/acceptance`),
    apiTry<MeOut>("/me"),
  ]);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const f = res.data;
  const reviewer = ["reviewer", "administrator"].includes(me.data?.role ?? "");
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
            {f.pipeline.length ? (
              <>
                <h3 style={{ marginTop: "1.4rem" }}>End to end: the chain fed by the schedules</h3>
                <p className="muted" style={{ fontSize: "0.85rem" }}>
                  The same chain, with its record inputs replaced by what each schedule&apos;s reproduction computes (power purchase, O&amp;M, depreciation, interest on security deposit, bad debts, revenue…). What is not fed stays the format&apos;s own figure, listed.
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Fed by schedules</th>
                        <th>Still records</th>
                        <th>Net ARR · gap (computed)</th>
                        <th>Result</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.pipeline.map((p) => {
                        const v = Object.fromEntries(p.checks.map((c) => [c.output, c]));
                        return (
                          <tr key={p.fiscal_year + p.voice}>
                            <td className="mono">{p.fiscal_year}</td>
                            <td>
                              <details>
                                <summary>{Object.keys(p.fed).length} inputs</summary>
                                <ul className="mono" style={{ fontSize: "0.75rem", margin: "0.3rem 0" }}>
                                  {Object.entries(p.fed).map(([k, x]) => (
                                    <li key={k}>
                                      {k} ← {x.binding}: {x.output}
                                    </li>
                                  ))}
                                </ul>
                              </details>
                            </td>
                            <td>
                              <details>
                                <summary>{p.records.length} inputs</summary>
                                <ul className="mono" style={{ fontSize: "0.75rem", margin: "0.3rem 0" }}>
                                  {p.records.map((k) => (
                                    <li key={k}>{k}</li>
                                  ))}
                                </ul>
                              </details>
                            </td>
                            <td className="mono">
                              {v.arr_net?.computed ?? "—"} · {v.arr_gap?.computed ?? "—"}
                              <div className="muted">
                                filed {v.arr_net?.filed ?? "—"} · {v.arr_gap?.filed ?? "—"}
                              </div>
                            </td>
                            <td>
                              <CountBadges counts={p.counts} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            ) : null}
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
        <p>
          <a className="btn" href={`/api/arr/reference-filings/${encodeURIComponent(f.id)}/queries`}>
            Draft queries to the petitioner (Markdown)
          </a>{" "}
          <span className="muted">a draft from the findings above, for a reviewer to edit and issue — not issued</span>
        </p>
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
      <Panel num="06" title="Every format accounted for" aside="each format the filing lists — reproduced, read, present, blank or missing">
        {!f.accounting ? (
          <p className="muted">No index of formats.</p>
        ) : (
          <>
            <p>
              <CountBadges counts={f.accounting.counts} />
            </p>
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              Against {f.accounting.list}.
              {f.accounting.not_in_index.length ? ` Filed but not in the index: ${f.accounting.not_in_index.join(", ")}.` : ""}
            </p>
            <details>
              <summary>All {f.accounting.formats.length} formats</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Format</th>
                      <th>Sheet</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {f.accounting.formats.map((x, i) => (
                      <tr key={i}>
                        <td>
                          {x.format}
                          <div className="muted">{x.title}</div>
                        </td>
                        <td className="mono">
                          {x.sheet ?? "—"}
                          {x.alias_why ? <div className="muted">{x.alias_why}</div> : null}
                        </td>
                        <td>
                          <span className="badge" data-tone={TONE[x.status] ?? "neutral"}>
                            {x.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </Panel>

      <Panel num="06b" title="The narrative against the formats" aside="every figure of the petition's text tables looked for in the formats; the summary tables bound row by row">
        {!f.narrative ? (
          <p className="muted">The narrative has not been reconciled.</p>
        ) : (
          <>
            <p>
              Summary tables, row by row: <CountBadges counts={f.narrative.bound.counts} />
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Tables</th>
                    <th>Figures traced, near, opposite sign, untraced, uninformative</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(f.narrative.documents).map(([doc, c]) => (
                    <tr key={doc}>
                      <td>{doc}</td>
                      <td className="mono">{c.tables}</td>
                      <td>
                        <CountBadges counts={Object.fromEntries(Object.entries(c).filter(([k]) => k !== "tables"))} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              {f.narrative.status}.  A figure with fewer than {f.narrative.min_digits} significant digits is not traced (it would match by chance).
            </p>
            <details>
              <summary>Summary-table figures that differ ({f.narrative.bound.checks.filter((c) => c.result !== "match").length})</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Where</th>
                      <th>Row</th>
                      <th>Printed</th>
                      <th>Format</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {f.narrative.bound.checks
                      .filter((c) => c.result !== "match")
                      .map((c, i) => (
                        <tr key={i}>
                          <td>
                            {c.table}
                            <div className="muted">
                              {c.document} · {c.column}
                            </div>
                          </td>
                          <td>{c.label}</td>
                          <td className="mono">{c.printed || "—"}</td>
                          <td className="mono">
                            {c.format_rounded ?? "—"}
                            <div className="muted">{c.cells.join(" + ")}</div>
                          </td>
                          <td>
                            <span className="badge" data-tone={TONE[c.result] ?? "neutral"}>
                              {c.result}
                            </span>
                            {c.last_place_units != null ? <div className="muted">{c.last_place_units} in the last place</div> : null}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </details>
            <details>
              <summary>Tables with the most untraced figures (the reviewer's reading list)</summary>
              <ul>
                {f.narrative.untraced_by_table.map((t, i) => (
                  <li key={i}>
                    {t.table} <span className="muted">— {t.document}, {t.figures}</span>
                  </li>
                ))}
              </ul>
            </details>
          </>
        )}
      </Panel>

      <Panel num="06c" title="The regulations' filing requirements" aside="what the regulations require a petition to contain or to have been done, and the evidence found — evidence is not compliance">
        {!f.checklist ? (
          <p className="muted">No filing checklist evaluated.</p>
        ) : (
          <>
            <p>
              <CountBadges counts={f.checklist.counts} />
            </p>
            <p className="muted" style={{ fontSize: "0.85rem" }}>
              {f.checklist.regulation.title} — {f.checklist.status}. {f.checklist.scope}
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Clause</th>
                    <th>Requirement</th>
                    <th>Evidence</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {f.checklist.items.map((it) => (
                    <tr key={it.id}>
                      <td className="mono">
                        {it.clause}
                        <div className="muted">p.{it.page}</div>
                      </td>
                      <td>
                        {it.requirement}
                        <div className="muted">“{it.quote}”</div>
                        {it.note ? <div className="muted">{it.note}</div> : null}
                      </td>
                      <td>
                        <ul>
                          {it.evidence.map((e, i) => (
                            <li key={i}>
                              <span className="badge" data-tone={e.found === null ? "neutral" : e.found ? "ok" : "bad"}>
                                {e.found === null ? "outside" : e.found ? "found" : "not found"}
                              </span>{" "}
                              {e.why}
                              {e.where ? <div className="muted mono">{e.where}</div> : null}
                              {e.context ? <div className="muted">…{e.context}…</div> : null}
                            </li>
                          ))}
                        </ul>
                      </td>
                      <td>
                        <span className="badge" data-tone={TONE[it.result] ?? "neutral"}>
                          {it.result.replace("_", " ")}
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

      <Panel num="07" title="Independent sign-off" aside="by a named checker who did not build it — pinned to this reproduction; the build signs nothing">
        {!acc.data ? (
          <p className="muted">No reproduction to sign off.</p>
        ) : (
          <>
            <p>
              <b>{acc.data.scopes.length - acc.data.open.length}</b> of <b>{acc.data.scopes.length}</b> scopes signed off on the current reproduction.{" "}
              {acc.data.open.includes("filing") ? (
                <span className="badge" data-tone="warn">
                  the filing is not signed off
                </span>
              ) : null}
            </p>
            {acc.data.records.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Scope</th>
                      <th>Decision</th>
                      <th>By · when</th>
                      <th>Reproduction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acc.data.records.map((r) => (
                      <tr key={r.id}>
                        <td className="mono">{r.scope}</td>
                        <td>
                          <span className="badge" data-tone={r.decision === "rejected" ? "bad" : r.decision === "accepted" ? "ok" : "warn"}>
                            {r.decision.replace(/_/g, " ")}
                          </span>
                          {r.note ? <div className="muted">{r.note}</div> : null}
                        </td>
                        <td>
                          {r.signed_by}
                          <div className="mono muted">{r.signed_at.slice(0, 16).replace("T", " ")}</div>
                        </td>
                        <td>
                          <span className="badge" data-tone={r.current ? "ok" : "warn"}>
                            {r.current ? "current" : "stale — changed since"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">Nobody has signed anything off yet.</p>
            )}
            {reviewer ? (
              <SignOff filingId={f.id} scopes={acc.data.scopes} sha={acc.data.reproduction_sha256} />
            ) : (
              <p className="muted">A reviewer who did not build the reproduction signs it off here.</p>
            )}
          </>
        )}
      </Panel>
      <p className="muted" style={{ fontSize: "0.82rem" }}>
        {f.status}
      </p>
    </>
  );
}
