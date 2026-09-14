import Link from "next/link";
import type { ExplorerReleaseList } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge } from "../components";

export const dynamic = "force-dynamic";

/**
 * Published releases (Section 9, screen 5 entry).  Only current data releases appear; a source
 * without a release is not listed and nothing here comes from candidates.  Fixture releases
 * are counted separately and labelled; they never count as coverage.
 */
export default async function ExplorerIndexPage() {
  const rl = await apiTry<ExplorerReleaseList>("/explorer/releases");
  if (rl.error || !rl.data) {
    return (
      <>
        <h1>Tariff explorer</h1>
        <ErrorBanner error={rl.error!} />
      </>
    );
  }
  return (
    <>
      <h1>Tariff explorer</h1>
      <p className="muted">
        {rl.data.real} real release(s), {rl.data.fixture} fixture release(s). Every value shown in the explorer is a published fact with
        its citation; a partial release is labelled partial everywhere and cannot be used to assert that no other condition applies.
      </p>
      {rl.data.total === 0 ? (
        <p className="muted">No published release yet. Coverage is empty; nothing is verified.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Dataset</th>
                <th>State</th>
                <th>Release</th>
                <th>Completeness</th>
                <th>Facts</th>
                <th>Utility / period</th>
                <th>Published</th>
              </tr>
            </thead>
            <tbody>
              {rl.data.items.map((i) => (
                <tr key={i.release.id}>
                  <td>
                    <Link href={`/explorer/${i.release.source_id}`}>{i.original_filename}</Link>{" "}
                    <Link href={`/explorer/${i.release.source_id}/network`}>network charges</Link>
                  </td>
                  <td>
                    <DatasetBadge kind={i.dataset_kind} />
                  </td>
                  <td>
                    <StateBadge state={i.state} />
                  </td>
                  <td className="mono">
                    {i.release.release_number} · {i.release.scope}
                  </td>
                  <td>
                    <span className="badge" data-tone={i.release.completeness === "complete" ? "ok" : "warn"}>
                      {i.release.completeness}
                      {i.release.completeness === "partial" ? ` (${i.release.gaps.length} gaps)` : ""}
                    </span>
                  </td>
                  <td className="mono">{i.release.fact_count}</td>
                  <td className="mono">{[i.release.utility, i.release.period].filter(Boolean).join(" / ") || "—"}</td>
                  <td className="muted">
                    {i.release.published_at} by {i.release.published_by}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
