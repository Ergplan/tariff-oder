"use client";

import Link from "next/link";
import { useCallback, useMemo, useRef, useState } from "react";
import type { CandidateOut, CategorySummaryOut, DecisionResult, ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";
import { COMPONENT_LABEL, FAMILY_LABEL, type FindingLine, type Rec, valueWords } from "../review-workspace";

type Outcome = "approve" | "reject" | "unresolved";
type Applic = {
  rate_block?: string | null;
  description?: string | null;
  voltage?: string | null;
  time_band?: string | null;
  season?: string | null;
  slab?: { original_text?: string | null } | null;
  load_band?: { original_text?: string | null } | null;
};
type Cell = { cand: CandidateOut; rec: Rec; a: Applic; page: number; row: number };
type Block = { key: string; label: string; components: string[]; rows: { label: string; cells: Record<string, Cell> }[] };
type Group = { key: string; title: string; subtitle: string | null; pages: number[]; blocks: Block[]; all: Cell[]; family: string };

const COMPONENT_ORDER = ["fixed", "demand", "energy", "minimum", "tod_adjustment", "rebate", "surcharge", "subsidy", "green_premium", "charge", "loss", "condition", "cross_reference"];
const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  awaiting_second_review: "1 of 2 approvals",
  approved: "Approved",
  corrected: "Corrected",
  rejected: "Rejected",
  unresolved: "Needs a decision",
};
const STATUS_TONE: Record<string, string> = {
  pending: "unknown",
  awaiting_second_review: "warn",
  approved: "ok",
  corrected: "ok",
  rejected: "bad",
  unresolved: "bad",
};

function effective(c: CandidateOut): Rec {
  return ((c.reviewed_record as Rec | null) ?? (c.record as Rec)) || {};
}
function blockLetter(block: string | null | undefined): string {
  const m = /^\s*\(?([a-z]|[ivx]{1,4}|\d{1,2})\)/i.exec(block ?? "");
  return m ? `(${m[1].toLowerCase()})` : (block ?? "").trim().toLowerCase().slice(0, 80);
}
function rowLabel(a: Applic): string {
  const parts = [a.description, a.voltage, a.slab?.original_text, a.load_band?.original_text, a.time_band, a.season]
    .filter((x): x is string => !!x)
    .map((x) => x.replace(/\s+/g, " ").trim());
  const seen = new Set<string>();
  const out = parts.filter((x) => {
    const k = x.toLowerCase();
    if (seen.has(k) || [...seen].some((y) => y.includes(k))) return false;
    seen.add(k);
    return true;
  });
  return out.join(" · ") || "Rate";
}
function isPlaceholder(code: string | null | undefined): boolean {
  return !code || /^(\?|<[^>]*>|unknown|n\/?a|general)$/i.test(code.trim());
}
function isOpen(c: CandidateOut): boolean {
  return c.review_status === "pending" || c.review_status === "awaiting_second_review";
}
function agreeBadge(c: CandidateOut): { text: string; tone: string; title: string } {
  if (c.risk_tags.includes("stale_reading")) return { text: "stale", tone: "bad", title: "From an earlier reading; the current reading does not produce this value. Reject it." };
  if (c.channel_agreement === "agree") return { text: "2 readings agree", tone: "ok", title: "The rules and the model read the same value from the page." };
  if (c.channel_agreement === "disagree") {
    const other = c.image_record ? valueWords(c.image_record as Rec) : "another value";
    return { text: `model read ${other}`, tone: "bad", title: `The two readings differ on: ${c.disagreeing_fields.join(", ")}.` };
  }
  if (c.channel_agreement === "one_missing") return { text: "1 reading", tone: "warn", title: "Only one of the two readings produced this value." };
  return { text: "rules only", tone: "neutral", title: "Read by the deterministic rules; no model reading for this region." };
}

