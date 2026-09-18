import Link from "next/link";
import type { CandidateList, CategorySummaryList, CategorySummaryOut, FindingList, SourceDetail } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge } from "../../../../components";
import type { FindingLine } from "../review-workspace";
import { TariffTable } from "./tariff-table";

export const dynamic = "force-dynamic";

/**
 * Tariff table review: every category as the order prints it — one grid per lettered
 * block, rows as printed, fixed / energy / other charges as columns — with approve, reject
 * and note on every value, a page view per block that outlines the cited tables, and
 * "approve all agreeing" per category.  Every value is a proposal until a reviewer decides;
 * the API still enforces the rendered-evidence rule, the version check and the audit event.
 */
export default async function TariffTablePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await apiTry<SourceDetail>(`/sources/${id}`);
  if (detail.error || !detail.data) {
    return (
      <>
        <h1>Tariff table</h1>
        <ErrorBanner error={detail.error!} />
      </>
    );
  }
  const s = detail.data;
  const [cands, summaryList, findingList] = await Promise.all([
    apiTry<CandidateList>(`/sources/${id}/candidates?limit=2000`),
    apiTry<CategorySummaryList>(`/sources/${id}/summaries`),
    apiTry<FindingList>(`/sources/${id}/findings`),
  ]);
  const summaries: Record<string, CategorySummaryOut> = {};
  for (const sm of summaryList.data?.summaries ?? []) summaries[sm.category_code] = sm;
  const findings: Record<string, FindingLine[]> = {};
  for (const f of findingList.data?.findings ?? []) {
    for (const cid of f.candidate_ids) (findings[cid] ??= []).push({ severity: f.severity, validator_id: f.validator_id, message: f.message });
  }
  return (
    <>
      <h1>
        Tariff table: {s.original_filename} <DatasetBadge kind={s.dataset_kind} /> <StateBadge state={s.state} />
      </h1>
      <p className="muted">
        <Link href={`/sources/${id}`}>Back to the source</Link> · <Link href={`/sources/${id}/review`}>One-at-a-time workspace (for changes)</Link> ·{" "}
        <Link href="/review">Review queue</Link>
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
      {cands.error || !cands.data ? (
        <ErrorBanner error={cands.error!} />
      ) : cands.data.total === 0 ? (
        <p className="muted">No candidates yet. Extraction has not run, or produced nothing.</p>
      ) : (
        <TariffTable sourceId={id} sourceState={s.state} initial={cands.data.candidates} summaries={summaries} findings={findings} />
      )}
    </>
  );
}
