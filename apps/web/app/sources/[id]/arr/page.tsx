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
  type Preview = {
    chapter: number;
    tables: number;
    tables_read: number;
    values: number;
    by_year_voice: Record<string, number>;
    identity_blocking: number;
    unplaced_top: [string, number][];
    findings?: { identity_id: string; message: string; reconciles_if: { total: string; includes: string[] } | null }[];
  };
  const summary = (r.arr_summary ?? {}) as {
    scan?: { unplaced_rows?: number; unplaced?: { key: string; count: number }[] };
    mapping?: { id: string; status: string };
    preview?: { rules: string; chapters: Preview[]; note: string };
  };
  const preview = new Map((summary.preview?.chapters ?? []).map((p) => [p.chapter, p]));
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
          {summary.preview ? <p className="muted">{summary.preview.note} (rules {summary.preview.rules})</p> : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Chapter</th>
                  <th>Pages</th>
                  <th>Would read</th>
                  <th>Years and voices</th>
                  <th>Identity failures</th>
                  <th>Commonest unplaced rows</th>
                </tr>
              </thead>
              <tbody>
                {r.chapters.map((c) => {
                  const p = preview.get(c.ordinal);
                  return (
                    <tr key={c.id}>
                      <td>
                        {c.ordinal}. <strong>{c.branch}</strong> “{c.cue_text}”{c.note ? <div className="muted">{c.note}</div> : null}
                      </td>
                      <td className="mono">
                        {c.page_start}–{c.page_end}
                      </td>
                      <td className="mono">{p ? `${p.values} values from ${p.tables_read} of ${p.tables} tables` : "—"}</td>
                      <td className="muted">
                        {p
                          ? Object.entries(p.by_year_voice)
                              .map(([k, n]) => `${k.replace(/_/g, " ")} ${n}`)
                              .join(" · ")
                          : ""}
                      </td>
                      <td>
                        {p ? (
                          p.identity_blocking ? (
                            <details>
                              <summary>
                                <span className="badge" data-tone="bad">
                                  {p.identity_blocking}
                                </span>
                              </summary>
                              {(p.findings ?? []).map((f, i) => (
                                <div key={i} className="muted">
                                  {f.message}
                                  {f.reconciles_if ? (
                                    <>
                                      {" "}
                                      <Link href={`/arr/mappings/${encodeURIComponent(r.commission ?? "")}`}>a convention question for the {r.commission} mapping →</Link>
                                    </>
                                  ) : null}
                                </div>
                              ))}
                            </details>
                          ) : (
                            <span className="badge" data-tone="ok">0</span>
                          )
                        ) : null}
                      </td>
                      <td className="muted">{p ? p.unplaced_top.map(([l, n]) => `${l} (${n})`).join("; ") : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
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
