"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type { CandidateOut, ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";
import { ErrorBanner } from "../../../components";

type Chapter = { id: string; ordinal: number; branch: string; cue_text: string; page_start: number; page_end: number; status: string };
type Finding = { validator_id: string; severity: string; message: string; candidate_ids: string[] };
type Rec = { chapter?: number | null; line_code: string; fiscal_year: string; value_type: string; stated_value: string | null; stated_unit: string | null; original_text: string; evidence: { page_index: number; excerpt: string }[] };

const VOICE_ORDER = ["petitioned", "approved", "control_period", "provisional_true_up", "final_true_up", "actual"];
const BRANCH_ORDER = "ECLRTKX";
const OPEN = ["pending", "awaiting_second_review"];
const TONE: Record<string, string> = { approved: "ok", corrected: "ok", rejected: "bad", unresolved: "warn", awaiting_second_review: "warn", pending: "neutral" };

function rec(c: CandidateOut): Rec {
  return (c.reviewed_record ?? c.record) as unknown as Rec;
}

/**
 * The ARR review screen (ARR spec section 7): chapters on the left with progress and their
 * identity failures; a grid per chapter of line items down and year / voice across; the cited
 * page on the right, rendered for the reviewer before any value can be approved (the API
 * refuses otherwise).  A first ARR order of a licensee needs a second reviewer per value.
 */
