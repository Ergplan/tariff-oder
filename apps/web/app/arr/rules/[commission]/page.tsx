import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { Eyebrow } from "../../../client/studio";

export const dynamic = "force-dynamic";

type Rule = {
  id: string;
  version: number;
  status: string;
  title: string;
  output: string;
  unit: string;
  schedule: string | null;
  per: string | null;
  formula: string;
  inputs: Record<string, { source: string; unit: string; value: string | null }>;
  regulation: string;
  clause: string | null;
  page: number | null;
  verified: boolean;
  clause_candidates: { page: number; score: number; words: string[]; values: string[]; snippet: string; regulation_pdf: string; kind: string }[];
  from_fy: string | null;
  to_fy: string | null;
  examples: number;
};
type Rules = {
  commission: string;
  rules: Rule[];
  summary: { rules: number; approved: number; clauses_verified: number; with_clause_candidates: number };
};

/** A commission's executable calculation rules and their status (ADR-0021): drafts until a person approves them on a verified clause. */
export default async function RulesPage({ params }: { params: Promise<{ commission: string }> }) {
  const { commission } = await params;
  const res = await apiTry<Rules>(`/arr/rules/${encodeURIComponent(commission)}`);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const d = res.data;
  return (
    <>
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>Calculation rules · {d.commission}</Eyebrow>
        <h1>{d.commission} rules</h1>
        <div className="case-meta">
          <span>
            Rules <b>{d.summary.rules}</b>
          </span>
          <span>
            Approved <b>{d.summary.approved}</b>
          </span>
          <span>
            Clauses verified <b>{d.summary.clauses_verified}</b>
          </span>
        </div>
      </header>
      {d.summary.approved === 0 ? (
        <div className="banner" data-tone="warn">
          Every rule is a draft and no clause has been verified against the regulation: a case computed with them is not filing-ready. Approval is a reviewer&apos;s act.
        </div>
      ) : null}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Formula</th>
              <th>Inputs</th>
              <th>Years</th>
              <th>Clause</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {d.rules.map((r) => (
              <tr key={`${r.id}-${r.version}`}>
                <td>
                  {r.title}
                  <div className="mono muted">
                    {r.id} v{r.version} → {r.output} ({r.unit}){r.per ? ` · per ${r.per}` : ""}
                  </div>
                </td>
                <td className="mono">{r.formula}</td>
                <td className="mono" style={{ fontSize: "0.75rem" }}>
                  {Object.entries(r.inputs).map(([k, v]) => (
                    <div key={k}>
                      {k}: {v.source === "regulation" ? `${v.value} ${v.unit} (regulation)` : v.source}
                    </div>
                  ))}
                </td>
                <td className="mono">
                  {r.from_fy ?? "…"} – {r.to_fy ?? "…"}
                </td>
                <td style={{ fontSize: "0.82rem" }}>
                  {r.regulation}
                  {r.clause ? `, ${r.clause}` : ""}
                  {r.page ? ` (p.${r.page})` : ""}
                  <div>
                    <span className="badge" data-tone={r.verified ? "ok" : "warn"}>
                      {r.verified ? "verified" : "not verified"}
                    </span>
                  </div>
                  {!r.verified && r.clause_candidates?.length ? (
                    <details style={{ marginTop: "0.3rem" }}>
                      <summary className="muted">
                        {r.clause_candidates.length} page{r.clause_candidates.length === 1 ? "" : "s"} to check (proposed, not verified)
                      </summary>
                      <ul style={{ margin: "0.3rem 0", paddingLeft: "1rem" }}>
                        {r.clause_candidates.map((c, i) => (
                          <li key={i}>
                            <span className="mono">
                              {c.regulation_pdf} p.{c.page}
                            </span>{" "}
                            {c.kind !== "regulation" ? <span className="muted">({c.kind.split(" — ")[0]})</span> : null}{" "}
                            {c.values.length ? <span className="badge" data-tone="neutral">{c.values.join(", ")}</span> : null}
                            <div className="muted">{c.snippet}</div>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </td>
                <td>
                  <span className="badge" data-tone={r.status === "approved" ? "ok" : "warn"}>
                    {r.status}
                  </span>
                  <div className="muted" style={{ fontSize: "0.75rem" }}>
                    {r.examples} example{r.examples === 1 ? "" : "s"}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
