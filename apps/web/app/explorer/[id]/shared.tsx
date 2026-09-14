import type { CompletenessBanner, PublishedFactOut } from "@tariff/contracts";

/** Completeness banner (Section 7.3): the release, its declaration and its gaps, always visible. */
export function CompletenessBannerView({ b, unresolved }: { b: CompletenessBanner; unresolved: string[] }) {
  const partial = b.completeness === "partial";
  return (
    <div className="banner" data-tone={b.is_fixture ? "fixture" : partial ? "warn" : "ok"} role="status">
      <strong>
        Release {b.release_number} · {partial ? "PARTIAL" : "complete"}
      </strong>{" "}
      · published {b.published_at}
      {b.is_fixture ? " · FIXTURE release: synthetic material, never coverage" : ""}
      {partial ? (
        <div>
          Declared gaps ({b.gaps.length}): <span className="mono">{b.gaps.map((g) => `${g.key} (${g.reason})`).join("; ")}</span>. A partial
          release cannot be used to assert that no other condition applies.
        </div>
      ) : null}
      {b.unresolved || b.pending || b.awaiting_second_review ? (
        <div className="muted">
          At publication: {b.unresolved} unresolved, {b.pending} pending, {b.awaiting_second_review} awaiting a second reviewer.
        </div>
      ) : null}
      {unresolved.length ? <div className="muted">Unresolved items relevant to this view: {unresolved.join(", ")}</div> : null}
    </div>
  );
}

/** Citations derived by the backend from published evidence rows; each opens the cited page. */
export function Citations({ f }: { f: PublishedFactOut }) {
  return (
    <span>
      {f.citations.map((c, i) => (
        <a
          key={c.evidence_id}
          href={`/api/explorer/facts/${f.fact_id}/evidence/${i}/image`}
          target="_blank"
          rel="noreferrer"
          className="mono"
          title={`${c.header_path.join(" › ")}${c.row_path.length ? " | " + c.row_path.join(" › ") : ""} — “${c.excerpt}”`}
        >
          p{c.pdf_page}
          {c.printed_page ? ` (${c.printed_page})` : ""}
          {c.table_id ? ` ${c.table_id}` : ""}
          {c.cell ? ` ${c.cell}` : c.line_no != null ? ` l${c.line_no}` : ""}
        </a>
      ))}
    </span>
  );
}