export function ArrReview({ sourceId, open, chapters, initial, findings }: { sourceId: string; open: boolean; chapters: Chapter[]; initial: CandidateOut[]; findings: Finding[] }) {
  const [cands, setCands] = useState(initial);
  const [current, setCurrent] = useState<number>(chapters.find((c) => c.status === "confirmed")?.ordinal ?? chapters[0]?.ordinal ?? 0);
  const [views, setViews] = useState<Record<string, string>>({});
  const [img, setImg] = useState<{ page: number; url: string } | null>(null);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const viewedAt = useRef<number | null>(null);

  const chapterOf = useCallback(
    (page: number) => chapters.filter((ch) => ch.status === "confirmed").find((ch) => page >= ch.page_start && page <= ch.page_end)?.ordinal ?? 0,
    [chapters],
  );
  const byChapter = useMemo(() => {
    const m = new Map<number, CandidateOut[]>();
    for (const c of cands) {
      const ch = rec(c).chapter ?? chapterOf(rec(c).evidence?.[0]?.page_index ?? 0);
      m.set(ch, [...(m.get(ch) ?? []), c]);
    }
    return m;
  }, [cands, chapterOf]);
  const flagged = useMemo(() => new Set(findings.filter((f) => f.severity === "blocking").flatMap((f) => f.candidate_ids)), [findings]);

  const list = byChapter.get(current) ?? [];
  const lines = [...new Set(list.map((c) => rec(c).line_code))].sort((a, b) => BRANCH_ORDER.indexOf(a[0]) - BRANCH_ORDER.indexOf(b[0]) || a.localeCompare(b));
  const cols = [...new Set(list.map((c) => `${rec(c).fiscal_year}|${rec(c).value_type}`))].sort((a, b) => {
    const [fa, va] = a.split("|");
    const [fb, vb] = b.split("|");
    return fa.localeCompare(fb) || VOICE_ORDER.indexOf(va) - VOICE_ORDER.indexOf(vb);
  });
  const cell = (line: string, col: string) => list.find((c) => rec(c).line_code === line && `${rec(c).fiscal_year}|${rec(c).value_type}` === col);
  const chFindings = findings.filter((f) => f.candidate_ids.some((id) => list.some((c) => c.id === id)));

  async function showPage(page: number): Promise<Record<string, string>> {
    const ids = cands.filter((c) => (rec(c).evidence?.[0]?.page_index ?? 0) === page && OPEN.includes(c.review_status) && !views[c.id]).map((c) => c.id);
    if (img?.page === page && ids.length === 0) return views;
    const res = await fetch(`/api/sources/${sourceId}/review/pages/${page}/image${ids.length ? `?candidates=${encodeURIComponent(ids.join(","))}` : ""}`, { cache: "no-store" });
    if (!res.ok) throw await readError(res);
    const issued = JSON.parse(res.headers.get("x-evidence-view-ids") || "{}") as Record<string, string>;
    const blob = await res.blob();
    setImg((old) => {
      if (old) URL.revokeObjectURL(old.url);
      return { page, url: URL.createObjectURL(blob) };
    });
    viewedAt.current = Date.now();
    const next = { ...views, ...issued };
    setViews(next);
    return next;
  }

  async function post(c: CandidateOut, outcome: "approve" | "reject", rationale: string | null, viewMap: Record<string, string>) {
    const res = await fetch(`/api/candidates/${c.id}/decision`, {
      method: "POST",
      headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({
        outcome,
        expected_version: c.version,
        rationale,
        evidence_view_ids: viewMap[c.id] ? [viewMap[c.id]] : [],
        time_spent_ms: viewedAt.current ? Date.now() - viewedAt.current : null,
      }),
    });
    if (!res.ok) throw await readError(res);
    const r = (await res.json()) as { candidate: CandidateOut };
    setCands((all) => all.map((x) => (x.id === c.id ? r.candidate : x)));
  }

  /** Every open value on the page shown, read alike by both channels and in no identity
   * failure: each still gets its own decision, citing this reviewer's view of the page. */
  async function approvePage() {
    if (!open || busy || !img) return;
    const page = img.page;
    const eligible = list.filter((c) => OPEN.includes(c.review_status) && rec(c).evidence[0].page_index === page && c.channel_agreement === "agree" && !flagged.has(c.id) && !(c.risk_tags ?? []).some((t) => t !== "new_profile"));
    if (!eligible.length || !window.confirm(`Approve ${eligible.length} value(s) on page ${page} that both readings agree on and no identity check flags?`)) return;
    setBusy("page");
    setError(null);
    try {
      const viewMap = await showPage(page);
      for (const c of eligible) await post(c, "approve", null, viewMap);
    } catch (e) {
      setError((e as ErrorResponse).message ? (e as ErrorResponse) : networkError("The decisions"));
    } finally {
      setBusy(null);
    }
  }

  async function decide(c: CandidateOut, outcome: "approve" | "reject") {
    if (!open || busy) return;
    let rationale: string | null = null;
    if (outcome === "reject") {
      rationale = window.prompt("Why is this value rejected? (shown in the audit trail)") ?? "";
      if (rationale.trim().length < 5) return;
    }
    setBusy(c.id);
    setError(null);
    try {
      const viewMap = await showPage(rec(c).evidence[0].page_index);
      await post(c, outcome, rationale, viewMap);
    } catch (e) {
      setError((e as ErrorResponse).message ? (e as ErrorResponse) : networkError("The decision"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="arr-review">
      <aside className="arr-rail" aria-label="Chapters">
        {chapters.map((ch) => {
          const cs = byChapter.get(ch.ordinal) ?? [];
          const done = cs.filter((c) => !OPEN.includes(c.review_status)).length;
          const bad = findings.filter((f) => f.severity === "blocking" && f.candidate_ids.some((id) => cs.some((c) => c.id === id))).length;
          return (
            <button key={ch.id} type="button" className="link" data-current={ch.ordinal === current} onClick={() => setCurrent(ch.ordinal)} disabled={ch.status !== "confirmed"}>
              <strong>
                {ch.ordinal}. {ch.branch}
              </strong>{" "}
              <span className="muted">
                p.{ch.page_start}–{ch.page_end} · {done}/{cs.length}
              </span>
              {bad ? (
                <span className="badge" data-tone="bad">
                  {bad} identity
                </span>
              ) : null}
              <div className="muted">{ch.cue_text}</div>
            </button>
          );
        })}
      </aside>
      <section className="arr-grid">
        {chFindings.map((f, i) => (
          <div key={i} className="banner" data-tone={f.severity === "blocking" ? "bad" : "warn"}>
            <strong>{f.validator_id}</strong> {f.message}
          </div>
        ))}
        {error ? <ErrorBanner error={error} /> : null}
        {list.length === 0 ? (
          <p className="muted">No values read in this chapter.</p>
        ) : (
          <div className="table-wrap">
            <table className="cov-table">
              <thead>
                <tr>
                  <th>Line</th>
                  {cols.map((col) => (
                    <th key={col}>
                      {col.split("|")[0]}
                      <div className="muted">{col.split("|")[1].replace(/_/g, " ")}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line}>
                    <td>
                      <span className="mono">{line}</span>
                      <div className="muted">{rec(list.find((c) => rec(c).line_code === line)!).original_text}</div>
                    </td>
                    {cols.map((col) => {
                      const c = cell(line, col);
                      if (!c) return <td key={col} className="muted">—</td>;
                      const r = rec(c);
                      return (
                        <td key={col} data-flag={flagged.has(c.id) ? "identity" : undefined}>
                          <button type="button" className="link mono" onClick={() => void showPage(r.evidence[0].page_index).catch((e) => setError(e))} title={`page ${r.evidence[0].page_index}: "${r.evidence[0].excerpt}"`}>
                            {r.stated_value ?? "—"} {r.stated_unit ? <span className="muted">{r.stated_unit}</span> : <span className="badge" data-tone="warn">no unit</span>}
                          </button>
                          <div>
                            <span className="badge" data-tone={TONE[c.review_status] ?? "neutral"}>
                              {c.review_status.replace(/_/g, " ")}
                            </span>
                            {c.channel_agreement !== "agree" ? <span className="badge" data-tone="warn">{c.channel_agreement}</span> : null}
                          </div>
                          {open && OPEN.includes(c.review_status) ? (
                            <div>
                              <button type="button" className="tt-btn" disabled={busy === c.id} onClick={() => void decide(c, "approve")}>
                                Approve
                              </button>{" "}
                              <button type="button" className="tt-btn" disabled={busy === c.id} onClick={() => void decide(c, "reject")}>
                                Reject
                              </button>
                            </div>
                          ) : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <aside className="arr-page" aria-label="Cited page">
        {img ? (
          <>
            <div className="muted">
              Page {img.page}{" "}
              {open ? (
                <button type="button" className="tt-btn" disabled={!!busy} onClick={() => void approvePage()}>
                  Approve agreeing values on this page
                </button>
              ) : null}
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={img.url} alt={`page ${img.page} with the cited table outlined`} style={{ width: "100%" }} />
          </>
        ) : (
          <p className="muted">Click a value to see its page. A value is approved only after its page has been shown to you.</p>
        )}
      </aside>
    </div>
  );
}
