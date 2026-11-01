import Link from "next/link";
import type { ArrActualOut, ArrCaseOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ActionButton } from "../../actions";
import ActualForm from "./actual-form";
import CaseActivity from "./activity";
import { Eyebrow, NextAction, Panel, Stepper, TRUE_UP_STEPS } from "../../studio";

type Ref = Record<string, string | number | boolean | null | Record<string, unknown>>;
type Row = {
  line_code: string;
  label: string;
  approved: Ref | null;
  actual: (Ref & { origin: Record<string, unknown> }) | null;
  variance: string | null;
  unit: string | null;
  status: string;
};
type Statement = {
  fiscal_year: string;
  rows: Row[];
  findings: { identity_id: string; severity: string; message: string; lines: string[] }[];
  summary: { ready: boolean; not_ready_because: string[]; unchecked_statements: number; estimates: number; complete: number; lines: number };
  input_hash: string;
  note: string;
  computed_at?: string;
  frozen_at?: string;
  frozen_by?: string;
};
type Readiness = {
  statement: Statement;
  documents: { kind: string; fiscal_year: string; status: string; arr_state: string | null; source_id: string | null }[];
  missing_actuals: string[];
  note: string;
};

const SOURCE: Record<string, { label: string; tone: string }> = {
  fact: { label: "reviewed fact", tone: "ok" },
  document: { label: "document, checked", tone: "ok" },
  statement: { label: "statement, unchecked", tone: "warn" },
  estimate: { label: "estimate", tone: "warn" },
};

const STATUS: Record<string, { label: string; tone: string }> = {
  complete: { label: "complete", tone: "ok" },
  actual_missing: { label: "actual missing", tone: "bad" },
  approved_missing: { label: "no approval", tone: "neutral" },
  unit_mismatch: { label: "unit mismatch", tone: "bad" },
  actual_unconverted: { label: "unit not convertible", tone: "bad" },
};

/**
 * A true-up or APR case (ADR-0020): the Commission's reviewed approval of the year against
 * the licensee's actuals, each with its source, the variance line by line, the identity
 * checks over the actuals, then freeze and draft.  The variance is never an allowed amount.
 */
