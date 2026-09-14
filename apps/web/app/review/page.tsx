import Link from "next/link";
import type { ReviewQueue } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge } from "../components";

export const dynamic = "force-dynamic";

/**
 * Review queue (Section 6.10): sources awaiting review with the individual / batch split.
 * Fixture sources carry their flag; there is no approval control here yet — the reviewer
 * workflow of Section 7.2 arrives in Milestone 5.  Nothing on this page is a published fact.
 */
export default async function ReviewQueuePage() {
  const q = await apiTry<ReviewQueue>("/review/queue");
  if (q.error || !q.data) {
    return (
      <>
        <h1>Review queue</h1>
        <ErrorBanner error={q.error!} />
      </>
    );
  }
  return (
    <>
      <h1>Review queue</h1>
      <p className="muted">
        {q.data.total_pending} candidates pending across {q.data.items.length} sources. Every candidate is a proposal until a
        reviewer decides; batch-eligible candidates still need a reviewer to view each one. Fixture sources are labelled and
        never mixed with real data.
      </p>
      {q.data.items.length === 0 ? (
        <p className="muted">Nothing awaiting review.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Dataset</th>
                <th>State</th>
                <th>Pending</th>
                <th>Individual</th>
                <th>Batch-eligible</th>
                <th>Blocked by validators</th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((i) => (
                <tr key={i.source_id}>
                  <td>
                    <Link href={`/sources/${i.source_id}`}>{i.original_filename}</Link>
                  </td>
                  <td>
                    <DatasetBadge kind={i.dataset_kind} />
                  </td>
                  <td>
                    <StateBadge state={i.state} />
                  </td>
                  <td className="mono">{i.pending}</td>
                  <td className="mono">{i.individual}</td>
                  <td className="mono">{i.batch}</td>
                  <td className="mono">{i.blocked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
