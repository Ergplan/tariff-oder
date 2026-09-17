"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { CandidateOut, CategorySummaryOut, DecisionResult, ErrorResponse, ReviewQueueDetail, TableRows } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

type Outcome = "approve" | "correct" | "reject" | "unresolved";
const CAUSE_TAGS = ["wrong_table", "header_misbound", "unit", "ocr", "footnote_missed", "cross_reference", "other"] as const;
const VALUE_STATES = ["value", "zero", "absent_in_source", "unknown", "unchanged_reference", "not_applicable", "formula", "cross_reference", "not_yet_verified"] as const;

type EvidenceRef = {
  page_index: number;
  kind: string;
  grid_ordinal?: number | null;
  row?: number | null;
  col?: number | null;
  line_no?: number | null;
  header_path?: string[];
  row_path?: string[];
  clause_path?: string[];
  excerpt: string;
};
type Formula = {
  formula?: string;
  level?: string;
  inputs?: Record<string, { value?: string; unit?: string; label?: string; evidence?: { page_index?: number } }>;
  computed?: string | null;
  printed_computed?: string | null;
  cap_20pct_of_T?: string;
  printed_cap?: string | null;
  d_components?: Record<string, string> | null;
  assumed?: string[];
  missing?: string[];
  formula_as_printed?: { text: string; page_index: number } | null;
  definitions?: Record<string, { text: string }>;
};
type Rec = {
  value?: string | null;
  value_state?: string;
  original_text?: string;
  currency?: string | null;
  per_unit?: string | null;
  frequency?: string | null;
  decision_status?: string | null;
  reference_target?: string | null;
  conditions?: string[];
  evidence?: EvidenceRef[];
  applicability?: Record<string, unknown>;
  rationale?: string | null;
  context?: string[];
  assessment?: {
    verdict?: string;
    confidence?: number;
    sub_category?: string | null;
    meaning?: string;
    quote?: string;
    grounded?: boolean;
    issue?: string | null;
    model?: string;
    is_fixture?: boolean;
    status?: string;
    sub_categories_seen?: string[];
  } | null;
  derivation?: { rule?: string; inputs?: Record<string, unknown>; formula?: Formula } | null;
  [k: string]: unknown;
};
export type FindingLine = { severity: string; validator_id: string; message: string };

const FAMILY_LABEL: Record<string, string> = {
  retail_tariff: "Retail tariff",
  wheeling_charge: "Wheeling charge",
  oa_loss: "Open-access losses",
  distribution_loss_approved: "Approved distribution loss",
  cross_subsidy_surcharge: "Cross-subsidy surcharge",
  additional_surcharge: "Additional surcharge",
  banking_rule: "Banking",
  green_tariff: "Green tariff",
  transmission_reference: "Transmission reference",
};
const COMPONENT_LABEL: Record<string, string> = {
  energy: "Energy charge",
  fixed: "Fixed charge",
  demand: "Demand charge",
  minimum: "Minimum charge",
  tod_adjustment: "Time-of-day adjustment",
  rebate: "Rebate",
  surcharge: "Surcharge",
  subsidy: "Subsidy",
  green_premium: "Green premium",
  charge: "Charge",
  loss: "Loss",
  condition: "Condition",
  cross_reference: "Cross-reference",
};
const UNIT_WORD: Record<string, string> = { kWh: "per kWh", kVAh: "per kVAh", kW: "per kW", kVA: "per kVA", HP: "per HP", BHP: "per BHP", unit: "per unit", connection: "per connection", percent: "%" };
const FREQ_WORD: Record<string, string> = { per_month: "per month", per_annum: "per year", per_bill: "per bill" };

