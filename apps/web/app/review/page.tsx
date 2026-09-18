import Link from "next/link";
import type { Me, ReviewQueue } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge } from "../components";

export const dynamic = "force-dynamic";

/**
 * Review queue (Section 6.10): sources awaiting review with the individual / batch split.
 * Fixture sources carry their flag.  Decisions are taken in each source's review workspace
 * (Section 7.2); nothing on this page is a published fact.
 */
export default async function ReviewQueuePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const me = await apiTry<Me>("/me");
  const mine = sp.mine === "1" && me.data ? me.data.email : null;
  const q = await apiTry<ReviewQueue>(`/review/queue${mine ? `?assigned=${encodeURIComponent(mine)}` : ""}`);
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
        {q.data.total_pending} values open across {q.data.items.length} orders{mine ? ` assigned to ${mine}` : ""}. Every value is a
        proposal until a reviewer decides. Fixture sources are labelled and never mixed with real data.{" "}
        {mine ? <Link href="/review">Show every order</Link> : me.data ? <Link href="/review?mine=1">Only mine</Link> : null}
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
                <th>Reviewer</th>
                <th>Open values</th>
                <th>Open categories</th>
                <th>Blocked by checks</th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((i) => (
                <tr key={i.source_id}>
                  <td>
                    <Link href={`/sources/${i.source_id}`}>{i.original_filename}</Link>{" "}
                    <Link href={`/sources/${i.source_id}/review/table`}>
                      <strong>open tariff table</strong>
                    </Link>{" "}
                    · <Link href={`/sources/${i.source_id}/review`}>one at a time</Link>
                  </td>
                  <td>
                    <DatasetBadge kind={i.dataset_kind} />
                  </td>
                  <td>
                    <StateBadge state={i.state} />
                  </td>
                  <td>{i.assigned_to ?? <span className="muted">unassigned</span>}</td>
                  <td className="mono">{i.pending}</td>
                  <td className="mono">{i.open_categories}</td>
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
