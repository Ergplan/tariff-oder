import Link from "next/link";
import type { MeOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
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
type Workbench = {
  commission: string;
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
