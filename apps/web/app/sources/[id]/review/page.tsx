import Link from "next/link";
import type { CategorySummaryList, CategorySummaryOut, FindingList, ReviewChecklist, ReviewQueueDetail, SourceDetail } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge } from "../../../components";
import { ReviewWorkspace, type FindingLine } from "./review-workspace";

export const dynamic = "force-dynamic";

/**
 * Review workspace (Section 7.2) for one order: the completeness checklist derived from the
 * inventory, the queue in review order, and the side-by-side candidate view with the
 * decision controls.  Every candidate shown here is a proposal; nothing on this page is a
 * published fact, and the approve control stays disabled until the evidence has rendered.
 */
export default async function ReviewWorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const detail = await apiTry<SourceDetail>(`/sources/${id}`);
  if (detail.error || !detail.data) {
    return (
      <>
        <h1>Review workspace</h1>
        <ErrorBanner error={detail.error!} />
      </>
    );
  }
  const s = detail.data;
  const filters = new URLSearchParams();
  for (const k of ["category", "component", "family", "page_start", "page_end", "risk", "channel", "status"]) {
    const v = sp[k];
    if (typeof v === "string" && v) filters.set(k, v);
  }
  const order = sp.order === "risk" ? "risk" : "document";
  filters.set("order", order);
  filters.set("limit", "500");
  const [queue, checklist, findingList, summaryList] = await Promise.all([
    apiTry<ReviewQueueDetail>(`/sources/${id}/review/queue?${filters.toString()}`),
    apiTry<ReviewChecklist>(`/sources/${id}/review/checklist`),
    apiTry<FindingList>(`/sources/${id}/findings`),
    apiTry<CategorySummaryList>(`/sources/${id}/summaries`),
  ]);
  const summaries: Record<string, CategorySummaryOut> = {};
  for (const sm of summaryList.data?.summaries ?? []) summaries[sm.category_code] = sm;
  const findings: Record<string, FindingLine[]> = {};
  for (const f of findingList.data?.findings ?? []) {
    for (const cid of f.candidate_ids) (findings[cid] ??= []).push({ severity: f.severity, validator_id: f.validator_id, message: f.message });
  }
  const otherOrder = order === "document" ? "risk" : "document";
  const switchParams = new URLSearchParams(filters);
  switchParams.set("order", otherOrder);
  switchParams.delete("limit");
  const tone = (status: string) =>
    status === "approved" || status === "corrected"
      ? "ok"
      : status === "unresolved" || status === "rejected"
        ? "bad"
        : status === "in_progress"
          ? "warn"
          : status.startsWith("disposition:")
            ? "neutral"
            : "unknown";
  return (
    <>
      <h1>
        Review: {s.original_filename} <DatasetBadge kind={s.dataset_kind} /> <StateBadge state={s.state} />
      </h1>
      <p className="muted">
        <Link href={`/sources/${id}`}>Back to the source</Link> · <Link href="/review">Review queue</Link>
      </p>
      {s.dataset_kind === "fixture" ? (
        <div className="banner" data-tone="fixture">
          Fixture dataset: decisions here exercise the workflow on synthetic material and never touch real data.
        </div>
      ) : null}
      {s.state !== "awaiting_review" ? (
        <div className="banner" data-tone="warn">
          The source is <code>{s.state}</code>; decisions are taken while it awaits review.
        </div>
      ) : null}

      {queue.error || !queue.data ? (
        <ErrorBanner error={queue.error!} />
      ) : queue.data.total === 0 ? (
        <p className="muted">No open candidates match. Decided candidates are listed under the source; nothing here is published.</p>
      ) : (
        <>
          <p className="muted">
            {queue.data.total} open candidates in {order === "document" ? "document order (schedule first, then the open-access chapter)" : "risk order (blocking findings first)"}.{" "}
            <Link href={`/sources/${id}/review?${switchParams.toString()}`}>Switch to {otherOrder} order</Link>
          </p>
          <ReviewWorkspace sourceId={id} queue={queue.data} sourceState={s.state} findings={findings} summaries={summaries} />
        </>
      )}

      <details className="section" id="checklist">
        <summary>
          <span className="title">Completeness checklist</span>
          <span className="summary muted">
            {checklist.data ? `${checklist.data.items.length} items · ${checklist.data.awaiting_second_review} awaiting a second reviewer · ${checklist.data.unresolved} unresolved` : ""}
          </span>
        </summary>
        <div className="body">
      {checklist.error || !checklist.data ? (
        <ErrorBanner error={checklist.error!} />
      ) : (
        <>
          <p className="muted">
            Derived from the inventory ({checklist.data.inventory_categories.length} rate-schedule headings) and the extraction.{" "}
            {checklist.data.awaiting_second_review} awaiting a second reviewer · {checklist.data.unresolved} unresolved ·{" "}
            {checklist.data.condition_records} verbatim condition records. Second review policy: material items{" "}
            {checklist.data.second_review_policy.material ? "on" : "off"}, first order from a utility{" "}
            {checklist.data.second_review_policy.first_order ? "on" : "off"}. Unknown is never green.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Expected from</th>
                  <th>Candidates</th>
                  <th>Status</th>
                  <th>Counts</th>
                </tr>
              </thead>
              <tbody>
                {checklist.data.items.map((i) => (
                  <tr key={i.key}>
                    <td>
                      <span className="mono">{i.kind === "family" ? i.key : `${i.category_code ?? "—"}${i.component_type ? ` · ${i.component_type}` : ""}`}</span>
                      {i.note ? <div className="muted">{i.note}</div> : null}
                    </td>
                    <td className="muted">{i.expected_from}</td>
                    <td className="mono">{i.candidates}</td>
                    <td>
                      <span className="badge" data-tone={tone(i.status)} aria-label={`status ${i.status}`}>
                        {i.status}
                      </span>
                    </td>
                    <td className="mono muted">
                      {Object.entries(i.counts)
                        .map(([k, v]) => `${k} ${v}`)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

        </div>
      </details>

      <details className="section" id="filters">
        <summary>
          <span className="title">Filters</span>
          <span className="summary muted">{filters.size > 2 ? "active" : "none"}</span>
        </summary>
        <div className="body">
      <form method="get" className="card" aria-label="Queue filters">
        <input type="hidden" name="order" value={order} />
        <label>
          Category <input name="category" defaultValue={(sp.category as string) ?? ""} size={10} />
        </label>{" "}
        <label>
          Component <input name="component" defaultValue={(sp.component as string) ?? ""} size={10} />
        </label>{" "}
        <label>
          Family <input name="family" defaultValue={(sp.family as string) ?? ""} size={14} />
        </label>{" "}
        <label>
          Pages <input name="page_start" defaultValue={(sp.page_start as string) ?? ""} size={3} />–
          <input name="page_end" defaultValue={(sp.page_end as string) ?? ""} size={3} />
        </label>{" "}
        <label>
          Risk tag <input name="risk" defaultValue={(sp.risk as string) ?? ""} size={14} />
        </label>{" "}
        <label>
          Channel{" "}
          <select name="channel" defaultValue={(sp.channel as string) ?? ""}>
            <option value="">any</option>
            <option value="agree">agree</option>
            <option value="disagree">disagree</option>
            <option value="one_missing">one_missing</option>
            <option value="single_channel">single_channel</option>
          </select>
        </label>{" "}
        <button type="submit">Apply</button>
      </form>
        </div>
      </details>
    </>
  );
}
