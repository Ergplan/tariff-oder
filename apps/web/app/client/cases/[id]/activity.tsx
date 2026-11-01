import { apiTry } from "@/lib/api";

type Event = { at: string; actor: string; action: string; after: Record<string, unknown> | null; before: Record<string, unknown> | null; reason: string | null };

const WORDS: Record<string, string> = {
  "arr_case.created": "created the case",
  "arr_case.assumption_removed": "removed an assumption",
  "arr.assumption_added": "added an assumption",
  "arr_case.actual_added": "entered an actual",
  "arr_case.actual_removed": "removed an actual",
  "arr_case.statement_computed": "computed the statement",
  "arr_case.formulated": "formulated",
  "arr_case.frozen": "froze",
  "arr_case.drafted": "drafted the petition",
  "arr_case.revised": "revised (unfroze)",
};

function detail(e: Event): string {
  const a = e.after ?? {};
  const b = e.before ?? {};
  if (a.key) return `${a.key} ${a.fiscal_year || "every year"} = ${a.value}`;
  if (a.line_code) return `${a.line_code} ${a.stated_value ?? ""} ${a.stated_unit ?? ""} (${a.source_kind})`;
  if (b.key) return `${b.key} ${b.fiscal_year || "every year"} = ${b.value}`;
  if (b.line_code) return `${b.line_code} ${b.stated_value ?? ""}`;
  if (a.input_hash) return `input hash ${String(a.input_hash).slice(0, 12)}`;
  if (a.draft_id) return "a new draft";
  return "";
}

/** Who did what in the case, newest first (from the audit trail; private to the organisation). */
export default async function CaseActivity({ caseId }: { caseId: string }) {
  const res = await apiTry<Event[]>(`/cases/${caseId}/activity`);
  const events = res.data ?? [];
  if (!events.length) return null;
  return (
    <details className="card">
      <summary>
        Activity <span className="muted">({events.length} events)</span>
      </summary>
      <ol className="activity">
        {events.map((e, i) => (
          <li key={i}>
            <span className="muted mono">{new Date(e.at).toLocaleString()}</span> {e.actor} {WORDS[e.action] ?? e.action} <span className="muted">{detail(e)}</span>
            {e.reason ? <span className="muted"> — {e.reason}</span> : null}
          </li>
        ))}
      </ol>
    </details>
  );
}