function buildGroups(cands: CandidateOut[]): Group[] {
  const cells: Cell[] = cands.map((cand) => {
    const rec = effective(cand);
    const ev = rec.evidence?.[0];
    return { cand, rec, a: (rec.applicability ?? {}) as Applic, page: ev?.page_index ?? 0, row: ev?.row ?? ev?.line_no ?? 0 };
  });
  const byGroup = new Map<string, Cell[]>();
  for (const c of cells) {
    const k =
      c.cand.family === "retail_tariff"
        ? isPlaceholder(c.cand.category_code)
          ? "general"
          : `retail:${c.cand.category_code}`
        : `family:${c.cand.family}`;
    (byGroup.get(k) ?? byGroup.set(k, []).get(k)!).push(c);
  }
  const groups: Group[] = [];
  for (const [key, list] of byGroup) {
    list.sort((x, y) => x.page - y.page || x.row - y.row);
    const pages = [...new Set(list.map((c) => c.page).filter(Boolean))].sort((a, b) => a - b);
    const blocksMap = new Map<string, Block>();
    for (const c of list) {
      const retail = key.startsWith("retail:") || key === "general";
      const bk = retail ? blockLetter(c.a.rate_block) || "" : c.cand.category_code ?? "";
      let block = blocksMap.get(bk);
      if (!block) {
        block = { key: bk, label: retail ? (c.a.rate_block ?? "").replace(/\s+/g, " ") || "Rates" : c.cand.category_code ?? "All categories", components: [], rows: [] };
        blocksMap.set(bk, block);
      }
      const comp = c.cand.component_type;
      if (!block.components.includes(comp)) block.components.push(comp);
      const label = retail ? rowLabel(c.a) : [c.cand.category_code, c.a.voltage, c.a.description].filter(Boolean).join(" · ") || "Value";
      let row = block.rows.find((r) => r.label === label && !r.cells[comp]);
      if (!row) {
        row = { label, cells: {} };
        block.rows.push(row);
      }
      row.cells[comp] = c;
    }
    for (const b of blocksMap.values()) b.components.sort((x, y) => (COMPONENT_ORDER.indexOf(x) + 99) % 99 - ((COMPONENT_ORDER.indexOf(y) + 99) % 99));
    const family = list[0].cand.family;
    groups.push({
      key,
      family,
      title:
        key === "general"
          ? "General provisions (not tied to one category)"
          : key.startsWith("retail:")
            ? `Rate schedule ${list[0].cand.category_code}`
            : FAMILY_LABEL[family] ?? family,
      subtitle: null,
      pages,
      blocks: [...blocksMap.values()],
      all: list,
    });
  }
  const famOrder = (g: Group) => (g.key === "general" ? 1 : g.family === "retail_tariff" ? 0 : 2);
  groups.sort((x, y) => famOrder(x) - famOrder(y) || (x.pages[0] ?? 0) - (y.pages[0] ?? 0));
  return groups;
}

/**
 * The tariff table: one card per category in document order, one grid per lettered block,
 * approve / reject / note on every value.  The page is rendered once per block with the
 * cited tables outlined and every candidate on it gets its evidence view from that render,
 * so a reviewer sees the page before a value can be approved (the API refuses otherwise).
 */
