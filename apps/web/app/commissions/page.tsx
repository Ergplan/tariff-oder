import Link from "next/link";
import type { CommissionList, Me } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../components";
import { AddUtility } from "./add-utility";
import { CommissionAssign } from "./commission-assign";

export const dynamic = "force-dynamic";

const STATE_TONE: Record<string, string> = { awaiting_review: "warn", localised: "warn", published: "ok", failed: "bad", rejected: "bad" };

/**
 * Commissions, alphabetically, each with its distribution companies underneath: orders by
 * state, an upload link per company, the commission's reviewer.  Upload an order under a
 * company and it inherits the company's reading profile and the commission's reviewer.
 */
export default async function CommissionsPage() {
  const [list, me] = await Promise.all([apiTry<CommissionList>("/commissions"), apiTry<Me>("/me")]);
  if (list.error || !list.data) {
    return (
      <>
        <h1>Commissions</h1>
        <ErrorBanner error={list.error!} />
      </>
    );
  }
  const isAdmin = me.data?.role === "administrator";
  const commissions = [...list.data.commissions].sort((a, b) => a.jurisdiction_name.localeCompare(b.jurisdiction_name));
  const totals = commissions.reduce((t, c) => ({ orders: t.orders + c.sources, open: t.open + c.open_values }), { orders: 0, open: 0 });
  return (
    <>
      <h1>Commissions</h1>
      <p className="muted">
        {commissions.length} commissions · {totals.orders} orders registered · {totals.open} values open for review. Upload an order
        against its distribution company; it takes the company&apos;s reading profile and the commission&apos;s reviewer. Nothing here
        is a tariff value.
      </p>
      <ol className="cm-list">
        {commissions.map((c) => (
          <li key={c.id} id={c.code}>
            <div className="cm-head">
              <div>
                <strong>{c.jurisdiction_name}</strong> · {c.code} <span className="muted">{c.name}</span>
              </div>
              <div className="cm-stats">
                {c.sources ? (
                  <span className="badge" data-tone={c.awaiting_review ? "warn" : "neutral"}>
                    {c.sources} order{c.sources === 1 ? "" : "s"}
                  </span>
                ) : (
                  <span className="badge" data-tone="neutral">no orders yet</span>
                )}{" "}
                {c.open_values ? <span className="badge" data-tone="warn">{c.open_values} open values</span> : null}
              </div>
            </div>
            <CommissionAssign code={c.code} assignedTo={c.assigned_to} isAdmin={isAdmin} />
            <ul className="cm-utils">
              {c.utilities.map((u) => (
                <li key={u.code}>
                  <span className="mono">{u.code}</span> <span className="muted">{u.name}</span>
                  {u.licensee_kind && u.licensee_kind !== "distribution" ? <span className="badge" data-tone="neutral" title="kind of licensee">{u.licensee_kind}</span> : null}
                  {u.active_reading_profile ? <span className="badge" data-tone="ok" title="reading profile bound at upload">profile</span> : <span className="badge" data-tone="unknown" title="no reading profile yet: the first order will need localisation cues">no profile</span>}{" "}
                  {Object.entries(u.by_state).map(([st, n]) => (
                    <span key={st} className="badge" data-tone={STATE_TONE[st] ?? "neutral"}>
                      {n} {st.replace(/_/g, " ")}
                    </span>
                  ))}{" "}
                  <Link href={`/sources?utility=${encodeURIComponent(u.code)}#upload`}>upload an order</Link>
                  {u.sources ? (
                    <>
                      {" · "}
                      <Link href={`/sources?utility=${encodeURIComponent(u.code)}`}>orders</Link>
                    </>
                  ) : null}
                </li>
              ))}
              {isAdmin ? (
                <li>
                  <AddUtility commissionCode={c.code} />
                </li>
              ) : null}
            </ul>
          </li>
        ))}
      </ol>
    </>
  );
}