/** "Rs 6.50 per kWh per month", "Zero (nil)", "Not applicable", "By reference: …". */
function valueWords(rec: Rec): string {
  const st = rec.value_state;
  if (st === "zero") return "Zero (nil)";
  if (st === "not_applicable") return "Not applicable";
  if (st === "absent_in_source") return rec.reference_target ? `By reference: ${rec.reference_target}` : "Not stated in the order";
  if (st === "cross_reference" || st === "unchanged_reference") return `Refers to: ${rec.reference_target ?? rec.original_text ?? "another instrument"}`;
  if (st === "formula") return `Formula: ${rec.original_text ?? ""}`;
  if (rec.value == null) return st ?? "unknown";
  const unit = rec.per_unit ? UNIT_WORD[rec.per_unit] ?? `per ${rec.per_unit}` : "";
  if (rec.per_unit === "percent") return `${rec.value}%`;
  const cur = rec.currency === "paise" ? "paise" : rec.currency === "rupees" ? "Rs" : "";
  return [cur, rec.value, unit, rec.frequency ? FREQ_WORD[rec.frequency] ?? rec.frequency : ""].filter(Boolean).join(" ");
}

/** A sentence a person can read instead of header/row paths. */
function whereRead(ev: EvidenceRef | undefined): string {
  if (!ev) return "No evidence reference.";
  if (ev.kind === "cell") {
    const row = ev.row_path?.length ? `row “${ev.row_path.join(" › ")}”` : "an unlabelled row";
    const col = ev.header_path?.length ? `column “${ev.header_path.join(" › ")}”` : "an unlabelled column";
    return `Page ${ev.page_index}, table ${(ev.grid_ordinal ?? 0) + 1}, ${row}, ${col}.`;
  }
  if (ev.kind === "clause") return `Page ${ev.page_index}, clause ${ev.clause_path?.join(" › ") ?? ""}${ev.line_no != null ? `, line ${ev.line_no}` : ""}.`;
  return `Page ${ev.page_index}, paragraph${ev.line_no != null ? ` at line ${ev.line_no}` : ""}.`;
}

function title(c: CandidateOut, rec: Rec): string {
  const a = (rec.applicability ?? {}) as { voltage?: string | null; description?: string | null; time_band?: string | null; slab?: { original_text?: string | null } | null; load_band?: { original_text?: string | null } | null; rate_block?: string | null };
  const block = a.rate_block ? a.rate_block.replace(/\s+/g, " ").slice(0, 60) + (a.rate_block.length > 60 ? "…" : "") : null;
  const qual = [block, a.description, a.voltage, a.slab?.original_text ?? a.load_band?.original_text, a.time_band].filter(Boolean).join(" · ");
  if (c.family === "retail_tariff") return `${c.category_code ?? "Category ?"} · ${COMPONENT_LABEL[c.component_type] ?? c.component_type}${qual ? ` · ${qual}` : ""}`;
  return `${FAMILY_LABEL[c.family] ?? c.family}${c.category_code ? ` · ${c.category_code}` : ""}${qual ? ` · ${qual}` : ""}`;
}

function groupKey(c: CandidateOut): string {
  return c.family === "retail_tariff" ? `Retail tariff · ${c.category_code ?? "?"}` : FAMILY_LABEL[c.family] ?? c.family;
}

/**
 * Review workspace (Section 7.2), one candidate at a time in the order the document
 * prints them: what was read, in words; where it was read; the page text that gives the
 * cue; the arithmetic when there is one; what the validators said; the cited page with the
 * table outlined; then approve, change, reject or "cannot decide".  Approve and change stay
 * disabled until the evidence image has loaded (the server refuses anyway).  Keyboard: a c
 * r u outcome, Enter approve, n/p next and previous, z undo.  Nothing renders as decided
 * until the API says so.
 */
