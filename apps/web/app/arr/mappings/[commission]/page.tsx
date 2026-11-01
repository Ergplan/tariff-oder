import Link from "next/link";
import type { MeOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import Convention from "./convention";
import Decide from "./decide";

export const dynamic = "force-dynamic";

type Label = {
  label: string;
  count: number;
  example: string | null;
  orders: { source_id: string; order: string; pages: number[] }[];
  decision: { kind: string; code: string | null; note: string | null; by: string; at: string } | null;
  suggestions: { code: string; label: string; score: number }[];
};
type Question = {
  key: string;
  kind: string;
  question: string;
  why: string | null;
  values: string[];
  evidence: { source_id: string; order: string; chapter: number; message: string }[];
  decision: { value: string; note: string | null; by: string; at: string } | null;
};
type Workbench = {
  commission: string;
  conventions: Question[];
  mapping: { id: string; version: number; status: string } | null;
  orders: { source_id: string; order: string; arr_state: string | null }[];
  labels: Label[];
  decided: number;
  note: string;
};

/**
 * The mapping workbench (increment 39): what a commission's mapping does not place yet, across
 * its read orders; a reviewer decides each label (an alias to a taxonomy line, or not a line);
 * the decisions are drafted into the next mapping version for a person to commit and confirm.
 */
export default async function MappingWorkbench({ params }: { params: Promise<{ commission: string }> }) {
  const { commission } = await params;
  const code = decodeURIComponent(commission).toUpperCase();
  const [res, me] = await Promise.all([apiTry<Workbench>(`/arr/mappings/${encodeURIComponent(code)}/workbench`), apiTry<MeOut>("/me")]);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const w = res.data;
  const reviewer = ["reviewer", "administrator"].includes(me.data?.role ?? "");
  return (
    <>
      <p>
        <Link href="/arr">← ARR</Link>
      </p>
      <h1>Mapping workbench · {w.commission}</h1>
      <p className="muted">
        Mapping {w.mapping ? `${w.mapping.id} v${w.mapping.version}` : "none (the generic skeleton reads this commission)"} · {w.mapping?.status.split(";")[0]} · {w.orders.length} order(s) read ·{" "}
        {w.labels.length} unplaced label(s), {w.decided} decided
      </p>
      <div className="banner" data-tone="neutral">
        {w.note} Real ARR values of {w.commission} cannot be approved until its mapping file is confirmed.
      </div>
      <p>
        <a href={`/api/client/arr/mappings/${encodeURIComponent(code)}/draft`}>Download the next mapping version (draft) with these decisions</a>{" "}
        <span className="muted">— or on the VM: <code>uv run tariff-api mapping-draft --commission {code} --out packages/arr-taxonomy/mappings/…</code></span>
      </p>
      <h2>Conventions</h2>
      {w.conventions.length === 0 ? (
        <p className="muted">No convention question: the identity checks of the read orders raise none the mapping must answer.</p>
      ) : (
        <>
          <p className="muted">
            How {w.commission} composes its printed totals. Each question comes from identity failures in the read orders&apos; previews; a hint says which convention would reconcile them, and
            only a reviewer&apos;s answer, written into the next mapping version, changes the checks.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Evidence</th>
                  <th>Answer</th>
                </tr>
              </thead>
              <tbody>
                {w.conventions.map((q) => (
                  <tr key={q.key}>
                    <td>
                      {q.question}
                      {q.why ? <div className="muted">{q.why}</div> : null}
                    </td>
                    <td className="muted">
                      {q.evidence.slice(0, 3).map((e, i) => (
                        <div key={i}>
                          <Link href={`/sources/${e.source_id}/arr`}>{e.order.slice(0, 30)}</Link> ch.{e.chapter}: {e.message.slice(0, 160)}
                        </div>
                      ))}
                      {q.evidence.length > 3 ? <div>… and {q.evidence.length - 3} more</div> : null}
                    </td>
                    <td>
                      <Convention commission={code} question={q.key} values={q.values} decision={q.decision} canDecide={reviewer} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <h2>Unplaced labels</h2>
      {w.labels.length === 0 ? (
        <p className="muted">Nothing unplaced: read an order of this commission first (its ARR scan lists what the mapping does not place).</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Printed label</th>
                <th>Times</th>
                <th>Where</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {w.labels.slice(0, 300).map((l) => (
                <tr key={l.label}>
                  <td>
                    <span className="mono">{l.label}</span>
                    {l.example && l.example.toLowerCase() !== l.label ? <div className="muted">{l.example.slice(0, 120)}</div> : null}
                  </td>
                  <td className="mono">{l.count}</td>
                  <td className="muted">
                    {l.orders.slice(0, 2).map((o) => (
                      <div key={o.source_id}>
                        <Link href={`/sources/${o.source_id}/arr`}>{o.order.slice(0, 40)}</Link> p.{o.pages.slice(0, 6).join(", ")}
                      </div>
                    ))}
                  </td>
                  <td>
                    <Decide commission={code} label={l.label} example={l.example} decision={l.decision} suggestions={l.suggestions} canDecide={reviewer} />
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
