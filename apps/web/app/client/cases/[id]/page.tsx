import Link from "next/link";
import type { ArrAssumptionSetOut, ArrCaseOut, ArrFormulationOut, MeOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { ActionButton } from "../../actions";
import AssumptionForm from "./assumption-form";
import TrueUpCase from "./true-up";
import CaseActivity from "./activity";
import { ARR_STEPS, Eyebrow, NextAction, Panel, Stepper } from "../../studio";

export const dynamic = "force-dynamic";

type Readiness = {
  plan: { id: string; version: number; status: string };
  base_facts: { line_code: string; present: boolean; value: string | null; value_type: string | null }[];
  parameters: { key: string; for_line: string; missing_years: string[]; supplied: boolean }[];
  documents: { kind: string; fiscal_year: string; status: string; arr_state: string | null; source_id: string | null }[];
  missing_base_facts: string[];
  missing_parameters: string[];
  ready_to_formulate: boolean;
  note: string;
};

/**
 * One ARR case (ADR-0019), step by step: what data is ready and missing, the assumptions,
 * the formulation (projections, with blocked lines and their reasons), freezing it, and the
 * draft petition.  Viewers see everything; editors and owners act.
 */
export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [res, me] = await Promise.all([apiTry<ArrCaseOut>(`/cases/${encodeURIComponent(id)}`), apiTry<MeOut>("/me")]);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const c = res.data;
  const role = (me.data?.organisations ?? []).find((o) => o.id === c.organisation_id)?.role;
  const canEdit = role === "editor" || role === "owner";
  if (c.filing_kind === "true_up" || c.filing_kind === "apr") return <TrueUpCase c={c} role={role} />;
  const r = c.readiness as unknown as Readiness;
  const [aset, form] = await Promise.all([
    apiTry<ArrAssumptionSetOut>(`/arr/assumption-sets/${c.assumption_set_id}`),
    c.formulation_id ? apiTry<ArrFormulationOut>(`/arr/formulations/${c.formulation_id}`) : Promise.resolve({ data: undefined, error: undefined }),
  ]);
  const years = (c.targets as { fiscal_year: string }[]).map((t) => t.fiscal_year);
  const frozen = ["frozen", "drafted", "closed"].includes(c.status);
  const f = form.data;
  const summary = (f?.summary ?? {}) as { blocked?: number; blocked_lines?: string[]; identity_findings?: { message: string; severity: string }[] };
  const keyLines = ["E.SALES", "E.INPUT.DIST", "C.PP", "C.OM", "C.TOTAL", "R.ARR", "R.REV.EXISTING", "R.GAP", "R.ACOS"];
  const next = (() => {
    if (c.status === "drafted") return { what: "Edit and file the draft", why: "The draft is watermarked; a person edits it, signs it and files it with the Commission." };
    if (c.status === "frozen") return { what: "Draft the petition", why: "The formulation is frozen: draft the petition and its formats from it." };
    if (f && summary.blocked) return { what: `Unblock ${summary.blocked} line(s)`, why: "Supply the missing inputs below, then formulate again." };
    if (c.status === "formulated") return { what: "Review and freeze", why: "Check the projected lines, then freeze this version to draft from it." };
    if (!r.ready_to_formulate)
      return {
        what: `Supply ${r.missing_parameters.length + r.missing_base_facts.length} input(s)`,
        why: r.missing_base_facts.length ? `Reviewed base facts missing: ${r.missing_base_facts.slice(0, 4).join(", ")}.` : "Enter the parameters the regulations leave to you.",
      };
    return { what: "Formulate", why: "Every input is in place: project the years of this filing." };
  })();
  return (
    <>
      <p>
        <Link href="/client">← Petition studio</Link>
      </p>
      <header className="case-head">
        <Eyebrow>
          {c.filing_kind === "myt" ? "MYT control period" : "Annual ARR"} · {c.commission} · {c.organisation}
        </Eyebrow>
        <h1>{c.title}</h1>
        <div className="case-meta">
          <span>
            Licensee <b>{c.utility_name}</b> ({c.utility})
          </span>
          <span>
            Base <b>{c.base_fy}</b> → <b>{years.join(", ")}</b>
          </span>
          <span>
            Plan <b>{r.plan.id} v{r.plan.version}</b> ({r.plan.status.split(";")[0]})
          </span>
          {role ? (
            <span>
              Your role <b>{role}</b>
            </span>
          ) : null}
        </div>
      </header>
      {r.plan.status !== "confirmed" ? (
        <div className="banner" data-tone="neutral">
          The formulation plan for {c.commission} is <strong>{r.plan.status.split(";")[0]}</strong>: its formulas are not yet confirmed against the commission&apos;s regulations. Treat every result as a working
          estimate.
        </div>
      ) : null}
      <Stepper steps={ARR_STEPS} current={c.status} />
      {canEdit ? <NextAction what={next.what} why={next.why} /> : null}

      <Panel num="01" title="Data readiness" aside={r.ready_to_formulate ? "ready to formulate" : "inputs missing"}>
      <p className="muted" style={{ marginTop: 0 }}>
        {r.note}
      </p>
      <div className="cards">
        <div className="card">
          <h3>Base facts ({c.base_fy})</h3>
          {r.missing_base_facts.length ? (
            <p>
              <span className="badge" data-tone="bad">
                {r.missing_base_facts.length} missing
              </span>{" "}
              {r.missing_base_facts.join(", ")}
            </p>
          ) : (
            <p>
              <span className="badge" data-tone="ok">
                all present
              </span>
            </p>
          )}
          <table className="cov-table">
            <tbody>
              {r.base_facts.map((b) => (
                <tr key={b.line_code}>
                  <td className="mono">{b.line_code}</td>
                  <td className="mono">{b.present ? b.value : "—"}</td>
                  <td className="muted">{b.value_type ?? "not reviewed"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>Parameters</h3>
          {r.missing_parameters.length ? (
            <p>
              <span className="badge" data-tone="warn">
                {r.missing_parameters.length} to supply
              </span>
            </p>
          ) : (
            <p>
              <span className="badge" data-tone="ok">
                all supplied
              </span>
            </p>
          )}
          <table className="cov-table">
            <tbody>
              {r.parameters.map((p) => (
                <tr key={`${p.key}-${p.for_line}`}>
                  <td className="mono">{p.key}</td>
                  <td>{p.supplied ? <span className="badge" data-tone="ok">ok</span> : <span className="badge" data-tone="warn">missing {p.missing_years.join(", ")}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3>Documents for {c.base_fy}</h3>
          {r.documents.length === 0 ? <p className="muted">None in the library for this year.</p> : null}
          <ul>
            {r.documents.map((d, i) => (
              <li key={i}>
                {d.kind} {d.fiscal_year || "(current period)"}: {d.status}
                {d.arr_state ? `, ARR ${d.arr_state}` : ""}
              </li>
            ))}
          </ul>
          <Link href={`/client/licensees/${encodeURIComponent(c.utility)}`}>All documents →</Link>
        </div>
      </div>
      </Panel>

      <Panel num="02" title="Assumptions" aside={<span className="badge" data-tone="neutral">assumption</span>}>
      {aset.data ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Key</th>
                <th>Year</th>
                <th>Value</th>
                <th>Source</th>
                <th>Rationale</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {aset.data.assumptions.map((a) => {
                const cl = a.clause_ref as { citation?: string; page_index?: number } | null;
                return (
                  <tr key={a.id}>
                    <td className="mono">{a.key}</td>
                    <td className="mono">{a.fiscal_year || "every year"}</td>
                    <td className="mono">
                      {a.value} <span className="muted">{a.unit}</span>
                    </td>
                    <td>{a.source_kind === "regulation_clause" && cl ? `${cl.citation ?? "clause"}, p.${cl.page_index}` : a.entered_by}</td>
                    <td className="muted">{a.rationale}</td>
                    <td>{canEdit && !frozen ? <ActionButton path={`cases/${c.id}/assumptions/${a.id}`} method="DELETE" label="Remove" tone="plain" /> : null}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {canEdit && !frozen ? <AssumptionForm caseId={c.id} keys={r.missing_parameters.length ? r.missing_parameters : r.parameters.map((p) => p.key)} years={years} /> : null}
      </Panel>

      <Panel num="03" title="Formulation" aside={<span className="badge" data-tone="warn">projection</span>}>
      {canEdit && !frozen ? (
        <p>
          <ActionButton path={`cases/${c.id}/formulate`} label={f ? "Formulate again" : "Formulate"} />
          {!r.ready_to_formulate ? <span className="muted">Missing inputs will show as blocked lines with the reason.</span> : null}
        </p>
      ) : null}
      {f ? (
        <>
          <p className="muted">
            {f.name} · input hash <code>{f.input_hash.slice(0, 12)}</code> · <Link href={`/arr/${encodeURIComponent(c.utility)}/formulations/${f.id}`}>every line with its working →</Link>
          </p>
          {summary.blocked ? (
            <div className="banner" data-tone="warn">
              {summary.blocked} line(s) blocked: {(summary.blocked_lines ?? []).slice(0, 4).join("; ")}
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
                  <th>Line</th>
                  {years.map((y) => (
                    <th key={y}>{y}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {keyLines.map((code) => (
                  <tr key={code}>
                    <td className="mono">{code}</td>
                    {years.map((y) => {
                      const ln = (f.lines ?? []).find((l) => l.line_code === code && l.fiscal_year === y);
                      return (
                        <td key={y} className="mono">
                          {!ln ? "—" : ln.status === "blocked" ? <span className="badge" data-tone="bad" title={ln.blocked_reason ?? ""}>blocked</span> : `${ln.value} ${ln.unit ?? ""}`}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {canEdit && c.status === "formulated" && !summary.blocked ? (
            <ActionButton path={`cases/${c.id}/freeze`} label="Freeze this formulation" confirm="Freezing locks the assumptions of this case version. Continue?" />
          ) : null}
        </>
      ) : (
        <p className="muted">Not formulated yet.</p>
      )}
      </Panel>

      <Panel num="04" title="Draft petition" aside={<span className="watermark">Draft · not filed</span>}>
      {c.draft_id ? (
        <p>
          <span className="badge" data-tone="warn">
            draft · not filed
          </span>{" "}
          <Link href={`/arr/${encodeURIComponent(c.utility)}/drafts/${c.draft_id}`}>Open the draft and its trace →</Link> · <a href={`/api/arr/drafts/${c.draft_id}/petition.docx`}>DOCX</a> ·{" "}
          <a href={`/api/arr/drafts/${c.draft_id}/formats.xlsx`}>XLSX</a>
        </p>
      ) : (
        <p className="muted">Freeze the formulation, then draft the petition.</p>
      )}
      {canEdit && (c.status === "frozen" || c.status === "drafted") ? (
        <p>
          <ActionButton path={`cases/${c.id}/draft`} label={c.draft_id ? "Draft again" : "Draft the petition"} />
          <ActionButton path={`cases/${c.id}/revise`} label="Revise (new assumptions version)" tone="plain" confirm="The frozen version and its drafts stay on record. Continue?" />
        </p>
      ) : null}
      </Panel>
      <Panel num="05" title="Activity">
        <CaseActivity caseId={c.id} />
      </Panel>
    </>
  );
}
