"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { CandidateOut, DecisionResult, ErrorResponse, ReviewQueueDetail } from "@tariff/contracts";

type Outcome = "approve" | "correct" | "reject" | "unresolved";
const CAUSE_TAGS = ["wrong_table", "header_misbound", "unit", "ocr", "footnote_missed", "cross_reference", "other"] as const;
const VALUE_STATES = [
  "value",
  "zero",
  "absent_in_source",
  "unknown",
  "unchanged_reference",
  "not_applicable",
  "formula",
  "cross_reference",
  "not_yet_verified",
] as const;

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
type Rec = {
  value?: string | null;
  value_state?: string;
  original_text?: string;
  currency?: string | null;
  per_unit?: string | null;
  frequency?: string | null;
  decision_status?: string | null;
  conditions?: string[];
  evidence?: EvidenceRef[];
  applicability?: Record<string, unknown>;
  [k: string]: unknown;
};

function fieldRows(rec: Rec, other: Rec | null, disagreeing: string[]) {
  const keys = ["value", "value_state", "original_text", "currency", "per_unit", "frequency", "decision_status", "period", "utility"];
  return keys.map((k) => ({
    key: k,
    a: rec[k] == null ? "—" : String(rec[k]),
    b: other ? (other[k] == null ? "—" : String(other[k])) : null,
    differs: disagreeing.includes(k),
  }));
}

/**
 * Side-by-side review (Section 7.2).  Left: the rendered page with the cited table outlined,
 * fetched through the same-origin proxy so the API can record that this reviewer saw it.
 * Right: the candidate, both channels when they disagree, findings count, and the four
 * outcomes.  Approve and correct stay disabled until the evidence image has loaded; the
 * server refuses anyway.  Keyboard: a approve, c correct, r reject, u unresolved, n/p next
 * and previous, z undo the last decision.  Nothing renders as decided until the API says so.
 */