export function ReviewWorkspace({
  sourceId,
  queue,
  sourceState,
  findings,
  summaries,
}: {
  sourceId: string;
  queue: ReviewQueueDetail;
  sourceState: string;
  findings: Record<string, FindingLine[]>;
  summaries: Record<string, CategorySummaryOut>;
}) {
  const router = useRouter();
  const items = queue.items;
  const [index, setIndex] = useState(0);
  const [outcome, setOutcome] = useState<Outcome>("approve");
  const [rationale, setRationale] = useState("");
  const [cause, setCause] = useState<(typeof CAUSE_TAGS)[number]>("other");
  const [correction, setCorrection] = useState<Record<string, string>>({});
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [viewId, setViewId] = useState<string | null>(null);
  const [viewMeta, setViewMeta] = useState<{ highlighted: boolean; page: string }>({ highlighted: false, page: "" });
  const [imageError, setImageError] = useState<ErrorResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [decided, setDecided] = useState<Record<string, DecisionResult>>({});
  const [showChannels, setShowChannels] = useState(false);
  const [table, setTable] = useState<TableRows | null>(null);
  const [showTable, setShowTable] = useState(false);
  const viewedAt = useRef<number | null>(null);
  const attemptKey = useRef<string | null>(null);

  const item = items[index];
  const cand: CandidateOut | undefined = item?.candidate;
  const rec = useMemo(() => ((cand?.reviewed_record ?? cand?.record ?? {}) as Rec), [cand]);
  const image = (cand?.image_record ?? null) as Rec | null;
  const evidence = rec.evidence ?? [];
  const ev0 = evidence[0];
  const prior = cand ? decided[cand.id] : undefined;
  const open = sourceState === "awaiting_review" && !prior;
  const groups = useMemo(() => {
    const out: { key: string; first: number; count: number }[] = [];
    items.forEach((it, i) => {
      const k = groupKey(it.candidate);
      const last = out[out.length - 1];
      if (last && last.key === k) last.count += 1;
      else out.push({ key: k, first: i, count: 1 });
    });
    return out;
  }, [items]);
  const fm = rec.derivation?.formula;
  const lines = cand ? findings[cand.id] ?? [] : [];
  const summary = cand?.category_code ? summaries[cand.category_code] : undefined;
  const prevItem = index > 0 ? items[index - 1] : undefined;
  const newGroup = !prevItem || groupKey(prevItem.candidate) !== groupKey(cand!);

  useEffect(() => {
    setTable(null);
    setShowTable(false);
    if (!ev0 || ev0.kind !== "cell") return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/sources/${sourceId}/tables/${ev0.page_index}/${ev0.grid_ordinal ?? 0}`, { cache: "no-store" });
        if (res.ok && !cancelled) setTable((await res.json()) as TableRows);
      } catch {
        /* the panel simply stays unavailable */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cand?.id]);

  const loadEvidence = useCallback(async (candidateId: string) => {
    setImageUrl(null);
    setViewId(null);
    setImageError(null);
    viewedAt.current = null;
    try {
      const res = await fetch(`/api/candidates/${candidateId}/evidence/0/image`, { cache: "no-store" });
      if (!res.ok) {
        setImageError(await readError(res));
        return;
      }
      const blob = await res.blob();
      setImageUrl(URL.createObjectURL(blob));
      setViewId(res.headers.get("x-evidence-view-id"));
      setViewMeta({ highlighted: res.headers.get("x-evidence-highlighted") === "1", page: res.headers.get("x-evidence-page") ?? "" });
      viewedAt.current = Date.now();
    } catch {
      setImageError(networkError("The evidence image"));
    }
  }, []);

  useEffect(() => {
    if (cand) {
      void loadEvidence(cand.id);
      setOutcome("approve");
      setRationale("");
      setCorrection({});
      setError(null);
      setShowChannels(false);
      attemptKey.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cand?.id]);

  async function submit(o: Outcome = outcome) {
    if (!cand || busy || !open) return;
    if (o !== "approve" && rationale.trim().length < 5) {
      setOutcome(o);
      setError({ error_type: "validation_failed", message: `${o === "correct" ? "A change" : o === "reject" ? "A rejection" : "Cannot decide"} needs a reason.`, next_step: "Say why in a sentence; it is recorded with the decision.", severity: "warning", request_id: null });
      return;
    }
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(correction)) {
      if (v === "") continue;
      patch[k] = k === "value" ? v : v === "null" ? null : v;
    }
    const body: Record<string, unknown> = {
      outcome: o,
      expected_version: cand.version,
      rationale: rationale || null,
      evidence_view_ids: viewId ? [viewId] : [],
      time_spent_ms: viewedAt.current ? Date.now() - viewedAt.current : null,
    };
    if (o === "correct") {
      body.correction = patch;
      body.cause_tag = cause;
      body.evidence_indices = [0];
    }
    if (!attemptKey.current) attemptKey.current = crypto.randomUUID();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/candidates/${cand.id}/decision`, {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": attemptKey.current },
        body: JSON.stringify(body),
      });
      if (!res.ok) setError(await readError(res));
      else {
        const r = (await res.json()) as DecisionResult;
        setDecided((d) => ({ ...d, [cand.id]: r }));
        attemptKey.current = null;
        router.refresh();
        if (o === "approve" && index < items.length - 1) setIndex(index + 1); // keep the flow moving
      }
    } catch {
      setError(networkError("The decision"));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    if (!cand || !prior || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/review/decisions/${prior.decision.id}/undo`, { method: "POST" });
      if (!res.ok) setError(await readError(res));
      else {
        setDecided((d) => {
          const copy = { ...d };
          delete copy[cand.id];
          return copy;
        });
        router.refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      if (e.key === "n") setIndex((i) => Math.min(items.length - 1, i + 1));
      else if (e.key === "p") setIndex((i) => Math.max(0, i - 1));
      else if (e.key === "a") setOutcome("approve");
      else if (e.key === "c") setOutcome("correct");
      else if (e.key === "r") setOutcome("reject");
      else if (e.key === "u") setOutcome("unresolved");
      else if (e.key === "z") void undo();
      else if (e.key === "Enter" && outcome === "approve") void submit("approve");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length, outcome, cand?.id, viewId, busy, prior, rationale, correction]);

  if (!cand) return null;
  const decidable = open && !busy;
  const needsImage = !viewId;
  const decidedCount = Object.keys(decided).length;

  return (
    <div className="rw">
      <aside className="rw-side" aria-label="Review order">
        <div className="label">In document order · {decidedCount} decided this session</div>
        <ol>
          {groups.map((g) => {
            const active = index >= g.first && index < g.first + g.count;
            return (
              <li key={g.key} data-active={active || undefined}>
                <button type="button" className="link" onClick={() => setIndex(g.first)}>
                  {g.key}
                </button>{" "}
                <span className="muted">{g.count}</span>
              </li>
            );
          })}
        </ol>
      </aside>

      <section className="rw-main" aria-label="Candidate under review">
        <p className="muted">
          {item.position} of {queue.total}
          {queue.total > items.length ? ` (first ${items.length} loaded)` : ""} · {item.reason}
          {item.coverage_impact ? " · this category has no approved fact yet" : ""}
          {cand.is_fixture ? " · FIXTURE" : ""}
        </p>
        {summary && newGroup ? (
          <div className="card rw-summary">
            <div className="label">
              Summary of {summary.category_code} · generated{summary.is_fixture ? " by the fixture template" : ` by ${summary.model}`} · not a fact ·{" "}
              {summary.grounded ? (
                <span className="badge" data-tone="ok">every number traced to the pages</span>
              ) : (
                <span className="badge" data-tone="bad">numbers not found in the pages: {summary.unsupported_numbers.join(", ")}</span>
              )}
            </div>
            <p>{summary.text}</p>
            <p className="muted">
              {summary.heading_text ? `${summary.heading_text} · ` : ""}pages {summary.page_indices.join(", ")} · {summary.candidate_count} candidates
            </p>
          </div>
        ) : null}
        <h2 className="rw-title">{title(cand, rec)}</h2>
        <div className="rw-value">{valueWords(rec)}</div>
        {rec.original_text && rec.original_text !== rec.value ? <div className="muted">As printed: “{rec.original_text}”</div> : null}
        {cand.channel_agreement === "disagree" ? (
          <div className="banner" data-tone="bad">
            The two reading channels disagree on {cand.disagreeing_fields.join(", ") || "this record"}.{" "}
            <button type="button" className="link" onClick={() => setShowChannels((v) => !v)}>
              {showChannels ? "hide" : "show"} both readings
            </button>
            {showChannels && image ? (
              <div className="mono muted" style={{ marginTop: "0.4rem" }}>
                structure: {valueWords(rec)} · image: {valueWords(image)}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="card rw-block">
          <div className="label">Where it was read</div>
          <p>{rec.rationale ?? whereRead(ev0)}</p>
          {rec.rationale ? <p className="muted">{whereRead(ev0)}</p> : null}
          {table ? (
            <details className="inline" open={showTable} onToggle={(e) => setShowTable((e.target as HTMLDetailsElement).open)}>
              <summary>
                Show the table as read ({table.reader}
                {table.agreement_class ? `, ${table.agreement_class.replace(/_/g, " ")} with ${table.secondary_reader ?? "the second reader"}` : ""})
              </summary>
              <div className="table-wrap">
                <table className="compact rw-grid">
                  <tbody>
                    {table.rows.map((r, ri) => (
                      <tr key={ri} data-header={ri < table.header_rows || undefined}>
                        {r.map((cell, ci) => (
                          <td key={ci} data-cited={ev0?.row === ri && ev0?.col === ci ? true : undefined}>
                            {cell || <span className="muted">·</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted">
                The highlighted cell is the one cited. If the column headings sit one cell off from the numbers, choose Change and say
                so: the cause tag “header misbound” tells us to fix the reader, not just this value.
              </p>
            </details>
          ) : null}
          {evidence.length > 1 ? (
            <p className="muted">
              Also cited: {evidence.slice(1).map((e, i) => (
                <span key={i}>
                  page {e.page_index}
                  {e.row != null ? ` r${e.row} c${e.col}` : ""}
                  {i < evidence.length - 2 ? ", " : ""}
                </span>
              ))}
            </p>
          ) : null}
        </div>

        {rec.assessment && rec.assessment.status !== "not_assessed" ? (
          <div className="card rw-block rw-assess" data-verdict={rec.assessment.verdict}>
            <div className="label">
              Model check · {rec.assessment.is_fixture ? "fixture template" : rec.assessment.model} ·{" "}
              <span className="badge" data-tone={rec.assessment.verdict === "supported" ? "ok" : rec.assessment.verdict === "contradicted" ? "bad" : "warn"}>
                {rec.assessment.verdict}
              </span>{" "}
              <span className="badge" data-tone={(rec.assessment.confidence ?? 0) >= 0.8 ? "ok" : (rec.assessment.confidence ?? 0) >= 0.6 ? "warn" : "bad"}>
                confidence {Math.round((rec.assessment.confidence ?? 0) * 100)}%
              </span>{" "}
              {rec.assessment.grounded ? (
                <span className="badge" data-tone="ok">quote found on the page</span>
              ) : (
                <span className="badge" data-tone="bad">quote not found on the page</span>
              )}
            </div>
            <p>{rec.assessment.meaning}</p>
            {rec.assessment.sub_category ? (
              <p className="muted">
                Consumer group: {rec.assessment.sub_category}
                {rec.assessment.quote ? <> · “{rec.assessment.quote}”</> : null}
              </p>
            ) : null}
            {rec.assessment.issue ? <p className="muted">Issue raised: {rec.assessment.issue}</p> : null}
            {rec.assessment.sub_categories_seen?.length ? (
              <p className="muted">Groups seen in this category: {rec.assessment.sub_categories_seen.join(" · ")}</p>
            ) : null}
          </div>
        ) : null}
        {rec.context?.length || rec.conditions?.length ? (
          <div className="card rw-block">
            <div className="label">What the order says around it</div>
            {rec.context?.map((c, i) => (
              <blockquote key={i}>{c}</blockquote>
            ))}
            {rec.conditions?.length ? (
              <>
                <div className="muted">Conditions attached to this value:</div>
                {rec.conditions.map((c, i) => (
                  <blockquote key={`c${i}`}>{c}</blockquote>
                ))}
              </>
            ) : null}
          </div>
        ) : null}

        {fm ? (
          <div className="card rw-block">
            <div className="label">How the surcharge is computed</div>
            <p className="mono">{fm.formula ?? "S = T - [C/(1 - L/100) + D + R]"}{fm.level ? ` at ${fm.level}` : ""}</p>
            <ul>
              {Object.entries(fm.inputs ?? {}).map(([k, v]) => (
                <li key={k}>
                  <strong>{k}</strong> = {v.value ?? "?"}
                  {v.unit === "paise" ? " paise" : v.unit === "percent" ? "%" : ""} <span className="muted">{v.label}{v.evidence?.page_index ? ` (page ${v.evidence.page_index})` : ""}</span>
                </li>
              ))}
            </ul>
            <p>
              {fm.computed != null ? (
                <>
                  The formula gives <strong>S = {fm.computed}</strong>
                  {fm.printed_computed != null ? `; the order prints ${fm.printed_computed}` : ""}.
                </>
              ) : (
                <>Not recomputed: {(fm.missing ?? []).join(", ") || "inputs missing"}.</>
              )}
              {fm.d_components ? ` D = ${Object.entries(fm.d_components).map(([k, v]) => `${k} ${v}`).join(" + ")}.` : ""}
              {fm.printed_cap ?? fm.cap_20pct_of_T ? ` Cap, 20% of T: ${fm.printed_cap ?? fm.cap_20pct_of_T}.` : ""}
              {fm.assumed?.length ? ` ${fm.assumed.join("; ")}.` : ""}
            </p>
            {fm.formula_as_printed ? <blockquote>{fm.formula_as_printed.text} (page {fm.formula_as_printed.page_index})</blockquote> : null}
          </div>
        ) : null}

        {lines.length ? (
          <div className="card rw-block">
            <div className="label">What the checks found</div>
            <ul className="findings">
              {lines.map((f, i) => (
                <li key={i}>
                  <span className="badge" data-tone={f.severity === "blocking" ? "bad" : f.severity === "warning" ? "warn" : "ok"}>
                    {f.severity}
                  </span>{" "}
                  {f.message} <span className="mono muted">{f.validator_id}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="rw-block">
          <div className="label">
            The page{viewMeta.page ? ` (printed ${viewMeta.page})` : ""}
            {viewMeta.highlighted ? " · cited table outlined" : imageUrl ? " · no outline available for this evidence" : ""}
          </div>
          {imageError ? (
            <div className="banner" data-tone="bad" role="alert">
              <strong>{imageError.message}</strong> {imageError.next_step}
            </div>
          ) : imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={imageUrl} alt={`Page ${viewMeta.page} of the source with the cited table outlined`} className="rw-page" />
          ) : (
            <p className="muted" aria-live="polite">
              Rendering the cited page…
            </p>
          )}
        </div>

        {prior ? (
          <div className="banner" data-tone={prior.candidate.review_status === "rejected" || prior.candidate.review_status === "unresolved" ? "warn" : "ok"} aria-live="polite">
            Recorded: <strong>{prior.decision.outcome}</strong> → {prior.candidate.review_status.replace(/_/g, " ")}
            {prior.candidate.review_status === "awaiting_second_review" ? " (a different reviewer must confirm before publication)" : ""}.{" "}
            <button type="button" onClick={undo} disabled={busy}>
              Undo (z)
            </button>
          </div>
        ) : null}

        {open ? (
          <form
            className="card rw-decide"
            aria-label="Decision"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <div className="rw-buttons">
              <button type="button" className="primary" disabled={!decidable || needsImage} onClick={() => void submit("approve")}>
                {busy ? "Recording…" : "Approve"}
              </button>
              <button type="button" data-active={outcome === "correct" || undefined} disabled={!decidable} onClick={() => setOutcome("correct")}>
                Change…
              </button>
              <button type="button" data-active={outcome === "reject" || undefined} disabled={!decidable} onClick={() => setOutcome("reject")}>
                Reject
              </button>
              <button type="button" data-active={outcome === "unresolved" || undefined} disabled={!decidable} onClick={() => setOutcome("unresolved")}>
                Cannot decide
              </button>
              <span className="muted">
                <button type="button" className="link" onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0}>
                  previous
                </button>{" "}
                ·{" "}
                <button type="button" className="link" onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))} disabled={index >= items.length - 1}>
                  skip for now
                </button>
              </span>
            </div>
            {needsImage ? <p className="muted">Approve and Change unlock once the page has rendered.</p> : null}
            {outcome === "correct" ? (
              <div className="rw-correct">
                <p className="muted">Fill only what is wrong; the rest stays as read. The cited cell stays as evidence.</p>
                <label>
                  Value <input value={correction.value ?? ""} onChange={(e) => setCorrection({ ...correction, value: e.target.value })} size={10} placeholder={rec.value ?? ""} />
                </label>{" "}
                <label>
                  State{" "}
                  <select value={correction.value_state ?? ""} onChange={(e) => setCorrection({ ...correction, value_state: e.target.value })}>
                    <option value="">(keep)</option>
                    {VALUE_STATES.map((v) => (
                      <option key={v} value={v}>
                        {v.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </label>{" "}
                <label>
                  Currency{" "}
                  <select value={correction.currency ?? ""} onChange={(e) => setCorrection({ ...correction, currency: e.target.value })}>
                    <option value="">(keep)</option>
                    <option value="rupees">rupees</option>
                    <option value="paise">paise</option>
                  </select>
                </label>{" "}
                <label>
                  Per <input value={correction.per_unit ?? ""} onChange={(e) => setCorrection({ ...correction, per_unit: e.target.value })} size={6} placeholder={rec.per_unit ?? ""} />
                </label>{" "}
                <label>
                  Frequency <input value={correction.frequency ?? ""} onChange={(e) => setCorrection({ ...correction, frequency: e.target.value })} size={10} placeholder={rec.frequency ?? ""} />
                </label>{" "}
                <label>
                  Category <input value={correction.category_code ?? ""} onChange={(e) => setCorrection({ ...correction, category_code: e.target.value })} size={8} placeholder={cand.category_code ?? ""} />
                </label>{" "}
                <label>
                  Cause{" "}
                  <select value={cause} onChange={(e) => setCause(e.target.value as (typeof CAUSE_TAGS)[number])}>
                    {CAUSE_TAGS.map((c) => (
                      <option key={c} value={c}>
                        {c.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            ) : null}
            {outcome !== "approve" ? (
              <p>
                <label>
                  Why{" "}
                  <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={2} cols={70} placeholder="one sentence; it is recorded with the decision" />
                </label>
                <br />
                <button type="submit" disabled={!decidable || (outcome === "correct" && needsImage)}>
                  {busy ? "Recording…" : outcome === "correct" ? "Record the change" : outcome === "reject" ? "Record the rejection" : "Record: cannot decide"}
                </button>
              </p>
            ) : (
              <p className="muted">
                Approving needs no reason. <label>Optional note <input value={rationale} onChange={(e) => setRationale(e.target.value)} size={40} /></label>
              </p>
            )}
            {error ? (
              <div className="banner" data-tone="bad" role="alert">
                <strong>{error.message}</strong> <span className="muted">({error.error_type})</span>
                <div>{error.next_step}</div>
                {error.detail ? <div className="muted mono">{error.detail}</div> : null}
                {error.error_type === "conflict_stale_version" ? <div className="muted">Someone changed this candidate since you loaded it. Reload; nothing was overwritten.</div> : null}
              </div>
            ) : null}
          </form>
        ) : null}
        <p className="muted">Keys: Enter approve · c change · r reject · u cannot decide · n next · p previous · z undo</p>
      </section>
    </div>
  );
}