export default async function TrueUpCase({ c, role }: { c: ArrCaseOut; role: string | undefined }) {
  const r = c.readiness as unknown as Readiness;
  const actuals = await apiTry<ArrActualOut[]>(`/cases/${c.id}/actuals`);
  const byLine = new Map((actuals.data ?? []).map((a) => [a.line_code, a]));
  const canEdit = role === "editor" || role === "owner";
  const frozen = ["frozen", "drafted", "closed"].includes(c.status);
  const computed = (c.statement as unknown as Statement | null) ?? null;
  const st = computed ?? r.statement;
  const fy = r.statement.fiscal_year;
  const word = c.filing_kind === "apr" ? "Annual performance review" : "True-up";
  const missing = st.rows.filter((x) => !x.actual).length;
  const next =
    c.status === "drafted"
      ? { what: "Edit and file the draft", why: "A person edits, signs and files the petition." }
      : c.status === "frozen"
        ? { what: "Draft the petition", why: "The statement is frozen: draft from it." }
        : computed && st.summary.ready
          ? { what: "Freeze the statement", why: "Every line has its actual and the identities hold." }
          : missing
            ? { what: `Enter ${missing} actual(s)`, why: "Each actual with its source: a reviewed fact, a document, a statement or an estimate." }
            : { what: "Compute the statement", why: "Set the actuals against the Commission's approval, line by line." };
  return (
    <>
      <p>
        <Link href="/client">← Petition studio</Link>
      </p>
      <header className="case-head">
        <Eyebrow>
          {word} · {c.commission} · {c.organisation}
        </Eyebrow>
        <h1>{c.title}</h1>
        <div className="case-meta">
          <span>
            Licensee <b>{c.utility_name}</b> ({c.utility})
          </span>
          <span>
            Year <b>{fy}</b>
          </span>
          {role ? (
            <span>
              Your role <b>{role}</b>
            </span>
          ) : null}
        </div>
      </header>
      <Stepper steps={TRUE_UP_STEPS} current={c.status} />
      {canEdit ? <NextAction what={next.what} why={next.why} /> : null}
      <p className="muted">{r.note}</p>
      {r.documents.length ? (
        <p className="muted">
          Library for {fy}:{" "}
          {r.documents.map((d, i) => (
            <span key={i}>
              {d.kind} ({d.status}
              {d.arr_state ? `, ARR ${d.arr_state}` : ""}){i < r.documents.length - 1 ? " · " : ""}
            </span>
          ))}{" "}
          <Link href={`/client/licensees/${encodeURIComponent(c.utility)}`}>all documents →</Link>
        </p>
      ) : (
        <div className="banner" data-tone="neutral">
          No document of {fy} in the library for this licensee. <Link href={`/client/licensees/${encodeURIComponent(c.utility)}`}>Add or locate it →</Link>
        </div>
      )}

      <Panel
        num="01"
        title="Approved and actual"
        aside={
          <>
            <span className="badge" data-tone="ok">
              fact
            </span>{" "}
            <span className="badge" data-tone="neutral">
              actual
            </span>
          </>
        }
      >
      <p className="muted">{st.note}</p>
      {computed ? (
        <p className="muted">
          Statement {computed.frozen_at ? `frozen by ${computed.frozen_by} on ${new Date(computed.frozen_at).toLocaleString()}` : `computed ${computed.computed_at ? new Date(computed.computed_at).toLocaleString() : ""}`} · input hash{" "}
          <code>{computed.input_hash.slice(0, 12)}</code>
        </p>
      ) : (
        <p className="muted">Live view: today&apos;s reviewed approvals against the actuals entered so far.</p>
      )}
      {st.findings.map((f, i) => (
        <div key={i} className="banner" data-tone={f.severity === "blocking" ? "bad" : "warn"}>
          {f.identity_id}: {f.message}
        </div>
      ))}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Line</th>
              <th>Approved</th>
              <th>Actual</th>
              <th>Variance</th>
              <th>Source of the actual</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {st.rows.map((row) => {
              const a = byLine.get(row.line_code);
              const s = row.actual ? SOURCE[String(row.actual.source_kind)] : null;
              const tone = STATUS[row.status] ?? { label: row.status, tone: "neutral" };
              return (
                <tr key={row.line_code}>
                  <td>
                    <span className="mono">{row.line_code}</span> <span className="muted">{row.label}</span>
                  </td>
                  <td className="mono" title={row.approved ? `${row.approved.order}, p.${row.approved.page}` : ""}>
                    {row.approved ? `${row.approved.value} ${row.approved.unit ?? ""}` : "—"}
                  </td>
                  <td className="mono">
                    {row.actual ? (
                      <>
                        {String(row.actual.value ?? "?")} {String(row.actual.unit ?? "")}
                        {row.actual.stated_unit !== row.actual.unit ? (
                          <div className="muted">
                            stated {String(row.actual.stated_value)} {String(row.actual.stated_unit)}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="mono">{row.variance ?? <span className="badge" data-tone={tone.tone}>{tone.label}</span>}</td>
                  <td>
                    {s ? (
                      <span className="badge" data-tone={s.tone}>
                        {s.label}
                      </span>
                    ) : null}{" "}
                    {a ? (
                      <span className="muted">
                        {a.document_name}
                        {a.page_index ? `, p.${a.page_index}` : ""}
                        {a.rationale ? ` — ${a.rationale}` : ""}
                      </span>
                    ) : null}
                  </td>
                  <td>{canEdit && !frozen && a ? <ActionButton path={`cases/${c.id}/actuals/${a.id}`} method="DELETE" label="Remove" tone="plain" /> : null}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!st.summary.ready ? (
        <div className="banner" data-tone="warn">
          Not ready to freeze: {st.summary.not_ready_because.join("; ")}.
        </div>
      ) : null}
      {st.summary.unchecked_statements || st.summary.estimates ? (
        <p className="muted">
          {st.summary.unchecked_statements} actual(s) rest on a statement the application could not check
          {st.summary.estimates ? ` and ${st.summary.estimates} on an estimate` : ""}; the draft names them.
        </p>
      ) : null}

      </Panel>
      {canEdit && !frozen ? (
        <Panel num="02" title="Enter an actual">
          <ActualForm
            caseId={c.id}
            kind={c.filing_kind}
            lines={st.rows.filter((x) => !x.actual).map((x) => ({ code: x.line_code, label: x.label, unit: x.approved ? String(x.approved.unit ?? "") : "" }))}
            documents={r.documents.filter((d) => d.source_id).map((d) => ({ id: String(d.source_id), label: `${d.kind} ${d.fiscal_year}` }))}
          />
          <p>
            <ActionButton path={`cases/${c.id}/statement`} label={computed ? "Compute the statement again" : "Compute the statement"} />
            {computed && c.status === "formulated" && st.summary.ready ? (
              <ActionButton path={`cases/${c.id}/statement/freeze`} label="Freeze the statement" confirm="Freezing locks the actuals of this case. Continue?" />
            ) : null}
          </p>
        </Panel>
      ) : null}

      <Panel num="03" title="Draft petition" aside={<span className="watermark">Draft · not filed</span>}>
      {c.draft_id ? (
        <p>
          <span className="badge" data-tone="warn">
            draft · not filed
          </span>{" "}
          <Link href={`/arr/${encodeURIComponent(c.utility)}/drafts/${c.draft_id}`}>Open the draft and its trace →</Link> · <a href={`/api/arr/drafts/${c.draft_id}/petition.docx`}>DOCX</a> ·{" "}
          <a href={`/api/arr/drafts/${c.draft_id}/formats.xlsx`}>XLSX</a>
        </p>
      ) : (
        <p className="muted">Freeze the statement, then draft the petition.</p>
      )}
      {canEdit && (c.status === "frozen" || c.status === "drafted") ? (
        <p>
          <ActionButton path={`cases/${c.id}/draft`} label={c.draft_id ? "Draft again" : "Draft the petition"} />
          <ActionButton path={`cases/${c.id}/revise`} label="Revise (unfreeze the actuals)" tone="plain" confirm="The frozen statement and its drafts stay on record. Continue?" />
        </p>
      ) : null}
      </Panel>
      <Panel num="04" title="Activity">
        <CaseActivity caseId={c.id} />
      </Panel>
    </>
  );
}
