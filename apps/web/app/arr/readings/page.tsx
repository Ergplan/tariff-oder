import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";

export const dynamic = "force-dynamic";

type Preview = {
  chapters: number;
  tables: number;
  tables_read: number;
  values: number;
  identity_blocking: number;
  explained_by_a_convention: number;
  rules: string | null;
};
type Order = {
  source_id: string;
  order: string;
  dataset: string;
  pages: number | null;
  licensees: string[];
  arr_state: string | null;
  preview: Preview | null;
  candidates: Record<string, number>;
  decided: number;
  mapping_confirmed: boolean;
  next_step: string;
};
type Commission = {
  code: string;
  name: string;
  mapping: { id: string; version: number; status: string } | null;
  mapping_confirmed: boolean;
  unplaced_labels: number;
  unplaced_labels_at_least: number;
  conventions_open: number;
  conventions: number;
  orders: Order[];
};
type Board = { states: { code: string; name: string; commissions: Commission[] }[]; totals: Record<string, number>; note: string };

const STATE_TONE: Record<string, string> = { published: "ok", awaiting_review: "warn", extracted: "warn", chapters_proposed: "neutral" };

/**
 * The ARR readings board (increment 49): every order whose ARR is being read, by state and
 * commission — the chapter preview, the review counts — and the next human step that unblocks
 * it.  The board decides nothing.
 */
export default async function ReadingsBoard() {
  const res = await apiTry<Board>("/arr/readings");
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const b = res.data;
  return (
    <>
      <p>
        <Link href="/arr">← ARR</Link>
      </p>
      <h1>ARR readings</h1>
      <p className="muted">
        {b.totals.states ?? 0} state(s) · {b.totals.orders ?? 0} order(s), {b.totals.real_orders ?? 0} real · {b.totals.values_previewed ?? 0} values previewed in real orders ·{" "}
        {b.totals.candidates_decided ?? 0} values decided by reviewers
      </p>
      <div className="banner" data-tone="neutral">
        {b.note}
      </div>
      {b.states.length === 0 ? <p className="muted">No order is being read yet: an administrator starts a reading from an order&apos;s ARR page.</p> : null}
      {b.states.map((s) => (
        <section key={s.code}>
          <h2>{s.name}</h2>
          {s.commissions.map((c) => (
            <div key={c.code}>
              <h3>
                {c.name} <span className="mono muted">{c.code}</span>
              </h3>
              <p className="muted">
                Mapping {c.mapping ? `${c.mapping.id} v${c.mapping.version}` : "none"}{" "}
                <span className="badge" data-tone={c.mapping_confirmed ? "ok" : "warn"}>
                  {c.mapping_confirmed ? "confirmed" : "not confirmed"}
                </span>{" "}
                ·{" "}
                {c.unplaced_labels_at_least > c.unplaced_labels
                  ? `${c.unplaced_labels_at_least} unplaced labels (the ${c.unplaced_labels} most frequent in the workbench)`
                  : `${c.unplaced_labels} unplaced label(s)`}{" "}
                · {c.conventions_open} of {c.conventions} convention question(s) open ·{" "}
                <Link href={`/arr/mappings/${encodeURIComponent(c.code)}`}>workbench →</Link>
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Order</th>
                      <th>Reading</th>
                      <th>Preview</th>
                      <th>Reviewed</th>
                      <th>Next step</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.orders.map((o) => (
                      <tr key={o.source_id}>
                        <td>
                          <Link href={`/sources/${o.source_id}/arr`}>{o.order.slice(0, 48)}</Link>{" "}
                          {o.dataset === "fixture" ? (
                            <span className="badge" data-tone="warn">
                              fixture
                            </span>
                          ) : null}
                          <div className="muted">
                            {o.licensees.join(", ")}
                            {o.pages ? ` · ${o.pages} pp.` : ""}
                          </div>
                        </td>
                        <td>
                          <span className="badge" data-tone={STATE_TONE[o.arr_state ?? ""] ?? "neutral"}>
                            {(o.arr_state ?? "not read").replace(/_/g, " ")}
                          </span>
                        </td>
                        <td className="mono">
                          {o.preview ? (
                            <>
                              {o.preview.chapters} ch. · {o.preview.values} values · {o.preview.tables_read}/{o.preview.tables} tables
                              <div>
                                {o.preview.identity_blocking ? (
                                  <span className="badge" data-tone="bad">
                                    {o.preview.identity_blocking} identity failure(s)
                                  </span>
                                ) : (
                                  <span className="badge" data-tone="ok">
                                    identities hold
                                  </span>
                                )}
                                {o.preview.explained_by_a_convention ? <span className="muted"> {o.preview.explained_by_a_convention} explained by a convention question</span> : null}
                              </div>
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="mono">
                          {o.decided} of {Object.values(o.candidates).reduce((a, n) => a + n, 0)}
                        </td>
                        <td className="muted">{o.next_step}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>
      ))}
    </>
  );
}