export function ReviewWorkspace({ sourceId, queue, sourceState }: { sourceId: string; queue: ReviewQueueDetail; sourceState: string }) {
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
  const [result, setResult] = useState<DecisionResult | null>(null);
  const [decided, setDecided] = useState<Record<string, DecisionResult>>({});
  const viewedAt = useRef<number | null>(null);
  const attemptKey = useRef<string | null>(null);

  const item = items[index];
  const cand: CandidateOut | undefined = item?.candidate;
  const rec = useMemo(() => ((cand?.reviewed_record ?? cand?.record ?? {}) as Rec), [cand]);
  const image = (cand?.image_record ?? null) as Rec | null;
  const evidence = rec.evidence ?? [];
  const prior = cand ? decided[cand.id] : undefined;
  const open = sourceState === "awaiting_review" && !prior;

  const loadEvidence = useCallback(async (candidateId: string) => {
    setImageUrl(null);
    setViewId(null);
    setImageError(null);
    viewedAt.current = null;
    try {
      const res = await fetch(`/api/candidates/${candidateId}/evidence/0/image`, { cache: "no-store" });
      if (!res.ok) {
        setImageError((await res.json()) as ErrorResponse);
        return;
      }
      const blob = await res.blob();
      setImageUrl(URL.createObjectURL(blob));
      setViewId(res.headers.get("x-evidence-view-id"));
      setViewMeta({ highlighted: res.headers.get("x-evidence-highlighted") === "1", page: res.headers.get("x-evidence-page") ?? "" });
      viewedAt.current = Date.now();
    } catch {
      setImageError({
        error_type: "provider_unavailable",
        message: "The evidence image could not be fetched.",
        next_step: "Check the connection and retry; no decision is possible without it.",
        severity: "error",
        request_id: null,
      });
    }
  }, []);

  useEffect(() => {
    if (cand) {
      void loadEvidence(cand.id);
      setOutcome("approve");
      setRationale("");
      setCorrection({});
      setError(null);
      setResult(decided[cand.id] ?? null);
      attemptKey.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cand?.id]);

  async function submit() {
    if (!cand || busy || !open) return;
    if (outcome !== "approve" && rationale.trim().length < 5) {
      setError({
        error_type: "validation_failed",
        message: `${outcome} needs a rationale.`,
        next_step: "Say why, in a sentence; it is recorded with the decision.",
        severity: "warning",
        request_id: null,
      });
      return;
    }
    const patch: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(correction)) {
      if (v === "") continue;
      patch[k] = k === "value" ? v : v === "null" ? null : v;
    }
    const body: Record<string, unknown> = {
      outcome,
      expected_version: cand.version,
      rationale: rationale || null,
      evidence_view_ids: viewId ? [viewId] : [],
      time_spent_ms: viewedAt.current ? Date.now() - viewedAt.current : null,
    };
    if (outcome === "correct") {
      body.correction = patch;
      body.cause_tag = cause;
      body.evidence_indices = [0];
    }
    if (!attemptKey.current) attemptKey.current = crypto.randomUUID(); // reused on retry: exactly one effect
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/candidates/${cand.id}/decision`, {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": attemptKey.current },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (!res.ok) setError(json as ErrorResponse);
      else {
        const r = json as DecisionResult;
        setResult(r);
        setDecided((d) => ({ ...d, [cand.id]: r }));
        attemptKey.current = null;
        router.refresh();
      }
    } catch {
      setError({
        error_type: "provider_unavailable",
        message: "The decision could not reach the server.",
        next_step: "Retry; the same idempotency key guarantees a single effect.",
        severity: "error",
        request_id: null,
      });
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
      const json = await res.json();
      if (!res.ok) setError(json as ErrorResponse);
      else {
        setDecided((d) => {
          const copy = { ...d };
          delete copy[cand.id];
          return copy;
        });
        setResult(null);
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
      else if (e.key === "Enter" && outcome === "approve") void submit();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length, outcome, cand?.id, viewId, busy, prior]);

  if (!cand) return null;
  const canDecide = open && !busy && (outcome === "reject" || outcome === "unresolved" || !!viewId);
  const ev0 = evidence[0];

  return (
    <div>
      <p className="muted">
        Candidate {item.position} of {queue.total}
        {queue.total > items.length ? ` (first ${items.length} loaded)` : ""} · {item.reason}
        {item.coverage_impact ? " · category has no approved fact yet" : ""} · keys: n next, p previous, a/c/r/u outcome, Enter approve, z undo
      </p>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-start" }}>
        <section style={{ flex: "1 1 460px", minWidth: 0 }} aria-label="Cited evidence">
          <div className="card">
            <div className="label">
              Evidence · page {ev0?.page_index ?? "?"} · {ev0?.kind}
              {ev0?.row != null ? ` · row ${ev0.row} col ${ev0.col}` : ev0?.line_no != null ? ` · line ${ev0.line_no}` : ""}
              {viewMeta.highlighted ? " · cited table outlined" : imageUrl ? " · no table outline available for this evidence" : ""}
            </div>
            {ev0?.header_path?.length ? (
              <div>
                Header path: <span className="mono">{ev0.header_path.join(" › ")}</span>
              </div>
            ) : null}
            {ev0?.row_path?.length ? (
              <div>
                Row path: <span className="mono">{ev0.row_path.join(" › ")}</span>
              </div>
            ) : null}
            {ev0?.clause_path?.length ? (
              <div>
                Clause: <span className="mono">{ev0.clause_path.join(" › ")}</span>
              </div>
            ) : null}
            <div>
              Excerpt: <code>{ev0?.excerpt}</code>
            </div>
            {rec.conditions?.length ? (
              <div className="muted">
                Linked conditions:
                <ul>
                  {rec.conditions.map((c, i) => (
                    <li key={i}>
                      <code>{c}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
          {imageError ? (
            <div className="banner" data-tone="bad" role="alert">
              <strong>{imageError.message}</strong> {imageError.next_step}
            </div>
          ) : imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={imageUrl} alt={`Page ${viewMeta.page} of the source with the cited table outlined`} style={{ maxWidth: "100%", border: "1px solid var(--border)" }} />
          ) : (
            <p className="muted" aria-live="polite">
              Rendering the cited page… (stage: evidence render)
            </p>
          )}
          {evidence.length > 1 ? (
            <p className="muted">
              {evidence.length - 1} further evidence reference(s):{" "}
              {evidence.slice(1).map((e, i) => (
                <span key={i} className="mono">
                  p{e.page_index} {e.kind}
                  {e.row != null ? ` r${e.row} c${e.col}` : ""}{" "}
                </span>
              ))}
            </p>
          ) : null}
        </section>

        <section style={{ flex: "1 1 420px", minWidth: 0 }} aria-label="Candidate">
          <div className="card">
            <div className="label">
              Candidate · <span className="mono">{cand.family}</span> {cand.category_code ? <span className="mono">{cand.category_code}</span> : null} ·{" "}
              {cand.component_type} · version {cand.version}
            </div>
            <div>
              <span className="badge" data-tone={cand.confidence === "high" ? "ok" : cand.confidence === "medium" ? "warn" : "bad"}>
                {cand.confidence}
              </span>{" "}
              <span className="badge" data-tone={cand.channel_agreement === "agree" ? "ok" : cand.channel_agreement === "disagree" ? "bad" : "warn"}>
                channels {cand.channel_agreement}
              </span>{" "}
              <span className="badge" data-tone={cand.routing === "batch" ? "neutral" : "warn"}>{cand.routing} review</span>{" "}
              {cand.is_fixture ? <span className="badge" data-tone="fixture">FIXTURE</span> : null}{" "}
              <span className="mono muted">{cand.risk_tags.join(", ")}</span>
              {cand.finding_count ? (
                <span className="badge" data-tone={cand.blocking_finding_count ? "bad" : "warn"}>
                  {cand.finding_count} finding(s){cand.blocking_finding_count ? `, ${cand.blocking_finding_count} blocking` : ""}
                </span>
              ) : null}
              {cand.review_status === "awaiting_second_review" ? (
                <span className="badge" data-tone="warn">second review · first by {cand.first_reviewer}</span>
              ) : null}
            </div>
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>{cand.reviewed_record ? "Corrected record" : "Structure channel"}</th>
                  {image ? <th>Image channel</th> : null}
                </tr>
              </thead>
              <tbody>
                {fieldRows(rec, image, cand.disagreeing_fields).map((f) => (
                  <tr key={f.key} data-differs={f.differs}>
                    <td className="muted">{f.key}</td>
                    <td className="mono">{f.a}</td>
                    {image ? <td className="mono" style={f.differs ? { color: "var(--bad)", fontWeight: 600 } : undefined}>{f.b}</td> : null}
                  </tr>
                ))}
                <tr>
                  <td className="muted">applicability</td>
                  <td className="mono" colSpan={image ? 2 : 1}>
                    {Object.entries(rec.applicability ?? {})
                      .filter(([, v]) => v != null)
                      .map(([k, v]) => `${k}=${typeof v === "object" ? ((v as { original_text?: string }).original_text ?? JSON.stringify(v)) : String(v)}`)
                      .join(" · ") || "—"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {prior ? (
            <div className="banner" data-tone={prior.candidate.review_status === "rejected" || prior.candidate.review_status === "unresolved" ? "warn" : "ok"} aria-live="polite">
              Recorded: <strong>{prior.decision.outcome}</strong> → candidate is <code>{prior.candidate.review_status}</code>
              {prior.candidate.review_status === "awaiting_second_review" ? " (a different reviewer must confirm before publication)" : ""}. Decision{" "}
              <code>{prior.decision.id}</code>.{" "}
              <button type="button" onClick={undo} disabled={busy}>
                Undo (z)
              </button>
            </div>
          ) : null}

          {open ? (
            <form
              className="card"
              aria-label="Decision"
              onSubmit={(e) => {
                e.preventDefault();
                void submit();
              }}
            >
              <div className="label">Decision</div>
              <p>
                {(["approve", "correct", "reject", "unresolved"] as Outcome[]).map((o) => (
                  <label key={o} style={{ marginRight: "0.75rem" }}>
                    <input type="radio" name="outcome" checked={outcome === o} onChange={() => setOutcome(o)} /> {o}
                  </label>
                ))}
              </p>
              {outcome === "correct" ? (
                <div>
                  <p className="muted">Structured edit: only filled fields change. Evidence selection defaults to the cited cell (index 0).</p>
                  <label>
                    value <input value={correction.value ?? ""} onChange={(e) => setCorrection({ ...correction, value: e.target.value })} size={10} />
                  </label>{" "}
                  <label>
                    value_state{" "}
                    <select value={correction.value_state ?? ""} onChange={(e) => setCorrection({ ...correction, value_state: e.target.value })}>
                      <option value="">(keep)</option>
                      {VALUE_STATES.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>{" "}
                  <label>
                    currency{" "}
                    <select value={correction.currency ?? ""} onChange={(e) => setCorrection({ ...correction, currency: e.target.value })}>
                      <option value="">(keep)</option>
                      <option value="rupees">rupees</option>
                      <option value="paise">paise</option>
                    </select>
                  </label>{" "}
                  <label>
                    per_unit <input value={correction.per_unit ?? ""} onChange={(e) => setCorrection({ ...correction, per_unit: e.target.value })} size={6} />
                  </label>{" "}
                  <label>
                    frequency <input value={correction.frequency ?? ""} onChange={(e) => setCorrection({ ...correction, frequency: e.target.value })} size={10} />
                  </label>{" "}
                  <label>
                    category_code <input value={correction.category_code ?? ""} onChange={(e) => setCorrection({ ...correction, category_code: e.target.value })} size={8} />
                  </label>
                  <p>
                    <label>
                      Cause{" "}
                      <select value={cause} onChange={(e) => setCause(e.target.value as (typeof CAUSE_TAGS)[number])}>
                        {CAUSE_TAGS.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </label>
                  </p>
                </div>
              ) : null}
              <p>
                <label>
                  Rationale {outcome === "approve" ? "(optional)" : "(required)"}
                  <br />
                  <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={2} cols={60} />
                </label>
              </p>
              {!viewId && (outcome === "approve" || outcome === "correct") ? (
                <p className="muted">The {outcome} control is disabled until the cited evidence has rendered.</p>
              ) : null}
              <button type="submit" disabled={!canDecide}>
                {busy ? "Recording…" : `Record ${outcome}`}
              </button>{" "}
              <button type="button" onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0}>
                Previous (p)
              </button>{" "}
              <button type="button" onClick={() => setIndex((i) => Math.min(items.length - 1, i + 1))} disabled={index >= items.length - 1}>
                Next (n)
              </button>
              {error ? (
                <div className="banner" data-tone="bad" role="alert" style={{ marginTop: "0.75rem" }}>
                  <strong>{error.message}</strong> <span className="muted">({error.error_type})</span>
                  <div>{error.next_step}</div>
                  {error.detail ? <div className="muted mono">{error.detail}</div> : null}
                  {error.error_type === "conflict_stale_version" ? (
                    <div className="muted">
                      Someone changed this candidate since you loaded it. Reload to see the current version; nothing was overwritten.
                    </div>
                  ) : null}
                  {error.request_id ? (
                    <div className="muted">
                      Request id: <code>{error.request_id}</code>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </form>
          ) : null}
          {result && !prior ? (
            <div className="banner" data-tone="ok">
              Recorded: {result.decision.outcome} → <code>{result.candidate.review_status}</code>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
