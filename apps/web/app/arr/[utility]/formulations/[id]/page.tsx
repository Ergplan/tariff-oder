import Link from "next/link";
import type { ArrAssumptionSetOut, ArrFormulationOut, ArrProjectionLineOut, FilingDraftOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../../components";

export const dynamic = "force-dynamic";

type Inputs = { facts?: { line_code: string; fiscal_year: string; value_type: string; value: string }[]; assumptions?: { key: string; value: string }[]; lines?: { line_code: string; fiscal_year: string; value: string }[] };

/**
 * One formulation version (ADR-0018): the projected lines for its years, blocked lines
 * first with the reason, each computed line with its formula and the facts, assumptions
 * and lines it used ("why"); the assumption set it ran on; the identity findings over the
 * projections; and the filing drafts made from it.  Everything here is a projection or an
 * assumption — labelled so — never a fact.
 */
export default async function FormulationPage({ params }: { params: Promise<{ utility: string; id: string }> }) {
  const { utility, id } = await params;
  const code = decodeURIComponent(utility);
  const res = await apiTry<ArrFormulationOut>(`/arr/formulations/${encodeURIComponent(id)}`);
  if (res.error || !res.data) {
    return (
      <>
        <h1>Formulation</h1>
        <ErrorBanner error={res.error!} />
      </>
    );
  }
  const f = res.data;
  const [aset, drafts] = await Promise.all([
    apiTry<ArrAssumptionSetOut>(`/arr/assumption-sets/${f.assumption_set_id}`),
    apiTry<FilingDraftOut[]>(`/arr/formulations/${f.id}/drafts`),
  ]);
  const lines = (f.lines ?? []) as ArrProjectionLineOut[];
  const ordered = [...lines.filter((l) => l.status === "blocked"), ...lines.filter((l) => l.status !== "blocked")];
  const summary = f.summary as { blocked?: number; identity_findings?: { identity_id: string; severity: string; message: string }[]; plan_status?: string };
  return (
    <>
      <p>
        <Link href={`/arr/${encodeURIComponent(code)}`}>← ARR history of {code}</Link>
      </p>
      <h1>
        {f.name}{" "}
        <span className="badge" data-tone="warn">
          projection
        </span>{" "}
        <span className="badge" data-tone={f.status === "frozen" ? "ok" : "neutral"}>
          {f.status}
        </span>{" "}
        {f.is_fixture ? (
          <span className="badge" data-tone="fixture">
            FIXTURE
          </span>
        ) : null}
      </h1>
      <p className="muted">
        Base {f.base_fy} · targets {(f.targets as { fiscal_year: string; value_type: string }[]).map((t) => `${t.fiscal_year} ${t.value_type}`).join(", ")} · plan {f.plan_id} v{f.plan_version} ({summary.plan_status}) · library{" "}
        {f.library_version} · input hash <code>{f.input_hash.slice(0, 16)}</code>
        {f.frozen_by ? ` · frozen by ${f.frozen_by}` : ""}
      </p>
      {summary.blocked ? (
        <div className="banner" data-tone="warn">
          {summary.blocked} line(s) blocked: a parameter has no source. Add it as an assumption with a rationale, or confirm it against a regulation clause, then create a new formulation.
        </div>
      ) : null}
      {(summary.identity_findings ?? []).map((x, i) => (
        <div key={i} className="banner" data-tone={x.severity === "blocking" ? "bad" : "warn"}>
          {x.message}
        </div>
      ))}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Year</th>
              <th>Line</th>
              <th>Value</th>
              <th>Formula and inputs (why)</th>
              <th>Clause</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((l) => {
              const inp = l.inputs as Inputs;
              const clause = l.regulation_clause as { citation?: string; source_name?: string } | null;
              return (
                <tr key={`${l.line_code}-${l.fiscal_year}`} data-status={l.status}>
                  <td className="mono">{l.fiscal_year}</td>
                  <td className="mono">{l.line_code}</td>
                  <td>
                    {l.status === "blocked" ? (
                      <span className="badge" data-tone="bad" title={l.blocked_reason ?? ""}>
                        blocked
                      </span>
                    ) : (
                      <span className="mono">
                        {l.value} <span className="muted">{l.unit}</span>
                      </span>
                    )}
                  </td>
                  <td>
                    <span className="mono">{l.formula_id}</span>
                    {l.status === "blocked" ? <div className="muted">{l.blocked_reason}</div> : null}
                    {(inp.facts ?? []).map((x, i) => (
                      <div key={`f${i}`} className="muted">
                        fact {x.line_code} {x.fiscal_year} {x.value_type} = {x.value}
                      </div>
                    ))}
                    {(inp.assumptions ?? []).map((x, i) => (
                      <div key={`a${i}`} className="muted">
                        assumption {x.key} = {x.value}
                      </div>
                    ))}
                    {(inp.lines ?? []).map((x, i) => (
                      <div key={`l${i}`} className="muted">
                        line {x.line_code} {x.fiscal_year} = {x.value}
                      </div>
                    ))}
                  </td>
                  <td className="muted">{clause ? `${clause.citation ?? ""} (${clause.source_name ?? ""})` : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h2>
        Assumptions{" "}
        <span className="badge" data-tone="neutral">
          assumption
        </span>
      </h2>
      {aset.error || !aset.data ? (
        <ErrorBanner error={aset.error!} />
      ) : (
        <>
          <p className="muted">
            Set &ldquo;{aset.data.name}&rdquo; v{aset.data.version} · {aset.data.status}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Year</th>
                  <th>Value</th>
                  <th>Source</th>
                  <th>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {aset.data.assumptions.map((a) => {
                  const c = a.clause_ref as { citation?: string; page_index?: number; excerpt?: string; confirmed_by?: string } | null;
                  return (
                    <tr key={a.id}>
                      <td className="mono">{a.key}</td>
                      <td className="mono">{a.fiscal_year || "every year"}</td>
                      <td className="mono">
                        {a.value} <span className="muted">{a.unit}</span>
                      </td>
                      <td>
                        {a.source_kind === "regulation_clause" && c ? (
                          <span title={c.excerpt}>
                            {c.citation}, p.{c.page_index} · confirmed by {c.confirmed_by}
                          </span>
                        ) : (
                          <span>entered by {a.entered_by}</span>
                        )}
                      </td>
                      <td className="muted">{a.rationale}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
      <h2>Filing drafts</h2>
      {f.status !== "frozen" ? <p className="muted">Freeze the formulation to draft a filing from it.</p> : null}
      {(drafts.data ?? []).length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <ul>
          {(drafts.data ?? []).map((d) => (
            <li key={d.id}>
              <Link href={`/arr/${encodeURIComponent(code)}/drafts/${d.id}`}>Draft of {new Date(d.generated_at).toLocaleString()}</Link>{" "}
              <span className="badge" data-tone="warn">
                draft · not filed
              </span>{" "}
              <span className="muted">
                {Number((d.trace as { numbers?: number }).numbers ?? 0)} traced numbers · template {d.template_id} v{d.template_version} ({d.template_status})
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
