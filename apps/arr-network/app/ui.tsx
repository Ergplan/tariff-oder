// Small server components shared by the pages.  All text is rendered through React, which
// escapes it: nothing read from an order is ever inserted as HTML.
import type { Loaded } from "@/lib/db.ts";
import { consensusWords, pageLink } from "@/lib/format.ts";

export function DbDown({ state }: { state: Exclude<Loaded<unknown>, { ok: true }> }) {
  const what = {
    not_configured: "No database is configured for this deployment (DATABASE_URL is not set).",
    unreachable: "The database could not be reached just now.",
    not_migrated: "The database is connected but its schema has not been applied yet.",
  }[state.reason];
  return (
    <div className="down" role="status">
      <p className="eyebrow">Database not connected</p>
      <h1>No data to show</h1>
      <p>{what}</p>
      <p className="note">This page shows only what the database holds, so it shows nothing rather than a guess. Try again later.</p>
    </div>
  );
}

/** The consensus class in words, and "reviewed by a person" only when a person reviewed it. */
export function Consensus({ c, reviewedBy }: { c: string | null | undefined; reviewedBy?: string | null }) {
  return (
    <>
      {c ? <span className={`cons ${c}`}>{consensusWords(c)}</span> : null}
      {reviewedBy ? <> <span className="cons reviewed" title={`reviewed by ${reviewedBy}`}>reviewed by a person</span></> : null}
    </>
  );
}

export function PageLink({ url, page, children }: { url: string | null | undefined; page?: number | null; children?: React.ReactNode }) {
  const href = pageLink(url, page);
  if (!href) return <>{children ?? (page ? `p. ${page}` : "—")}</>;
  return <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children ?? `p. ${page}`}</a>;
}

export function Crumbs({ items }: { items: [string, string | null][] }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {items.map(([label, href], i) => (
        <span key={i}>{i ? " › " : ""}{href ? <a href={href}>{label}</a> : <span aria-current="page">{label}</span>}</span>
      ))}
    </nav>
  );
}
