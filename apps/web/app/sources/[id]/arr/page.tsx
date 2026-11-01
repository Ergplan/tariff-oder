import Link from "next/link";
import type { ArrReadingOut, CandidateList, MeOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { ActionButton } from "../../../client/actions";
import { ArrReview } from "./arr-review";
import Licensees from "./licensees";

export const dynamic = "force-dynamic";

/**
 * The ARR track of one order (ADR-0018): read it, confirm its chapters, review every value
 * against its page, publish.  The tariff track of the same order is separate.
 */
export default async function SourceArrPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [rd, cl, me] = await Promise.all([
    apiTry<ArrReadingOut>(`/sources/${encodeURIComponent(id)}/arr`),
    apiTry<CandidateList>(`/sources/${encodeURIComponent(id)}/arr/candidates`),
    apiTry<MeOut>("/me"),
  ]);
  const lic = await apiTry<{ code: string; name: string; primary: boolean }[]>(`/sources/${encodeURIComponent(id)}/licensees`);
  if (rd.error || !rd.data) return <ErrorBanner error={rd.error!} />;
  const r = rd.data;
  const role = me.data?.role;
  const summary = (r.arr_summary ?? {}) as { scan?: { unplaced_rows?: number; unplaced?: { key: string; count: number }[] }; mapping?: { id: string; status: string } };
  const blocking = r.findings.filter((f) => f.severity === "blocking").length;
  const counts = r.candidates_by_status;
  const decided = Object.entries(counts).filter(([k]) => !["pending", "awaiting_second_review"].includes(k)).reduce((a, [, v]) => a + v, 0);
  return (
    <>
      <p>
        <Link href={`/sources/${id}`}>← Source</Link>
      </p>
      <h1>
        ARR reading <span className="badge" data-tone="neutral">{r.arr_state ?? "not read"}</span>
      </h1>
      <p className="muted">
        Mapping {summary.mapping?.id ?? "—"} ({(summary.mapping?.status ?? "").split(" ")[0] || "—"}) ·{" "}
        {r.mapping_confirmed ? "real lines can be approved" : `real lines cannot be approved yet: ${r.mapping_note}`} · {decided} of{" "}
        {Object.values(counts).reduce((a, b) => a + b, 0)} values decided
      </p>
      {lic.data?.length ? <Licensees sourceId={id} licensees={lic.data} canEdit={role === "administrator"} /> : null}
      {r.arr_state === null && role === "administrator" ? <ActionButton path={`/api/sources/${id}/arr/read`} label="Read this order's ARR" /> : null}
      {r.arr_state === "chapters_proposed" ? (
        <>
          <h2>Chapters proposed</h2>
          <ul>
            {r.chapters.map((c) => (
              <li key={c.id}>
                {c.ordinal}. <strong>{c.branch}</strong> “{c.cue_text}” pages {c.page_start}–{c.page_end} {c.note ? <span className="muted">({c.note})</span> : null}
              </li>
            ))}
          </ul>
          {summary.scan?.unplaced_rows ? (
            <p className="muted">
              The hand-mapping scan found {summary.scan.unplaced_rows} table rows the taxonomy cannot place, e.g.{" "}
              {(summary.scan.unplaced ?? []).slice(0, 5).map((u) => `“${u.key}”`).join(", ")}: they are the reviewer&apos;s work for the commission mapping.
            </p>
          ) : null}
          {role !== "analyst" ? <ActionButton path={`/api/sources/${id}/arr/chapters/decision`} body={{ rationale: "Chapters checked against the pages" }} label="Confirm chapters and read them" /> : null}
        </>
      ) : null}
      {["awaiting_review", "published", "extracted"].includes(r.arr_state ?? "") ? (
        <>
          <ArrReview sourceId={id} open={r.arr_state !== "extracted" && role !== "analyst"} chapters={r.chapters} initial={cl.data?.candidates ?? []} findings={r.findings} />
          {role !== "analyst" ? (
            <p>
              {blocking ? (
                <span className="muted">{blocking} blocking identity finding(s): correct or reject the lines involved before publishing.</span>
              ) : (
                <ActionButton path={`/api/sources/${id}/arr/publish`} label="Publish the decided values" confirm="Publish every finally approved ARR value of this order as a fact?" />
              )}
            </p>
          ) : null}
        </>
      ) : null}
    </>
  );
}
