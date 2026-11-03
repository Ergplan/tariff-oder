import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { Eyebrow, Panel } from "../../../client/studio";

export const dynamic = "force-dynamic";

type Rule = { id: string; title: string; output: string; formula: string; per: string | null; clause: string | null; verified: boolean; from_fy: string | null; to_fy: string | null };
type Schedule = { schedule: string; name: string; commissions: Record<string, Rule[]> };
type Compare = { commissions: string[]; totals: Record<string, { rules: number; approved: number; clauses_verified: number }>; schedules: Schedule[] };

function years(r: Rule) {
  if (r.from_fy && r.to_fy) return `${r.from_fy}–${r.to_fy}`;
  if (r.from_fy) return `from ${r.from_fy}`;
  if (r.to_fy) return `to ${r.to_fy}`;
  return "";
}

/**
 * The commissions' draft calculation rules side by side, schedule by schedule: how each
 * regulation, as read so far, computes the same head.  A reading aid — nothing here is approved.
 */
export default async function RulesCompare() {
  const res = await apiTry<Compare>("/arr/rules-compare");
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const d = res.data;
  return (
    <>
      <p>
        <Link href="/arr/reference">← Reference filings and reproduced orders</Link>
      </p>
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>
          Desk · calculation rules
          <span className="badge" data-tone="warn">
            draft rules · nothing approved
          </span>
        </Eyebrow>
        <h1>Rules across commissions</h1>
        <p className="muted" style={{ margin: 0, maxWidth: "52rem" }}>
          The same head, as each commission&apos;s regulation computes it — read from the regulations or from the orders that quote them, and reproduced against those
          orders&apos; figures. No rule is approved and no clause verified; a formula here is a draft until a reviewer reads its clause.
        </p>
        <div className="case-meta">
          {d.commissions.map((c) => (
            <span key={c}>
              <Link href={`/arr/rules/${c}`}>{c}</Link> <b>{d.totals[c].rules}</b>
            </span>
          ))}
        </div>
      </header>
      {d.schedules.map((s, i) => {
        const present = d.commissions.filter((c) => s.commissions[c]?.length);
        return (
          <Panel key={s.schedule} num={String(i + 1).padStart(2, "0")} title={s.name} aside={`${s.schedule} · ${present.join(", ")}`}>
            {present.map((c) => (
              <details key={c} open={present.length > 1 && s.commissions[c].length <= 6} style={{ marginBottom: "0.7rem" }}>
                <summary>
                  <b className="mono">{c}</b> <span className="muted">{s.commissions[c].length} rules</span>
                </summary>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Rule</th>
                        <th>Formula</th>
                        <th>Clause</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.commissions[c].map((r) => (
                        <tr key={r.id}>
                          <td style={{ fontSize: "0.88rem" }}>
                            {r.title}
                            <div className="mono muted">
                              {r.id}
                              {r.per ? ` · per ${r.per}` : ""}
                              {years(r) ? ` · ${years(r)}` : ""}
                            </div>
                          </td>
                          <td className="mono" style={{ fontSize: "0.85rem" }}>
                            {r.output} = {r.formula}
                          </td>
                          <td className="mono muted" style={{ fontSize: "0.85rem" }}>
                            {r.clause ?? "—"}
                            {r.verified ? "" : " · unverified"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            ))}
          </Panel>
        );
      })}
    </>
  );
}