export function TariffTable({
  sourceId,
  sourceState,
  initial,
  summaries,
  findings,
}: {
  sourceId: string;
  sourceState: string;
  initial: CandidateOut[];
  summaries: Record<string, CategorySummaryOut>;
  findings: Record<string, FindingLine[]>;
}) {
  const [cands, setCands] = useState<CandidateOut[]>(initial);
  const [views, setViews] = useState<Record<string, string>>({});
  const [pageImage, setPageImage] = useState<{ page: number; url: string } | null>(null);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState<{ cid: string; outcome: Outcome; text: string } | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [showSummary, setShowSummary] = useState<Record<string, boolean>>({});
  const viewedAt = useRef<number | null>(null);
  const open = sourceState === "awaiting_review";
  const groups = useMemo(() => buildGroups(cands), [cands]);
  const byId = useMemo(() => new Map(cands.map((c) => [c.id, c])), [cands]);

  /** Render a page once for every candidate cited on it; returns the view ids issued. */
  const ensurePage = useCallback(
    async (page: number, ids: string[]): Promise<Record<string, string>> => {
      const missing = ids.filter((id) => !views[id]);
      if (missing.length === 0) return views;
      const res = await fetch(`/api/sources/${sourceId}/review/pages/${page}/image?candidates=${encodeURIComponent(missing.join(","))}`, { cache: "no-store" });
      if (!res.ok) throw await readError(res);
      const blob = await res.blob();
      const issued = JSON.parse(res.headers.get("x-evidence-view-ids") || "{}") as Record<string, string>;
      setPageImage((old) => {
        if (old) URL.revokeObjectURL(old.url);
        return { page, url: URL.createObjectURL(blob) };
      });
      viewedAt.current = Date.now();
      const next = { ...views, ...issued };
      setViews(next);
      return next;
    },
    [sourceId, views],
  );

  const showPage = useCallback(
    async (page: number, g: Group) => {
      setError(null);
      try {
        await ensurePage(page, g.all.filter((c) => c.page === page && isOpen(c.cand)).map((c) => c.cand.id));
      } catch (e) {
        setError((e as ErrorResponse).message ? (e as ErrorResponse) : networkError("The page image"));
      }
    },
    [ensurePage],
  );

  const decide = useCallback(
    async (cid: string, outcome: Outcome, rationale: string | null, viewMap: Record<string, string>): Promise<boolean> => {
      const cand = byId.get(cid);
      if (!cand) return false;
      const body = {
        outcome,
        expected_version: cand.version,
        rationale,
        evidence_view_ids: viewMap[cid] ? [viewMap[cid]] : [],
        time_spent_ms: viewedAt.current ? Date.now() - viewedAt.current : null,
      };
      const res = await fetch(`/api/candidates/${cid}/decision`, {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw await readError(res);
      const r = (await res.json()) as DecisionResult;
      setCands((list) => list.map((c) => (c.id === cid ? r.candidate : c)));
      return true;
    },
    [byId],
  );

  /** One value: render its page for the block first when this reviewer has not seen it. */
  async function act(cell: Cell, g: Group, outcome: Outcome, rationale: string | null) {
    if (!open || busy) return;
    if (outcome !== "approve" && (rationale ?? "").trim().length < 5) {
      setReason({ cid: cell.cand.id, outcome, text: rationale ?? "" });
      return;
    }
    setBusy(cell.cand.id);
    setError(null);
    try {
      const viewMap = await ensurePage(cell.page, g.all.filter((c) => c.page === cell.page && isOpen(c.cand)).map((c) => c.cand.id));
      await decide(cell.cand.id, outcome, rationale, viewMap);
      setReason(null);
    } catch (e) {
      setError((e as ErrorResponse).message ? (e as ErrorResponse) : networkError("The decision"));
    } finally {
      setBusy(null);
    }
  }

  /** Every open value in the category on which both readings agree and no validator blocks. */
  async function approveAgreeing(g: Group) {
    if (!open || busy) return;
    const targets = g.all.filter(
      (c) => isOpen(c.cand) && c.cand.channel_agreement === "agree" && c.cand.blocking_finding_count === 0 && !c.cand.risk_tags.includes("stale_reading"),
    );
    if (targets.length === 0) return;
    setBusy(g.key);
    setError(null);
    let done = 0;
    try {
      let viewMap = views;
      for (const page of [...new Set(targets.map((c) => c.page))].sort((a, b) => a - b)) {
        setProgress(`${g.title}: showing page ${page}…`);
        viewMap = await ensurePage(page, g.all.filter((c) => c.page === page && isOpen(c.cand)).map((c) => c.cand.id));
        for (const c of targets.filter((t) => t.page === page)) {
          setProgress(`${g.title}: approving ${done + 1} of ${targets.length}…`);
          await decide(c.cand.id, "approve", null, viewMap);
          done += 1;
        }
      }
      setProgress(`${g.title}: ${done} approved.`);
    } catch (e) {
      setProgress(`${g.title}: ${done} approved before an error.`);
      setError((e as ErrorResponse).message ? (e as ErrorResponse) : networkError("The approval"));
    } finally {
      setBusy(null);
    }
  }

  const totals = useMemo(() => {
    const t = { open: 0, approved: 0, rejected: 0, other: 0 };
    for (const c of cands) {
      if (isOpen(c)) t.open += 1;
      else if (c.review_status === "approved" || c.review_status === "corrected") t.approved += 1;
      else if (c.review_status === "rejected") t.rejected += 1;
      else t.other += 1;
    }
    return t;
  }, [cands]);

  const pct = cands.length ? Math.round(((totals.approved + totals.rejected) / cands.length) * 100) : 0;
  return (
    <div className="tt" data-page={pageImage ? "1" : undefined}>
      <nav className="tt-nav" aria-label="Categories">
        <div className="tt-nav-head">
          <div className="tt-progress" title={`${pct}% decided`}>
            <span style={{ width: `${pct}%` }} />
          </div>
          <div className="muted">
            {totals.open} open · {totals.approved} approved · {totals.rejected} rejected{totals.other ? ` · ${totals.other} undecided` : ""}
          </div>
        </div>
        <ol>
          {groups.map((g) => {
            const openHere = g.all.filter((c) => isOpen(c.cand)).length;
            const done = g.all.length - openHere;
            return (
              <li key={g.key} data-done={openHere === 0 || undefined}>
                <a href={`#${g.key}`}>{g.title.replace(/^Rate schedule /, "")}</a>
                <span className="mono muted">
                  {done}/{g.all.length}
                </span>
              </li>
            );
          })}
        </ol>
      </nav>
      <div className="tt-main">
        {progress ? <div className="tt-bar muted">{progress}</div> : null}
        {error ? (
          <div className="banner" data-tone="bad" role="alert">
            <strong>{error.message}</strong> {error.next_step}
            {error.detail ? <div className="muted">{error.detail}</div> : null}
          </div>
        ) : null}
        {groups.map((g) => {
          const code = g.key.startsWith("retail:") ? g.key.slice(7) : null;
          const sm = code ? summaries[code] : undefined;
          const agreeing = g.all.filter((c) => isOpen(c.cand) && c.cand.channel_agreement === "agree" && c.cand.blocking_finding_count === 0 && !c.cand.risk_tags.includes("stale_reading")).length;
          const openHere = g.all.filter((c) => isOpen(c.cand)).length;
          return (
            <section className="tt-cat" key={g.key} id={g.key}>
              <header className="tt-cat-head">
                <div>
                  <h2>{g.title}</h2>
                  <div className="muted">
                    {sm?.heading_text ? `${sm.heading_text} · ` : ""}
                    {g.pages.length ? `pages ${g.pages.join(", ")}` : ""} · {g.all.length} values · {openHere} open
                  </div>
                </div>
                <div className="tt-cat-actions">
                  {g.pages.map((p) => (
                    <button key={p} type="button" className="tt-btn" onClick={() => void showPage(p, g)} disabled={!!busy}>
                      Page {p}
                    </button>
                  ))}
                  {open && agreeing > 0 ? (
                    <button type="button" className="tt-btn primary" onClick={() => void approveAgreeing(g)} disabled={!!busy}>
                      Approve all agreeing ({agreeing})
                    </button>
                  ) : null}
                </div>
              </header>
              {sm ? (
                <div className="tt-summary">
                  <button type="button" className="link" onClick={() => setShowSummary((x) => ({ ...x, [g.key]: !x[g.key] }))}>
                    {showSummary[g.key] ? "Hide" : "Show"} the model&apos;s summary of {code} ({sm.is_fixture ? "fixture" : sm.model}
                    {sm.grounded ? ", every number traced to the pages" : ", NOT grounded: contains numbers not on the pages"})
                  </button>
                  {showSummary[g.key] ? <p>{sm.text}</p> : null}
                </div>
              ) : null}
              {g.blocks.map((b) => (
                <div className="tt-block" key={b.key || "default"}>
                  {b.label !== "Rates" ? <h3>{b.label}</h3> : null}
                  <div className="table-wrap">
                    <table className="tt-grid">
                      <thead>
                        <tr>
                          <th>{g.family === "retail_tariff" ? "Applies to" : "Category · applies to"}</th>
                          {b.components.map((comp) => (
                            <th key={comp}>{COMPONENT_LABEL[comp] ?? comp}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {b.rows.map((r, i) => (
                          <tr key={`${r.label}-${i}`}>
                            <td className="tt-row-label">{r.label}</td>
                            {b.components.map((comp) => {
                              const cell = r.cells[comp];
                              if (!cell) return <td key={comp} className="muted">—</td>;
                              const c = cell.cand;
                              const badge = agreeBadge(c);
                              const fl = findings[c.id] ?? [];
                              const blocking = fl.filter((f) => f.severity === "blocking");
                              const reasonHere = reason?.cid === c.id;
                              const st = c.review_status;
                              const meaning = (c.record?.assessment as { meaning?: string; grounded?: boolean } | null)?.meaning;
                              return (
                                <td key={comp} className="tt-cell" data-status={st} data-busy={busy === c.id || undefined}>
                                  <div className="tt-val" title={cell.rec.rationale ?? ""}>
                                    {valueWords(cell.rec)}
                                  </div>
                                  {meaning ? <div className="tt-cue muted">{meaning}</div> : null}
                                  <div className="tt-meta">
                                    <span className="badge" data-tone={badge.tone} title={badge.title}>
                                      {badge.text}
                                    </span>{" "}
                                    <span className="badge" data-tone={STATUS_TONE[st] ?? "unknown"}>
                                      {STATUS_LABEL[st] ?? st}
                                    </span>
                                    {blocking.length ? (
                                      <span className="badge" data-tone="bad" title={blocking.map((f) => `${f.validator_id}: ${f.message}`).join("\n")}>
                                        {blocking.length} blocking check{blocking.length > 1 ? "s" : ""}
                                      </span>
                                    ) : null}
                                    {c.record?.assessment && (c.record.assessment as { verdict?: string }).verdict === "contradicted" ? (
                                      <span className="badge" data-tone="warn" title={String((c.record.assessment as { issue?: string }).issue ?? "")}>
                                        model check disagrees
                                      </span>
                                    ) : null}
                                  </div>
                                  <div className="tt-where muted" title={cell.rec.rationale ?? ""}>
                                    p. {cell.page}
                                    {cell.rec.original_text && cell.rec.original_text !== cell.rec.value
                                      ? ` · “${cell.rec.original_text.length > 90 ? `${cell.rec.original_text.slice(0, 90)}…` : cell.rec.original_text}”`
                                      : ""}
                                  </div>
                                  {open && isOpen(c) ? (
                                    <div className="tt-actions">
                                      <button type="button" className="tt-btn ok" onClick={() => void act(cell, g, "approve", null)} disabled={!!busy} title="Approve this value as printed">
                                        ✓ Approve
                                      </button>
                                      <button type="button" className="tt-btn bad" onClick={() => setReason({ cid: c.id, outcome: "reject", text: "" })} disabled={!!busy} title="Reject: the value is wrong or not a tariff">
                                        ✗
                                      </button>
                                      <button type="button" className="tt-btn" onClick={() => setReason({ cid: c.id, outcome: "unresolved", text: "" })} disabled={!!busy} title="Leave a note; the value stays undecided">
                                        Note
                                      </button>
                                      <Link className="tt-link" href={`/sources/${sourceId}/review?category=${encodeURIComponent(c.category_code ?? "")}&component=${encodeURIComponent(comp)}`} title="Change the value or its unit in the one-at-a-time workspace">
                                        Change
                                      </Link>
                                    </div>
                                  ) : null}
                                  {reasonHere ? (
                                    <form
                                      className="tt-reason"
                                      onSubmit={(e) => {
                                        e.preventDefault();
                                        void act(cell, g, reason!.outcome, reason!.text);
                                      }}
                                    >
                                      <input
                                        autoFocus
                                        value={reason!.text}
                                        onChange={(e) => setReason({ ...reason!, text: e.target.value })}
                                        placeholder={reason!.outcome === "reject" ? "Why it is rejected (recorded)" : "Your note (recorded; value stays undecided)"}
                                        aria-label="Reason"
                                      />
                                      <button type="submit" className="tt-btn primary" disabled={!!busy || reason!.text.trim().length < 5}>
                                        {reason!.outcome === "reject" ? "Reject" : "Save note"}
                                      </button>
                                      <button type="button" className="tt-btn" onClick={() => setReason(null)}>
                                        Cancel
                                      </button>
                                    </form>
                                  ) : null}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </section>
          );
        })}
      </div>
      {pageImage ? (
        <aside className="tt-page">
          <div className="tt-page-head">
            <span className="muted">Page {pageImage.page} as printed, cited tables outlined. Seeing it is what allows approval.</span>
            <button type="button" className="tt-btn" onClick={() => setPageImage(null)} title="Hide the page and widen the table">
              Hide
            </button>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={pageImage.url} alt={`Page ${pageImage.page} with the cited tables outlined`} />
        </aside>
      ) : null}
    </div>
  );
}
