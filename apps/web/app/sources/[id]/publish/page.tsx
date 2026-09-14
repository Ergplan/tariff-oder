import Link from "next/link";
import type { ReleaseList, SourceDetail } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge } from "../../../components";
import { PublishForm } from "./publish-form";

export const dynamic = "force-dynamic";

/**
 * Publication (Section 7.2): a transaction over a declared scope with an explicit
 * completeness declaration.  The consequences are shown first (preview) and the publish
 * call carries the preview token, so a release never rests on a stale view of the order.
 */
export default async function PublishPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await apiTry<SourceDetail>(`/sources/${id}`);
  if (detail.error || !detail.data) {
    return (
      <>
        <h1>Publish</h1>
        <ErrorBanner error={detail.error!} />
      </>
    );
  }
  const s = detail.data;
  const releases = await apiTry<ReleaseList>(`/sources/${id}/releases`);
  return (
    <>
      <h1>
        Publish: {s.original_filename} <DatasetBadge kind={s.dataset_kind} /> <StateBadge state={s.state} />
      </h1>
      <p className="muted">
        <Link href={`/sources/${id}`}>Back to the source</Link> · <Link href={`/sources/${id}/review`}>Review workspace</Link>
      </p>
      {s.dataset_kind === "fixture" ? (
        <div className="banner" data-tone="fixture">
          Fixture dataset: a release here is labelled FIXTURE everywhere and never counts as coverage.
        </div>
      ) : null}
      {releases.data && releases.data.total > 0 ? (
        <div className="table-wrap">
          <table>
            <caption>Releases so far (cumulative; the current one carries every published fact)</caption>
            <thead>
              <tr>
                <th>#</th>
                <th>Scope</th>
                <th>Completeness</th>
                <th>Facts</th>
                <th>By</th>
                <th>At</th>
                <th>Current</th>
              </tr>
            </thead>
            <tbody>
              {releases.data.releases.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.release_number}</td>
                  <td className="mono">
                    {r.scope}
                    {r.scope_categories.length ? ` (${r.scope_categories.join(", ")})` : ""}
                  </td>
                  <td>
                    <span className="badge" data-tone={r.completeness === "complete" ? "ok" : "warn"}>
                      {r.completeness}
                    </span>{" "}
                    <span className="muted">{r.gaps.length ? `${r.gaps.length} gaps` : ""}</span>
                  </td>
                  <td className="mono">{r.fact_count}</td>
                  <td>{r.published_by}</td>
                  <td className="muted">{r.published_at}</td>
                  <td>{r.is_current ? "current" : "superseded"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {s.state === "awaiting_review" || s.state === "published" ? (
        <PublishForm sourceId={id} sourceVersion={s.version} />
      ) : (
        <div className="banner" data-tone="warn">
          The source is <code>{s.state}</code>; publication needs an order awaiting review.
        </div>
      )}
    </>
  );
}
