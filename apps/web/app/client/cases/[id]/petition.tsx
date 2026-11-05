import type { PetitionLayoutOut, PetitionWorkbookOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { ActionButton } from "../../actions";
import { AutoRefresh } from "../../../sources/[id]/auto-refresh";
import PetitionUpload from "./petition-upload";

type InputsSummary = {
  inputs?: {
    input_cells: number;
    inputs_blank: number;
    inputs_changed: number;
    inputs_as_filed: number;
    blank_examples: string[];
    fill_cells_entered: number;
  };
  formulas_without_values?: number;
};
type SheetCounts = { computed?: number; carried?: number; agrees?: number; differs?: number; blocked?: number };
type FillSummary = {
  passes: number;
  computed: number;
  carried: number;
  agrees: number;
  differs: number;
  blocked: number;
  conflicts: number;
  not_printed?: number;
  by_sheet: Record<string, SheetCounts>;
  status: string;
};
type Report = {
  checked: { cell: string; present: string; computed: string; binding: string; output: string; result: string }[];
  blocked: { cell: string; binding: string; output: string; fiscal_year: string | null; why: string | null }[];
  conflicts: { cell: string; kept: string; kept_from: string; other: string; other_from: string }[];
};

const fmt = (n: number | undefined) => (n ?? 0).toLocaleString("en-IN");
const num = (s: string) => {
  const v = Number(s);
  return Number.isFinite(v) ? v.toLocaleString("en-IN", { maximumFractionDigits: 4 }) : s;
};

/**
 * The case's formats workbook (increment 151): the rule engine fills the commission's formats
 * from the petitioner's inputs.  Step by step: the layout it follows, the inputs template, the
 * upload with its comparison against the filed inputs, the fill (a job), and the filled
 * workbook format by format — figures written, entered figures checked, differences and cells
 * left blank with the engine's reason.  Every rule is a draft: the filled workbook is a
 * working draft, never a filing.
 */
export default async function PetitionWorkbook({ caseId, canEdit }: { caseId: string; canEdit: boolean }) {
  const base = `/cases/${encodeURIComponent(caseId)}/petition`;
  const [lay, list] = await Promise.all([apiTry<PetitionLayoutOut>(`${base}/layout`), apiTry<PetitionWorkbookOut[]>(`${base}/workbooks`)]);
  if (lay.error || !lay.data) return <ErrorBanner error={lay.error!} />;
  const l = lay.data;
  if (!l.available) return <p className="muted">{l.why}</p>;
  const books = list.data ?? [];
  const inputs = books.filter((w) => w.role === "inputs").reverse();
  const filled = books.filter((w) => w.role === "filled").reverse();
  const pending = filled.some((w) => w.status === "queued" || w.status === "running");
  const latest = filled.find((w) => w.status === "filled");
  const rep = latest ? await apiTry<Report>(`${base}/workbooks/${latest.id}/report`) : undefined;
  const dl = (id: string) => `/api/client/cases/${encodeURIComponent(caseId)}/petition/workbooks/${id}/download`;
  const nameOf = (id: string | null | undefined) => inputs.find((w) => w.id === id)?.filename ?? "an inputs workbook";
  return (
    <>
      <div className="banner" data-tone="neutral">
        Every rule is a draft: none approved, no clause verified. A filled workbook is a <strong>working draft</strong> for the petitioner and the reviewer to check cell by cell. It is not a filing.
      </div>
      {(l.warnings ?? []).map((w, i) => (
        <div key={i} className="banner" data-tone="warn">
          {w}
        </div>
      ))}
      <div className="cards">
        <div className="card">
          <h3>Layout</h3>
          <p>{l.title}</p>
          <p className="muted mono">{l.workbook}</p>
          <p>
            {Object.entries(l.years ?? {})
              .filter(([k]) => k !== "note")
              .map(([k, v]) => (
                <span key={k} className="badge" data-tone="neutral" style={{ marginRight: 6 }}>
                  {k.replace("_", "-")} {v}
                </span>
              ))}
          </p>
        </div>
        <div className="card">
          <h3>What a fill writes</h3>
          <p>
            <b>{fmt(l.cells_filled)}</b> cells in {l.sheets} formats: {fmt(l.cells_computed)} computed by the rules, {fmt(l.cells_carried)} carried from the format they repeat.
          </p>
          <p className="muted">
            {l.bindings} bindings fill; {l.bindings_left_out} verification-only bindings (order approvals, annexures, the ledger) are left out.
          </p>
        </div>
        <div className="card">
          <h3>1 · Inputs template</h3>
          <p className="muted">The filed workbook with every cell a fill writes blanked. Replace the other figures with the petition&apos;s inputs.</p>
          <a className="btn primary" href={`/api/client${base}/template`}>
            Download the template
          </a>
        </div>
      </div>

      <h3>2 · Inputs workbooks</h3>
      {canEdit ? <PetitionUpload caseId={caseId} /> : null}
      {inputs.length === 0 ? (
        <p className="muted">None uploaded yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Workbook</th>
                <th>Uploaded</th>
                <th>Input cells</th>
                <th>Fill cells already entered</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {inputs.map((w) => {
                const s = (w.summary ?? {}) as InputsSummary;
                const i = s.inputs;
                return (
                  <tr key={w.id}>
                    <td>
                      <a href={dl(w.id)}>{w.filename}</a>
                      <div className="muted mono">{w.sha256?.slice(0, 12)}</div>
                    </td>
                    <td className="muted">
                      {w.created_by}
                      <br />
                      {new Date(w.created_at).toLocaleString("en-IN")}
                    </td>
                    <td>
                      {i ? (
                        <>
                          <span className="badge" data-tone={i.inputs_changed ? "ok" : "warn"}>
                            {fmt(i.inputs_changed)} changed
                          </span>{" "}
                          <span className="badge" data-tone="neutral">
                            {fmt(i.inputs_as_filed)} as filed
                          </span>{" "}
                          {i.inputs_blank ? (
                            <span className="badge" data-tone="warn" title={i.blank_examples.join(", ")}>
                              {fmt(i.inputs_blank)} blank
                            </span>
                          ) : null}
                          {!i.inputs_changed ? <div className="muted">Every input is still the filing&apos;s own: a fill will reproduce the filed petition.</div> : null}
                        </>
                      ) : null}
                      {s.formulas_without_values ? (
                        <div className="badge" data-tone="warn">
                          {fmt(s.formulas_without_values)} formulas saved without a value (read as blank) — open and save the workbook in a spreadsheet program
                        </div>
                      ) : null}
                    </td>
                    <td>{i ? (i.fill_cells_entered ? `${fmt(i.fill_cells_entered)} — kept and checked, never overwritten` : "none") : null}</td>
                    <td>{canEdit ? <ActionButton path={`cases/${caseId}/petition/workbooks/${w.id}/fill`} label="Fill" /> : null}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <h3>3 · Filled workbooks</h3>
      {pending ? <AutoRefresh seconds={10} /> : null}
      {filled.length === 0 ? <p className="muted">Nothing filled yet. A fill runs as a job and takes about a minute and a half.</p> : null}
      {filled.map((w) => {
        const s = w.summary as unknown as FillSummary | null;
        return (
          <div key={w.id} className="card" style={{ marginBottom: 12 }}>
            <p>
              <span className="badge" data-tone={w.status === "filled" ? "ok" : w.status === "failed" ? "bad" : "warn"}>
                {w.status}
              </span>{" "}
              <b>{w.filename}</b> <span className="muted">from {nameOf(w.inputs_id)} · {new Date(w.created_at).toLocaleString("en-IN")}</span>{" "}
              <span className="watermark">Working draft · not filed</span>
            </p>
            {w.status === "failed" ? <div className="banner" data-tone="bad">{w.error}</div> : null}
            {s ? (
              <>
                <p>
                  <span className="badge" data-tone="ok">
                    {fmt(s.computed)} computed
                  </span>{" "}
                  <span className="badge" data-tone="ok">
                    {fmt(s.carried)} carried
                  </span>{" "}
                  <span className="badge" data-tone="neutral">
                    {fmt(s.agrees)} entered figures agree
                  </span>{" "}
                  <span className="badge" data-tone={s.differs ? "warn" : "neutral"}>
                    {fmt(s.differs)} differ
                  </span>{" "}
                  <span className="badge" data-tone={s.blocked ? "bad" : "neutral"}>
                    {fmt(s.blocked)} left blank
                  </span>{" "}
                  <span className="badge" data-tone={s.conflicts ? "bad" : "neutral"}>
                    {fmt(s.conflicts)} conflicts
                  </span>{" "}
                  <span className="muted">
                    {s.passes} passes{s.not_printed ? ` · ${fmt(s.not_printed)} outputs the formats do not print` : ""}
                  </span>
                </p>
                <p>
                  <a className="btn primary" href={dl(w.id)}>
                    Download the filled workbook
                  </a>{" "}
                  <a href={`/api/client${base}/workbooks/${w.id}/report`}>Full report (JSON)</a>
                  <span className="muted"> · green cells computed, blue carried; the &ldquo;Fill trace&rdquo; sheet gives each figure&apos;s binding and pass.</span>
                </p>
                <details>
                  <summary>Format by format ({Object.keys(s.by_sheet).length})</summary>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Format</th>
                          <th>Computed</th>
                          <th>Carried</th>
                          <th>Agree</th>
                          <th>Differ</th>
                          <th>Left blank</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(s.by_sheet).map(([sheet, c]) => (
                          <tr key={sheet}>
                            <td className="mono">{sheet}</td>
                            <td className="mono">{c.computed ?? ""}</td>
                            <td className="mono">{c.carried ?? ""}</td>
                            <td className="mono">{c.agrees ?? ""}</td>
                            <td className="mono">{c.differs ? <span className="badge" data-tone="warn">{c.differs}</span> : ""}</td>
                            <td className="mono">{c.blocked ? <span className="badge" data-tone="bad">{c.blocked}</span> : ""}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
                {latest?.id === w.id && rep?.data ? <Findings report={rep.data} /> : null}
              </>
            ) : null}
          </div>
        );
      })}
    </>
  );
}

function Findings({ report }: { report: Report }) {
  const differs = report.checked.filter((c) => c.result === "differs");
  return (
    <>
      {report.conflicts.length ? (
        <details open>
          <summary>Conflicts — two bindings compute one cell differently ({report.conflicts.length})</summary>
          <ul>
            {report.conflicts.map((c) => (
              <li key={c.cell + c.other_from}>
                <span className="mono">{c.cell}</span>: {num(c.kept)} ({c.kept_from}) kept, against {num(c.other)} ({c.other_from})
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {differs.length ? (
        <details>
          <summary>Entered figures that differ from the computation ({differs.length})</summary>
          <p className="muted">An entered figure is never overwritten. Each difference is the petitioner&apos;s to explain or correct, and the reviewer&apos;s to check.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cell</th>
                  <th>Entered</th>
                  <th>Computed</th>
                  <th>Binding · output</th>
                </tr>
              </thead>
              <tbody>
                {differs.slice(0, 200).map((c) => (
                  <tr key={c.cell + c.binding + c.output}>
                    <td className="mono">{c.cell}</td>
                    <td className="mono">{num(c.present)}</td>
                    <td className="mono">{num(c.computed)}</td>
                    <td className="muted">
                      {c.binding} · {c.output}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {differs.length > 200 ? <p className="muted">The first 200; the report lists every one.</p> : null}
        </details>
      ) : null}
      {report.blocked.length ? (
        <details>
          <summary>Cells left blank, with the engine&apos;s reason ({report.blocked.length})</summary>
          <ul>
            {report.blocked.slice(0, 200).map((b) => (
              <li key={b.cell + b.binding + b.output}>
                <span className="mono">{b.cell}</span> {b.fiscal_year ?? ""}: {b.why ?? "inputs missing"} <span className="muted">({b.binding})</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </>
  );
}
